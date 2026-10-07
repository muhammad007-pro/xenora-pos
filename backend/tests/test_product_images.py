"""Mahsulot rasmi: siqish (800px WebP + 200px thumbnail), xavfsizlik, tenant papkasi,
eski faylni tozalash, eski rasmlarni ko'chirish skripti.

Ishga tushirish:  cd backend && py -m pytest tests/test_product_images.py -v
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core import product_images
from database import Base
from models import Cafe, Product

import routers.product as product_router

TID = 7
OTHER_TID = 8


class _User:
    is_superuser = False
    tenant_id = TID
    id = 5
    role = None
    _active_branch_id = None


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    s.add(Cafe(id=TID, name="DOKON", code="DOKON"))
    s.add(Cafe(id=OTHER_TID, name="BOSHQA", code="BOSHQA"))
    s.add(Product(id=1, name="ATIR", price=1000, tenant_id=TID))
    s.add(Product(id=2, name="BEGONA", price=1000, tenant_id=OTHER_TID))
    s.add(Product(id=3, name="ATIR 2", price=1000, tenant_id=TID))
    s.commit()
    yield s
    s.close()


def _img_bytes(fmt="JPEG", size=(2000, 1500), mode="RGB", color=(200, 30, 30)):
    im = Image.new(mode, size, color)
    buf = io.BytesIO()
    im.save(buf, format=fmt)
    return buf.getvalue()


def _upload(db, raw, filename="rasm.jpg", product_id=1, user=None):
    f = UploadFile(file=io.BytesIO(raw), filename=filename)
    return asyncio.run(product_router.upload_product_image(
        product_id=product_id, file=f, db=db, current_user=user or _User()))


def _path(uploads, url):
    assert url.startswith("/uploads/")
    return os.path.join(str(uploads), *url[len("/uploads/"):].split("/"))


def _all_files(root):
    return sorted(os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
                  for d, _, fs in os.walk(root) for f in fs)


# ═══════════════════════════════════════════════════════════════════════════
# 1. SIQISH — WebP, 800px, thumbnail 200px
# ═══════════════════════════════════════════════════════════════════════════
def test_rasm_siqiladi_va_webp_boladi(db, uploads):
    raw = _img_bytes(size=(2000, 1500))
    r = _upload(db, raw)
    url = r["image_url"]
    assert url.startswith("/uploads/products/tenant_7/product_1_") and url.endswith(".webp")

    with Image.open(_path(uploads, url)) as im:
        assert im.format == "WEBP"
        assert im.size == (800, 600), "uzun tomon 800px, nisbat saqlanadi"
    assert db.get(Product, 1).image_url == url


def test_thumbnail_yaratiladi(db, uploads):
    r = _upload(db, _img_bytes(size=(1500, 2000)))
    assert r["thumb_url"] == r["image_url"].replace(".webp", "_thumb.webp")
    with Image.open(_path(uploads, r["thumb_url"])) as im:
        assert im.format == "WEBP"
        assert im.size == (150, 200)


def test_original_saqlanmaydi(db, uploads):
    """Diskda faqat ikkita fayl: asosiy + thumbnail. JPG original yo'q."""
    _upload(db, _img_bytes())
    files = _all_files(str(uploads))
    assert len(files) == 2
    assert all(f.endswith(".webp") for f in files)


def test_kichik_rasm_kattalashtirilmaydi(db, uploads):
    r = _upload(db, _img_bytes(size=(300, 120)))
    with Image.open(_path(uploads, r["image_url"])) as im:
        assert im.size == (300, 120)


def test_shaffof_png_alfa_kanali_saqlanadi(db, uploads):
    raw = _img_bytes(fmt="PNG", size=(400, 400), mode="RGBA", color=(0, 0, 0, 0))
    r = _upload(db, raw, filename="logo.png")
    with Image.open(_path(uploads, r["image_url"])) as im:
        assert im.mode == "RGBA"
        assert im.getpixel((10, 10))[3] == 0


def test_exif_aylanishi_togrilanadi(db, uploads):
    """Telefon rasmi: piksellar 2000x1000, EXIF Orientation=6 (90° burilgan)."""
    im = Image.new("RGB", (2000, 1000), (10, 20, 30))
    exif = Image.Exif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif.tobytes())
    r = _upload(db, buf.getvalue())
    with Image.open(_path(uploads, r["image_url"])) as out:
        assert out.size == (400, 800)


def test_haqiqiy_foto_sezilarli_kichrayadi(db, uploads):
    """Shovqinli (foto'ga yaqin) 2560x1600 rasm — natija asl JPEG'dan kamida 5 marta kichik."""
    im = Image.effect_noise((2560, 1600), 60).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    raw = buf.getvalue()
    r = _upload(db, raw)
    assert os.path.getsize(_path(uploads, r["image_url"])) * 5 < len(raw)


# ═══════════════════════════════════════════════════════════════════════════
# 2. XAVFSIZLIK — rasm bo'lmagan fayl, format, hajm, o'lcham
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("raw,filename", [
    (b"<?php system($_GET['c']); ?>", "shell.jpg"),
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.png"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "buzuq.png"),   # PNG sarlavhasi, ichi buzuq
    (b"", "bosh.jpg"),
])
def test_rasm_bolmagan_fayl_rad_etiladi(db, uploads, raw, filename):
    with pytest.raises(HTTPException) as e:
        _upload(db, raw, filename=filename)
    assert e.value.status_code == 400
    assert _all_files(str(uploads)) == []
    assert db.get(Product, 1).image_url is None


def test_ruxsat_etilmagan_format_rad_etiladi(db, uploads):
    """Haqiqiy GIF, lekin nomi .jpg — baytlar bo'yicha aniqlanadi."""
    with pytest.raises(HTTPException) as e:
        _upload(db, _img_bytes(fmt="GIF", mode="P", color=1), filename="anim.jpg")
    assert e.value.status_code == 400
    assert "GIF" in e.value.detail


def test_ruxsat_etilmagan_kengaytma_rad_etiladi(db, uploads):
    with pytest.raises(HTTPException) as e:
        _upload(db, _img_bytes(), filename="rasm.svg")
    assert e.value.status_code == 400


def test_5mb_dan_katta_rad_etiladi(db, uploads):
    assert settings.MAX_UPLOAD_SIZE == 5 * 1024 * 1024
    raw = b"\xff\xd8\xff" + b"\x00" * settings.MAX_UPLOAD_SIZE
    with pytest.raises(HTTPException) as e:
        _upload(db, raw)
    assert e.value.status_code == 400
    assert "5 MB" in e.value.detail
    assert _all_files(str(uploads)) == []


def test_aynan_5mb_chegarada_otadi(db, uploads, monkeypatch):
    """Chegara qat'iy `>`: limitga teng fayl o'tadi."""
    raw = _img_bytes(fmt="PNG", size=(50, 50))
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", len(raw))
    assert _upload(db, raw, filename="a.png")["image_url"].endswith(".webp")
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", len(raw) - 1)
    with pytest.raises(HTTPException):
        _upload(db, raw, filename="a.png")


def test_dekompressiya_bombasi_rad_etiladi(db, uploads, monkeypatch):
    monkeypatch.setattr(product_images, "MAX_PIXELS", 1000 * 1000)
    with pytest.raises(HTTPException) as e:
        _upload(db, _img_bytes(fmt="PNG", size=(1200, 1000)), filename="b.png")
    assert e.value.status_code == 400
    assert "megapiksel" in e.value.detail


# ═══════════════════════════════════════════════════════════════════════════
# 3. TENANT PAPKASI
# ═══════════════════════════════════════════════════════════════════════════
def test_tenant_papkasi_togri(db, uploads):
    r = _upload(db, _img_bytes())
    assert os.path.isdir(os.path.join(str(uploads), "products", "tenant_7"))
    assert all(f.startswith("products/tenant_7/") for f in _all_files(str(uploads)))
    assert "/tenant_7/" in r["image_url"]


def test_papka_mahsulot_tenantidan_olinadi(db, uploads):
    """Superadmin boshqa do'kon mahsulotiga yuklasa — papka MAHSULOT tenant'iniki."""
    class _Super(_User):
        is_superuser = True
        tenant_id = None
    r = _upload(db, _img_bytes(), product_id=2, user=_Super())
    assert r["image_url"].startswith("/uploads/products/tenant_8/")


def test_tenantsiz_mahsulot_platform_papkasiga(db, uploads):
    db.add(Product(id=9, name="PLATFORMA", price=1, tenant_id=None))
    db.commit()

    class _Super(_User):
        is_superuser = True
        tenant_id = None
    r = _upload(db, _img_bytes(), product_id=9, user=_Super())
    assert r["image_url"].startswith("/uploads/products/platform/")


def test_begona_tenant_mahsulotiga_yuklab_bolmaydi(db, uploads):
    with pytest.raises(HTTPException) as e:
        _upload(db, _img_bytes(), product_id=2)
    assert e.value.status_code == 404
    assert _all_files(str(uploads)) == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. ESKI FAYL TOZALASH
# ═══════════════════════════════════════════════════════════════════════════
def test_almashtirilganda_eski_fayl_ochiriladi(db, uploads):
    old = _upload(db, _img_bytes(color=(1, 2, 3)))
    new = _upload(db, _img_bytes(color=(9, 9, 9)))
    assert old["image_url"] != new["image_url"]
    assert not os.path.exists(_path(uploads, old["image_url"]))
    assert not os.path.exists(_path(uploads, old["thumb_url"]))
    assert os.path.exists(_path(uploads, new["image_url"]))
    assert os.path.exists(_path(uploads, new["thumb_url"]))
    assert len(_all_files(str(uploads))) == 2


def test_eski_formatdagi_jpg_ham_ochiriladi(db, uploads):
    legacy_dir = os.path.join(str(uploads), "products")
    os.makedirs(legacy_dir)
    legacy = os.path.join(legacy_dir, "product_1_abcd1234.jpg")
    with open(legacy, "wb") as f:
        f.write(_img_bytes())
    p = db.get(Product, 1)
    p.image_url = "/uploads/products/product_1_abcd1234.jpg"
    db.commit()

    _upload(db, _img_bytes())
    assert not os.path.exists(legacy)


def test_boshqa_mahsulot_ishlatayotgan_fayl_ochirilmaydi(db, uploads):
    first = _upload(db, _img_bytes())
    p3 = db.get(Product, 3)
    p3.image_url = first["image_url"]       # nusxalangan mahsulot — bir xil fayl
    db.commit()

    _upload(db, _img_bytes(color=(5, 5, 5)))
    assert os.path.exists(_path(uploads, first["image_url"]))
    assert os.path.exists(_path(uploads, first["thumb_url"]))


def test_commit_yiqilsa_yangi_fayl_qolmaydi(db, uploads, monkeypatch):
    def _boom():
        raise RuntimeError("db yiqildi")
    monkeypatch.setattr(db, "commit", _boom)
    with pytest.raises(RuntimeError):
        _upload(db, _img_bytes())
    assert _all_files(str(uploads)) == []


def test_mahsulot_ochirilganda_rasm_qoladi(db, uploads, monkeypatch):
    """Soft-delete: qayta faollashtirilsa rasm kerak bo'ladi."""
    monkeypatch.setattr(product_router, "log_audit", lambda *a, **k: None)
    r = _upload(db, _img_bytes())
    asyncio.run(product_router.delete_product(product_id=1, db=db, current_user=_User()))
    assert db.get(Product, 1).image_url == r["image_url"]
    assert os.path.exists(_path(uploads, r["image_url"]))


def test_ochirishda_products_papkasidan_tashqariga_chiqilmaydi(uploads):
    secret = os.path.join(str(uploads), "secret.txt")
    with open(secret, "w") as f:
        f.write("x")
    product_images.delete_image_files("/uploads/products/../secret.txt")
    product_images.delete_image_files("/uploads/products/..")
    product_images.delete_image_files("/etc/passwd")
    assert os.path.exists(secret)


# ═══════════════════════════════════════════════════════════════════════════
# 5. THUMBNAIL KONVENSIYASI (frontend thumbOf/pmThumb bilan bir xil)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("url,expected", [
    ("/uploads/products/tenant_7/product_1_ab12cd34.webp",
     "/uploads/products/tenant_7/product_1_ab12cd34_thumb.webp"),
    ("/uploads/products/platform/product_9_ab12cd34.webp",
     "/uploads/products/platform/product_9_ab12cd34_thumb.webp"),
    ("/uploads/products/product_3_63422037.jpg", None),     # eski format
    ("https://cdn.example.com/a.webp", None),
    ("/uploads/products/tenant_7/../x.webp", None),
    (None, None),
    ("", None),
])
def test_thumb_url_konvensiyasi(url, expected):
    assert product_images.thumb_url(url) == expected


# ═══════════════════════════════════════════════════════════════════════════
# 6. ESKI RASMLARNI KO'CHIRISH SKRIPTI
# ═══════════════════════════════════════════════════════════════════════════
def _legacy(db, uploads, pid, name, raw=None):
    d = os.path.join(str(uploads), "products")
    os.makedirs(d, exist_ok=True)
    if raw is not False:
        with open(os.path.join(d, name), "wb") as f:
            f.write(raw or _img_bytes())
    p = db.get(Product, pid)
    p.image_url = f"/uploads/products/{name}"
    db.commit()
    return os.path.join(d, name)


def _migrate_mod():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import migrate_product_images
    return migrate_product_images


def test_kochirish_preview_hech_narsa_ozgartirmaydi(db, uploads):
    _legacy(db, uploads, 1, "product_1_aaaa1111.jpg")
    r = _migrate_mod().migrate(db, apply=False)
    assert len(r["migrated"]) == 1
    assert db.get(Product, 1).image_url == "/uploads/products/product_1_aaaa1111.jpg"
    assert _all_files(str(uploads)) == ["products/product_1_aaaa1111.jpg"]


def test_kochirish_apply(db, uploads):
    old1 = _legacy(db, uploads, 1, "product_1_aaaa1111.jpg")
    old2 = _legacy(db, uploads, 2, "product_2_bbbb2222.jpg")
    m = _migrate_mod()
    r = m.migrate(db, apply=True)
    assert len(r["migrated"]) == 2 and r["skipped"] == []

    u1, u2 = db.get(Product, 1).image_url, db.get(Product, 2).image_url
    assert u1.startswith("/uploads/products/tenant_7/") and u1.endswith(".webp")
    assert u2.startswith("/uploads/products/tenant_8/")
    for u in (u1, u2):
        assert os.path.exists(_path(uploads, u))
        assert os.path.exists(_path(uploads, product_images.thumb_url(u)))
    # eski fayllar default'da QOLADI (orqaga qaytish uchun)
    assert os.path.exists(old1) and os.path.exists(old2)

    # idempotent
    r2 = m.migrate(db, apply=True)
    assert r2["migrated"] == [] and r2["already"] == 2
    assert db.get(Product, 1).image_url == u1


def test_kochirish_delete_old(db, uploads):
    old = _legacy(db, uploads, 1, "product_1_aaaa1111.jpg")
    _migrate_mod().migrate(db, apply=True, delete_old=True)
    assert not os.path.exists(old)
    assert os.path.exists(_path(uploads, db.get(Product, 1).image_url))


def test_kochirish_fayl_yoq_yoki_buzuq_otkaziladi(db, uploads):
    _legacy(db, uploads, 1, "product_1_yoq00000.jpg", raw=False)
    _legacy(db, uploads, 3, "product_3_buzuq000.jpg", raw=b"rasm emas")
    r = _migrate_mod().migrate(db, apply=True)
    assert len(r["skipped"]) == 2 and r["migrated"] == []
    assert db.get(Product, 1).image_url == "/uploads/products/product_1_yoq00000.jpg"
    assert db.get(Product, 3).image_url == "/uploads/products/product_3_buzuq000.jpg"

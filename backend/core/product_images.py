"""Mahsulot rasmlari — tekshirish, siqish, tenant papkasi, eski faylni tozalash.

Yuklangan rasm HECH QACHON kelgan holida saqlanmaydi:
  * haqiqiy rasm ekani bayt darajasida tasdiqlanadi (PIL, `upload.py` dagidek);
  * 800px WebP (asosiy) + 200px WebP (thumbnail) yaratiladi, original tashlanadi.

Fayl joylashuvi:  <UPLOAD_DIR>/products/tenant_<id>/product_<pid>_<hex>.webp
                  <UPLOAD_DIR>/products/tenant_<id>/product_<pid>_<hex>_thumb.webp

Thumbnail URL alohida ustunda SAQLANMAYDI — nomlash konvensiyasidan olinadi
(`thumb_url`). Shu sabab migratsiya yo'q; eski (.jpg) URL'lar uchun thumbnail
yo'q va frontend asosiy rasmni ko'rsatadi.

⚠️ Mahsulot o'chirilganda rasm O'CHIRILMAYDI: o'chirish soft-delete
(`is_active=False`), mahsulot qayta faollashtirilishi mumkin.
"""
import io
import logging
import os
import re
import uuid

from config import settings

logger = logging.getLogger(__name__)

MAIN_PX = 800
THUMB_PX = 200
MAIN_QUALITY = 80     # 2560x1600 JPEG 1.1 MB → 51 KB; 85 da 65 KB, 75 da 40 KB
THUMB_QUALITY = 75
THUMB_SUFFIX = "_thumb"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Dekompressiya bombasi: 5 MB PNG ichida 20000x20000 bo'lishi mumkin (≈1.6 GB RAM).
# Ochishdan (load) OLDIN o'lchamni tekshiramiz. 40 MP — eng katta telefon kamerasidan ham ko'p.
MAX_PIXELS = 40_000_000

URL_PREFIX = "/uploads/products"
_NEW_URL_RE = re.compile(r"^/uploads/products/(tenant_\d+|platform)/[A-Za-z0-9_]+\.webp$")


class ProductImageError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (HTTP 400)."""


def products_root() -> str:
    return os.path.join(settings.UPLOAD_DIR, "products")


def tenant_folder(tenant_id) -> str:
    return f"tenant_{int(tenant_id)}" if tenant_id is not None else "platform"


def thumb_url(url):
    """Asosiy rasm URL'idan thumbnail URL'i. Eski formatda (jpg) — None."""
    if not url or not _NEW_URL_RE.match(url):
        return None
    return url[: -len(".webp")] + THUMB_SUFFIX + ".webp"


def process_image(raw: bytes):
    """Baytlarni tekshiradi va (asosiy_webp, thumb_webp) qaytaradi.

    Rasm bo'lmagan, buzuq, ruxsat etilmagan formatdagi yoki haddan katta
    o'lchamdagi fayl → ProductImageError.
    """
    from PIL import Image, ImageOps

    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = (probe.format or "").upper()
        w, h = probe.size
        probe.verify()                   # butunlik: buzuq/rasm-emas → xato
    except Exception as e:
        raise ProductImageError(
            "Fayl haqiqiy rasm emas (buzuq yoki noto'g'ri format). Faqat: JPG, PNG, WEBP"
        ) from e
    if fmt not in ALLOWED_FORMATS:
        raise ProductImageError(f"'{fmt or 'aniqlanmadi'}' formati ruxsat etilmagan. Faqat: JPG, PNG, WEBP")
    if w * h > MAX_PIXELS:
        raise ProductImageError(f"Rasm o'lchami juda katta ({w}x{h}). Ko'pi bilan 40 megapiksel")

    try:
        img = Image.open(io.BytesIO(raw))   # verify() dan keyin qayta ochish shart
        img = ImageOps.exif_transpose(img)   # telefon aylanishini to'g'rila
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")

        def _webp(px, quality):
            t = img.copy()
            t.thumbnail((px, px), Image.LANCZOS)   # nisbat saqlanadi, kichigi kattalashmaydi
            buf = io.BytesIO()
            t.save(buf, format="WEBP", quality=quality, method=6)
            return buf.getvalue()

        return _webp(MAIN_PX, MAIN_QUALITY), _webp(THUMB_PX, THUMB_QUALITY)
    except Exception as e:
        raise ProductImageError("Rasmni qayta ishlab bo'lmadi — fayl buzuq") from e


def write_product_image(tenant_id, product_id: int, raw: bytes) -> str:
    """Siqib diskka yozadi va asosiy rasm URL'ini qaytaradi."""
    main_bytes, thumb_bytes = process_image(raw)
    folder = tenant_folder(tenant_id)
    directory = os.path.join(products_root(), folder)
    os.makedirs(directory, exist_ok=True)

    stem = f"product_{int(product_id)}_{uuid.uuid4().hex[:8]}"
    main_path = os.path.join(directory, stem + ".webp")
    thumb_path = os.path.join(directory, stem + THUMB_SUFFIX + ".webp")
    with open(main_path, "wb") as f:
        f.write(main_bytes)
    with open(thumb_path, "wb") as f:
        f.write(thumb_bytes)
    return f"{URL_PREFIX}/{folder}/{stem}.webp"


def _local_path(url):
    """/uploads/products/... URL → disk yo'li. products/ dan tashqariga chiqsa — None."""
    if not url or not url.startswith(URL_PREFIX + "/"):
        return None
    rel = url[len(URL_PREFIX) + 1:]
    root = os.path.realpath(products_root())
    path = os.path.realpath(os.path.join(root, *rel.split("/")))
    if os.path.commonpath([root, path]) != root or path == root:
        return None
    return path


def delete_image_files(url) -> None:
    """Rasm (va thumbnail) fayllarini o'chiradi. Xato — faqat log, hech qachon raise emas."""
    for u in (url, thumb_url(url)):
        path = _local_path(u)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError as e:
                logger.warning("eski mahsulot rasmi o'chirilmadi %s: %s", path, e)

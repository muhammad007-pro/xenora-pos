"""
AI-Ombor servisi — rasmdagi qog'oz mahsulot ro'yxatini o'qib, tuzilgan
(JSON) mahsulot ma'lumotiga aylantiradi (Claude API, vision).

BOSQICH 1 (backend asos): faqat O'QISH mantiqi.
  - rasm siqish (token tejash: PIL bilan max px + JPEG sifat)
  - Claude API'ga rasm + tizim prompti yuborish (arzon Haiku model)
  - javobni XAVFSIZ JSON parse (buzuq bo'lsa tushunarli xato, crash emas)

XAVFSIZLIK:
  - ANTHROPIC_API_KEY faqat SERVERDA (config → .env), mijozga hech qachon ketmaydi.
  - rasm DISKKA saqlanmaydi — faqat xotirada ishlanadi (maxfiylik).
  - `anthropic` kutubxonasi o'rnatilmagan yoki kalit yo'q bo'lsa ham import/app
    ishga tushadi — xato faqat /scan chaqirilganda tushunarli tarzda qaytadi.

Omborga QO'SHISH, kirim yozish, narx — keyingi bosqichlarda (bu yerda YO'Q).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("ai_warehouse")

# Kalit hali qo'yilmaganini bildiruvchi placeholder qiymatlar (config/.env).
_PLACEHOLDER_KEYS = {"", "change_me", "changeme", "your-api-key", "sk-ant-xxx"}


class AiWarehouseError(Exception):
    """AI-Ombor xatosi — router uni HTTP javobiga o'giradi (crash emas)."""

    def __init__(self, message: str, http_status: int = 400, code: str = "ai_error"):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code


def is_configured() -> bool:
    """API kalit haqiqiy qo'yilganmi (placeholder emasmi)?"""
    key = (settings.ANTHROPIC_API_KEY or "").strip()
    return bool(key) and key.lower() not in _PLACEHOLDER_KEYS


# ── Rasm siqish (token tejash) ──────────────────────────────────────────────
def compress_image(raw: bytes) -> str:
    """
    Katta rasmni kichiklashtirib, base64 JPEG qaytaradi (token tejash).
    - uzun tomon max AI_WAREHOUSE_MAX_IMAGE_PX px gacha
    - telefon EXIF aylanishini to'g'rilaydi (yotgan rasm to'g'ri o'qiladi)
    - JPEG sifat AI_WAREHOUSE_JPEG_QUALITY
    Rasm DISKKA yozilmaydi — hammasi xotirada.
    """
    try:
        from PIL import Image, ImageOps
    except Exception as e:  # Pillow yo'q — bu holat bo'lmasligi kerak (requirements'da)
        raise AiWarehouseError(
            "Rasm ishlash kutubxonasi (Pillow) o'rnatilmagan.",
            http_status=500, code="pillow_missing",
        ) from e

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)          # aylanishni to'g'rila
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        max_px = max(200, int(settings.AI_WAREHOUSE_MAX_IMAGE_PX))
        img.thumbnail((max_px, max_px), Image.LANCZOS)  # nisbatni saqlab kichiklashtir
        buf = io.BytesIO()
        img.save(buf, format="JPEG",
                 quality=int(settings.AI_WAREHOUSE_JPEG_QUALITY), optimize=True)
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except AiWarehouseError:
        raise
    except Exception as e:
        raise AiWarehouseError(
            "Rasmni o'qib bo'lmadi — rasm buzuq yoki qo'llab-quvvatlanmaydigan format.",
            http_status=400, code="bad_image",
        ) from e


# ── Tizim prompti (AI ni to'g'ri yo'naltiradi) ──────────────────────────────
SYSTEM_PROMPT = (
    "Sen do'kon uchun ombor yordamchisisan. Foydalanuvchi QOG'OZ mahsulot ro'yxati "
    "(spiska) rasmini yuboradi. Har qatordan quyidagilarni o'qi: mahsulot NOMI, "
    "MIQDORI (soni), KELISH NARXI (dona uchun).\n"
    "MUHIM qoidalar:\n"
    "- BOSMA va QO'LYOZMA matnni ham o'qi.\n"
    "- Til aralash bo'lishi mumkin: o'zbek/rus, lotin/kirill.\n"
    "- Miqdor va narx turli formatда: '5x60000', '5 dona 60ming', '5 ta 60,000', "
    "'5 60 000'. Bularni sonlarga aylantir (60ming=60000, 60,000=60000).\n"
    "- unit_price = bitta dona narxi (agar faqat jami berilgan bo'lsa, jamini "
    "miqdorga bo'lib chiqar; aniq bo'lmasa confidence pastroq qo'y).\n"
    "- confidence = 0..100 — o'sha qatorni qanchalik ishonch bilan o'qiganing.\n"
    "- Sarlavha, jami/итого qatori, tushunarsiz chiziqlarni MAHSULOT deb olma.\n"
    "- Faqat rasmda haqiqatan bor narsani qaytar — o'ylab topma.\n"
    "Agar rasmni umuman o'qib bo'lmasa (xira, ro'yxat emas, bo'sh), products bo'sh "
    "va error='noaniq' bilan sababini reason'ga yoz."
)

# Javob shaklini qat'iy belgilaymiz — FAQAT JSON obyekt, boshqa matnsiz.
USER_INSTRUCTION = (
    "Ushbu qog'oz ro'yxatdagi mahsulotlarni o'qi.\n"
    "Javobni FAQAT JSON obyekt sifatida qaytar (markdown, izoh yoki boshqa matnsiz):\n"
    '{"products":[{"name":"...","quantity":0,"unit_price":0,"confidence":0}],'
    '"error":"","reason":""}\n'
    "error/reason — faqat rasmni o'qib bo'lmasa to'ldiriladi, aks holda bo'sh."
)


def _safe_json(text: str) -> Dict[str, Any]:
    """
    Model matnidan JSON ni XAVFSIZ ajratib olish (buzuq bo'lsa tushunarli xato).
    Ham obyekt `{...}`, ham massiv `[...]` javobni qabul qiladi (massiv → products).
    """
    if not text or not text.strip():
        raise AiWarehouseError("AI bo'sh javob qaytardi.", http_status=502, code="empty_response")

    def _wrap(obj: Any) -> Dict[str, Any]:
        # Model ba'zan to'g'ridan massiv qaytaradi — uni standart shaklga o'ray.
        if isinstance(obj, list):
            return {"products": obj, "error": "", "reason": ""}
        if isinstance(obj, dict):
            return obj
        raise AiWarehouseError("AI javobi kutilmagan shaklda.", http_status=502, code="bad_shape")

    # 1) to'g'ridan
    try:
        return _wrap(json.loads(text))
    except AiWarehouseError:
        raise
    except Exception:
        pass
    # 2) markdown ``` yoki preamble bo'lsa — birinchi {..} yoki [..] blokini top
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return _wrap(json.loads(m.group(0)))
        except Exception:
            pass
    raise AiWarehouseError(
        "AI javobini o'qib bo'lmadi (JSON buzuq).", http_status=502, code="bad_json",
    )


def _normalize_products(data: Dict[str, Any]) -> Dict[str, Any]:
    """Model javobini tozalab, barqaror shaklga keltiradi."""
    raw_products = data.get("products") or []
    products: List[Dict[str, Any]] = []
    for item in raw_products:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        try:
            quantity = float(item.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0.0
        try:
            unit_price = float(item.get("unit_price") or 0)
        except (TypeError, ValueError):
            unit_price = 0.0
        try:
            confidence = int(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        confidence = max(0, min(100, confidence))
        products.append({
            "name": name,
            "quantity": round(quantity, 3),
            "unit_price": round(unit_price, 2),
            "confidence": confidence,
        })
    return {
        "products": products,
        "error": str(data.get("error") or "").strip() or None,
        "reason": str(data.get("reason") or "").strip() or None,
    }


# ── Asosiy: rasmni Claude'ga yuborib, mahsulotlarni o'qish ──────────────────
def scan_image(raw: bytes, *, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Rasmni Claude API'ga yuborib, mahsulot ro'yxatini qaytaradi.
    Qaytish: {products, error, reason, usage:{input_tokens, output_tokens}}
    Xatolarni AiWarehouseError bilan qaytaradi (router HTTP'ga o'giradi).
    """
    if not settings.AI_WAREHOUSE_ENABLED:
        raise AiWarehouseError("AI-Ombor o'chirilgan.", http_status=503, code="disabled")
    if not is_configured():
        raise AiWarehouseError(
            "AI-Ombor sozlanmagan: server .env faylida ANTHROPIC_API_KEY qo'yilmagan. "
            "Administrator kalitni qo'shishi kerak.",
            http_status=503, code="not_configured",
        )

    # Lazy import — kutubxona yo'q bo'lsa ham app ishga tushadi, xato faqat shu yerда.
    try:
        import anthropic
    except Exception as e:
        raise AiWarehouseError(
            "AI kutubxonasi (anthropic) o'rnatilmagan. `pip install anthropic` kerak.",
            http_status=503, code="anthropic_missing",
        ) from e

    b64 = compress_image(raw)

    try:
        # timeout — SDK standarti 600s; rasm tahliliga 75s yetadi, aks holda so'rov osiladi.
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=float(settings.AI_WAREHOUSE_TIMEOUT),
        )
        resp = client.messages.create(
            model=settings.AI_WAREHOUSE_MODEL,
            max_tokens=int(settings.AI_WAREHOUSE_MAX_TOKENS),
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": b64,
                    }},
                    {"type": "text", "text": USER_INSTRUCTION},
                ],
            }],
        )
    except AiWarehouseError:
        raise
    except Exception as e:
        raise _map_anthropic_error(e)

    # Javob matnini ol (structured output → birinchi text bloki toza JSON)
    text = ""
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = block.text
            break

    result = _normalize_products(_safe_json(text))

    usage = getattr(resp, "usage", None)
    in_tok = getattr(usage, "input_tokens", 0) or 0
    out_tok = getattr(usage, "output_tokens", 0) or 0
    result["usage"] = {"input_tokens": in_tok, "output_tokens": out_tok}

    # Xarajat logi (kelajakda limit/hisob uchun) — oddiy structured log.
    logger.info(
        "ai_warehouse.scan tenant=%s model=%s in_tok=%s out_tok=%s products=%s",
        tenant_id, settings.AI_WAREHOUSE_MODEL, in_tok, out_tok, len(result["products"]),
    )
    return result


def _map_anthropic_error(e: Exception) -> AiWarehouseError:
    """Anthropic SDK xatosini tushunarli AiWarehouseError'ga o'giradi (crash emas)."""
    try:
        import anthropic
    except Exception:
        return AiWarehouseError(f"AI xizmatida xato: {e}", http_status=502, code="ai_unavailable")

    if isinstance(e, anthropic.AuthenticationError):
        return AiWarehouseError(
            "ANTHROPIC_API_KEY noto'g'ri yoki muddati o'tgan (server sozlamasi).",
            http_status=503, code="bad_key")
    if isinstance(e, anthropic.RateLimitError):
        return AiWarehouseError(
            "AI xizmatiga so'rov limiti oshib ketdi — birozdan keyin urinib ko'ring.",
            http_status=429, code="rate_limited")
    # DIQQAT: APITimeoutError — APIConnectionError'ning bola sinfi, shuning uchun UNDAN OLDIN tekshiriladi.
    if isinstance(e, anthropic.APITimeoutError):
        return AiWarehouseError(
            "Tahlil vaqti tugadi — rasmni qayta yuklab, urinib ko'ring (yengilroq/aniqroq rasm).",
            http_status=504, code="timeout")
    if isinstance(e, anthropic.APIConnectionError):
        return AiWarehouseError(
            "AI xizmatiga ulanib bo'lmadi — internet yoki xizmatni tekshiring.",
            http_status=502, code="connection")
    if isinstance(e, anthropic.APIStatusError):
        return AiWarehouseError(
            f"AI xizmati xatosi ({getattr(e, 'status_code', '?')}).",
            http_status=502, code="ai_status")
    return AiWarehouseError(f"AI xizmatida kutilmagan xato: {e}",
                            http_status=502, code="ai_unexpected")

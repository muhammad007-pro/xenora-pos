"""
Telegram bot webhook (BOSQICH 5.3)

Bot imkoniyatlari:
  - Yangi buyurtma bildirishnomalari (oshxona/menejer uchun)
  - /today → bugungi savdo xisoboti
  - /orders → faol buyurtmalar ro'yxati
  - /status → tizim holati

O'rnatish:
  1. BotFather'dan token olish → .env TELEGRAM_BOT_TOKEN=xxx
  2. Webhook: POST https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://domain/telegram/webhook
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
import httpx

from database import get_db
from config import settings

router = APIRouter()


# ── Telegram API yordamchi ────────────────────────────────────────────────────

async def _send_message(chat_id: int | str, text: str, parse_mode: str = "HTML"):
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=5,
        )


def _verify_token(x_telegram_bot_api_secret_token: Optional[str] = Header(None)):
    """Webhook xavfsizlik tekshiruvi"""
    secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None)
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_token),
):
    """Telegram'dan kelgan update'ni qayta ishlash"""
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    msg     = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True}

    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "").strip()

    if text.startswith("/start"):
        await _send_message(chat_id,
            "👋 <b>RestoPOS Bot</b>'ga xush kelibsiz!\n\n"
            "Buyruqlar:\n"
            "/today — bugungi savdo\n"
            "/orders — faol buyurtmalar\n"
            "/status — tizim holati\n"
        )

    elif text.startswith("/today"):
        response = await _get_today_report(db)
        await _send_message(chat_id, response)

    elif text.startswith("/orders"):
        response = await _get_active_orders(db)
        await _send_message(chat_id, response)

    elif text.startswith("/status"):
        await _send_message(chat_id, "✅ <b>RestoPOS</b> ishlayapti.")

    else:
        await _send_message(chat_id, "❓ Noma'lum buyruq. /start orqali yordam oling.")

    return {"ok": True}


# ── Hisobot yordamchilari ─────────────────────────────────────────────────────

async def _get_today_report(db: Session) -> str:
    from models import Order, Payment
    from sqlalchemy import func

    today_start = date.today().isoformat()

    orders = db.query(Order).filter(
        func.date(Order.created_at) == today_start,
        Order.status == "completed"
    ).all()

    total_orders = len(orders)
    total_revenue = sum(o.final_amount for o in orders)
    by_source = {}
    for o in orders:
        by_source[o.source or "pos"] = by_source.get(o.source or "pos", 0) + 1

    source_lines = "\n".join(f"  {k}: {v} ta" for k, v in by_source.items())
    return (
        f"📊 <b>Bugungi hisobot — {today_start}</b>\n\n"
        f"Yakunlangan buyurtmalar: <b>{total_orders} ta</b>\n"
        f"Jami tushum: <b>{total_revenue:,.0f} UZS</b>\n\n"
        f"Manba bo'yicha:\n{source_lines or '  —'}"
    )


async def _get_active_orders(db: Session) -> str:
    from models import Order

    orders = db.query(Order).filter(
        Order.status.in_(["pending", "confirmed", "preparing", "ready"])
    ).order_by(Order.created_at).limit(10).all()

    if not orders:
        return "📋 Hozirda faol buyurtma yo'q."

    lines = []
    for o in orders:
        status_icons = {"pending":"⏳", "confirmed":"✅", "preparing":"🍳", "ready":"🔔"}
        icon = status_icons.get(o.status, "•")
        table_num = o.table.number if o.table else "—"
        lines.append(f"{icon} #{o.order_number} | Stol {table_num} | {o.final_amount:,.0f} UZS")

    return "📋 <b>Faol buyurtmalar:</b>\n" + "\n".join(lines)


# ── Proaktiv bildirishnoma funksiyasi (boshqa modullar chaqiradi) ─────────────

async def notify_new_order(order_id: int, order_number: str, table: str, amount: float, chat_ids: list):
    """Yangi buyurtma haqida belgilangan chat'larga xabar yuborish"""
    text = (
        f"🆕 <b>Yangi buyurtma</b>\n"
        f"#{order_number} | Stol {table}\n"
        f"Summa: {amount:,.0f} UZS"
    )
    for chat_id in chat_ids:
        await _send_message(chat_id, text)


async def notify_payment(order_number: str, amount: float, method: str, chat_ids: list):
    method_names = {"cash": "Naqd", "card": "Karta", "click": "Click", "payme": "Payme"}
    text = (
        f"💰 <b>To'lov qabul qilindi</b>\n"
        f"#{order_number}\n"
        f"{method_names.get(method, method)}: {amount:,.0f} UZS"
    )
    for chat_id in chat_ids:
        await _send_message(chat_id, text)

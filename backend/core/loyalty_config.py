"""Tenant-scoped sodiqlik (loyalty ball) sozlamalari + qo'llash mantiqi (Tier 4).

MIGRATSIYASIZ: sozlamalar TenantSettings(config_name="loyalty")da; LoyaltyTransaction
va Customer.points allaqachon mavjud.

Egasi qarorlari:
- Ball NET summadan (order.final_amount — chegirmalardan keyin) yig'iladi.
- Redeem = TO'LOV TENDERI: order.final_amount O'ZGARMAYDI; sotuv `total_paid + redeem_amount
  >= final_amount` bo'lganda yakunlanadi (ball bilan qoplangan qism naqd emas).
- Walk-in (mijozsiz) → ball yig'ilmaydi/ishlatilmaydi. Ball muddati YO'Q (abadiy).
- Stavkalar tenant sozlaydi (default: 1000 so'm=1 ball; 1 ball=10 so'm; min 100 ball; maks 30%).
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

CONFIG_NAME = "loyalty"

DEFAULTS = {
    "enabled": True,
    "earn_rate": 1000,          # har shu UZS xariddan 1 ball
    "redeem_value": 10,         # 1 ball = shu UZS
    "min_redeem_points": 100,   # minimal yechish (ball)
    "max_redeem_percent": 30,   # to'lovning maks foizi ball bilan qoplanadi
}


def get_loyalty_config(db: Session, tenant_id) -> dict:
    """Tenant loyalty sozlamalari (default bilan birlashtirilgan, turlar normallashtirilgan)."""
    from core.tenant_config import get_tenant_config
    cfg = dict(DEFAULTS)
    if tenant_id:
        saved = get_tenant_config(db, tenant_id, CONFIG_NAME) or {}
        for k in DEFAULTS:
            if k in saved and saved[k] is not None:
                cfg[k] = saved[k]
    cfg["enabled"]           = bool(cfg["enabled"])
    cfg["earn_rate"]         = max(1, int(cfg["earn_rate"] or 1))
    cfg["redeem_value"]      = max(0.0, float(cfg["redeem_value"] or 0))
    cfg["min_redeem_points"] = max(0, int(cfg["min_redeem_points"] or 0))
    cfg["max_redeem_percent"] = min(100.0, max(0.0, float(cfg["max_redeem_percent"] or 0)))
    return cfg


def calc_earn_points(final_amount: float, cfg: dict) -> int:
    if not cfg["enabled"] or cfg["earn_rate"] <= 0:
        return 0
    return max(0, int((final_amount or 0) // cfg["earn_rate"]))


def validate_redeem(db: Session, order, cfg: dict, redeem_points: int) -> float:
    """SERVER TOMONDA tekshirish — client yuborgan qiymatga ISHONMAYMIZ (#34 kabi).
    Yaroqli bo'lsa redeem summasini (UZS) qaytaradi; aks holda 400."""
    from models import Customer
    if redeem_points <= 0:
        return 0.0
    if not cfg["enabled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sodiqlik dasturi o'chirilgan")
    if not order.customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ball ishlatish uchun mijoz tanlanishi shart")
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    bal = ((customer.points if customer else 0) or 0)
    if redeem_points < cfg["min_redeem_points"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Kamida {cfg['min_redeem_points']} ball ishlatiladi")
    if redeem_points > bal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Balansda yetarli ball yo'q (mavjud: {bal})")
    amount = redeem_points * cfg["redeem_value"]
    max_amt = (order.final_amount or 0) * cfg["max_redeem_percent"] / 100.0
    if amount > max_amt + 0.001:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Ball bilan eng ko'pi {int(cfg['max_redeem_percent'])}% qoplash mumkin")
    return round(amount, 2)


def apply_redeem(db: Session, order, redeem_points: int, redeem_amount: float, tenant_id) -> None:
    """Sotuv YAKUNLANGANDA bir marta (status endi completed). Customer row-lock — double-spend yo'q."""
    from models import Customer, LoyaltyTransaction
    customer = db.query(Customer).filter(Customer.id == order.customer_id).with_for_update().first()
    if not customer or (customer.points or 0) < redeem_points:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yetarli ball yo'q")
    customer.points = (customer.points or 0) - redeem_points
    db.add(LoyaltyTransaction(
        tenant_id=tenant_id, customer_id=customer.id, order_id=order.id,
        type="redeem", points=-redeem_points,
        description=f"{redeem_amount:.0f} so'm chegirma (to'lov)"))


def apply_earn(db: Session, order, cfg: dict, tenant_id) -> int:
    """Ball NETDAN (order.final_amount) yig'iladi. Sotuv yakunида bir marta."""
    from models import Customer, LoyaltyTransaction
    earn = calc_earn_points(order.final_amount, cfg)
    if earn <= 0:
        return 0
    customer = db.query(Customer).filter(Customer.id == order.customer_id).with_for_update().first()
    if not customer:
        return 0
    customer.points = (customer.points or 0) + earn
    db.add(LoyaltyTransaction(
        tenant_id=tenant_id, customer_id=customer.id, order_id=order.id,
        type="earn", points=earn,
        description=f"{order.final_amount:.0f} so'm xariddan"))
    return earn


def reverse_on_refund(db: Session, order, tenant_id) -> None:
    """Refund'да: yig'ilgan ball QAYTARIB OLINADI (-), ishlatilgan ball QAYTARILADI (+).
    Idempotent — order uchun 'adjust' yozuvi allaqachon bo'lsa hech narsa qilmaydi."""
    from models import Customer, LoyaltyTransaction
    if not order.customer_id:
        return
    already = db.query(LoyaltyTransaction).filter(
        LoyaltyTransaction.order_id == order.id,
        LoyaltyTransaction.type == "adjust").first()
    if already:
        return
    txns = db.query(LoyaltyTransaction).filter(
        LoyaltyTransaction.order_id == order.id,
        LoyaltyTransaction.type.in_(("earn", "redeem"))).all()
    earned   = sum(t.points for t in txns if t.type == "earn")      # musbat
    redeemed = sum(-t.points for t in txns if t.type == "redeem")   # sarflangan (musbat)
    if earned == 0 and redeemed == 0:
        return
    customer = db.query(Customer).filter(Customer.id == order.customer_id).with_for_update().first()
    if not customer:
        return
    net = redeemed - earned   # ishlatilgan qaytadi (+), yig'ilgan olinadi (-)
    customer.points = max(0, (customer.points or 0) + net)
    db.add(LoyaltyTransaction(
        tenant_id=tenant_id, customer_id=customer.id, order_id=order.id,
        type="adjust", points=net, description="Refund: ball tuzatildi"))

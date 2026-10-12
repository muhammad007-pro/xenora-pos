"""
Bir martalik to'ldirish: `order_items.tenant_id` ni BUYURTMADAN (`orders.tenant_id`)
olish.

NEGA: 2026-10-07 gacha sotuv qatorlari `tenant_id` SIZ yozilgan
(`services/order_service.py`, `add_item`, `public.py`) — prodda hamma qator NULL.
Kod endi tenantni buyurtma orqali tekshiradi (`deps.scoped_order_items`), ya'ni
vozvrat bu skriptsiz ham ishlaydi. Skript ma'lumotni TO'G'RI holatga keltiradi
(hisobotlar/kelajakdagi `OrderItem.tenant_id` filtrlari uchun).

XAVFSIZLIK:
  • Default — PREVIEW, hech narsa yozilmaydi.
  • FAQAT `tenant_id IS NULL` qatorlar to'ldiriladi. Allaqachon to'ldirilgan
    qator TEGILMAYDI — buyurtmanikidan FARQ qilsa ham (u faqat hisobotda
    ko'rsatiladi, qo'lda ko'rib chiqish uchun).
  • Buyurtmasi tenantsiz (`orders.tenant_id IS NULL`) qatorlar tegilmaydi.
  • Idempotent: ikkinchi marta ishga tushirilsa 0 qator.
  • --tenant N bilan bitta do'kon.
  • Bu MIGRATSIYA EMAS (sxema o'zgarmaydi), alembic'ga qo'shilmaydi.

ISHGA TUSHIRISH (backend/ katalogidan):
    venv/bin/python scripts/backfill_order_items_tenant.py              # preview
    venv/bin/python scripts/backfill_order_items_tenant.py --apply
    venv/bin/python scripts/backfill_order_items_tenant.py --tenant 30 --apply
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select, update  # noqa: E402

from models import Order, OrderItem  # noqa: E402


def _null_filter(tenant):
    """To'ldiriladigan qatorlar: tenant_id NULL va buyurtmasining tenanti bor."""
    order_q = select(Order.id).where(Order.tenant_id.isnot(None))
    if tenant is not None:
        order_q = order_q.where(Order.tenant_id == tenant)
    return (OrderItem.tenant_id.is_(None), OrderItem.order_id.in_(order_q))


def plan(db, tenant=None) -> dict:
    """Nima o'zgarishi: tenant bo'yicha to'ldiriladigan qatorlar + nomuvofiqliklar."""
    by_tenant = dict(
        db.query(Order.tenant_id, func.count(OrderItem.id))
          .join(Order, Order.id == OrderItem.order_id)
          .filter(*_null_filter(tenant))
          .group_by(Order.tenant_id).all()
    )
    mismatch_q = (db.query(func.count(OrderItem.id))
                    .join(Order, Order.id == OrderItem.order_id)
                    .filter(OrderItem.tenant_id.isnot(None),
                            Order.tenant_id.isnot(None),
                            OrderItem.tenant_id != Order.tenant_id))
    orphan_q = (db.query(func.count(OrderItem.id))
                  .join(Order, Order.id == OrderItem.order_id)
                  .filter(OrderItem.tenant_id.is_(None), Order.tenant_id.is_(None)))
    if tenant is not None:
        mismatch_q = mismatch_q.filter(Order.tenant_id == tenant)
    return {
        "to_fill": by_tenant,
        "total": sum(by_tenant.values()),
        "mismatch": mismatch_q.scalar() or 0,
        "order_without_tenant": 0 if tenant is not None else (orphan_q.scalar() or 0),
    }


def apply(db, tenant=None) -> int:
    """To'ldiradi va o'zgargan qatorlar sonini qaytaradi (bitta tranzaksiya)."""
    sub = (select(Order.tenant_id)
           .where(Order.id == OrderItem.order_id)
           .scalar_subquery())
    res = db.execute(
        update(OrderItem)
        .where(*_null_filter(tenant))
        .values(tenant_id=sub)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return res.rowcount or 0


def main():
    ap = argparse.ArgumentParser(description="order_items.tenant_id ni buyurtmadan to'ldirish")
    ap.add_argument("--apply", action="store_true", help="Haqiqiy yozish. Berilmasa — preview.")
    ap.add_argument("--tenant", type=int, default=None, help="Faqat shu tenant.")
    args = ap.parse_args()

    from database import SessionLocal
    db = SessionLocal()
    try:
        p = plan(db, args.tenant)
        line = "-" * 60
        print(line)
        print(f"Tenant filtri: {args.tenant if args.tenant is not None else 'BARCHA'}")
        for tid, n in sorted(p["to_fill"].items()):
            print(f"  tenant {tid:<5}: {n} qator to'ldiriladi")
        print(f"  JAMI           : {p['total']}")
        print(f"  Nomuvofiq (tegilmaydi, ko'rib chiqing): {p['mismatch']}")
        print(f"  Buyurtmasi tenantsiz (tegilmaydi)     : {p['order_without_tenant']}")
        print(line)
        if not args.apply:
            print("PREVIEW — hech narsa o'zgartirilmadi. Bajarish: --apply")
            return
        n = apply(db, args.tenant)
        print(f"BAJARILDI: {n} qator to'ldirildi.")
        left = plan(db, args.tenant)["total"]
        print(f"Qolgan NULL (to'ldiriladigan): {left}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

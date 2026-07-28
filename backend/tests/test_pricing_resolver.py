"""GOLDEN + FAZA 2 — #34 chegirma (_compute_auto_discount) va Promotion (flash/min_qty/min_amount).

#34 GOLDEN (S1-S10): Promotion YO'Q savatда natija AYNAN bir xil bo'lishi SHART (regressiya yo'q).
FAZA 2 (P1-P8): flash_price, min_qty, min_amount, STACKING-yo'q (best-only), muddati o'tган.
DB fake — matematika sinaladi. Ishga tushirish:  cd backend && py tests/test_pricing_resolver.py
"""
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Discount, Product, Promotion
from services.order_service import OrderService


class _FakeQ:
    def __init__(self, rows): self.rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self.rows


class _FakeDB:
    def __init__(self, discounts, promos, prodcats):
        self._d, self._pr, self._pc = discounts, promos, prodcats
    def query(self, *ent):
        if ent and ent[0] is Discount:  return _FakeQ(self._d)
        if ent and ent[0] is Promotion: return _FakeQ(self._pr)
        return _FakeQ(self._pc)


def _d(id, type, value, product_id=None, category_id=None, min_order_amount=0.0):
    return Discount(id=id, name=f"d{id}", type=type, value=value,
                    product_id=product_id, category_id=category_id, min_order_amount=min_order_amount)


def _p(id, promo_type, product_id=None, category_id=None, discount_type="percentage",
       discount_value=0.0, min_purchase_amount=0.0, min_purchase_qty=0, flash_price=None,
       start_date=None, end_date=None, days_of_week=None, time_from=None, time_to=None):
    return Promotion(id=id, name=f"p{id}", promo_type=promo_type, product_id=product_id,
                     category_id=category_id, discount_type=discount_type, discount_value=discount_value,
                     min_purchase_amount=min_purchase_amount, min_purchase_qty=min_purchase_qty,
                     flash_price=flash_price, start_date=start_date, end_date=end_date,
                     days_of_week=days_of_week, time_from=time_from, time_to=time_to,
                     is_active=True, usage_limit=None, used_count=0)


def _run(discounts, promos, items, subtotal, prodcats):
    svc = OrderService(_FakeDB(discounts, promos, prodcats))
    total, dids, pids = svc._compute_auto_discount(tenant_id=20, items_data=items, subtotal=subtotal)
    return round(total, 2), sorted(dids), sorted(pids)


def _it(pid, qty, unit_price):
    return {"product_id": pid, "quantity": qty, "unit_price": unit_price, "total_price": unit_price * qty}


I1 = [_it(100, 2, 5000)]   # bitta item: 2×5000 = 10000
PC = [(100, 5)]            # product 100 → category 5
_past = datetime.now() - timedelta(days=1)

SCENARIOS = {
    # ── #34 GOLDEN (Promotion YO'Q — AYNAN bir xil) ──
    "S1_bo'sh_savat":       (_run([], [], [], 0, []),                                             (0.0, [], [])),
    "S2_chegirmasiz":       (_run([], [], I1, 10000, PC),                                         (0.0, [], [])),
    "S3_item_foiz10":       (_run([_d(1,"percentage",10,product_id=100)], [], I1, 10000, PC),     (1000.0, [1], [])),
    "S4_item_fixed_cap":    (_run([_d(2,"fixed",500,product_id=100)], [], [_it(100,1,300)], 300, PC), (300.0, [2], [])),
    "S5_product>category":  (_run([_d(3,"percentage",10,product_id=100), _d(4,"percentage",50,category_id=5)], [], I1, 10000, PC), (1000.0, [3], [])),
    "S6_category_fallback": (_run([_d(5,"percentage",20,category_id=5)], [], I1, 10000, PC),       (2000.0, [5], [])),
    "S7_best_only_2item":   (_run([_d(6,"percentage",10,product_id=100), _d(7,"percentage",25,product_id=100)], [], I1, 10000, PC), (2500.0, [7], [])),
    "S8_cart_min_met":      (_run([_d(8,"percentage",5,min_order_amount=5000)], [], I1, 10000, PC),(500.0, [8], [])),
    "S9_cart_min_notmet":   (_run([_d(9,"fixed",1000,min_order_amount=50000)], [], I1, 10000, PC), (0.0, [], [])),
    "S10_item+cart":        (_run([_d(10,"percentage",10,product_id=100), _d(11,"percentage",5,min_order_amount=0)], [], I1, 10000, PC), (1450.0, [10, 11], [])),

    # ── FAZA 2 Promotion ──
    "P1_flash":             (_run([], [_p(20,"flash_price",product_id=100,flash_price=4000)], I1, 10000, PC), (2000.0, [], [20])),
    "P2_min_qty_met":       (_run([], [_p(21,"min_qty_discount",product_id=100,discount_value=10,min_purchase_qty=2)], I1, 10000, PC), (1000.0, [], [21])),
    "P3_min_qty_notmet":    (_run([], [_p(22,"min_qty_discount",product_id=100,discount_value=10,min_purchase_qty=5)], I1, 10000, PC), (0.0, [], [])),
    "P4_min_amount_met":    (_run([], [_p(23,"min_amount",discount_value=5,min_purchase_amount=10000)], I1, 10000, PC), (500.0, [], [23])),
    "P5_min_amount_notmet": (_run([], [_p(24,"min_amount",discount_value=5,min_purchase_amount=50000)], I1, 10000, PC), (0.0, [], [])),
    "P6_stacking_best_only":(_run([_d(1,"percentage",10,product_id=100)], [_p(50,"flash_price",product_id=100,flash_price=4000)], I1, 10000, PC), (2000.0, [], [50])),
    "P7_tie_discount_wins": (_run([_d(1,"percentage",20,product_id=100)], [_p(51,"flash_price",product_id=100,flash_price=4000)], I1, 10000, PC), (2000.0, [1], [])),
    "P8_expired_promo":     (_run([], [_p(52,"flash_price",product_id=100,flash_price=4000,end_date=_past)], I1, 10000, PC), (0.0, [], [])),
}


def test_pricing_snapshot():
    fails = [f"{n}: kutilgan {exp}, olindi {act}" for n, (act, exp) in SCENARIOS.items() if act != exp]
    assert not fails, "REGRESSIYA/XATO:\n" + "\n".join(fails)


if __name__ == "__main__":
    ok = 0
    for name, (act, exp) in SCENARIOS.items():
        good = act == exp
        ok += good
        print(f"[{'OK  ' if good else 'FAIL'}] {name}: {act}" + ("" if good else f"  != {exp}"))
    print(f"\n{ok}/{len(SCENARIOS)} PASS")
    sys.exit(0 if ok == len(SCENARIOS) else 1)

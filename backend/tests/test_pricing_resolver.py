"""FAZA 0 — GOLDEN SNAPSHOT: #34 avto-chegirma (_compute_auto_discount) hozirgi xatti-harakati.

Bu test resolver refaktoringidan OLDIN va KEYIN bir xil natija berishi SHART (behavior-preserving).
DB'ni fake qilamiz — faqat MATEMATIKA sinaladi (is_active/valid_from/valid_to/usage filtri DB
so'rovida qoladi, refaktoringda TEGILMAYDI). Ishga tushirish:  cd backend && py tests/test_pricing_resolver.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Discount, Product
from services.order_service import OrderService


class _FakeQ:
    def __init__(self, rows): self.rows = rows
    def filter(self, *a, **k): return self
    def all(self): return self.rows


class _FakeDB:
    """query(Discount) → discount ro'yxati; query(Product.id, Product.category_id) → (pid,cid)."""
    def __init__(self, discounts, prodcats):
        self._d, self._pc = discounts, prodcats
    def query(self, *ent):
        if ent and ent[0] is Discount:
            return _FakeQ(self._d)
        return _FakeQ(self._pc)


def _d(id, type, value, product_id=None, category_id=None, min_order_amount=0.0):
    return Discount(id=id, name=f"d{id}", type=type, value=value,
                    product_id=product_id, category_id=category_id,
                    min_order_amount=min_order_amount)


def _run(discounts, items, subtotal, prodcats):
    svc = OrderService(_FakeDB(discounts, prodcats))
    total, ids = svc._compute_auto_discount(tenant_id=20, items_data=items, subtotal=subtotal)
    return round(total, 2), sorted(ids)


# ── GOLDEN stsenariylar: (total, sorted_ids) hozirgi kod natijasi ──
SCENARIOS = {
    "S1_bo'sh_savat":        (_run([], [], 0, []), (0.0, [])),
    "S2_chegirmasiz":        (_run([], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (0.0, [])),
    "S3_item_foiz10":        (_run([_d(1,"percentage",10,product_id=100)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (1000.0, [1])),
    "S4_item_fixed_cap":     (_run([_d(2,"fixed",500,product_id=100)], [{"product_id":100,"total_price":300}], 300, [(100,5)]), (300.0, [2])),
    "S5_product>category":   (_run([_d(3,"percentage",10,product_id=100), _d(4,"percentage",50,category_id=5)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (1000.0, [3])),
    "S6_category_fallback":  (_run([_d(5,"percentage",20,category_id=5)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (2000.0, [5])),
    "S7_best_only_2item":    (_run([_d(6,"percentage",10,product_id=100), _d(7,"percentage",25,product_id=100)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (2500.0, [7])),
    "S8_cart_min_met":       (_run([_d(8,"percentage",5,min_order_amount=5000)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (500.0, [8])),
    "S9_cart_min_notmet":    (_run([_d(9,"fixed",1000,min_order_amount=50000)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (0.0, [])),
    "S10_item+cart":         (_run([_d(10,"percentage",10,product_id=100), _d(11,"percentage",5,min_order_amount=0)], [{"product_id":100,"total_price":10000}], 10000, [(100,5)]), (1450.0, [10,11])),
}


def test_golden_snapshot():
    fails = []
    for name, (actual, expected) in SCENARIOS.items():
        if actual != expected:
            fails.append(f"{name}: kutilgan {expected}, olindi {actual}")
    assert not fails, "REGRESSIYA:\n" + "\n".join(fails)


if __name__ == "__main__":
    ok = 0
    for name, (actual, expected) in SCENARIOS.items():
        mark = "OK  " if actual == expected else "FAIL"
        if actual == expected: ok += 1
        print(f"[{mark}] {name}: {actual}" + ("" if actual == expected else f"  != {expected}"))
    print(f"\n{ok}/{len(SCENARIOS)} PASS")
    sys.exit(0 if ok == len(SCENARIOS) else 1)

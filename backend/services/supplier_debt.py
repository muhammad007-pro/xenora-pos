"""Firma (yetkazib beruvchi) qarzi — YAGONA HISOB MANBAI.

NEGA ALOHIDA SERVIS: qarz ilgari IKKI xil formula bilan hisoblanardi va ikki ekran
har xil son ko'rsatardi:
  - routers/suppliers.py  /debt-summary   -> xarid - to'lov - vozvrat
  - routers/analytics.py  /store-dashboard -> `status != paid` priyomkalar SUMMASI
    (draftlarni ham qo'shardi, to'lov va vozvratni umuman ayirmasdi)
Endi ikkalasi ham SHU faylni chaqiradi. Formula bitta joyda o'zgaradi.

ASOSIY TUZATISH (mijozda topildi — Fazza Parfum, 5-6 firma bilan nasiya):
    SupplierPayment.receipt_id.isnot(None)
Eski `/debt-summary` faqat NAKLADNOYGA BOG'LANGAN to'lovlarni sanardi. Firma agenti
tovarsiz kelib pul olib ketganda (UI'dagi "Umumiy to'lov" varianti) to'lov saqlanardi,
tarixda ko'rinardi, LEKIN qarzni kamaytirmasdi — do'konchi ikki marta to'lash xavfi
ostida edi. Endi BARCHA to'lovlar sanaladi.

TAQSIMOT (FIFO) — nima uchun kerak:
"Muddati o'tgan" (otsrochka) nakladnoy darajasida hisoblanadi, umumiy to'lov esa hech
qaysi nakladnoyga bog'lanmagan. Shuning uchun bog'lanmagan pul O'QISH PAYTIDA eng eski
qarzdan boshlab taqsimlanadi (buxgalteriyaning odatiy qoidasi). Taqsimot BAZAGA
YOZILMAYDI — har safar qayta hisoblanadi, ya'ni migratsiya kerak emas va to'lov
o'chirilsa/qo'shilsa natija o'z-o'zidan to'g'rilanadi.

AVANS: ortiqcha to'langan pul endi yo'qolmaydi — `advance` bo'lib qaytadi
(ilgari `max(0, ...)` uni jimgina 0 qilardi).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date, timedelta
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from models import PurchaseReceipt, Supplier, SupplierPayment, SupplierReturn

# Qarzga KIRADIGAN priyomka holatlari. `draft` ATAYLAB yo'q: tovar hali omborga
# kirmagan, hujjat tasdiqlanmagan -> qarz ham yo'q (bu xato emas, qoida).
DEBT_STATUSES = ("confirmed", "paid")

# So'mning yuzdan biri. Float yaxlitlash qoldig'i (0.0000001) "qarz" yoki
# "muddati o'tgan" bo'lib ko'rinmasligi uchun.
_EPS = 0.01


@dataclass
class ReceiptDebt:
    """Bitta nakladnoy bo'yicha qoldiq (FIFO taqsimotdan keyin)."""
    receipt_id:     int
    receipt_date:   Optional[Date]
    invoice_number: Optional[str]
    net_amount:     float
    paid:           float           # bog'langan to'lov + FIFO'dan tushgan ulush
    remaining:      float
    due_date:       Optional[Date]  # receipt_date + otsrochka
    is_overdue:     bool


@dataclass
class SupplierDebt:
    """Bitta firma bo'yicha to'liq holat."""
    supplier_id:     int
    supplier_name:   str
    phone:           Optional[str]
    opening_debt:    float          # FAZA 3: tizimga o'tishdan OLDINGI qarz
    total_purchases: float          # faqat PRIYOMKALAR (opening_debt bu yerda EMAS)
    total_paid:      float          # BARCHA to'lovlar (bog'langan + umumiy)
    total_returned:  float
    balance:         float          # ISHORALI: musbat = biz qarzdormiz, manfiy = avans
    debt:            float          # max(balance, 0)  — eski UI shuni ko'rsatadi
    advance:         float          # max(-balance, 0) — ortiqcha to'langan pul
    overdue_amount:  float
    last_purchase:   Optional[Date]
    receipts:        List[ReceiptDebt] = field(default_factory=list)


def compute_supplier_debt(
    supplier: Supplier,
    receipts: Sequence[PurchaseReceipt],
    payments: Sequence[SupplierPayment],
    returns:  Sequence[SupplierReturn],
    today:    Optional[Date] = None,
) -> SupplierDebt:
    """Bitta firma qarzini hisoblash (DB'ga tegmaydi — sof funksiya, test qulay)."""
    today = today or Date.today()
    delay = supplier.payment_delay_days or 0

    # FAZA 3: BOSHLANG'ICH QARZ — tizimga o'tishdan oldingi qarz. Unga hujjat yo'q,
    # shuning uchun alohida qoldiq sifatida yuritiladi va FIFO'da ENG ESKI qarz
    # hisoblanadi (pul avval shuni yopadi — buxgalteriyaning odatiy tartibi).
    # `Numeric` -> float: qolgan summalar Float, aralashtirmaymiz (Decimal+float xato).
    # MUDDAT: boshlang'ich qarzga "muddati o'tgan" belgisi QO'YILMAYDI — uning asl
    # shartnoma sanasi bizda yo'q, o'ylab topilgan muddat yolg'on ogohlantirish berardi.
    opening = float(getattr(supplier, "opening_debt", 0) or 0)
    opening_left = opening

    # Qarz yaratadigan nakladnoylar, ESKIDAN YANGIGA (FIFO tartibi).
    # Sana bo'lmasa eng oxiriga tushadi (Date.max), id — barqaror tie-breaker.
    debt_receipts = sorted(
        [r for r in receipts if r.status in DEBT_STATUSES],
        key=lambda r: (r.receipt_date or Date.max, r.id),
    )
    remaining: Dict[int, float] = {r.id: float(r.net_amount or 0) for r in debt_receipts}

    # ── 1-bosqich: nakladnoyga BOG'LANGAN to'lovlar o'z nakladnoyiga ─────────
    # Ortiqchasi (nakladnoydan ko'p to'langan bo'lsa) umumiy hovuzga o'tadi —
    # pul yo'qolmasin.
    pool = 0.0
    for p in payments:
        amount = float(p.amount or 0)
        rid = p.receipt_id
        if rid is not None and rid in remaining:
            applied = min(amount, remaining[rid])
            remaining[rid] -= applied
            pool += amount - applied
        else:
            # receipt_id=None (umumiy to'lov) YOKI draft/o'chirilgan nakladnoyga
            # bog'langan to'lov — baribir firmaga berilgan pul, hovuzga tushadi.
            pool += amount

    # ── 2-bosqich: vozvrat ham qarzni kamaytiradi ────────────────────────────
    total_returned = sum(float(r.total_amount or 0) for r in returns)
    pool += total_returned

    # ── 3-bosqich: hovuzni FIFO bilan taqsimlash (eng eski qarzdan) ──────────
    # Boshlang'ich qarz — hujjatlardan ham eski, shuning uchun BIRINCHI yopiladi.
    if pool > _EPS and opening_left > 0:
        applied = min(pool, opening_left)
        opening_left -= applied
        pool -= applied

    for r in debt_receipts:
        if pool <= _EPS:
            break
        applied = min(pool, remaining[r.id])
        remaining[r.id] -= applied
        pool -= applied

    # ── Natija ───────────────────────────────────────────────────────────────
    rows: List[ReceiptDebt] = []
    overdue = 0.0
    for r in debt_receipts:
        net  = float(r.net_amount or 0)
        rem  = remaining[r.id]
        if rem < _EPS:
            rem = 0.0
        due  = (r.receipt_date + timedelta(days=delay)) if r.receipt_date else None
        is_overdue = bool(due and due < today and rem > 0)
        if is_overdue:
            overdue += rem
        rows.append(ReceiptDebt(
            receipt_id=r.id,
            receipt_date=r.receipt_date,
            invoice_number=r.invoice_number,
            net_amount=round(net, 2),
            paid=round(net - rem, 2),
            remaining=round(rem, 2),
            due_date=due,
            is_overdue=is_overdue,
        ))

    total_purchases = sum(float(r.net_amount or 0) for r in debt_receipts)
    total_paid      = sum(float(p.amount or 0) for p in payments)
    # FAZA 3: qoplanmagan boshlang'ich qarz ham jami qarzning bir qismi:
    #   jami_qarz = opening_debt + priyomkalar − to'lovlar − vozvratlar
    _opening_rem    = opening_left if opening_left > _EPS else 0.0
    debt            = _opening_rem + sum(remaining[r.id] for r in debt_receipts if remaining[r.id] > _EPS)
    advance         = pool if pool > _EPS else 0.0
    last_purchase   = max((r.receipt_date for r in debt_receipts if r.receipt_date), default=None)

    return SupplierDebt(
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        phone=supplier.phone,
        opening_debt=round(opening, 2),
        total_purchases=round(total_purchases, 2),
        total_paid=round(total_paid, 2),
        total_returned=round(total_returned, 2),
        balance=round(debt - advance, 2),
        debt=round(debt, 2),
        advance=round(advance, 2),
        overdue_amount=round(overdue, 2),
        last_purchase=last_purchase,
        receipts=rows,
    )


@dataclass
class LedgerEntry:
    """Oborot varag'ining bitta qatori (FAZA 4)."""
    date:    Optional[Date]
    kind:    str              # opening | receipt | payment | return
    label:   str              # "Priyomka #12 · INV-77", "To'lov (umumiy)" ...
    amount:  float            # + qarz OSHDI, − qarz KAMAYDI
    balance: float            # shu qatordan keyingi yugurib boruvchi qoldiq
    ref_id:  Optional[int]    # hujjat id (opening uchun None)


def build_ledger(
    supplier: Supplier,
    receipts: Sequence[PurchaseReceipt],
    payments: Sequence[SupplierPayment],
    returns:  Sequence[SupplierReturn],
) -> List[LedgerEntry]:
    """Bitta firma bo'yicha XRONOLOGIK oborot varag'i.

    Do'konchi agent bilan hisob-kitob qilganda "qara, hammasi shu yerda" deydigan
    ekran. Hisob mantig'i YANGIDAN o'ylab topilmaydi — shu fayldagi qoidalar:
      • qarzga faqat DEBT_STATUSES priyomkalari kiradi (draft KIRMAYDI)
      • boshlang'ich qarz eng birinchi qator (hujjatlardan ham eski)
      • to'lov va vozvrat qarzni kamaytiradi

    KAFOLAT (test bilan qotirilgan): oxirgi qator `balance` =
    `compute_supplier_debt(...).balance` (ya'ni debt − advance). Ikki ekran
    bir xil raqamni ko'rsatadi.

    DIQQAT: bu yerda FIFO taqsimot YO'Q — u nakladnoy darajasidagi "muddati
    o'tgan" hisobi uchun kerak. Oborot varag'i esa sof xronologiya.
    """
    items: List[tuple] = []   # (sana, tartib, kind, label, amount, ref_id)

    opening = float(getattr(supplier, "opening_debt", 0) or 0)
    if opening > _EPS:
        # Sana yo'q — har doim eng tepada (tartib 0, Date.min).
        items.append((Date.min, 0, "opening", "Boshlang'ich qarz", opening, None))

    for r in receipts:
        if r.status not in DEBT_STATUSES:
            continue
        inv = f" · {r.invoice_number}" if r.invoice_number else ""
        items.append((r.receipt_date or Date.min, 1, "receipt",
                      f"Priyomka #{r.id}{inv}", float(r.net_amount or 0), r.id))

    for p in payments:
        label = f"To'lov (Nakladnoy #{p.receipt_id})" if p.receipt_id else "To'lov (umumiy)"
        items.append((p.payment_date or Date.min, 2, "payment",
                      label, -float(p.amount or 0), p.id))

    for r in returns:
        items.append((r.return_date or Date.min, 3, "return",
                      f"Vozvrat #{r.id}", -float(r.total_amount or 0), r.id))

    # Sana bo'yicha, bir kun ichida: priyomka → to'lov → vozvrat (o'qishga qulay)
    items.sort(key=lambda t: (t[0], t[1], t[5] or 0))

    out: List[LedgerEntry] = []
    running = 0.0
    for dt, _ord, kind, label, amount, ref_id in items:
        running += amount
        out.append(LedgerEntry(
            date=None if kind == "opening" else dt,
            kind=kind,
            label=label,
            amount=round(amount, 2),
            balance=round(running, 2),
            ref_id=ref_id,
        ))
    return out


def supplier_ledger(db: Session, supplier: Supplier) -> List[LedgerEntry]:
    """Bitta firma uchun oborot varag'i — 3 ta so'rov."""
    receipts = db.query(PurchaseReceipt).filter(PurchaseReceipt.supplier_id == supplier.id).all()
    payments = db.query(SupplierPayment).filter(SupplierPayment.supplier_id == supplier.id).all()
    returns  = db.query(SupplierReturn).filter(SupplierReturn.supplier_id == supplier.id).all()
    return build_ledger(supplier, receipts, payments, returns)


def compute_debts(
    db: Session,
    suppliers: Sequence[Supplier],
    today: Optional[Date] = None,
) -> Dict[int, SupplierDebt]:
    """Bir nechta firma uchun — hammasi 3 ta so'rovda (N+1 yo'q).

    TENANT: `suppliers` ro'yxati chaqiruvchida ALLAQACHON tenant bo'yicha
    filtrlangan bo'lishi shart. Hujjatlar supplier_id orqali olinadi, supplier esa
    bitta tenantga tegishli — shuning uchun boshqa tenant ma'lumoti kira olmaydi.
    """
    ids = [s.id for s in suppliers]
    if not ids:
        return {}

    receipts = db.query(PurchaseReceipt).filter(PurchaseReceipt.supplier_id.in_(ids)).all()
    payments = db.query(SupplierPayment).filter(SupplierPayment.supplier_id.in_(ids)).all()
    returns  = db.query(SupplierReturn).filter(SupplierReturn.supplier_id.in_(ids)).all()

    by_receipt: Dict[int, List[PurchaseReceipt]] = {i: [] for i in ids}
    by_payment: Dict[int, List[SupplierPayment]] = {i: [] for i in ids}
    by_return:  Dict[int, List[SupplierReturn]]  = {i: [] for i in ids}
    for r in receipts:
        by_receipt[r.supplier_id].append(r)
    for p in payments:
        by_payment[p.supplier_id].append(p)
    for r in returns:
        by_return[r.supplier_id].append(r)

    return {
        s.id: compute_supplier_debt(
            s, by_receipt[s.id], by_payment[s.id], by_return[s.id], today=today
        )
        for s in suppliers
    }


def total_debt(
    db: Session,
    suppliers: Sequence[Supplier],
    today: Optional[Date] = None,
) -> float:
    """Barcha firmalar bo'yicha JAMI qarz (avanslar bilan qoplanmaydi).

    Avans BOSHQA firmaning qarzini yashirmasligi kerak, shuning uchun `debt`
    (manfiysi kesilgan) yig'iladi, `balance` emas.
    """
    return round(sum(d.debt for d in compute_debts(db, suppliers, today=today).values()), 2)

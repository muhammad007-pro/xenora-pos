"""
Bonus karta router — BOSQICH 26
Mijoz xarid qilganda ball to'plash, keyin sarflash.
ball = xarid_summa * earn_rate / 100
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import random, string

from database import get_db
from models import BonusCard, BonusTransaction, Customer, User
from schemas import (
    BonusCardCreate, BonusCardUpdate, BonusCardInDB,
    BonusEarnRequest, BonusSpendRequest, BonusTransactionInDB,
    PaginatedResponse, MessageResponse,
)
from deps import resolve_tenant_id, get_current_active_user, apply_tenant_filter, has_permission

router = APIRouter()


def _gen_card_number(db: Session) -> str:
    while True:
        num = "BC" + "".join(random.choices(string.digits, k=8))
        if not db.query(BonusCard).filter(BonusCard.card_number == num).first():
            return num


def _enrich(c: BonusCard) -> BonusCardInDB:
    d = BonusCardInDB.model_validate(c)
    d.customer_name = c.customer.name if c.customer else None
    return d


@router.get("/", response_model=PaginatedResponse)
async def list_cards(
    is_active:   Optional[bool] = None,
    customer_id: Optional[int]  = None,
    search:      Optional[str]  = None,
    page:        int = Query(1, ge=1),
    page_size:   int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    q = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user)
    if is_active is not None: q = q.filter(BonusCard.is_active == is_active)
    if customer_id:           q = q.filter(BonusCard.customer_id == customer_id)
    if search:                q = q.filter(BonusCard.card_number.ilike(f"%{search}%"))
    total = q.count()
    rows  = q.order_by(BonusCard.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[_enrich(r) for r in rows], total=total,
                             page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)


@router.post("/", response_model=BonusCardInDB)
async def create_card(
    data: BonusCardCreate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    card_num = data.card_number or _gen_card_number(db)
    if db.query(BonusCard).filter(BonusCard.card_number == card_num).first():
        raise HTTPException(status_code=400, detail="Bu karta raqami allaqachon mavjud")
    c = BonusCard(
        tenant_id   = resolve_tenant_id(db, current_user),
        card_number = card_num,
        customer_id = data.customer_id,
        earn_rate   = data.earn_rate,
    )
    db.add(c); db.commit(); db.refresh(c)
    return _enrich(c)


@router.get("/lookup")
async def lookup_card(
    card_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Karta raqami bo'yicha tezkor qidirish (POS uchun)"""
    c = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
            .filter(BonusCard.card_number == card_number).first()
    if not c:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    return _enrich(c)


@router.patch("/{card_id}", response_model=BonusCardInDB)
async def update_card(
    card_id: int,
    data: BonusCardUpdate,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    c = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
            .filter(BonusCard.id == card_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return _enrich(c)


@router.post("/{card_id}/earn", response_model=BonusTransactionInDB)
async def earn_bonus(
    card_id: int,
    data: BonusEarnRequest,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xarid uchun bonus ball to'plash"""
    c = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
            .filter(BonusCard.id == card_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    if not c.is_active:
        raise HTTPException(status_code=400, detail="Karta faol emas")

    bonus = round(data.amount * c.earn_rate / 100, 2)
    c.balance      += bonus
    c.total_earned += bonus

    tx = BonusTransaction(
        tenant_id   = c.tenant_id,
        card_id     = c.id,
        order_id    = data.order_id,
        tx_type     = "earn",
        amount      = bonus,
        description = data.description or f"Xarid: {data.amount:,.0f} so'm → +{bonus:.2f} ball",
        created_by  = current_user.id,
    )
    db.add(tx); db.commit(); db.refresh(tx)
    return BonusTransactionInDB.model_validate(tx)


@router.post("/{card_id}/spend", response_model=BonusTransactionInDB)
async def spend_bonus(
    card_id: int,
    data: BonusSpendRequest,
    db:   Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bonus balini to'lov uchun sarflash"""
    c = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
            .filter(BonusCard.id == card_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    if not c.is_active:
        raise HTTPException(status_code=400, detail="Karta faol emas")
    if c.balance < data.amount:
        raise HTTPException(status_code=400,
                            detail=f"Yetarli ball yo'q. Balans: {c.balance:.2f}")

    c.balance     -= data.amount
    c.total_spent += data.amount

    tx = BonusTransaction(
        tenant_id   = c.tenant_id,
        card_id     = c.id,
        order_id    = data.order_id,
        tx_type     = "spend",
        amount      = -data.amount,
        description = data.description or f"Ball sarflash: -{data.amount:.2f}",
        created_by  = current_user.id,
    )
    db.add(tx); db.commit(); db.refresh(tx)
    return BonusTransactionInDB.model_validate(tx)


@router.post("/{card_id}/adjust", response_model=BonusTransactionInDB)
async def manual_adjust(
    card_id: int,
    amount:  float,
    reason:  Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Qo'lda ball to'g'irlash (admin uchun)"""
    c = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
            .filter(BonusCard.id == card_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    if c.balance + amount < 0:
        raise HTTPException(status_code=400, detail="Balans manfiy bo'lib qolmaydi")
    c.balance += amount
    if amount > 0: c.total_earned += amount
    else:          c.total_spent  += abs(amount)
    tx = BonusTransaction(
        tenant_id   = c.tenant_id,
        card_id     = c.id,
        tx_type     = "manual",
        amount      = amount,
        description = reason or "Admin to'g'irlash",
        created_by  = current_user.id,
    )
    db.add(tx); db.commit(); db.refresh(tx)
    return BonusTransactionInDB.model_validate(tx)


@router.get("/{card_id}/transactions", response_model=PaginatedResponse)
async def get_transactions(
    card_id:  int,
    page:     int = Query(1, ge=1),
    page_size:int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(has_permission("view_reports")),
):
    card = apply_tenant_filter(db.query(BonusCard), BonusCard, current_user) \
               .filter(BonusCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Karta topilmadi")
    q = db.query(BonusTransaction).filter(BonusTransaction.card_id == card_id)
    total = q.count()
    rows  = q.order_by(BonusTransaction.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return PaginatedResponse(items=[BonusTransactionInDB.model_validate(r) for r in rows],
                             total=total, page=page, page_size=page_size,
                             total_pages=(total+page_size-1)//page_size)

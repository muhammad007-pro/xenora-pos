from sqlalchemy.orm import Session
from sqlalchemy import func  # ← qo'shildi
from datetime import datetime
from typing import Optional, Dict, Any

from models import Payment, Order
from config import settings

class PaymentService:
    def __init__(self, db: Session):
        self.db = db
    
    def process_payment(
        self,
        order: Order,
        amount: float,
        method: str,
        cashier_id: int,
        reference: Optional[str] = None,
        commit: bool = True,
    ) -> Payment:
        """To'lovni qayta ishlash.

        commit=False → faqat flush (ID hosil bo'ladi), COMMIT chaqiruvchida bo'ladi.
        Bu — atomik sotuv uchun: to'lov + order + ombor bitta tranzaksiyada commit qilinadi
        (create_payment), xato bo'lsa BUTUN sotuv rollback (yarim holat qolmaydi).
        """
        # Click/Payme integratsiyasi
        if method in ["click", "payme"]:
            return self._process_online_payment(order, amount, method, cashier_id, commit=commit)

        # Naqd yoki karta
        payment = Payment(
            order_id=order.id,
            cashier_id=cashier_id,
            amount=amount,
            method=method,
            status="paid",
            reference=reference,
            transaction_id=self._generate_transaction_id()
        )

        self.db.add(payment)
        if commit:
            self.db.commit()
            self.db.refresh(payment)
        else:
            self.db.flush()   # ID hosil bo'ladi; commit — chaqiruvchida (atomik sotuv)

        return payment

    def _process_online_payment(self, order: Order, amount: float, method: str, cashier_id: int, commit: bool = True) -> Payment:
        """Online to'lovni qayta ishlash"""
        # TODO: Click/Payme API integratsiyasi
        payment = Payment(
            order_id=order.id,
            cashier_id=cashier_id,
            amount=amount,
            method=method,
            status="pending",
            transaction_id=self._generate_transaction_id()
        )

        self.db.add(payment)
        if commit:
            self.db.commit()
            self.db.refresh(payment)
        else:
            self.db.flush()

        return payment
    
    def _generate_transaction_id(self) -> str:
        """Tranzaksiya ID yaratish"""
        import uuid
        return f"TRX{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
    
    def confirm_payment(self, payment_id: int, external_transaction_id: str) -> Optional[Payment]:
        """To'lovni tasdiqlash"""
        payment = self.db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return None
        
        payment.status = "paid"
        payment.reference = external_transaction_id
        self.db.commit()
        self.db.refresh(payment)
        
        return payment
    
    def refund_payment(self, payment: Payment, amount: float, reason: Optional[str] = None, commit: bool = True) -> bool:
        """To'lovni qaytarish.

        commit=False → flush (COMMIT chaqiruvchida) — refund + order + ombor tiklash
        bitta tranzaksiyada atomik bo'lsin. Bu holatда xato YUQORIGA uzatiladi (raise),
        chaqiruvchi butun tranzaksiyani rollback qiladi (yarim qaytarish qolmaydi).
        """
        try:
            if payment.method in ["click", "payme"]:
                # TODO: Online to'lovni qaytarish API
                pass

            # Qaytarish yozuvi
            refund = Payment(
                order_id=payment.order_id,
                cashier_id=payment.cashier_id,
                amount=-amount,
                method=payment.method,
                status="refunded",
                reference=f"Refund for {payment.transaction_id}: {reason}" if reason else f"Refund for {payment.transaction_id}"
            )

            self.db.add(refund)

            # Asl to'lov holatini yangilash
            if amount >= payment.amount:
                payment.status = "refunded"

            if commit:
                self.db.commit()
            else:
                self.db.flush()

            return True

        except Exception as e:
            print(f"Refund error: {e}")
            if commit:
                self.db.rollback()
                return False
            raise   # commit=False: chaqiruvchining tranzaksiya-handleri rollback qiladi
    
    def get_order_payments(self, order_id: int) -> list:
        """Buyurtma to'lovlarini olish"""
        return self.db.query(Payment).filter(Payment.order_id == order_id).all()
    
    def get_total_paid(self, order_id: int) -> float:
        """Jami to'langan summa"""
        result = self.db.query(Payment).filter(
            Payment.order_id == order_id,
            Payment.status == "paid"
        ).with_entities(func.sum(Payment.amount)).scalar()  # ← func shu yerda ishlatilgan
        
        return float(result or 0)
    
    def is_order_fully_paid(self, order: Order) -> bool:
        """Buyurtma to'liq to'langanligini tekshirish"""
        total_paid = self.get_total_paid(order.id)
        return total_paid >= order.final_amount
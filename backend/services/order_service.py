from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, time
from typing import Optional, List

from models import Order, OrderItem, Product, Table, User, Shift, Discount, order_discounts, Promotion
from schemas import OrderCreate, OrderUpdate

class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def generate_order_number(self) -> str:
        """Buyurtma raqami — ICHKI unikal id (YYMMDD + 4 tasodifiy raqam).
        To'qnashuvni oldini olish uchun bazada band emasligini tekshiradi (retry).
        Bu ko'rinadigan raqam emas — ko'rinadigan raqam `daily_number`."""
        import random

        now = datetime.now()
        prefix = f"{str(now.year)[-2:]}{now.month:02d}{now.day:02d}"
        for _ in range(20):
            candidate = f"{prefix}{random.randint(1000, 9999)}"
            if not self.db.query(Order.id).filter(Order.order_number == candidate).first():
                return candidate
        # Zaxira: millisekund asosida (deyarli to'qnashmas)
        return f"{prefix}{int(now.timestamp() * 1000) % 10000:04d}"

    def _next_daily_number(self, tenant_id: Optional[int]) -> int:
        """Kunlik chek raqami — shu TENANT + shu KUN bo'yicha eng katta daily_number + 1.
        Kun boshida 1 dan boshlanadi. Tenant izolyatsiya: har tenant alohida sanaydi.

        "Kun" — timezone('Asia/Tashkent', created_at)::date ifodasi bilan aniqlanadi
        (unique indeks uq_orders_tenant_day_daily bilan AYNAN bir xil). Shu sabab max+1 va
        unique constraint bir xil kun-guruhini ko'radi → konkurensiyada IntegrityError →
        create_order retry qiladi."""
        from sqlalchemy import cast, Date
        day_expr   = cast(func.timezone('Asia/Tashkent', Order.created_at), Date)
        today_expr = cast(func.timezone('Asia/Tashkent', func.now()), Date)
        q = self.db.query(func.max(Order.daily_number)).filter(day_expr == today_expr)
        if tenant_id is not None:
            q = q.filter(Order.tenant_id == tenant_id)
        else:
            q = q.filter(Order.tenant_id.is_(None))
        return (q.scalar() or 0) + 1

    def _product_cost(self, product: Product) -> float:
        """Sotuv paytidagi tan narx snapshoti (retseptli bo'lsa — retseptdan)"""
        from services.cost_service import get_product_cost
        return get_product_cost(self.db, product.id)

    # ── #34 1-bosqich: AVTOMATIK chegirma (server-authoritative) ─────────────────
    def _disc_amount(self, d: Discount, base: float) -> float:
        """Bitta chegirma summasi. Foiz → base×%; belgilangan → value (base'dan oshmaydi)."""
        if base <= 0:
            return 0.0
        if d.type == "percentage":
            return base * (d.value or 0) / 100.0
        return min(d.value or 0, base)   # fixed — narxni 0 dan pastga tushirmaydi

    def _compute_auto_discount(self, tenant_id, items_data, subtotal):
        """Faol chegirmalarni SERVER tomonda qo'llab, umumiy chegirma + qo'llangan
        id'larni qaytaradi. Ustuvorlik: mahsulot > kategoriya > butun savat; bir
        mahsulotga bitta (eng aniq qamrov) chegirma; bir xil qamrovda eng foydalisi.
        Butun savat chegirmasi item-chegirmalardan keyingi summaga (min_order_amount).
        Client yuborgan chegirmaga ISHONILMAYDI — shu hisob asosiy.
        """
        # FAZA 1+2: DB fetch (Discount filtri O'ZGARMAGAN + Promotion) + cat xaritasi, keyin PURE resolver.
        now = datetime.now()
        active = self.db.query(Discount).filter(
            Discount.tenant_id == tenant_id,
            Discount.is_active == True,   # noqa: E712
            (Discount.valid_from.is_(None) | (Discount.valid_from <= now)),
            (Discount.valid_to.is_(None) | (Discount.valid_to >= now)),
            (Discount.usage_limit.is_(None) | (Discount.used_count < Discount.usage_limit)),
        ).all()
        promos = self._fetch_active_promotions(tenant_id, now)
        if not active and not promos:
            return 0.0, [], []
        # product → category xaritasi
        pids = [it["product_id"] for it in items_data]
        cat_of = {}
        if pids:
            for pid, cid in self.db.query(Product.id, Product.category_id).filter(Product.id.in_(pids)).all():
                cat_of[pid] = cid
        return self._resolve_pricing(active, promos, items_data, subtotal, cat_of)

    def _fetch_active_promotions(self, tenant_id, now):
        """FAZA 2 Promotion turlari: flash_price, min_amount, min_qty_discount (buy_x_get_y — Faza 3).
        Vaqt/kun/usage filtri promotions.py `_is_valid` bilan AYNAN bir xil (happy-hour)."""
        promos = self.db.query(Promotion).filter(
            Promotion.tenant_id == tenant_id,
            Promotion.is_active == True,   # noqa: E712
            Promotion.promo_type.in_(("flash_price", "min_amount", "min_qty_discount", "buy_x_get_y")),
            (Promotion.usage_limit.is_(None) | (Promotion.used_count < Promotion.usage_limit)),
        ).all()
        out = []
        for p in promos:
            if p.start_date and now < p.start_date:
                continue
            if p.end_date and now > p.end_date:
                continue
            if p.time_from and p.time_to:
                cur = now.strftime("%H:%M")
                if not (p.time_from <= cur <= p.time_to):
                    continue
            if p.days_of_week and str(now.isoweekday()) not in p.days_of_week.split(","):
                continue
            out.append(p)
        return out

    def _promo_line_disc(self, p, line, qty):
        """Promotion foiz/fiks (promotions.py /validate bilan bir xil): pct → line×%; fixed → value×qty."""
        if p.discount_type == "percentage":
            return line * (p.discount_value or 0) / 100.0
        return (p.discount_value or 0) * qty

    def _best_item_promo(self, promotions, pid, qty, unit_price, line, total_amount):
        """Shu item uchun ENG foydali Promotion offeri (capped, /validate scoping). Qaytadi (promo, benefit)."""
        best, best_amt = None, 0.0
        for p in promotions:
            if p.product_id and p.product_id != pid:
                continue
            amt = 0.0
            if p.promo_type == "flash_price" and p.flash_price is not None:
                if unit_price > p.flash_price:
                    amt = (unit_price - p.flash_price) * qty
            elif p.promo_type == "min_qty_discount":
                if qty >= (p.min_purchase_qty or 0):
                    amt = self._promo_line_disc(p, line, qty)
            elif p.promo_type == "min_amount":
                if total_amount >= (p.min_purchase_amount or 0):
                    amt = self._promo_line_disc(p, line, qty)
            elif p.promo_type == "buy_x_get_y" and getattr(p, "free_product_id", None) is None:
                # FAZA 3a: BIR XIL mahsulot (free_product_id NULL) — har (buy+get) to'plamда
                # get_qty dona bepul. Benefit = bepul_qty × birlik narx → final kamayadi; ORDER
                # QTY o'zgarmaydi → ombor to'g'ri ayiradi. 3b (free_product_id bор) — INJEKSIYA
                # (create_order Y ni alohida OrderItem qiladi), bu yerда HISOBLANMAYDI.
                unit = (p.buy_qty or 0) + (p.get_qty or 0)
                if unit > 0:
                    free = (qty // unit) * (p.get_qty or 0)
                    amt = free * unit_price
            amt = min(amt, line)
            if amt > best_amt:
                best, best_amt = p, amt
        return best, best_amt

    def _compute_gift_items(self, gift_promos, cart_qty_map, stock_map):
        """FAZA 3b PURE (server-authoritative) — qaysi bepul Y qo'shilishini hisoblaydi.
        gift_promos: buy_x_get_y + free_product_id bор (kassir TASDIQLAGAN). cart_qty_map: {pid: qty}
        (to'langan X). stock_map: {pid: mavjud_ombor}. Qaytadi: [{product_id, quantity, promo_id, name}].
        SHART: X yetarli (qty >= buy_qty) VA Y ombor yetarli — aks holda SKIP (aksiya qo'llanmaydi).
        Ko'p to'plam: sets = x_qty // buy_qty (4 X, buy=2 → 2 to'plam). Client soxta yubora olmaydi —
        server X'ni HAQIQIY savatdan, Y ombor'ni DB'dan tekshiradi."""
        gifts = []
        for p in gift_promos:
            yid = getattr(p, "free_product_id", None)
            if not yid:
                continue
            buy = p.buy_qty or 0
            x_qty = cart_qty_map.get(p.product_id, 0)
            if buy <= 0 or x_qty < buy:
                continue
            free_qty = (x_qty // buy) * (p.free_qty_per_set or 1)
            if free_qty <= 0:
                continue
            if stock_map.get(yid, 0) < free_qty:
                continue   # Y ombor yetmaydi → aksiya qo'llanmaydi (kassir ogohlantirilgan)
            gifts.append({"product_id": yid, "quantity": free_qty, "promo_id": p.id, "name": p.name})
        return gifts

    def _gift_stock_map(self, y_ids, tenant_id):
        """Bepul Y uchun MAVJUD ombor (dona). To'g'ridan mahsulot → Inventory.quantity[Y].
        Retseptli → ingredientlardan nechа Y tayyorlanadi (min; yield_pct hisobga olinadi —
        deduct_recipe_ingredients bilan bir xil raw_qty mantiqi)."""
        from models import Recipe, Inventory

        def _inv(pid):
            q = self.db.query(Inventory).filter(Inventory.product_id == pid)
            if tenant_id is not None:
                q = q.filter(Inventory.tenant_id == tenant_id)
            inv = q.first()
            return inv.quantity if inv else 0.0

        stock = {}
        for yid in set(y_ids):
            recipe = self.db.query(Recipe).filter(Recipe.product_id == yid).first()
            if not recipe:
                stock[yid] = _inv(yid)   # to'g'ridan mahsulot (magazin/dorixona/chakana)
                continue
            makeable = None                # retseptli: ingredientlardan nechа Y
            for item in recipe.items:
                per1 = item.quantity or 0
                yld = getattr(getattr(item, "ingredient", None), "yield_pct", None)
                raw1 = per1 / (yld / 100.0) if (yld and 0 < yld < 100) else per1
                m = int(_inv(item.ingredient_id) // raw1) if raw1 > 0 else 0
                makeable = m if makeable is None else min(makeable, m)
            stock[yid] = makeable or 0
        return stock

    def _resolve_pricing(self, active_discounts, promotions, items_data, subtotal, cat_of):
        """PURE narx-yechish — item: Discount (product>category) VA Promotion (flash/min_qty/min_amount)
        orasidan ENG YAXSHI BITTASI (best-only, STACKING YO'Q). Cart: Discount (min_order_amount) best-only.
        Promotion YO'Q bo'lsa → #34 bilan AYNAN bir xil (byte-identical). Qaytadi:
        (total_discount, applied_discount_ids, applied_promotion_ids)."""
        prod_disc, cat_disc, cart_disc = {}, {}, []
        for d in active_discounts:
            if d.product_id:
                prod_disc.setdefault(d.product_id, []).append(d)
            elif d.category_id:
                cat_disc.setdefault(d.category_id, []).append(d)
            else:
                cart_disc.append(d)
        applied_disc, applied_promo = {}, {}
        item_total = 0.0
        for it in items_data:
            pid, line = it["product_id"], it["total_price"]
            qty = it.get("quantity", 1)
            unit_price = it.get("unit_price", line)
            # #34 Discount eng yaxshisi (MAVJUD MANTIQ — o'zgarmagan)
            cands = prod_disc.get(pid) or cat_disc.get(cat_of.get(pid)) or []
            disc_best, disc_amt = None, 0.0
            if cands:
                disc_best = max(cands, key=lambda d: self._disc_amount(d, line))
                disc_amt = min(self._disc_amount(disc_best, line), line)
            # Promotion eng yaxshisi (FAZA 2)
            promo_best, promo_amt = self._best_item_promo(promotions, pid, qty, unit_price, line, subtotal)
            # BEST-ONLY: kattaroq benefit; TENG bo'lsa Discount ustun (byte-identical #34 kafolati)
            if promo_amt > disc_amt:
                if promo_amt > 0:
                    item_total += promo_amt
                    applied_promo[promo_best.id] = promo_best
            elif disc_amt > 0:
                item_total += disc_amt
                applied_disc[disc_best.id] = disc_best
        sub_after = subtotal - item_total
        cart_total = 0.0
        if cart_disc and sub_after > 0:
            eligible = [d for d in cart_disc if (d.min_order_amount or 0) <= sub_after]
            if eligible:
                best = max(eligible, key=lambda d: self._disc_amount(d, sub_after))
                amt = min(self._disc_amount(best, sub_after), sub_after)
                if amt > 0:
                    cart_total += amt
                    applied_disc[best.id] = best
        return round(item_total + cart_total, 2), list(applied_disc.keys()), list(applied_promo.keys())

    def create_order(self, order_data: OrderCreate, waiter_id: int, tenant_id: Optional[int] = None) -> Order:
        """Yangi buyurtma yaratish.

        tenant_id — buyurtma egasi tenant (kunlik chek raqami SHU tenant bo'yicha sanaladi).
        order_number ichki unikal id; daily_number — ko'rinadigan kunlik raqam.
        order_number to'qnashuvida (unique constraint) qayta urinadi.
        """
        # Elementlar va summani hisoblash (DB yozuvisiz — retry'da qayta ishlatiladi).
        # product ORM emas, product_id (rollback'dan keyin expiry muammosi bo'lmasin).
        total_amount = 0
        items_data = []
        for item in order_data.items:
            product = self.db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise ValueError(f"Mahsulot topilmadi: {item.product_id}")
            if not product.is_available:
                raise ValueError(f"Mahsulot mavjud emas: {product.name}")

            # BOSQICH B3 (pachka/dona): narx + ombor miqdori SERVERDA hisoblanadi
            # (client narxiga ishonilmaydi). unit_sold — client faqat SHUNI yuboradi.
            unit_sold = getattr(item, "unit_sold", None)
            pack_enabled = bool(
                product.pack_size and product.pack_size >= 2
                and product.pack_price and product.pack_price > 0
            )
            dona_cost = self._product_cost(product)
            if unit_sold == "pachka" and pack_enabled:
                # Pachka sotuvi: pack_price × soni; ombordan pack_size×soni DONA kamayadi.
                # unit_cost ham pachka bo'yicha (dona_cost × pack_size) — COGS to'g'ri.
                # Wholesale (optom) qo'llanmaydi — pachka o'zi ulgurji (backend'da
                # wholesale mantig'i yo'q, shu bois qo'shimcha bloklash shart emas).
                unit_price = product.pack_price
                unit_cost  = dona_cost * product.pack_size
                base_qty   = product.pack_size * item.quantity
                item_unit_sold = "pachka"
            else:
                # Dona yoki oddiy: mavjud mantiq. Client "pachka" desa-yu mahsulot
                # pachkasiz bo'lsa — oddiy dona sifatida (xavfsiz fallback, xato emas).
                unit_price = product.price
                unit_cost  = dona_cost
                base_qty   = item.quantity
                item_unit_sold = "dona" if unit_sold == "dona" else None

            total_price = unit_price * item.quantity
            total_amount += total_price
            items_data.append({
                "product_id": product.id,
                "quantity": item.quantity,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "total_price": total_price,
                "base_qty": base_qty,
                "unit_sold": item_unit_sold,
                "notes": item.notes,
            })

        # SERVER subtotal (item totallaridan) — CHEGIRMA shundan hisoblanadi (xavfsizlik).
        server_subtotal = total_amount
        # Ko'rinadigan total_amount: agar frontend yuborsa (POS/delivery), shuni ishlatamiz
        if order_data.total_amount is not None:
            total_amount = order_data.total_amount

        # #34: AVTOMATIK chegirma — SERVER tomonda qayta hisoblanadi (client'ga ishonilmaydi).
        auto_disc, applied_discount_ids, applied_promotion_ids = self._compute_auto_discount(tenant_id, items_data, server_subtotal)

        # FAZA 3b: kassir TASDIQLAGAN "boshqa mahsulot bepul" aksiyalari → bepul Y OrderItem injeksiya.
        # GATED: accepted_gift_promotions BO'SH → bu blok umuman ishlamaydi (mavjud sotuv AYNAN hozirgidek).
        # SERVER-AUTHORITATIVE: X qty HAQIQIY savatdan, Y ombor DB'dan, promo haqiqiy — client'ga ishonilmaydi.
        accepted_gifts = getattr(order_data, "accepted_gift_promotions", None) or []
        if accepted_gifts:
            gift_promos = self.db.query(Promotion).filter(
                Promotion.id.in_(accepted_gifts),
                Promotion.tenant_id == tenant_id,
                Promotion.is_active == True,   # noqa: E712
                Promotion.promo_type == "buy_x_get_y",
                Promotion.free_product_id.isnot(None),
            ).all()
            if gift_promos:
                cart_qty_map = {}
                for it in items_data:
                    cart_qty_map[it["product_id"]] = cart_qty_map.get(it["product_id"], 0) + it["quantity"]
                stock_map = self._gift_stock_map([p.free_product_id for p in gift_promos], tenant_id)
                for g in self._compute_gift_items(gift_promos, cart_qty_map, stock_map):
                    yprod = self.db.query(Product).filter(Product.id == g["product_id"]).first()
                    if not yprod:
                        continue
                    # Y — narx=0 OrderItem. Ombor ayirish/refund/chek/loyalty MAVJUD atomik yo'llar orqali.
                    items_data.append({
                        "product_id":  g["product_id"],
                        "quantity":    g["quantity"],
                        "unit_price":  0.0,
                        "unit_cost":   self._product_cost(yprod),
                        "total_price": 0.0,
                        "base_qty":    g["quantity"],   # ombordan ayiriladigan dona
                        "unit_sold":   None,
                        "notes":       f"Aksiya (bepul): {g['name']}",
                    })
                    applied_promotion_ids.append(g["promo_id"])   # used_count + biz_meta izи
        # Qo'lda/mijoz % chegirma — discount_type/value dan QAYTA hisoblanadi (client'ning
        # tayyor discount_amount summasiga ISHONILMAYDI): foiz 0–100, fixed subtotaldan oshmaydi.
        dv = order_data.discount_value or 0
        if dv > 0:
            manual_disc = (server_subtotal * min(dv, 100) / 100.0
                           if order_data.discount_type == "pct" else min(dv, server_subtotal))
        else:
            manual_disc = 0
        tax_amount  = order_data.tax_amount or 0
        service_amt = getattr(order_data, "service_amount", 0) or 0
        total_disc  = min(round(manual_disc + auto_disc, 2), server_subtotal)   # subtotaldan oshmaydi
        final = round(server_subtotal - total_disc + tax_amount + service_amt, 2)

        # Biznes-turi xususiy meta (pharmacy rx, auto_service car, school student, dry_cleaning)
        biz_meta = {}
        # FAZA 2: qo'llangan aksiya izi (migratsiyasiz — biz_meta JSON). used_count pastda oshadi.
        if applied_promotion_ids:
            biz_meta['applied_promotions'] = applied_promotion_ids
        if getattr(order_data, 'rx_patient_name', None):
            biz_meta['rx_patient_name']  = order_data.rx_patient_name
            biz_meta['rx_patient_phone'] = order_data.rx_patient_phone
            biz_meta['rx_number']        = order_data.rx_number
        if getattr(order_data, 'car_plate', None):
            biz_meta['car_plate'] = order_data.car_plate
            biz_meta['car_make']  = order_data.car_make
            biz_meta['car_model'] = order_data.car_model
            biz_meta['car_year']  = order_data.car_year
        if getattr(order_data, 'student_name', None):
            biz_meta['student_name']  = order_data.student_name
            biz_meta['student_phone'] = order_data.student_phone
            biz_meta['student_group'] = order_data.student_group
        if getattr(order_data, 'cleaning_items', None):
            biz_meta['cleaning_items'] = order_data.cleaning_items
            biz_meta['cleaning_notes'] = order_data.cleaning_notes
        # C1: POS savatcha snapshot — held qayta ochilganda modifikator/og'irlik tiklanadi.
        if getattr(order_data, 'cart_snapshot', None):
            biz_meta['cart'] = order_data.cart_snapshot

        # Z-hisobot: buyurtmani kassirning joriy ochiq smenasiga bog'lash.
        active_shift = self.db.query(Shift).filter(
            Shift.user_id == waiter_id,
            Shift.end_time.is_(None),
        ).first()
        shift_id = active_shift.id if active_shift else None

        # Yaratish — order_number unique to'qnashuvida qayta urinadi (retry)
        for _ in range(5):
            order = Order(
                order_number=self.generate_order_number(),
                daily_number=self._next_daily_number(tenant_id),
                tenant_id=tenant_id,
                table_id=order_data.table_id,
                waiter_id=waiter_id,
                shift_id=shift_id,
                customer_id=order_data.customer_id,
                total_amount=total_amount,
                discount_amount=total_disc,        # #34: qo'lda + AVTOMATIK (server)
                tax_amount=tax_amount,
                service_charge=service_amt,
                final_amount=final,
                notes=order_data.notes,
                order_type=order_data.order_type or "dine-in",
                source=order_data.source or "pos",
                delivery_address=order_data.delivery_address,
                delivery_phone=order_data.delivery_phone,
                delivery_note=getattr(order_data, 'delivery_note', None),
                biz_meta=biz_meta or None,
                status="pending",
            )
            self.db.add(order)
            try:
                self.db.flush()  # ID olish + order_number unique tekshiruvi
            except IntegrityError:
                self.db.rollback()
                continue

            for item_data in items_data:
                self.db.add(OrderItem(
                    order_id=order.id,
                    product_id=item_data["product_id"],
                    quantity=item_data["quantity"],
                    unit_price=item_data["unit_price"],
                    unit_cost=item_data["unit_cost"],
                    total_price=item_data["total_price"],
                    base_qty=item_data["base_qty"],       # BOSQICH B3: ombor chiqimi (dona)
                    unit_sold=item_data["unit_sold"],     # BOSQICH B3: "pachka"|"dona"|None
                    notes=item_data["notes"],
                ))
            # #34: qo'llangan avtomatik chegirmalar — order_discounts M2M + used_count
            if applied_discount_ids:
                applied = self.db.query(Discount).filter(Discount.id.in_(applied_discount_ids)).all()
                order.applied_discounts = applied
                for d in applied:
                    d.used_count = (d.used_count or 0) + 1
            # FAZA 2: qo'llangan aksiya used_count (Discount kabi; order-link biz_meta'da).
            # Eslatma: refundда used_count teskarisi Discount'da ham YO'Q → parity uchun bu ham yo'q.
            if applied_promotion_ids:
                for p in self.db.query(Promotion).filter(Promotion.id.in_(applied_promotion_ids)).all():
                    p.used_count = (p.used_count or 0) + 1
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                continue
            self.db.refresh(order)
            return order

        raise ValueError("Buyurtma raqami yaratilmadi (unique to'qnashuv)")
    
    def update_order(self, order_id: int, order_data: OrderUpdate) -> Optional[Order]:
        """Buyurtmani yangilash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        update_data = order_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(order, field, value)
        
        if "status" in update_data and update_data["status"] == "completed":
            order.completed_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def add_item(self, order_id: int, product_id: int, quantity: int, notes: Optional[str] = None) -> Optional[Order]:
        """Buyurtmaga mahsulot qo'shish"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return None
        
        # Mavjud elementni tekshirish
        existing_item = self.db.query(OrderItem).filter(
            OrderItem.order_id == order_id,
            OrderItem.product_id == product_id
        ).first()
        
        if existing_item:
            existing_item.quantity += quantity
            existing_item.total_price = existing_item.unit_price * existing_item.quantity
        else:
            order_item = OrderItem(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.price,
                unit_cost=self._product_cost(product),
                total_price=product.price * quantity,
                notes=notes
            )
            self.db.add(order_item)
        
        # Jami summani yangilash
        self._update_order_total(order)
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def remove_item(self, order_id: int, item_id: int) -> bool:
        """Buyurtmadan mahsulotni o'chirish"""
        item = self.db.query(OrderItem).filter(
            OrderItem.id == item_id,
            OrderItem.order_id == order_id
        ).first()
        
        if not item:
            return False
        
        self.db.delete(item)
        
        # Jami summani yangilash
        order = self.db.query(Order).filter(Order.id == order_id).first()
        self._update_order_total(order)
        
        self.db.commit()
        
        return True
    
    def _update_order_total(self, order: Order):
        """Buyurtma jami summasini yangilash"""
        items = self.db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        total = sum(item.total_price for item in items)
        order.total_amount = total
        order.final_amount = total - (order.discount_amount or 0)
    
    def cancel_order(self, order_id: int, reason: Optional[str] = None) -> Optional[Order]:
        """Buyurtmani bekor qilish"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        order.status = "cancelled"
        if reason:
            order.notes = f"{order.notes or ''}\nBekor qilish sababi: {reason}".strip()
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
    
    def get_orders(self, page: int, page_size: int, current_user: Optional[User] = None, **filters):
        """Buyurtmalarni filtrlash"""
        # N+1 oldini olish: har buyurtma uchun items/payments/waiter/shift ni alohida
        # so'rov qilmasdan oldindan yuklaymiz (_enrich_order va OrderInDB shularni o'qiydi).
        # items/payments — kolleksiya → selectinload (bitta qo'shimcha IN so'rov, dekart
        # ko'paytmasi bo'lmaydi); waiter/shift.register — bir-bir → joinedload.
        query = self.db.query(Order).options(
            selectinload(Order.items),
            selectinload(Order.payments),
            joinedload(Order.waiter),
            joinedload(Order.shift).joinedload(Shift.register),
        )

        # BOSQICH 1.5: tenant bo'yicha cheklash
        if current_user is not None:
            from deps import apply_tenant_filter
            query = apply_tenant_filter(query, Order, current_user)

        if filters.get("status"):
            statuses = [s.strip() for s in str(filters["status"]).split(",")]
            query = query.filter(Order.status.in_(statuses))

        # Kassir (waiter) bo'yicha — qaysi kassir sotgan
        if filters.get("cashier_id"):
            query = query.filter(Order.waiter_id == filters["cashier_id"])

        # Kassa bo'yicha — Order.shift_id -> Shift.register_id JOIN orqali
        if filters.get("register_id"):
            query = query.join(Shift, Order.shift_id == Shift.id).filter(
                Shift.register_id == filters["register_id"]
            )

        if filters.get("table_id"):
            query = query.filter(Order.table_id == filters["table_id"])

        if filters.get("order_type"):
            query = query.filter(Order.order_type == filters["order_type"])

        if filters.get("date_from"):
            query = query.filter(Order.created_at >= filters["date_from"])

        if filters.get("date_to"):
            query = query.filter(Order.created_at <= filters["date_to"])

        if filters.get("has_rx") is True:
            query = query.filter(Order.biz_meta.isnot(None))

        if filters.get("has_student") is True:
            query = query.filter(Order.biz_meta.op('->>')('student_name').isnot(None))

        if filters.get("student_group"):
            query = query.filter(
                Order.biz_meta.op('->>')('student_group') == filters["student_group"]
            )

        if filters.get("has_cleaning") is True:
            query = query.filter(Order.biz_meta.op('->>')('cleaning_items').isnot(None))

        if filters.get("search"):
            from sqlalchemy import cast, String
            s = f"%{filters['search']}%"
            query = query.filter(
                Order.order_number.ilike(s) |
                cast(Order.biz_meta, String).ilike(s)
            )

        total = query.count()
        orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return orders, total
    
    def apply_discount(self, order_id: int, discount_amount: float) -> Optional[Order]:
        """Buyurtmaga chegirma qo'llash"""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return None
        
        if discount_amount > order.total_amount:
            discount_amount = order.total_amount
        
        order.discount_amount = discount_amount
        order.final_amount = order.total_amount - discount_amount
        
        self.db.commit()
        self.db.refresh(order)
        
        return order
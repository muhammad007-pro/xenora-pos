"""Rol/tenant biriktirish himoyasi — imtiyoz oshirishning oldini oladi.

XAVFSIZLIK KONTEKSTI (2026-08-27 auditi):
    `POST /auth/register` autentifikatsiyasiz ochiq edi va tanadan `tenant_id`
    hamda `role_id` ni qabul qilardi. Ya'ni istalgan odam istalgan do'konga
    admin bo'lib qo'shila olardi. Bu modul o'sha teshikni yopadigan YAGONA
    tekshiruv joyi — `/auth/register` ham, `POST /users/` ham shu yerdan
    foydalanadi (ikki xil mantiq bo'lib ketmasligi uchun).

Uchta qoida:
  1. tenant_id HECH QACHON so'rov tanasidan olinmaydi (super-admin bundan mustasno,
     lekin unda ham kafe mavjudligi + faolligi tekshiriladi) — `resolve_target_tenant`.
  2. Yaratuvchi o'zida YO'Q ruxsatga ega rolni bera olmaydi — `assert_can_assign_role`.
  3. Filial faqat o'sha tenantniki bo'lishi mumkin — `assert_branch_in_tenant`.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import User, Role, Cafe, Branch


def resolve_target_tenant(
    db: Session,
    current_user: User,
    body_tenant_id: Optional[int] = None,
) -> int:
    """Yangi foydalanuvchi qaysi tenant'ga biriktirilishini SERVER aniqlaydi.

    - Oddiy foydalanuvchi (kafe admini): har doim O'Z tenant'i. `body_tenant_id`
      butunlay E'TIBORSIZ qoldiriladi — bu teshikning ildizi edi.
    - Super-admin / platforma egasi (tenant_id=NULL): `body_tenant_id` MAJBURIY
      va u faol kafe bo'lishi shart (owner paneli shu yo'ldan yuradi).
    """
    if current_user.is_superuser or current_user.tenant_id is None:
        if not body_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Super-admin foydalanuvchi yaratishda tenant_id (kafe) majburiy",
            )
        cafe = db.query(Cafe).filter(
            Cafe.id == body_tenant_id,
            Cafe.is_active == True,   # noqa: E712 — SQLAlchemy solishtirishi
        ).first()
        if not cafe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bunday faol kafe yo'q",
            )
        return cafe.id

    # Kafe admini — tanadagi tenant_id nima bo'lishidan qat'i nazar, o'z tenant'i.
    return current_user.tenant_id


def _permission_codes(user: User) -> set[str]:
    if not user.role:
        return set()
    return {p.code for p in user.role.permissions}


def assert_can_assign_role(db: Session, current_user: User, role_id: Optional[int]) -> None:
    """Yaratuvchi o'zidan KUCHLIROQ rol bera olmasligini kafolatlaydi.

    Qoida: beriladigan rolning ruxsatlari yaratuvchining ruxsatlari ICHIDA
    bo'lishi shart (kichik to'plam). Masalan `menejer` (8 ruxsat) `admin`
    (barcha ruxsat) rolini bera olmaydi.

    Super-admin — cheklovsiz (platforma egasi).
    role_id berilmasa — tekshirishga narsa yo'q (rolsiz xodim).

    ESLATMA: `Role` jadvali GLOBAL (tenant_id yo'q) — shuning uchun bu yerda
    tenant tekshiruvi emas, faqat ruxsat darajasi solishtiriladi.
    """
    if current_user.is_superuser:
        return
    if not role_id:
        return

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rol topilmadi")

    target_perms = {p.code for p in role.permissions}
    own_perms = _permission_codes(current_user)

    missing = target_perms - own_perms
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"'{role.name}' rolini berish uchun sizda yetarli ruxsat yo'q "
                f"(yetishmaydi: {', '.join(sorted(missing))})"
            ),
        )


def assert_branch_in_tenant(db: Session, branch_id: Optional[int], tenant_id: int) -> None:
    """Filial shu tenant'ga tegishli ekanini tekshiradi (begona filialga biriktirmaslik)."""
    if not branch_id:
        return
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.tenant_id == tenant_id,
    ).first()
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bunday filial yo'q yoki u sizning do'koningizga tegishli emas",
        )

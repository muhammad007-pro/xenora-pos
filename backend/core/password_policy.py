"""
Parol va PIN siyosati — YAGONA joy (Tier 3).

MUHIM: bu qoidalar FAQAT parol/PIN O'RNATISH yoki O'ZGARTIRISHDA ishlatiladi.
LOGIN'da (authenticate_user / authenticate_by_pin) HECH QACHON chaqirilmaydi —
shuning uchun eski (qisqa/oddiy parolli) foydalanuvchi kirishда davom etadi.
Faqat yangi parol/PIN yaratishga ta'sir qiladi.

Amaliy balans: do'kon xodimi uchun juda qattiq emas — 8 belgi + harf + raqam,
ommabop zaif parollarni rad etadi. PIN — 4–6 raqam, ketma-ket/takroriy rad.
"""
from fastapi import HTTPException, status

MIN_PASSWORD_LEN = 8

# Ommabop zaif parollar (kichik harfda solishtiriladi). config.py'dagi superadmin
# ro'yxati bilan uyg'un + kengaytirilgan.
_WEAK_PASSWORDS = {
    "12345678", "123456789", "1234567890", "password", "password1", "parol",
    "parol123", "qwerty", "qwertyui", "qwerty123", "admin123", "administrator",
    "changeme", "welcome1", "iloveyou", "11111111", "00000000", "abcd1234",
    "aaaaaaaa", "letmein1", "xenora123", "test1234",
}


def _has_letter(s: str) -> bool:
    return any(c.isalpha() for c in s)


def _has_digit(s: str) -> bool:
    return any(c.isdigit() for c in s)


def validate_password(password: str) -> None:
    """Yangi parolni tekshiradi. Yaroqsiz bo'lsa 400 (aniq o'zbekcha sabab). Login'da EMAS."""
    pw = password or ""
    if len(pw) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parol kamida {MIN_PASSWORD_LEN} belgidan iborat bo'lishi kerak",
        )
    if not _has_letter(pw) or not _has_digit(pw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parolda kamida bitta harf VA bitta raqam bo'lishi kerak",
        )
    if pw.lower() in _WEAK_PASSWORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu parol juda oddiy va oson topiladi — murakkabroq parol tanlang",
        )


def _is_sequential(pin: str) -> bool:
    """Ketma-ket raqamlar (o'sish 1234 yoki kamayish 4321)."""
    asc  = all(ord(pin[i + 1]) - ord(pin[i]) == 1 for i in range(len(pin) - 1))
    desc = all(ord(pin[i]) - ord(pin[i + 1]) == 1 for i in range(len(pin) - 1))
    return asc or desc


def validate_pin(pin: str) -> None:
    """Yangi PIN'ni tekshiradi (4–6 raqam, takroriy/ketma-ket emas). Login'da EMAS."""
    p = pin or ""
    if not p.isdigit() or not (4 <= len(p) <= 6):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN 4–6 xonali raqamdan iborat bo'lishi kerak",
        )
    if len(set(p)) == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN bir xil raqamlardan iborat bo'lmasin (masalan 0000, 1111)",
        )
    if _is_sequential(p):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN ketma-ket raqamlardan iborat bo'lmasin (masalan 1234, 4321)",
        )

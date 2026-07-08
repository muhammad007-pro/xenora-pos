"""
Yordamchi funksiyalar
"""

import os
import re
import uuid
import hashlib
import random
import string
from datetime import datetime, timedelta
from typing import Any, Optional, List, Dict


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """O'zbekiston telefon raqamini yagona standart formatga keltiradi: +998XXXXXXXXX.

    Login va saqlashda BIR XIL format ishlatilishi shart — aks holda bir xil raqam
    turli ko'rinishda ("+998901234567", "998901234567", "901234567") ikki marta
    kirib ketadi yoki login topolmaydi.

    Misollar:
      "+998 90 123 45 67" -> "+998901234567"
      "998901234567"       -> "+998901234567"
      "901234567"          -> "+998901234567"
    Noaniq qiymatda: bor raqamlarni '+' bilan qaytaradi (yoki bo'sh bo'lsa None).
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)        # faqat raqamlar
    if not digits:
        return None
    if len(digits) == 9:                   # 901234567 -> 998901234567
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return "+" + digits                     # boshqa hollarda ham '+' bilan barqaror


def generate_uuid() -> str:
    """UUID yaratish"""
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """Qisqa ID yaratish"""
    return uuid.uuid4().hex[:length]


def generate_order_number() -> str:
    """Buyurtma raqami yaratish"""
    now = datetime.now()
    year = str(now.year)[-2:]
    month = str(now.month).zfill(2)
    day = str(now.day).zfill(2)
    random_part = ''.join(random.choices(string.digits, k=4))
    
    return f"{year}{month}{day}{random_part}"


def generate_transaction_id(prefix: str = "TRX") -> str:
    """Tranzaksiya ID yaratish"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}{timestamp}{random_part}"


def generate_barcode(prefix: str = "2") -> str:
    """Barcode yaratish (EAN-13 format)"""
    # 12 ta raqam
    digits = prefix
    for _ in range(11 - len(prefix)):
        digits += str(random.randint(0, 9))
    
    # Checksum hisoblash
    checksum = calculate_ean13_checksum(digits)
    
    return digits + str(checksum)


def calculate_ean13_checksum(digits: str) -> int:
    """EAN-13 checksum hisoblash"""
    total = 0
    for i, digit in enumerate(digits[:12]):
        if i % 2 == 0:
            total += int(digit)
        else:
            total += int(digit) * 3
    
    checksum = (10 - (total % 10)) % 10
    return checksum


def hash_password(password: str) -> str:
    """Parolni hash qilish"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Parolni tekshirish"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def generate_random_code(length: int = 6) -> str:
    """Tasdiqlash kodi yaratish"""
    return ''.join(random.choices(string.digits, k=length))


def generate_random_string(length: int = 10) -> str:
    """Tasodifiy matn yaratish"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def get_file_extension(filename: str) -> str:
    """Fayl kengaytmasini olish"""
    return os.path.splitext(filename)[1].lower()


def is_allowed_file(filename: str, allowed_extensions: List[str]) -> bool:
    """Ruxsat etilgan fayl formatini tekshirish"""
    ext = get_file_extension(filename)
    return ext in allowed_extensions


def safe_filename(filename: str) -> str:
    """Xavfsiz fayl nomi yaratish"""
    # Maxsus belgilarni almashtirish
    safe_chars = string.ascii_letters + string.digits + ".-_"
    name, ext = os.path.splitext(filename)
    
    safe_name = ''.join(c if c in safe_chars else '_' for c in name)
    safe_ext = ''.join(c if c in safe_chars else '_' for c in ext)
    
    if not safe_name:
        safe_name = generate_short_id()
    
    return safe_name + safe_ext


def ensure_directory(path: str) -> bool:
    """Papka mavjudligini ta'minlash"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def get_file_size(filepath: str) -> int:
    """Fayl hajmini olish"""
    try:
        return os.path.getsize(filepath)
    except Exception:
        return 0


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Ro'yxatni bo'laklarga bo'lish"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def merge_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """Lug'atlarni birlashtirish"""
    result = dict1.copy()
    result.update(dict2)
    return result


def deep_merge(dict1: Dict, dict2: Dict) -> Dict:
    """Chuqur birlashtirish"""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def get_nested_value(data: Dict, path: str, default: Any = None) -> Any:
    """Ichki qiymatni olish (masalan: 'user.profile.name')"""
    keys = path.split('.')
    value = data
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value


def set_nested_value(data: Dict, path: str, value: Any) -> Dict:
    """Ichki qiymatni o'rnatish"""
    keys = path.split('.')
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    return data


def calculate_percentage(value: float, total: float) -> float:
    """Foiz hisoblash"""
    if total == 0:
        return 0
    return round((value / total) * 100, 2)


def calculate_discount(amount: float, discount_type: str, discount_value: float) -> float:
    """Chegirma summasini hisoblash"""
    if discount_type == "percentage":
        return amount * (discount_value / 100)
    else:  # fixed
        return min(discount_value, amount)


def calculate_tax(amount: float, tax_rate: float = 12.0) -> float:
    """Soliq hisoblash"""
    return amount * (tax_rate / 100)


def calculate_service_charge(amount: float, rate: float = 10.0) -> float:
    """Xizmat haqi hisoblash"""
    return amount * (rate / 100)


def round_up(value: float, decimals: int = 0) -> float:
    """Yuqoriga yaxlitlash"""
    import math
    multiplier = 10 ** decimals
    return math.ceil(value * multiplier) / multiplier


def round_down(value: float, decimals: int = 0) -> float:
    """Pastga yaxlitlash"""
    import math
    multiplier = 10 ** decimals
    return math.floor(value * multiplier) / multiplier


def get_week_range(date: datetime = None) -> tuple:
    """Hafta oralig'ini olish"""
    if date is None:
        date = datetime.now()
    
    start = date - timedelta(days=date.weekday())
    end = start + timedelta(days=6)
    
    return start.replace(hour=0, minute=0, second=0), end.replace(hour=23, minute=59, second=59)


def get_month_range(date: datetime = None) -> tuple:
    """Oy oralig'ini olish"""
    if date is None:
        date = datetime.now()
    
    start = date.replace(day=1, hour=0, minute=0, second=0)
    
    if date.month == 12:
        end = date.replace(year=date.year + 1, month=1, day=1)
    else:
        end = date.replace(month=date.month + 1, day=1)
    
    end = end - timedelta(seconds=1)
    
    return start, end
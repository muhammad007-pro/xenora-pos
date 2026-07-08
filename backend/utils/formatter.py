"""
Formatlash uchun yordamchi funksiyalar
"""

from datetime import datetime, timedelta
from typing import Optional, Union
import re


def format_money(amount: Union[int, float], currency: str = "UZS", locale: str = "uz-UZ") -> str:
    """Pul summasini formatlash"""
    if amount is None:
        return f"0 {currency}"
    
    try:
        # Intl orqali formatlash
        import locale as loc
        try:
            loc.setlocale(loc.LC_ALL, 'uz_UZ.UTF-8')
        except:
            pass
        
        return f"{amount:,.0f}".replace(",", " ") + f" {currency}"
    except:
        return f"{amount:,.0f} {currency}".replace(",", " ")


def format_number(number: Union[int, float], decimal_places: int = 0) -> str:
    """Sonni formatlash"""
    if number is None:
        return "0"
    
    if decimal_places > 0:
        return f"{number:,.{decimal_places}f}".replace(",", " ")
    else:
        return f"{number:,.0f}".replace(",", " ")


def format_date(date: Union[datetime, str], format_type: str = "short") -> str:
    """Sanani formatlash"""
    if date is None:
        return "-"
    
    if isinstance(date, str):
        try:
            date = datetime.fromisoformat(date.replace('Z', '+00:00'))
        except:
            return date
    
    formats = {
        "short": "%d.%m.%Y",
        "medium": "%d %B %Y",
        "long": "%d %B %Y, %A",
        "iso": "%Y-%m-%d",
        "datetime": "%d.%m.%Y %H:%M",
        "time": "%H:%M:%S"
    }
    
    fmt = formats.get(format_type, "%d.%m.%Y")
    
    if format_type == "medium" or format_type == "long":
        # O'zbekcha oy nomlari
        months_uz = {
            1: "yanvar", 2: "fevral", 3: "mart", 4: "aprel",
            5: "may", 6: "iyun", 7: "iyul", 8: "avgust",
            9: "sentabr", 10: "oktabr", 11: "noyabr", 12: "dekabr"
        }
        result = date.strftime(fmt)
        month_num = date.month
        result = result.replace(date.strftime("%B"), months_uz[month_num])
        return result
    
    return date.strftime(fmt)


def format_time(time: Union[datetime, str], include_seconds: bool = False) -> str:
    """Vaqtni formatlash"""
    if time is None:
        return "-"
    
    if isinstance(time, str):
        try:
            time = datetime.fromisoformat(time.replace('Z', '+00:00'))
        except:
            return time
    
    fmt = "%H:%M:%S" if include_seconds else "%H:%M"
    return time.strftime(fmt)


def format_datetime(dt: Union[datetime, str], format_type: str = "short") -> str:
    """Sana va vaqtni formatlash"""
    if dt is None:
        return "-"
    
    return f"{format_date(dt, format_type)} {format_time(dt)}"


def format_relative_time(dt: Union[datetime, str]) -> str:
    """Nisbiy vaqtni formatlash (5 daqiqa oldin, 2 soat oldin)"""
    if dt is None:
        return "-"
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    now = datetime.now()
    diff = now - dt
    
    if diff.total_seconds() < 0:
        return "kelajakda"
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "hozir"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} daqiqa oldin"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} soat oldin"
    elif seconds < 2592000:
        days = int(seconds / 86400)
        return f"{days} kun oldin"
    elif seconds < 31536000:
        months = int(seconds / 2592000)
        return f"{months} oy oldin"
    else:
        years = int(seconds / 31536000)
        return f"{years} yil oldin"


def format_duration(minutes: int) -> str:
    """Davomiylikni formatlash"""
    if minutes is None:
        return "-"
    
    if minutes < 60:
        return f"{minutes} daqiqa"
    
    hours = minutes // 60
    mins = minutes % 60
    
    if mins == 0:
        return f"{hours} soat"
    
    return f"{hours} soat {mins} daqiqa"


def format_phone(phone: str) -> str:
    """Telefon raqamni formatlash"""
    if not phone:
        return ""
    
    # Faqat raqamlarni olish
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) == 12 and digits.startswith('998'):
        return f"+{digits[0:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:12]}"
    elif len(digits) == 9:
        return f"+998 {digits[0:2]} {digits[2:5]} {digits[5:7]} {digits[7:9]}"
    
    return phone


def format_percent(value: float, decimals: int = 1) -> str:
    """Foizni formatlash"""
    if value is None:
        return "0%"
    return f"{value:.{decimals}f}%"


def format_file_size(size_bytes: int) -> str:
    """Fayl hajmini formatlash"""
    if size_bytes is None or size_bytes == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    
    return f"{size:.2f} {units[i]}"


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Matnni qisqartirish"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length].strip() + suffix


def format_order_number(order_id: int, prefix: str = "#") -> str:
    """Buyurtma raqamini formatlash"""
    return f"{prefix}{order_id:06d}"


def format_table_number(table_number: str) -> str:
    """Stol raqamini formatlash"""
    return f"Stol #{table_number}"


def format_status(status: str, status_type: str = "order") -> str:
    """Holat matnini formatlash"""
    status_map = {
        "order": {
            "pending": "Kutilmoqda",
            "confirmed": "Tasdiqlangan",
            "preparing": "Tayyorlanmoqda",
            "ready": "Tayyor",
            "served": "Xizmat qilingan",
            "completed": "Yakunlangan",
            "cancelled": "Bekor qilingan"
        },
        "payment": {
            "pending": "Kutilmoqda",
            "paid": "To'langan",
            "partial": "Qisman",
            "refunded": "Qaytarilgan",
            "failed": "Xatolik"
        },
        "table": {
            "free": "Bo'sh",
            "occupied": "Band",
            "reserved": "Bron",
            "cleaning": "Tozalanmoqda"
        }
    }
    
    return status_map.get(status_type, {}).get(status, status)


def format_json(data: dict, indent: int = 2) -> str:
    """JSON formatlash"""
    import json
    return json.dumps(data, ensure_ascii=False, indent=indent)


def parse_date(date_str: str) -> Optional[datetime]:
    """Sana matnini datetime ga o'girish"""
    if not date_str:
        return None
    
    formats = [
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None
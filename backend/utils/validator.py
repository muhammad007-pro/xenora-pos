import re
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

class Validator:
    """Ma'lumotlarni validatsiya qilish"""
    
    @staticmethod
    def email(value: str) -> bool:
        """Email validatsiyasi"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, value))
    
    @staticmethod
    def phone(value: str, country: str = 'uz') -> bool:
        """Telefon raqam validatsiyasi"""
        patterns = {
            'uz': r'^\+998[0-9]{9}$',
            'ru': r'^\+7[0-9]{10}$',
            'us': r'^\+1[0-9]{10}$'
        }
        pattern = patterns.get(country, r'^\+[0-9]{10,15}$')
        return bool(re.match(pattern, value))
    
    @staticmethod
    def password_strength(password: str) -> Dict[str, Any]:
        """Parol murakkabligini tekshirish"""
        strength = {
            "length": len(password) >= 6,
            "has_upper": bool(re.search(r'[A-Z]', password)),
            "has_lower": bool(re.search(r'[a-z]', password)),
            "has_digit": bool(re.search(r'\d', password)),
            "has_special": bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
        }
        
        score = sum(strength.values())
        
        return {
            "valid": score >= 3,
            "score": score,
            "max_score": 5,
            "details": strength
        }
    
    @staticmethod
    def username(value: str) -> bool:
        """Username validatsiyasi"""
        pattern = r'^[a-zA-Z0-9_]{3,20}$'
        return bool(re.match(pattern, value))
    
    @staticmethod
    def url(value: str) -> bool:
        """URL validatsiyasi"""
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, value))
    
    @staticmethod
    def ip_address(value: str) -> bool:
        """IP manzil validatsiyasi"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(pattern, value):
            return False
        
        parts = value.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    
    @staticmethod
    def date(value: str, format: str = '%Y-%m-%d') -> bool:
        """Sana validatsiyasi"""
        try:
            datetime.strptime(value, format)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def time(value: str, format: str = '%H:%M:%S') -> bool:
        """Vaqt validatsiyasi"""
        try:
            datetime.strptime(value, format)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def number_range(value: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> bool:
        """Son oralig'i validatsiyasi"""
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        return True
    
    @staticmethod
    def length(value: str, min_len: Optional[int] = None, max_len: Optional[int] = None) -> bool:
        """Matn uzunligi validatsiyasi"""
        if min_len is not None and len(value) < min_len:
            return False
        if max_len is not None and len(value) > max_len:
            return False
        return True


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
    """Majburiy maydonlarni tekshirish"""
    missing = []
    for field in required_fields:
        if field not in data or data[field] is None or data[field] == "":
            missing.append(field)
    return missing


def validate_schema(data: Dict[str, Any], schema: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Sxema bo'yicha validatsiya"""
    errors = {}
    
    for field, rules in schema.items():
        value = data.get(field)
        field_errors = []
        
        # Majburiylik
        if rules.get('required', False) and (value is None or value == ""):
            field_errors.append("Majburiy maydon")
            errors[field] = field_errors
            continue
        
        if value is not None and value != "":
            # Tip tekshirish
            expected_type = rules.get('type')
            if expected_type:
                if expected_type == 'int' and not isinstance(value, int):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        field_errors.append("Butun son bo'lishi kerak")
                
                elif expected_type == 'float' and not isinstance(value, (int, float)):
                    try:
                        float(value)
                    except (ValueError, TypeError):
                        field_errors.append("Son bo'lishi kerak")
                
                elif expected_type == 'email' and not Validator.email(str(value)):
                    field_errors.append("To'g'ri email kiriting")
                
                elif expected_type == 'phone' and not Validator.phone(str(value)):
                    field_errors.append("To'g'ri telefon raqam kiriting")
                
                elif expected_type == 'url' and not Validator.url(str(value)):
                    field_errors.append("To'g'ri URL kiriting")
            
            # Minimal/maksimal qiymat
            if 'min' in rules and isinstance(value, (int, float)):
                if value < rules['min']:
                    field_errors.append(f"Minimal qiymat: {rules['min']}")
            
            if 'max' in rules and isinstance(value, (int, float)):
                if value > rules['max']:
                    field_errors.append(f"Maksimal qiymat: {rules['max']}")
            
            # Minimal/maksimal uzunlik
            if 'min_length' in rules and isinstance(value, str):
                if len(value) < rules['min_length']:
                    field_errors.append(f"Minimal uzunlik: {rules['min_length']} ta belgi")
            
            if 'max_length' in rules and isinstance(value, str):
                if len(value) > rules['max_length']:
                    field_errors.append(f"Maksimal uzunlik: {rules['max_length']} ta belgi")
            
            # Regex pattern
            if 'pattern' in rules and isinstance(value, str):
                if not re.match(rules['pattern'], value):
                    field_errors.append(rules.get('pattern_message', 'Noto\'g\'ri format'))
            
            # Maxsus validator
            if 'validator' in rules and callable(rules['validator']):
                try:
                    if not rules['validator'](value):
                        field_errors.append("Validatsiyadan o'tmadi")
                except Exception:
                    field_errors.append("Validatsiya xatoligi")
        
        if field_errors:
            errors[field] = field_errors
    
    return errors
from fastapi import HTTPException, status

class BaseAppException(HTTPException):
    """Asosiy xatolik klassi"""
    def __init__(self, status_code: int, detail: str, error_code: str = None):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code

class InvalidCredentialsError(BaseAppException):
    """Noto'g'ri login yoki parol"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Noto'g'ri foydalanuvchi nomi yoki parol",
            error_code="INVALID_CREDENTIALS"
        )

class UserNotFoundError(BaseAppException):
    """Foydalanuvchi topilmadi"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foydalanuvchi topilmadi",
            error_code="USER_NOT_FOUND"
        )

class UserInactiveError(BaseAppException):
    """Foydalanuvchi faol emas"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hisob faol emas",
            error_code="USER_INACTIVE"
        )

class PermissionDeniedError(BaseAppException):
    """Ruxsat yo'q"""
    def __init__(self, permission: str = None):
        detail = "Bu amal uchun ruxsat yo'q"
        if permission:
            detail = f"'{permission}' ruxsati yo'q"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="PERMISSION_DENIED"
        )

class ResourceNotFoundError(BaseAppException):
    """Resurs topilmadi"""
    def __init__(self, resource: str = "Resurs"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} topilmadi",
            error_code="RESOURCE_NOT_FOUND"
        )

class ValidationError(BaseAppException):
    """Validatsiya xatoligi"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="VALIDATION_ERROR"
        )

class DuplicateError(BaseAppException):
    """Takroriy ma'lumot"""
    def __init__(self, field: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bu {field} allaqachon mavjud",
            error_code="DUPLICATE_ERROR"
        )

class InsufficientStockError(BaseAppException):
    """Ombor yetarli emas"""
    def __init__(self, product_name: str, available: float, requested: float):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{product_name} uchun yetarli miqdor mavjud emas. Mavjud: {available}, So'ralgan: {requested}",
            error_code="INSUFFICIENT_STOCK"
        )
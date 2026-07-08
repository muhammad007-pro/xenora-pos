from fastapi import FastAPI, HTTPException  # ← QO'SHILDI
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

def register_startup_events(app: FastAPI):
    """Startup eventlarini ro'yxatdan o'tkazish"""
    
    @app.on_event("startup")
    async def startup_event():
        """Tizim ishga tushganda bajariladigan amallar"""
        logger.info("🚀 Tizim ishga tushmoqda...")
        
        # Papkalarni tekshirish va yaratish
        import os
        directories = ["static", "static/uploads", "static/receipts", "backup/auto", "logs"]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        
        logger.info("✅ Papkalar tayyor")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Tizim to'xtaganda bajariladigan amallar"""
        logger.info("👋 Tizim to'xtatilmoqda...")
        
        # WebSocket ulanishlarini yopish
        from websocket.manager import manager
        # TODO: Barcha ulanishlarni yopish

def register_exception_handlers(app: FastAPI):
    """Xatolik handlerlarini ro'yxatdan o'tkazish"""
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Global xatolik: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ichki server xatoligi"}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
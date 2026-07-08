import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

async def clean_old_notifications():
    """Eski bildirishnomalarni tozalash"""
    from database import SessionLocal
    from models import Notification
    
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(days=30)
        
        result = db.query(Notification).filter(
            Notification.created_at < cutoff,
            Notification.is_read == True
        ).delete()
        
        db.commit()
        logger.info(f"Cleaned {result} old notifications")
        return {"success": True, "deleted_count": result}
        
    except Exception as e:
        logger.error(f"Failed to clean notifications: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def send_daily_report_notifications():
    """Kunlik hisobot bildirishnomalari"""
    from database import SessionLocal
    from services.notification_service import NotificationService
    from services.analytics_service import AnalyticsService
    
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        analytics_service = AnalyticsService(db)
        
        today = datetime.now().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.now()
        
        # Kunlik statistika
        data = analytics_service.get_period_data(start_of_day, end_of_day)
        
        message = f"Bugun: {data['total_orders']} ta buyurtma, {data['total_revenue']:,.0f} UZS"
        
        await notification_service.send_to_role(
            role_name="admin",
            title="Kunlik hisobot",
            message=message,
            notification_type="report",
            data=data
        )
        
        logger.info("Daily report notifications sent")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Failed to send daily report: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def check_low_stock_notifications():
    """Kam qolgan mahsulotlar haqida bildirishnoma"""
    from database import SessionLocal
    from services.inventory_service import InventoryService
    from services.notification_service import NotificationService
    
    db = SessionLocal()
    try:
        inventory_service = InventoryService(db)
        notification_service = NotificationService(db)
        
        alerts = inventory_service.get_low_stock_alerts()
        
        if alerts:
            for alert in alerts[:5]:  # Birinchi 5 tasi
                await notification_service.notify_low_stock(
                    product_name=alert["product_name"],
                    quantity=alert["current_quantity"],
                    unit=alert["unit"]
                )
            
            if len(alerts) > 5:
                await notification_service.send_to_role(
                    role_name="admin",
                    title="Ombor ogohlantirishi",
                    message=f"Jami {len(alerts)} ta mahsulot kam qolgan",
                    notification_type="inventory"
                )
        
        logger.info(f"Low stock check completed: {len(alerts)} alerts")
        return {"success": True, "alerts_count": len(alerts)}
        
    except Exception as e:
        logger.error(f"Failed to check low stock: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def send_shift_reminders():
    """Smena eslatmalari"""
    from database import SessionLocal
    from models import Shift, User
    from services.notification_service import NotificationService
    
    db = SessionLocal()
    try:
        notification_service = NotificationService(db)
        
        # Faol smenalarni tekshirish
        active_shifts = db.query(Shift).filter(Shift.end_time.is_(None)).all()
        
        for shift in active_shifts:
            # 8 soatdan ortiq ishlayotganlar uchun eslatma
            if shift.start_time:
                duration = datetime.now() - shift.start_time
                if duration.total_seconds() > 8 * 3600:
                    user = db.query(User).filter(User.id == shift.user_id).first()
                    if user:
                        await notification_service.send_notification(
                            user_id=shift.user_id,
                            title="Smena eslatmasi",
                            message="Siz 8 soatdan ortiq ishlayapsiz. Smenani yopishni unutmang.",
                            notification_type="shift"
                        )
        
        logger.info("Shift reminders sent")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Failed to send shift reminders: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()
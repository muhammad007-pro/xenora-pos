import logging
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

async def generate_daily_reports():
    """Kunlik hisobotlarni generatsiya qilish"""
    from database import SessionLocal
    from services.report_service import ReportService
    
    db = SessionLocal()
    try:
        report_service = ReportService(db)
        today = datetime.now().date()
        
        # Kunlik hisobot
        report = report_service.generate_daily_report(today)
        
        # Hisobotni saqlash
        reports_dir = "static/reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        filename = f"daily_report_{today.strftime('%Y%m%d')}.json"
        filepath = os.path.join(reports_dir, filename)
        
        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Daily report generated: {filename}")
        return {"success": True, "file": filename}
        
    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def generate_weekly_reports():
    """Haftalik hisobotlarni generatsiya qilish"""
    from database import SessionLocal
    from services.report_service import ReportService
    from services.analytics_service import AnalyticsService
    
    db = SessionLocal()
    try:
        report_service = ReportService(db)
        analytics_service = AnalyticsService(db)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        # Haftalik savdo hisoboti
        sales_report = report_service.generate_sales_report(start_date, end_date)
        
        # Mahsulotlar hisoboti
        products_report = report_service.generate_products_report(start_date, end_date)
        
        # Xodimlar hisoboti
        staff_report = report_service.generate_staff_report(start_date, end_date)
        
        reports_dir = "static/reports/weekly"
        os.makedirs(reports_dir, exist_ok=True)
        
        week_num = datetime.now().strftime("%Y_W%W")
        
        import json
        report_data = {
            "week": week_num,
            "date_from": start_date.isoformat(),
            "date_to": end_date.isoformat(),
            "sales": sales_report,
            "products": products_report,
            "staff": staff_report
        }
        
        filename = f"weekly_report_{week_num}.json"
        filepath = os.path.join(reports_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Weekly report generated: {filename}")
        return {"success": True, "file": filename}
        
    except Exception as e:
        logger.error(f"Failed to generate weekly report: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def generate_monthly_reports():
    """Oylik hisobotlarni generatsiya qilish"""
    from database import SessionLocal
    from services.report_service import ReportService
    
    db = SessionLocal()
    try:
        report_service = ReportService(db)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Oylik hisobot
        sales_report = report_service.generate_sales_report(start_date, end_date)
        
        reports_dir = "static/reports/monthly"
        os.makedirs(reports_dir, exist_ok=True)
        
        month = datetime.now().strftime("%Y_%m")
        filename = f"monthly_report_{month}.json"
        filepath = os.path.join(reports_dir, filename)
        
        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(sales_report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Monthly report generated: {filename}")
        return {"success": True, "file": filename}
        
    except Exception as e:
        logger.error(f"Failed to generate monthly report: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()

async def cleanup_old_reports(days: int = 90):
    """Eski hisobotlarni tozalash"""
    reports_dir = "static/reports"
    
    if not os.path.exists(reports_dir):
        return {"success": True, "message": "No reports directory"}
    
    cutoff = datetime.now() - timedelta(days=days)
    deleted_count = 0
    
    for root, dirs, files in os.walk(reports_dir):
        for file in files:
            if file.endswith('.json'):
                filepath = os.path.join(root, file)
                file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                
                if file_time < cutoff:
                    os.remove(filepath)
                    deleted_count += 1
    
    logger.info(f"Cleaned up {deleted_count} old reports")
    return {"success": True, "deleted_count": deleted_count}
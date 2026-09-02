import asyncio
from datetime import datetime, timedelta
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)

class TaskScheduler:
    """Vazifalarni rejalashtirish"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self._task = None
    
    def add_task(
        self,
        name: str,
        func: Callable,
        interval: int = 3600,
        run_immediately: bool = False
    ):
        """Vazifa qo'shish"""
        self.tasks[name] = {
            "func": func,
            "interval": interval,
            "last_run": None,
            "next_run": datetime.now() if run_immediately else datetime.now() + timedelta(seconds=interval)
        }
        logger.info(f"Task added: {name} (interval: {interval}s)")
    
    def remove_task(self, name: str):
        """Vazifani o'chirish"""
        if name in self.tasks:
            del self.tasks[name]
            logger.info(f"Task removed: {name}")
    
    async def _run_task(self, name: str, task_info: Dict[str, Any]):
        """Vazifani bajarish"""
        try:
            logger.info(f"Running task: {name}")
            
            if asyncio.iscoroutinefunction(task_info["func"]):
                await task_info["func"]()
            else:
                task_info["func"]()
            
            task_info["last_run"] = datetime.now()
            task_info["next_run"] = datetime.now() + timedelta(seconds=task_info["interval"])
            
            logger.info(f"Task completed: {name}")
            
        except Exception as e:
            logger.error(f"Task failed: {name} - {str(e)}")
    
    async def _scheduler_loop(self):
        """Scheduler loop"""
        while self.running:
            now = datetime.now()
            
            for name, task_info in self.tasks.items():
                if task_info["next_run"] and now >= task_info["next_run"]:
                    await self._run_task(name, task_info)
            
            await asyncio.sleep(1)
    
    def start(self):
        """Schedulerni ishga tushirish"""
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._scheduler_loop())
            logger.info("Scheduler started")
    
    def stop(self):
        """Schedulerni to'xtatish"""
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Scheduler stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Scheduler holati"""
        tasks_status = {}
        for name, task_info in self.tasks.items():
            tasks_status[name] = {
                "last_run": task_info["last_run"].isoformat() if task_info["last_run"] else None,
                "next_run": task_info["next_run"].isoformat() if task_info["next_run"] else None,
                "interval": task_info["interval"]
            }
        
        return {
            "running": self.running,
            "tasks": tasks_status
        }


# Global scheduler
scheduler = TaskScheduler()


async def clean_old_notifications():
    """Eski bildirishnomalarni tozalash"""
    from database import SessionLocal
    from models import Notification
    from datetime import datetime, timedelta
    
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(days=30)
        db.query(Notification).filter(
            Notification.created_at < cutoff,
            Notification.is_read == True
        ).delete()
        db.commit()
        logger.info("Old notifications cleaned")
    except Exception as e:
        logger.error(f"Failed to clean notifications: {e}")
    finally:
        db.close()


async def check_expired_tenants():
    """Muhlati (grace) ham tugagan tenantlarni `expired` deb belgilaydi.

    ⚠️ 2026-09-02 gacha bu vazifa UCH XATO qilardi:

    1) `is_active = False` qo'yardi. `is_active` — do'kon O'CHIRILGANINI bildiradi
       (super-admin qo'lda), obuna holatini emas. Va u KIRISH yo'lida tekshiriladi:
       `routers/auth.py` dagi `resolve-code` va `pin-login` `Cafe.is_active == True`
       filtri bilan ishlaydi. Natijada muddat tugashi bilan kassirlar kirish
       ekranida "Do'kon topilmadi" ko'rardi. Endi bu maydonga TEGILMAYDI.

    2) MUHLATNI (grace) hisobga olmasdi — muddat o'tishi bilan (≤1 soat)
       `expired` qo'yardi. `core/subscription.subscription_state` esa `expired`
       holatini QATTIQ blok deb biladi, ya'ni `SUBSCRIPTION_GRACE_DAYS` amalda
       hech qachon ishlamasdi. Endi muhlat tugagandan KEYIN belgilanadi.

    3) KILL-SWITCH dan tashqarida edi: `ENFORCE_SUBSCRIPTION=False` bo'lsa ham
       bazani o'zgartirardi. Endi o'chiq bo'lsa umuman ishlamaydi — kill-switch
       to'liq (kod serverda tursa ham hech narsaga tegmaydi).

    Bu vazifa faqat BELGI qo'yadi; bloklashning o'zi `deps._enforce_subscription`
    da, u ham kill-switch ostida.
    """
    from database import SessionLocal
    from models import Cafe
    from datetime import datetime, timedelta
    from config import settings

    # KILL-SWITCH: o'chiq bo'lsa bazaga TEGMAYMIZ.
    if not settings.ENFORCE_SUBSCRIPTION:
        return

    db = SessionLocal()
    try:
        now = datetime.now()
        # Muhlat ham tugagan bo'lsin: muddat + grace < hozir.
        grace = timedelta(days=max(0, settings.SUBSCRIPTION_GRACE_DAYS))
        cutoff = now - grace
        expired = (
            db.query(Cafe)
            .filter(
                Cafe.is_active == True,          # noqa: E712 — o'chirilganlarga tegmaymiz
                Cafe.tenant_status == "active",
                Cafe.subscription_expires != None,  # noqa: E711
                Cafe.subscription_expires < cutoff,
            )
            .all()
        )
        for cafe in expired:
            cafe.tenant_status = "expired"       # `is_active` ATAYLAB tegilmaydi
            logger.info(
                "Tenant obunasi tugadi (muhlat ham): %s (%s), muddat=%s, grace=%d kun",
                cafe.id, cafe.name, cafe.subscription_expires,
                settings.SUBSCRIPTION_GRACE_DAYS,
            )
        if expired:
            db.commit()
            logger.info("Muddati tugagan tenantlar belgilandi: %d", len(expired))
    except Exception as e:
        logger.error(f"check_expired_tenants failed: {e}")
    finally:
        db.close()


def start_scheduler():
    # BACKUP endi CRON'da (scripts/backup.py, har kuni 03:00) — app scheduler'дан OLIB TASHLANDI.
    # SABAB: scheduler taymeri xotirada (next_run = app_start + interval); HAR RESTART/DEPLOY'da
    # nollanardi → 24 soatdan tez-tez restart → backup umuman ishlamas edi (Jul 19/20/23/24 tushib
    # qoldi). Cron restart'дan mustaqil, belgilangan soatda ishonchli. Qarang: DEPLOY.md §10.
    # DIQQAT: bu o'zgarish faqat cron O'RNATILGANDAN KEYIN deploy qilinsin (backup uzilmasin).
    scheduler.add_task("clean_notifications", clean_old_notifications,     interval=3600)   # soatda
    # (B6) update_inventory vazifasi olib tashlandi — ombor chiqimi endi to'lov paytida
    # real vaqtda (deduct_order_ingredients) bajariladi, davriy sync yo'li kerak emas edi.
    scheduler.add_task("check_expired_tenants", check_expired_tenants,     interval=3600,   # soatda
                       run_immediately=True)
    scheduler.start()


def stop_scheduler():
    """Schedulerni to'xtatish"""
    scheduler.stop()
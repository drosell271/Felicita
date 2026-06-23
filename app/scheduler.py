import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .database import SessionLocal
from .models import AppSetting
from .services.dispatch import dispatch_daily

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone=get_settings().timezone)


def scheduled_dispatch() -> None:
    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    dispatch_daily(today)


def configure_schedule() -> None:
    with SessionLocal() as db:
        settings = db.get(AppSetting, 1)
        send_time = settings.send_time if settings else "09:00"
    hour, minute = (int(part) for part in send_time.split(":"))
    scheduler.add_job(
        scheduled_dispatch,
        CronTrigger(hour=hour, minute=minute, timezone=get_settings().timezone),
        id="daily-dispatch",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    logger.info("Envío diario programado a las %s (%s)", send_time, get_settings().timezone)


def start_scheduler() -> None:
    configure_schedule()
    if not scheduler.running:
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


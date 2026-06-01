from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings


def create_scheduler() -> AsyncIOScheduler:
    """
    Создать настроенный планировщик.

    job_defaults:
    - max_instances=1 — парсинг не запускается параллельно сам с собой
    - coalesce=True — пропущенные запуски схлопываются в один
    - misfire_grace_time — допустимое опоздание запуска
    """
    settings = get_settings()
    return AsyncIOScheduler(
        timezone=settings.scheduler_timezone,
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 300,
        },
    )

def create_cron_trigger() -> IntervalTrigger:
    """
    Создать cron-триггер для регулярного парсинга.

    Расписание берётся из настроек (по умолчанию: пн-пт, 09:00-17:00,
    каждый час, по времени Asia/Almaty).
    """
    # settings = get_settings()
    # return CronTrigger(
    #     day_of_week=settings.scheduler_cron_day_of_week,
    #     hour=settings.scheduler_cron_hour,
    #     minute=0,
    #     timezone=settings.scheduler_timezone,
    # )
    return IntervalTrigger(minutes=3) # TODO: временно

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.repositories.provider_repo import list_providers

logger = logging.getLogger(__name__)

_scheduler = None
_app = None

WEEKDAY_MAP = {
    0: "mon", 1: "tue", 2: "wed", 3: "thu",
    4: "fri", 5: "sat", 6: "sun",
}


def _scheduled_refresh(provider_id):
    if _app is None:
        return
    with _app.app_context():
        from app.services.updater import RefreshOrchestrator
        orch = RefreshOrchestrator(_app)
        try:
            orch.refresh(provider_id, trigger="scheduled")
        except Exception:
            logger.exception("Scheduled refresh failed for provider %d", provider_id)


def _get_timezone():
    if _app is not None:
        return _app.config.get("TIMEZONE", "Asia/Hong_Kong")
    return "Asia/Hong_Kong"


def _build_trigger(schedule):
    stype = schedule.get("type", "disabled")
    if stype == "disabled":
        return None

    from zoneinfo import ZoneInfo
    tz = ZoneInfo(_get_timezone())

    hour, minute = 0, 0
    time_str = schedule.get("time_of_day")
    if time_str and ":" in time_str:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1])

    if stype == "daily":
        return CronTrigger(hour=hour, minute=minute, timezone=tz)

    if stype == "weekly":
        dow = schedule.get("day_of_week", 0)
        if isinstance(dow, int):
            dow = WEEKDAY_MAP.get(dow, "mon")
        return CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone=tz)

    if stype == "monthly":
        dom = schedule.get("day_of_month", 1)
        return CronTrigger(day=dom, hour=hour, minute=minute, timezone=tz)

    if stype == "interval":
        hours = schedule.get("interval_hours", 24)
        return IntervalTrigger(hours=hours)

    return None


def _schedule_provider(provider):
    job_id = f"provider_{provider.id}"
    schedule = {
        "type": provider.schedule_type,
        "day_of_month": provider.schedule_day_of_month,
        "day_of_week": provider.schedule_day_of_week,
        "time_of_day": provider.schedule_time_of_day,
        "interval_hours": provider.schedule_interval_hours,
    }
    trigger = _build_trigger(schedule)
    if trigger is None:
        remove_provider_schedule(provider.id)
        return

    _scheduler.add_job(
        _scheduled_refresh,
        trigger=trigger,
        args=[provider.id],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Scheduled provider %d: %s", provider.id, schedule)


def remove_provider_schedule(provider_id):
    job_id = f"provider_{provider_id}"
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass


def init_scheduler(app):
    global _scheduler, _app
    _app = app
    from apscheduler.events import EVENT_JOB_ERROR
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(app.config.get("TIMEZONE", "Asia/Hong_Kong"))
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.start()

    with app.app_context():
        try:
            providers = list_providers()
            for p in providers:
                if p.enabled and p.schedule_type != "disabled":
                    try:
                        _schedule_provider(p)
                    except Exception:
                        logger.exception("Failed to schedule provider %d", p.id)
        except Exception:
            logger.debug("Scheduler init: tables not ready yet, skipping provider load")

    return _scheduler


def reschedule_provider(provider):
    if _scheduler is None:
        return
    if provider.enabled and provider.schedule_type != "disabled":
        _schedule_provider(provider)
    else:
        remove_provider_schedule(provider.id)


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None

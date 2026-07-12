from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.provider import Provider
from app.repositories.provider_repo import create_provider
from app.services.scheduler import (
    _build_trigger,
    init_scheduler,
    reschedule_provider,
    remove_provider_schedule,
    _scheduler,
)
import app.services.scheduler as sched_mod


def test_build_trigger_disabled():
    assert _build_trigger({"type": "disabled"}) is None


def test_build_trigger_daily():
    trigger = _build_trigger({"type": "daily", "time_of_day": "08:30"})
    assert trigger is not None


def test_build_trigger_weekly():
    trigger = _build_trigger({"type": "weekly", "day_of_week": 1, "time_of_day": "09:00"})
    assert trigger is not None


def test_build_trigger_monthly():
    trigger = _build_trigger({"type": "monthly", "day_of_month": 15, "time_of_day": "12:00"})
    assert trigger is not None


def test_build_trigger_interval():
    trigger = _build_trigger({"type": "interval", "interval_hours": 6})
    assert trigger is not None


def test_init_scheduler_loads_providers(app):
    with app.app_context():
        p = create_provider("Sched", "https://example.com/clash.yaml", {
            "type": "daily", "time_of_day": "08:00"
        })
        scheduler = init_scheduler(app)
        job = scheduler.get_job(f"provider_{p.id}")
        assert job is not None
        scheduler.shutdown(wait=False)


def test_reschedule_provider_enable(app):
    with app.app_context():
        sched_mod._scheduler = init_scheduler(app)
        p = create_provider("Resched", "https://example.com/clash.yaml", {"type": "disabled"})
        p.enabled = True
        p.schedule_type = "daily"
        p.schedule_time_of_day = "10:00"
        db.session.commit()
        reschedule_provider(p)
        job = sched_mod._scheduler.get_job(f"provider_{p.id}")
        assert job is not None
        sched_mod._scheduler.shutdown(wait=False)


def test_reschedule_provider_disable(app):
    with app.app_context():
        sched_mod._scheduler = init_scheduler(app)
        p = create_provider("Disable", "https://example.com/clash.yaml", {
            "type": "daily", "time_of_day": "10:00"
        })
        reschedule_provider(p)
        job = sched_mod._scheduler.get_job(f"provider_{p.id}")
        assert job is not None
        p.enabled = False
        db.session.commit()
        reschedule_provider(p)
        job = sched_mod._scheduler.get_job(f"provider_{p.id}")
        assert job is None
        sched_mod._scheduler.shutdown(wait=False)


def test_remove_provider_schedule(app):
    with app.app_context():
        sched_mod._scheduler = init_scheduler(app)
        p = create_provider("Remove", "https://example.com/clash.yaml", {
            "type": "daily", "time_of_day": "10:00"
        })
        reschedule_provider(p)
        job = sched_mod._scheduler.get_job(f"provider_{p.id}")
        assert job is not None
        remove_provider_schedule(p.id)
        job = sched_mod._scheduler.get_job(f"provider_{p.id}")
        assert job is None
        sched_mod._scheduler.shutdown(wait=False)

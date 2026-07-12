from app.extensions import db
from app.models.provider import Provider, SubscriptionVersion, UpdateRun
from app.repositories import provider_repo


def test_create_provider(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Test Provider",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "daily", "time_of_day": "08:00"},
        )
        assert p.id is not None
        assert p.name == "Test Provider"
        assert len(p.public_token) == 32
        assert p.schedule_type == "daily"
        assert p.schedule_time_of_day == "08:00"


def test_get_provider(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Get Test",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        fetched = provider_repo.get_provider(p.id)
        assert fetched.name == "Get Test"


def test_get_provider_by_token(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Token Test",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        fetched = provider_repo.get_provider_by_token(p.public_token)
        assert fetched.id == p.id


def test_update_provider(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Old Name",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        updated = provider_repo.update_provider(p, {
            "name": "New Name",
            "schedule": {"type": "weekly", "day_of_week": 1, "time_of_day": "09:00"},
        })
        assert updated.name == "New Name"
        assert updated.schedule_type == "weekly"
        assert updated.schedule_day_of_week == 1


def test_delete_provider(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Delete Me",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        pid = p.id
        provider_repo.delete_provider(p)
        assert provider_repo.get_provider(pid) is None


def test_token_rotation(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Rotate",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        old_token = p.public_token
        p.rotate_token()
        db.session.commit()
        assert p.public_token != old_token
        assert len(p.public_token) == 32


def test_version_lifecycle(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="Versioned",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        v1 = provider_repo.create_version(
            p.id, 1, "hash1", "chash1", "/raw/1", "/converted/1", 10
        )
        v2 = provider_repo.create_version(
            p.id, 2, "hash2", "chash2", "/raw/2", "/converted/2", 12
        )
        current = provider_repo.get_current_version(p.id)
        assert current.sequence == 2
        versions = provider_repo.get_versions(p.id, limit=5)
        assert len(versions) == 2


def test_update_run_lifecycle(app):
    with app.app_context():
        p = provider_repo.create_provider(
            name="RunTest",
            source_url="https://example.com/clash.yaml",
            schedule={"type": "disabled"},
        )
        run = provider_repo.create_update_run(p.id, "manual")
        assert run.stage == "querying"
        assert run.status == "running"
        provider_repo.update_run_stage(run, "received", "Got response")
        assert run.stage == "received"
        provider_repo.complete_update_run(run, "success", "Done")
        assert run.status == "success"
        assert run.completed_at is not None

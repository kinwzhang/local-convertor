import os
import shutil

from app.extensions import db
from app.models.provider import Provider
from app.repositories.provider_repo import create_provider
from app.services.version_store import VersionStore


def _make_store(app):
    return VersionStore(
        subscriptions_dir=app.config["SUBSCRIPTIONS_DIR"],
        retention_count=5,
    )


def test_store_and_retrieve(app):
    with app.app_context():
        p = create_provider("VS Test", "https://example.com/clash.yaml", {"type": "disabled"})
        store = _make_store(app)
        raw = b"proxies:\n  - name: test\n    type: ss\n    server: 1.2.3.4\n    port: 443\n    cipher: aes-256-gcm\n    password: pass"
        converted = b"ss://test@1.2.3.4:443#test"
        v = store.store_version(p.id, raw, converted)
        assert v.sequence == 1
        assert len(v.raw_hash) == 64
        assert store.get_current(p.id) == converted
        assert store.get_current_raw(p.id) == raw


def test_multiple_versions_increment(app):
    with app.app_context():
        p = create_provider("VS Multi", "https://example.com/clash.yaml", {"type": "disabled"})
        store = _make_store(app)
        for i in range(3):
            raw = f"raw-{i}".encode()
            converted = f"converted-{i}".encode()
            v = store.store_version(p.id, raw, converted)
            assert v.sequence == i + 1
        assert store.get_current(p.id) == b"converted-2"


def test_prune_old_versions(app):
    with app.app_context():
        p = create_provider("VS Prune", "https://example.com/clash.yaml", {"type": "disabled"})
        store = _make_store(app)
        for i in range(8):
            raw = f"raw-{i}".encode()
            converted = f"converted-{i}".encode()
            store.store_version(p.id, raw, converted)
        versions = db.session.query(
            __import__("app.models.provider", fromlist=["SubscriptionVersion"]).SubscriptionVersion
        ).filter_by(provider_id=p.id).all()
        assert len(versions) <= 5


def test_content_hash_unchanged(app):
    with app.app_context():
        p = create_provider("VS Hash", "https://example.com/clash.yaml", {"type": "disabled"})
        store = _make_store(app)
        raw = b"same content"
        converted = b"same converted"
        v1 = store.store_version(p.id, raw, converted)
        assert store.get_current_hash(p.id) == v1.converted_hash


def test_delete_provider_files(app):
    with app.app_context():
        p = create_provider("VS Delete", "https://example.com/clash.yaml", {"type": "disabled"})
        store = _make_store(app)
        store.store_version(p.id, b"raw", b"converted")
        pdir = os.path.join(app.config["SUBSCRIPTIONS_DIR"], str(p.id))
        assert os.path.exists(pdir)
        store.delete_provider_files(p.id)
        assert not os.path.exists(pdir)

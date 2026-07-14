import os
import shutil

from app.extensions import db
from app.models.provider import Provider, SubscriptionVersion
from app.repositories.provider_repo import create_provider
from app.services.version_store import VersionStore, slugify, _provider_dir_name, migrate_naming


def _make_store(app):
    return VersionStore(
        subscriptions_dir=app.config["SUBSCRIPTIONS_DIR"],
        retention_count=5,
    )


def _dir_for(app, provider):
    return os.path.join(
        app.config["SUBSCRIPTIONS_DIR"],
        _provider_dir_name(provider.id, provider.name),
    )


def test_slugify_lowercases_and_collapses():
    assert slugify("My HK VPN") == "my-hk-vpn"


def test_slugify_strips_punctuation_and_truncates():
    assert slugify("  --@@weird!!name@@--  ") == "weird-name"
    long = slugify("a" * 100 + "!" * 100)
    assert len(long) <= 32


def test_slugify_falls_back_when_empty():
    assert slugify("") == ""
    assert slugify("!!!") == "provider"


def _make_provider(app, name="VS Test"):
    return create_provider(name, "https://example.com/clash.yaml", {"type": "disabled"})


def test_store_and_retrieve(app):
    with app.app_context():
        p = _make_provider(app, "VS Test Retrieve")
        store = _make_store(app)
        raw = b"proxies:\n  - name: test\n    type: ss\n    server: 1.2.3.4\n    port: 443\n    cipher: aes-256-gcm\n    password: pass"
        converted = b"ss://test@1.2.3.4:443#test"
        v = store.store_version(p.id, p.name, raw, converted)
        assert v.sequence == 1
        assert len(v.raw_hash) == 64
        assert store.get_current(p.id) == converted
        assert store.get_current_raw(p.id) == raw


def test_directory_naming_uses_provider_slug_and_id(app):
    with app.app_context():
        p = _make_provider(app, "VS Multi")
        store = _make_store(app)
        store.store_version(p.id, p.name, b"raw", b"converted")
        # Directory uses slug-id format, not just an integer id.
        pdir = _dir_for(app, p)
        assert os.path.isdir(pdir), f"expected {pdir} to exist"


def test_iteration_cycles_mod_ten(app):
    with app.app_context():
        p = _make_provider(app, "VS Cycle")
        store = _make_store(app)
        for i in range(12):
            raw = f"raw-{i}".encode()
            converted = f"converted-{i}".encode()
            v = store.store_version(p.id, p.name, raw, converted)
            expected_iter = str((i + 1) % 10)
            assert os.path.basename(v.raw_path) == f"{expected_iter}_raw.yaml"
            assert os.path.basename(v.converted_path) == f"{expected_iter}_converted.txt"


def test_multiple_versions_increment(app):
    with app.app_context():
        p = _make_provider(app, "VS Multi Inc")
        store = _make_store(app)
        for i in range(3):
            raw = f"raw-{i}".encode()
            converted = f"converted-{i}".encode()
            v = store.store_version(p.id, p.name, raw, converted)
            assert v.sequence == i + 1
        assert store.get_current(p.id) == b"converted-2"


def test_prune_old_versions(app):
    with app.app_context():
        p = _make_provider(app, "VS Prune")
        store = _make_store(app)
        for i in range(8):
            store.store_version(p.id, p.name, f"raw-{i}".encode(), f"converted-{i}".encode())
        versions = db.session.query(SubscriptionVersion).filter_by(provider_id=p.id).all()
        assert len(versions) <= 5


def test_content_hash_unchanged(app):
    with app.app_context():
        p = _make_provider(app, "VS Hash")
        store = _make_store(app)
        v1 = store.store_version(p.id, p.name, b"same content", b"same converted")
        assert store.get_current_hash(p.id) == v1.converted_hash


def test_delete_provider_files(app):
    with app.app_context():
        p = _make_provider(app, "VS Delete")
        store = _make_store(app)
        store.store_version(p.id, p.name, b"raw", b"converted")
        pdir = _dir_for(app, p)
        assert os.path.exists(pdir)
        store.delete_provider_files(p.id, p.name)
        assert not os.path.exists(pdir)


def test_migrate_naming_renames_existing_files(app):
    """migrate_naming rewrites legacy <seq>_ files to <seq%10>_ and updates DB paths."""
    with app.app_context():
        p = _make_provider(app, "Legacy Provider")
        store = _make_store(app)
        # Simulate a legacy on-disk layout: integer-id directory + sequence-numbered files.
        legacy_dir = os.path.join(app.config["SUBSCRIPTIONS_DIR"], str(p.id))
        os.makedirs(legacy_dir, exist_ok=True)
        legacy_raw = os.path.join(legacy_dir, "1_raw.yaml")
        legacy_converted = os.path.join(legacy_dir, "1_converted.txt")
        with open(legacy_raw, "wb") as f:
            f.write(b"legacy raw")
        with open(legacy_converted, "wb") as f:
            f.write(b"legacy converted")
        # Persist a SubscriptionVersion row pointing at the legacy paths.
        v = SubscriptionVersion(
            provider_id=p.id,
            sequence=1,
            raw_hash="0" * 64,
            converted_hash="1" * 64,
            raw_path=legacy_raw,
            converted_path=legacy_converted,
            node_count=1,
        )
        db.session.add(v)
        db.session.commit()

        migrate_naming(app)

        new_pdir = _dir_for(app, p)
        new_raw = os.path.join(new_pdir, "1_raw.yaml")
        new_converted = os.path.join(new_pdir, "1_converted.txt")
        assert os.path.exists(new_raw)
        assert os.path.exists(new_converted)
        assert open(new_raw, "rb").read() == b"legacy raw"
        # The DB row should now point at the new paths.
        db.session.refresh(v)
        assert v.raw_path == new_raw
        assert v.converted_path == new_converted
        # Legacy integer-id directory should be empty or absent.
        leftovers = os.listdir(legacy_dir) if os.path.exists(legacy_dir) else []
        assert leftovers == [], f"legacy directory still has: {leftovers}"

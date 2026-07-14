"""Subscription file storage.

Files live under `DATA_DIR/subscriptions/<slug>-<id>/`. The `<slug>` is a
URL-safe, lower-cased form of `provider.name` (the user-supplied name), and
`<id>` is the database primary key. Including the id guarantees uniqueness
even if two providers share the same name.

Files inside use an iteration counter that cycles 0..9: `<iter>_raw.yaml`,
`<iter>_converted.txt`, with `iter = sequence % 10`. The sequence column on
`SubscriptionVersion` continues to be monotonic; we just project it onto a
10-slot on-disk ring so the directory only ever carries at most 10 raw and
10 converted pairs. Older versions are reclaimed by the on-disk cycle, not
by `_prune`.

Migration: see `migrate_naming` below. It rewrites file names and
`SubscriptionVersion.raw_path` / `converted_path` at app startup, idempotently.
"""
import hashlib
import os
import re
import tempfile

from app.extensions import db
from app.models.provider import Provider, SubscriptionVersion
from app.repositories.provider_repo import (
    get_current_version,
    get_versions,
    create_version,
    delete_version,
    list_providers,
)


def slugify(name):
    """Return a URL-safe, lower-cased slug of `name`.

    Replaces any non-`[a-z0-9]` run with `-`, trims, and caps at 32 chars.
    Returns "provider" if `name` is empty or only punctuation.
    """
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:32] or "provider"


def _provider_dir_name(provider_id, provider_name=None):
    """Compute the per-provider directory name: `<slug>-<id>`."""
    slug = slugify(provider_name) if provider_name else ""
    if not slug:
        slug = "provider"
    return f"{slug}-{provider_id}"


class VersionStore:
    def __init__(self, subscriptions_dir, retention_count=5):
        self.subscriptions_dir = subscriptions_dir
        self.retention_count = retention_count

    def _provider_dir(self, provider_id, provider_name=None):
        d = os.path.join(
            self.subscriptions_dir,
            _provider_dir_name(provider_id, provider_name),
        )
        os.makedirs(d, exist_ok=True)
        return d

    def _write_atomic(self, path, data):
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def store_version(self, provider_id, provider_name, raw_bytes, converted_bytes):
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        converted_hash = hashlib.sha256(converted_bytes).hexdigest()

        current = get_current_version(provider_id)
        next_seq = (current.sequence + 1) if current else 1

        pdir = self._provider_dir(provider_id, provider_name)
        iter_slot = str(next_seq % 10)
        raw_path = os.path.join(pdir, f"{iter_slot}_raw.yaml")
        converted_path = os.path.join(pdir, f"{iter_slot}_converted.txt")

        self._write_atomic(raw_path, raw_bytes)
        try:
            self._write_atomic(converted_path, converted_bytes)
        except BaseException:
            if os.path.exists(raw_path):
                os.unlink(raw_path)
            raise

        node_count = converted_bytes.strip().count(b"\n") + (1 if converted_bytes.strip() else 0)

        try:
            version = create_version(
                provider_id=provider_id,
                sequence=next_seq,
                raw_hash=raw_hash,
                converted_hash=converted_hash,
                raw_path=raw_path,
                converted_path=converted_path,
                node_count=node_count,
            )
        except BaseException:
            if os.path.exists(raw_path):
                os.unlink(raw_path)
            if os.path.exists(converted_path):
                os.unlink(converted_path)
            raise

        self._prune(provider_id)
        return version

    def get_current(self, provider_id):
        version = get_current_version(provider_id)
        if not version:
            return None
        with open(version.converted_path, "rb") as f:
            return f.read()

    def get_current_hash(self, provider_id):
        version = get_current_version(provider_id)
        return version.converted_hash if version else None

    def get_current_raw(self, provider_id):
        version = get_current_version(provider_id)
        if not version:
            return None
        with open(version.raw_path, "rb") as f:
            return f.read()

    def get_current_raw_hash(self, provider_id):
        version = get_current_version(provider_id)
        return version.raw_hash if version else None

    def _prune(self, provider_id):
        # The on-disk cycle handles file GC; we only trim the DB row count.
        versions = get_versions(provider_id, limit=self.retention_count + 10)
        if len(versions) <= self.retention_count:
            return
        for v in versions[self.retention_count:]:
            delete_version(v)

    def read_file(self, path):
        with open(path, "rb") as f:
            return f.read()

    def delete_provider_files(self, provider_id, provider_name=None):
        pdir = self._provider_dir(provider_id, provider_name)
        if os.path.exists(pdir):
            import shutil
            shutil.rmtree(pdir)


def migrate_naming(app):
    """Migrate on-disk subscription files to the new naming scheme.

    For every `Provider`, list its `SubscriptionVersion` rows ordered by
    sequence. Rename each row's files from `<seq>_raw.yaml` /
    `<seq>_converted.txt` to `<seq % 10>_raw.yaml` /
    `<seq % 10>_converted.txt` and update the DB columns to the new absolute
    paths. If the per-provider directory does not exist (provider was
    created but never refreshed), there is nothing to migrate.

    Idempotent: running it twice is safe because the second invocation
    finds `<seq % 10>_...` patterns and sees that the renamed files are
    already there. Mismatches between the DB-recorded path and the on-disk
    path are reconciled at every step.
    """
    subs_dir = app.config["SUBSCRIPTIONS_DIR"]
    vs = VersionStore(subs_dir)
    with app.app_context():
        for provider in list_providers():
            new_pdir = vs._provider_dir(provider.id, provider.name)
            rows = (
                db.session.query(SubscriptionVersion)
                .filter(SubscriptionVersion.provider_id == provider.id)
                .order_by(SubscriptionVersion.sequence.asc())
                .all()
            )
            if not rows:
                continue
            for v in rows:
                _migrate_version_files(v, new_pdir)
            db.session.commit()


def _migrate_version_files(version, target_dir):
    """Rename one version's files into `target_dir` if needed; update paths."""
    seq = version.sequence
    new_iter = str(seq % 10)
    new_raw = os.path.join(target_dir, f"{new_iter}_raw.yaml")
    new_converted = os.path.join(target_dir, f"{new_iter}_converted.txt")

    old_raw = version.raw_path or ""
    old_converted = version.converted_path or ""

    # If the recorded path already points at the target slot, nothing to do.
    if old_raw == new_raw and old_converted == new_converted:
        return

    # If the file lives somewhere else (legacy naming), move it.
    if old_raw and os.path.exists(old_raw) and old_raw != new_raw:
        os.makedirs(os.path.dirname(new_raw), exist_ok=True)
        try:
            os.rename(old_raw, new_raw)
        except OSError:
            # Destination already exists (rotation collision) — overwrite.
            try:
                os.replace(old_raw, new_raw)
            except OSError:
                pass

    if old_converted and os.path.exists(old_converted) and old_converted != new_converted:
        os.makedirs(os.path.dirname(new_converted), exist_ok=True)
        try:
            os.rename(old_converted, new_converted)
        except OSError:
            try:
                os.replace(old_converted, new_converted)
            except OSError:
                pass

    version.raw_path = new_raw
    version.converted_path = new_converted

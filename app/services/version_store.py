import hashlib
import os
import tempfile

from app.extensions import db
from app.models.provider import SubscriptionVersion
from app.repositories.provider_repo import get_current_version, get_versions, create_version, delete_version


class VersionStore:
    def __init__(self, subscriptions_dir, retention_count=5):
        self.subscriptions_dir = subscriptions_dir
        self.retention_count = retention_count

    def _provider_dir(self, provider_id):
        d = os.path.join(self.subscriptions_dir, str(provider_id))
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

    def store_version(self, provider_id, raw_bytes, converted_bytes):
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        converted_hash = hashlib.sha256(converted_bytes).hexdigest()

        current = get_current_version(provider_id)
        next_seq = (current.sequence + 1) if current else 1

        pdir = self._provider_dir(provider_id)
        raw_path = os.path.join(pdir, f"{next_seq}_raw.yaml")
        converted_path = os.path.join(pdir, f"{next_seq}_converted.txt")

        self._write_atomic(raw_path, raw_bytes)
        self._write_atomic(converted_path, converted_bytes)

        node_count = converted_bytes.strip().count(b"\n") + (1 if converted_bytes.strip() else 0)

        version = create_version(
            provider_id=provider_id,
            sequence=next_seq,
            raw_hash=raw_hash,
            converted_hash=converted_hash,
            raw_path=raw_path,
            converted_path=converted_path,
            node_count=node_count,
        )

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
        versions = get_versions(provider_id, limit=self.retention_count + 10)
        if len(versions) <= self.retention_count:
            return
        to_delete = versions[self.retention_count:]
        for v in to_delete:
            for path in (v.raw_path, v.converted_path):
                if os.path.exists(path):
                    os.unlink(path)
            delete_version(v)

    def read_file(self, path):
        with open(path, "rb") as f:
            return f.read()

    def delete_provider_files(self, provider_id):
        pdir = self._provider_dir(provider_id)
        if os.path.exists(pdir):
            import shutil
            shutil.rmtree(pdir)

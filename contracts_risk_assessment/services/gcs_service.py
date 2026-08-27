"""GCS + local filesystem artifact storage."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..config import (
    CONTRACTS_DIR,
    GCS_BUCKET_NAME,
    GOOGLE_CLOUD_PROJECT,
    LOCAL_STORE_DIR,
    REPORTS_DIR,
    USE_MOCK_GCP,
)


class ArtifactStore:
    """Upload/download contract DOCX and risk PDF artifacts."""

    def __init__(self) -> None:
        self.use_mock = USE_MOCK_GCP or not GCS_BUCKET_NAME
        CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        LOCAL_STORE_DIR.mkdir(parents=True, exist_ok=True)
        self._bucket = None
        if not self.use_mock:
            from google.cloud import storage

            client = storage.Client(project=GOOGLE_CLOUD_PROJECT or None)
            self._bucket = client.bucket(GCS_BUCKET_NAME)

    def upload_file(
        self,
        local_path: str | Path,
        *,
        session_id: str,
        artifact_type: str,
        filename: Optional[str] = None,
    ) -> dict[str, str]:
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Artifact not found: {src}")
        name = filename or src.name
        object_key = f"sessions/{session_id}/{artifact_type}/{name}"

        if self.use_mock:
            dest = LOCAL_STORE_DIR / object_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return {
                "uri": f"file://{dest.resolve()}",
                "path": str(dest.resolve()),
                "object_key": object_key,
            }

        blob = self._bucket.blob(object_key)  # type: ignore[union-attr]
        blob.upload_from_filename(str(src))
        uri = f"gs://{GCS_BUCKET_NAME}/{object_key}"
        # Also keep a local mirror for FastAPI downloads
        mirror = LOCAL_STORE_DIR / object_key
        mirror.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, mirror)
        return {"uri": uri, "path": str(mirror.resolve()), "object_key": object_key}

    def download_to_path(self, uri_or_path: str, dest: str | Path) -> Path:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if uri_or_path.startswith("file://"):
            src = Path(urlparse(uri_or_path).path)
            # Windows file:// URLs may look like /C:/...
            if src.as_posix().startswith("/") and len(src.parts) > 1 and src.parts[0] == "/":
                maybe = Path(uri_or_path.replace("file:///", "").replace("file://", ""))
                if maybe.exists():
                    src = maybe
            shutil.copy2(src, dest_path)
            return dest_path

        if uri_or_path.startswith("gs://"):
            if self.use_mock:
                raise RuntimeError("Received gs:// URI but USE_MOCK_GCP is enabled")
            _, _, rest = uri_or_path.partition("gs://")
            bucket_name, _, object_key = rest.partition("/")
            from google.cloud import storage

            client = storage.Client(project=GOOGLE_CLOUD_PROJECT or None)
            blob = client.bucket(bucket_name).blob(object_key)
            blob.download_to_filename(str(dest_path))
            return dest_path

        src = Path(uri_or_path)
        if not src.exists():
            raise FileNotFoundError(uri_or_path)
        shutil.copy2(src, dest_path)
        return dest_path


_artifact_store: Optional[ArtifactStore] = None


def get_artifact_store() -> ArtifactStore:
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore()
    return _artifact_store

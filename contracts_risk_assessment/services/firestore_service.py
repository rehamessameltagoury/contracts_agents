"""Firestore + local JSON persistence for negotiation sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import (
    FIRESTORE_COLLECTION,
    GOOGLE_CLOUD_PROJECT,
    LOCAL_STORE_DIR,
    USE_MOCK_GCP,
)
from ..models import NegotiationSession, utc_now_iso


class SessionRepository:
    """CRUD for negotiation sessions (Firestore or local JSON)."""

    def __init__(self) -> None:
        self.use_mock = USE_MOCK_GCP or not GOOGLE_CLOUD_PROJECT
        self._local_dir = LOCAL_STORE_DIR / "firestore" / FIRESTORE_COLLECTION
        self._local_dir.mkdir(parents=True, exist_ok=True)
        self._db = None
        if not self.use_mock:
            from google.cloud import firestore

            self._db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)

    def _local_path(self, session_id: str) -> Path:
        return self._local_dir / f"{session_id}.json"

    def save(self, session: NegotiationSession) -> NegotiationSession:
        session.touch()
        payload = session.model_dump()
        if self.use_mock:
            self._local_path(session.session_id).write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
            return session

        self._db.collection(FIRESTORE_COLLECTION).document(session.session_id).set(payload)  # type: ignore[union-attr]
        return session

    def get(self, session_id: str) -> Optional[NegotiationSession]:
        if self.use_mock:
            path = self._local_path(session_id)
            if not path.exists():
                return None
            return NegotiationSession.model_validate_json(path.read_text(encoding="utf-8"))

        doc = self._db.collection(FIRESTORE_COLLECTION).document(session_id).get()  # type: ignore[union-attr]
        if not doc.exists:
            return None
        return NegotiationSession.model_validate(doc.to_dict())

    def update_summary(self, session_id: str, summary: str) -> NegotiationSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        session.summary = summary
        session.last_updated = utc_now_iso()
        return self.save(session)

    def list_sessions(self, limit: int = 50) -> list[NegotiationSession]:
        if self.use_mock:
            sessions: list[NegotiationSession] = []
            for path in sorted(self._local_dir.glob("*.json"), reverse=True)[:limit]:
                sessions.append(
                    NegotiationSession.model_validate_json(path.read_text(encoding="utf-8"))
                )
            return sessions

        docs = (
            self._db.collection(FIRESTORE_COLLECTION)  # type: ignore[union-attr]
            .order_by("last_updated", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [NegotiationSession.model_validate(d.to_dict()) for d in docs]


_repo: Optional[SessionRepository] = None


def get_session_repo() -> SessionRepository:
    global _repo
    if _repo is None:
        _repo = SessionRepository()
    return _repo

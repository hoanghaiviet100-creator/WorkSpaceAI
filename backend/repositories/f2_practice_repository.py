"""Process-local practice sessions. Private keys never belong in learner DTOs.

The service holds transaction() through read/check/update. This serializes
in-process actions only; it does not lock the independent source repository.
No persistence, global singleton, TTL or multi-worker coordination is provided.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock

from backend.core.f2_practice_schemas import QuizSubmission
from backend.core.f2_study_schemas import FlashcardDeck, QuizSet


@dataclass(frozen=True)
class QuizPracticeSession:
    session_id: str
    workspace_id: str
    learner_id: str
    quiz: QuizSet
    resource_digest: str
    source_snapshot_digest: str
    submission: QuizSubmission | None = None


@dataclass(frozen=True)
class FlashcardPracticeSession:
    session_id: str
    workspace_id: str
    learner_id: str
    deck: FlashcardDeck
    resource_digest: str
    source_snapshot_digest: str
    current_index: int = 0
    revealed: bool = False


PracticeSession = QuizPracticeSession | FlashcardPracticeSession


class InMemoryPracticeRepository:
    def __init__(self):
        self._sessions: dict[str, PracticeSession] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        with self._lock:
            yield

    def get(self, session_id: str) -> PracticeSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def create(self, session: PracticeSession) -> None:
        with self._lock:
            if session.session_id in self._sessions:
                raise ValueError("session already exists")
            self._sessions[session.session_id] = session

    def replace(self, session: PracticeSession) -> None:
        with self._lock:
            if session.session_id not in self._sessions:
                raise ValueError("session does not exist")
            self._sessions[session.session_id] = session

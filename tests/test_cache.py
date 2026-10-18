from __future__ import annotations

from app.models import InternalNote
from app.services.cache import ResultCache


def _note(note_id: str) -> InternalNote:
    return InternalNote(note_id, None, "image", (), (), None)


def test_ttl_and_lru_capacity() -> None:
    now = 0.0
    cache = ResultCache(10, 2, clock=lambda: now)
    cache.put("a", _note("a" * 24))
    cache.put("b", _note("b" * 24))
    assert cache.get("a") is not None
    cache.put("c", _note("c" * 24))
    assert cache.get("b") is None
    now = 11.0
    assert cache.get("a") is None
    assert len(cache) == 0

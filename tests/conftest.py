"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def kafka_off_for_unit_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force inline spawn dispatch in tests (no broker consumer in pytest)."""

    monkeypatch.delenv("KAFKA_BOOTSTRAP", raising=False)

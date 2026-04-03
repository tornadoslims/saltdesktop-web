"""Tests for retry logic and mission lifecycle."""
from __future__ import annotations

import pytest
from tests.conftest import make_task

from runtime.jb_queue import (
    enqueue, get_task, get_retryable, retry_task,
    mark_dispatched, mark_failed, mark_complete,
)


class TestGetRetryable:
    def test_empty(self, tmp_data):
        assert get_retryable() == []

    def test_failed_with_retries_left(self, tmp_data):
        tid = enqueue(make_task())
        mark_failed(tid, error="boom")
        retryable = get_retryable()
        assert len(retryable) == 1
        assert retryable[0]["id"] == tid

    def test_failed_exhausted(self, tmp_data):
        tid = enqueue(make_task(max_retries=1))
        mark_failed(tid, error="boom")  # retry_count = 1, max_retries = 1
        assert get_retryable() == []

    def test_completed_not_retryable(self, tmp_data):
        tid = enqueue(make_task())
        mark_complete(tid)
        assert get_retryable() == []

    def test_pending_not_retryable(self, tmp_data):
        enqueue(make_task())
        assert get_retryable() == []

    def test_multiple_failures_counted(self, tmp_data):
        tid = enqueue(make_task(max_retries=3))
        mark_failed(tid, error="first")   # retry_count = 1
        mark_failed(tid, error="second")  # retry_count = 2
        retryable = get_retryable()
        assert len(retryable) == 1
        assert retryable[0]["retry_count"] == 2

    def test_exhausted_after_max(self, tmp_data):
        tid = enqueue(make_task(max_retries=2))
        mark_failed(tid, error="first")   # 1
        mark_failed(tid, error="second")  # 2
        assert get_retryable() == []


class TestRetryTask:
    def test_retry_moves_to_pending(self, tmp_data):
        tid = enqueue(make_task())
        mark_dispatched(tid)
        mark_failed(tid, error="boom")
        result = retry_task(tid)
        assert result["status"] == "pending"
        assert result["error"] is None
        assert result["assigned_to"] is None

    def test_retry_preserves_retry_count(self, tmp_data):
        tid = enqueue(make_task())
        mark_failed(tid, error="first")
        result = retry_task(tid)
        assert result["retry_count"] == 1  # preserves count

    def test_cannot_retry_pending(self, tmp_data):
        tid = enqueue(make_task())
        with pytest.raises(ValueError, match="failed"):
            retry_task(tid)

    def test_cannot_retry_complete(self, tmp_data):
        tid = enqueue(make_task())
        mark_complete(tid)
        with pytest.raises(ValueError, match="failed"):
            retry_task(tid)

    def test_cannot_retry_exhausted(self, tmp_data):
        tid = enqueue(make_task(max_retries=1))
        mark_failed(tid, error="boom")
        with pytest.raises(ValueError, match="exhausted"):
            retry_task(tid)

    def test_nonexistent_raises(self, tmp_data):
        with pytest.raises(ValueError, match="not found"):
            retry_task("nope")

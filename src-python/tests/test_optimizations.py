"""
Tests for performance optimization modules.
"""

import pytest
import asyncio
from app.core.optimizations import (
    EmbeddingCache,
    PriorityIndexQueue,
    BatchScheduler,
    SearchCache,
)


class TestEmbeddingCache:
    def test_put_and_get(self):
        cache = EmbeddingCache(max_size=100)
        cache.put("hello world", [0.1, 0.2, 0.3])
        result = cache.get("hello world")
        assert result == [0.1, 0.2, 0.3]

    def test_cache_miss(self):
        cache = EmbeddingCache(max_size=100)
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self):
        cache = EmbeddingCache(max_size=3)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        cache.put("d", [4.0])  # Should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == [2.0]

    def test_lru_touch_on_get(self):
        cache = EmbeddingCache(max_size=3)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        cache.get("a")  # Touch "a" → now "b" is oldest
        cache.put("d", [4.0])  # Should evict "b"
        assert cache.get("a") == [1.0]
        assert cache.get("b") is None

    def test_batch_get(self):
        cache = EmbeddingCache(max_size=100)
        cache.put("x", [1.0])
        cache.put("z", [3.0])

        results, misses = cache.get_batch(["x", "y", "z"])
        assert results[0] == [1.0]
        assert results[1] is None
        assert results[2] == [3.0]
        assert misses == [1]

    def test_hit_rate(self):
        cache = EmbeddingCache()
        cache.put("a", [1.0])
        cache.get("a")   # hit
        cache.get("a")   # hit
        cache.get("b")   # miss
        assert cache.hit_rate == pytest.approx(2 / 3, abs=0.01)

    def test_stats(self):
        cache = EmbeddingCache(max_size=1000)
        cache.put("a", [1.0])
        cache.get("a")
        cache.get("b")
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_clear(self):
        cache = EmbeddingCache()
        cache.put("a", [1.0])
        cache.clear()
        assert cache.size == 0
        assert cache.get("a") is None


class TestPriorityIndexQueue:
    @pytest.mark.asyncio
    async def test_put_and_get(self, tmp_path):
        queue = PriorityIndexQueue()
        f = tmp_path / "test.pdf"
        f.write_text("test")
        await queue.put(str(f))
        assert queue.size == 1
        job = await queue.get()
        assert job is not None
        assert job.file_path == str(f)
        assert queue.size == 0

    @pytest.mark.asyncio
    async def test_dedup(self, tmp_path):
        queue = PriorityIndexQueue()
        f = tmp_path / "test.txt"
        f.write_text("test")
        await queue.put(str(f))
        await queue.put(str(f))  # Duplicate
        assert queue.size == 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self, tmp_path):
        queue = PriorityIndexQueue()

        pdf = tmp_path / "doc.pdf"
        pdf.write_text("pdf content")
        conf = tmp_path / "config.yaml"
        conf.write_text("yaml content")

        await queue.put(str(conf))
        await queue.put(str(pdf))

        # PDF should come first (priority 1 < yaml priority 4)
        first = await queue.get()
        assert first is not None
        assert first.file_path == str(pdf)

    @pytest.mark.asyncio
    async def test_empty_queue(self):
        queue = PriorityIndexQueue()
        assert queue.is_empty
        assert await queue.get() is None


class TestBatchScheduler:
    @pytest.mark.asyncio
    async def test_add_and_flush(self):
        scheduler = BatchScheduler(batch_size=10)
        await scheduler.add("/file1.txt", ["chunk1", "chunk2"])
        await scheduler.add("/file2.txt", ["chunk3"])
        assert scheduler.pending_count == 3

        items = await scheduler.flush()
        assert len(items) == 2
        assert scheduler.pending_count == 0

    @pytest.mark.asyncio
    async def test_should_flush(self):
        scheduler = BatchScheduler(batch_size=3)
        await scheduler.add("/file.txt", ["a", "b"])
        assert not await scheduler.should_flush()
        await scheduler.add("/file2.txt", ["c"])
        assert await scheduler.should_flush()


class TestSearchCache:
    def test_put_and_get(self):
        cache = SearchCache(ttl_seconds=60)
        cache.put("test query", [{"result": 1}])
        assert cache.get("test query") == [{"result": 1}]

    def test_case_insensitive(self):
        cache = SearchCache()
        cache.put("Hello World", [1])
        assert cache.get("hello world") == [1]
        assert cache.get("  HELLO WORLD  ") == [1]

    def test_ttl_expiry(self):
        cache = SearchCache(ttl_seconds=0)  # Immediate expiry
        cache.put("query", [1])
        import time
        time.sleep(0.01)
        assert cache.get("query") is None

    def test_invalidate(self):
        cache = SearchCache()
        cache.put("a", [1])
        cache.put("b", [2])
        cache.invalidate()
        assert cache.get("a") is None
        assert cache.get("b") is None

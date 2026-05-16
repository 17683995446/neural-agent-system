"""
Tests for scalability optimization components
"""
import time
from pathlib import Path

from app.core.ast_cache import ASTCache
from app.core.llm_rate_limiter import LLMRateLimiter
from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.llm_cache import LLMResponseCache
from app.core.scalability_profile import ScalabilityProfile
from app.services.convolution.module_partitioner import Module
from app.services.convolution.change_detector import ChangeDetector
from app.services.pooling.hierarchical_compressor import HierarchicalCompressor
from app.services.fullconnect.modification_graph import ModificationDependencyGraph
from app.services.fullconnect.smart_context import SmartContextWindow


class TestASTCache:
    def test_basic_cache(self, tmp_path):
        cache = ASTCache(cache_dir=str(tmp_path / "ast"), max_memory=10)
        call_count = 0

        def parser(f):
            nonlocal call_count
            call_count += 1
            return f.read_text()

        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        result1 = cache.get_or_parse(test_file, parser)
        assert result1 == "def hello(): pass"
        assert call_count == 1

        result2 = cache.get_or_parse(test_file, parser)
        assert result2 == "def hello(): pass"
        assert call_count == 1

    def test_invalidate(self, tmp_path):
        cache = ASTCache(cache_dir=str(tmp_path / "ast"), max_memory=10)
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")
        cache.get_or_parse(test_file, lambda f: f.read_text())
        cache.invalidate(test_file)
        assert cache.stats["memory_entries"] == 0


class TestLLMRateLimiter:
    def test_singleton(self):
        inst1 = LLMRateLimiter.get_instance()
        inst2 = LLMRateLimiter.get_instance()
        assert inst1 is inst2

    def test_configure(self):
        LLMRateLimiter.configure(max_qps=10.0, max_concurrent=2)
        inst = LLMRateLimiter.get_instance()
        stats = inst.get_stats()
        assert stats["max_qps"] == 10.0
        assert stats["max_concurrent"] == 2
        LLMRateLimiter.configure(max_qps=3.0, max_concurrent=5)

    def test_acquire_release(self):
        limiter = LLMRateLimiter(max_qps=100.0, max_concurrent=1)
        assert limiter.acquire(timeout=1.0)
        limiter.release()


class TestCircuitBreaker:
    def test_closed_state(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        result = cb.call(lambda: 42, fallback=lambda: 0)
        assert result == 42

    def test_opens_after_failures(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        for _ in range(2):
            try:
                cb.call(lambda: 1 / 0)
            except ZeroDivisionError:
                pass
        assert cb.state == CircuitState.OPEN

    def test_fallback_when_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass
        result = cb.call(lambda: 42, fallback=lambda: 99)
        assert result == 99

    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        try:
            cb.call(lambda: 1 / 0)
        except ZeroDivisionError:
            pass
        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestLLMResponseCache:
    def test_put_get(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "hello"}]
        cache.put(msgs, "response")
        assert cache.get(msgs) == "response"

    def test_miss(self):
        cache = LLMResponseCache(ttl_seconds=60)
        assert cache.get([{"role": "user", "content": "miss"}]) is None

    def test_ttl_expiry(self):
        cache = LLMResponseCache(ttl_seconds=0.01)
        msgs = [{"role": "user", "content": "expire"}]
        cache.put(msgs, "old")
        time.sleep(0.02)
        assert cache.get(msgs) is None

    def test_stats(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "stat"}]
        cache.put(msgs, "val")
        cache.get(msgs)
        cache.get([{"role": "user", "content": "miss"}])
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_lru_eviction(self):
        cache = LLMResponseCache(ttl_seconds=60, max_size=2)
        cache.put([{"role": "u", "content": "1"}], "a")
        cache.put([{"role": "u", "content": "2"}], "b")
        cache.put([{"role": "u", "content": "3"}], "c")
        assert cache.get([{"role": "u", "content": "1"}]) is None


class TestModificationDependencyGraph:
    def test_single_file_serial(self):
        graph = ModificationDependencyGraph()
        mods = [
            {"file": "a.py", "target": "f1", "line": 10},
            {"file": "a.py", "target": "f2", "line": 20},
        ]
        plan = graph.build_execution_plan(mods)
        assert len(plan) >= 1

    def test_different_files_parallel(self):
        graph = ModificationDependencyGraph()
        mods = [
            {"file": "a.py", "target": "f1", "line": 10},
            {"file": "b.py", "target": "f2", "line": 5},
        ]
        plan = graph.build_execution_plan(mods)
        assert len(plan) >= 1

    def test_sequential_groups(self):
        batch = [
            {"_sequential_group": "a.py", "target": "f1"},
            {"_sequential_group": "a.py", "target": "f2"},
            {"_sequential_group": "b.py", "target": "f3"},
        ]
        groups = ModificationDependencyGraph.get_sequential_groups(batch)
        assert len(groups) == 2
        assert len(groups["a.py"]) == 2
        assert len(groups["b.py"]) == 1


class TestHierarchicalCompressor:
    def test_compress_basic(self):
        hc = HierarchicalCompressor(max_module_summaries=10, max_file_summaries=10, max_function_details=5)
        data = [
            {"file_path": "a.py", "functions": [{"name": "foo"}], "classes": [], "summary": "test"},
            {"file_path": "b.py", "functions": [], "classes": [{"name": "Bar"}], "summary": "test2"},
        ]
        out = hc.compress(data, user_requirement="foo")
        assert out.total_files_scanned == 2
        assert len(out.file_summaries) == 2

    def test_compress_with_modules(self):
        hc = HierarchicalCompressor()
        mod = Module(name="core", root=Path("."), files=[Path("a.py")], file_count=1)
        data = [{"file_path": "a.py", "functions": [], "classes": [], "summary": ""}]
        out = hc.compress(data, modules=[mod])
        assert out.total_modules == 1


class TestSmartContextWindow:
    def test_python_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("import os\n\ndef hello():\n    return 42\n")
        scw = SmartContextWindow(max_chars=4000)
        ctx = scw.get_context(f, "hello")
        assert "hello" in ctx
        assert "import os" in ctx

    def test_non_python_file(self, tmp_path):
        f = tmp_path / "test.js"
        f.write_text("function hello() { return 42; }\n" * 20)
        scw = SmartContextWindow(max_chars=1000)
        ctx = scw.get_context(f, "hello")
        assert len(ctx) > 0


class TestScalabilityProfile:
    def test_small_project(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text("pass")
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile["_profile"] == "SMALL"

    def test_detect_current(self):
        profile = ScalabilityProfile.detect(".")
        assert "_profile" in profile
        assert "_file_count" in profile


class TestChangeDetector:
    def test_detect_changes(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        cd = ChangeDetector(cache_dir=str(tmp_path / ".cache"))
        changes = cd.detect_changes(tmp_path)
        assert changes.total_files >= 1
        assert len(changes.changed_files) >= 1

    def test_incremental(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        cd = ChangeDetector(cache_dir=str(tmp_path / ".cache"))
        cd.detect_changes(tmp_path)
        changes = cd.detect_changes(tmp_path)
        assert len(changes.unchanged_files) >= 1

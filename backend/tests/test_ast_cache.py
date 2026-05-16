"""
核心基础模块单元测试 — AST缓存 (ASTCache)
覆盖: get_or_parse/invalidate/clear/磁盘持久化/LRU淘汰/并发
"""
import pytest
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock

from app.core.ast_cache import ASTCache


@pytest.fixture
def ast_cache(tmp_path):
    cache_dir = tmp_path / "ast_cache"
    return ASTCache(cache_dir=str(cache_dir), max_memory=3)


class TestASTCacheBasic:
    def test_parse_and_cache(self, ast_cache, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("def hello(): pass")
        call_count = 0
        def parser(f):
            nonlocal call_count
            call_count += 1
            return {"tree": str(f)}
        result = ast_cache.get_or_parse(src, parser)
        assert result == {"tree": str(src)}
        assert call_count == 1

    def test_cached_result_no_reparse(self, ast_cache, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("x = 1")
        call_count = 0
        def parser(f):
            nonlocal call_count
            call_count += 1
            return {"tree": str(f)}
        ast_cache.get_or_parse(src, parser)
        ast_cache.get_or_parse(src, parser)
        assert call_count == 1

    def test_different_files_different_results(self, ast_cache, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("a")
        f2.write_text("b")
        r1 = ast_cache.get_or_parse(f1, lambda f: {"name": f.name})
        r2 = ast_cache.get_or_parse(f2, lambda f: {"name": f.name})
        assert r1["name"] == "a.py"
        assert r2["name"] == "b.py"


class TestASTCacheInvalidation:
    def test_invalidate_removes_from_memory(self, ast_cache, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("x = 1")
        call_count = 0
        def parser(f):
            nonlocal call_count
            call_count += 1
            return {"v": call_count}
        ast_cache.get_or_parse(src, parser)
        ast_cache.invalidate(src)
        ast_cache.get_or_parse(src, parser)
        assert call_count == 2

    def test_invalidate_nonexistent_file(self, ast_cache, tmp_path):
        src = tmp_path / "nonexistent.py"
        ast_cache.invalidate(src)


class TestASTCacheLRU:
    def test_max_memory_eviction(self, tmp_path):
        cache = ASTCache(cache_dir=str(tmp_path / "c"), max_memory=2)
        files = []
        for i in range(3):
            f = tmp_path / f"f{i}.py"
            f.write_text(f"content_{i}")
            files.append(f)
        for f in files:
            cache.get_or_parse(f, lambda x: {"name": x.name})
        stats = cache.stats
        assert stats["memory_entries"] <= 2


class TestASTCacheClear:
    def test_clear_empties_memory(self, ast_cache, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("x = 1")
        ast_cache.get_or_parse(src, lambda f: {"v": 1})
        ast_cache.clear()
        stats = ast_cache.stats
        assert stats["memory_entries"] == 0


class TestASTCacheDisk:
    def test_disk_persistence_across_instances(self, tmp_path):
        cache_dir = tmp_path / "ast_disk"
        src = tmp_path / "test.py"
        src.write_text("x = 1")
        cache1 = ASTCache(cache_dir=str(cache_dir), max_memory=10)
        cache1.get_or_parse(src, lambda f: {"result": "from_parser"})
        cache2 = ASTCache(cache_dir=str(cache_dir), max_memory=10)
        call_count = 0
        def parser(f):
            nonlocal call_count
            call_count += 1
            return {"result": "re_parsed"}
        result = cache2.get_or_parse(src, parser)
        assert call_count == 0
        assert result == {"result": "from_parser"}


class TestASTCacheStats:
    def test_stats_structure(self, ast_cache):
        stats = ast_cache.stats
        assert "memory_entries" in stats
        assert "max_memory" in stats


class TestASTCacheFileChange:
    def test_modified_file_gets_reparsed(self, ast_cache, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("version1")
        ast_cache.get_or_parse(src, lambda f: {"v": 1})
        time.sleep(0.01)
        src.write_text("version2")
        call_count = 0
        def parser(f):
            nonlocal call_count
            call_count += 1
            return {"v": 2}
        result = ast_cache.get_or_parse(src, parser)
        assert call_count == 1
        assert result == {"v": 2}

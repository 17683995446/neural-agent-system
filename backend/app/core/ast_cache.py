"""
ASTCache — AST解析缓存 (内存+磁盘)
避免重复解析同一文件
"""
import hashlib
import pickle
import threading
from pathlib import Path
from typing import Any, Callable, Dict

from app.core.logging import logger
from app.core.safe_pickle import safe_dump_to_file, safe_load_from_file


class ASTCache:
    def __init__(self, cache_dir: str = ".cache/ast", max_memory: int = 500):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[str, Any] = {}
        self._max_memory = max_memory
        self._lock = threading.Lock()

    def get_or_parse(self, file_path: Path, parser_func: Callable[[Path], Any]) -> Any:
        try:
            file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
        except OSError:
            return parser_func(file_path)

        with self._lock:
            if file_hash in self._memory:
                return self._memory[file_hash]

        cache_file = self._cache_dir / f"{file_hash}.pkl"
        if cache_file.exists():
            tree = safe_load_from_file(cache_file)
            if tree is not None:
                with self._lock:
                    self._memory[file_hash] = tree
                return tree

        tree = parser_func(file_path)

        with self._lock:
            if len(self._memory) >= self._max_memory:
                oldest = next(iter(self._memory))
                del self._memory[oldest]
            self._memory[file_hash] = tree

        try:
            safe_dump_to_file(tree, cache_file)
        except Exception:
            logger.debug("ASTCache: failed to write disk cache for %s", file_path)

        return tree

    def invalidate(self, file_path: Path):
        try:
            file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
        except OSError:
            return
        with self._lock:
            self._memory.pop(file_hash, None)
        cache_file = self._cache_dir / f"{file_hash}.pkl"
        try:
            cache_file.unlink(missing_ok=True)
        except OSError:
            pass

    def clear(self):
        with self._lock:
            self._memory.clear()
        for f in self._cache_dir.glob("*.pkl"):
            try:
                f.unlink()
            except OSError:
                pass

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {"memory_entries": len(self._memory), "max_memory": self._max_memory}

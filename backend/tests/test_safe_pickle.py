"""
核心基础模块单元测试 — 安全序列化 (safe_pickle)
覆盖: safe_dumps/safe_loads/safe_dump_to_file/safe_load_from_file
场景: 正常/边界/异常/篡改
"""
import pytest
import tempfile
from pathlib import Path

from app.core.safe_pickle import safe_dumps, safe_loads, safe_dump_to_file, safe_load_from_file


class TestSafeDumpsLoads:
    def test_roundtrip_dict(self):
        obj = {"key": "value", "num": 42, "nested": {"a": [1, 2, 3]}}
        raw = safe_dumps(obj)
        result = safe_loads(raw)
        assert result == obj

    def test_roundtrip_list(self):
        obj = [1, "two", 3.0, None, True, False]
        assert safe_loads(safe_dumps(obj)) == obj

    def test_roundtrip_string(self):
        obj = "hello world 你好世界"
        assert safe_loads(safe_dumps(obj)) == obj

    def test_roundtrip_none(self):
        assert safe_loads(safe_dumps(None)) is None

    def test_roundtrip_empty(self):
        assert safe_loads(safe_dumps({})) == {}
        assert safe_loads(safe_dumps([])) == []
        assert safe_loads(safe_dumps("")) == ""

    def test_roundtrip_tuple(self):
        obj = (1, 2, 3)
        assert safe_loads(safe_dumps(obj)) == obj

    def test_roundtrip_set(self):
        obj = {1, 2, 3}
        result = safe_loads(safe_dumps(obj))
        assert result == obj

    def test_tampered_data_returns_none(self):
        raw = safe_dumps({"secret": 42})
        tampered = raw[:10] + b"X" + raw[11:]
        assert safe_loads(tampered) is None

    def test_missing_mac_separator(self):
        assert safe_loads(b"nocolondata") is None

    def test_empty_bytes(self):
        assert safe_loads(b"") is None

    def test_only_colon(self):
        assert safe_loads(b":") is None

    def test_invalid_mac_format(self):
        assert safe_loads(b"nothex:pickledata") is None

    def test_large_object(self):
        obj = {"data": list(range(10000))}
        assert safe_loads(safe_dumps(obj)) == obj

    def test_bytes_type_in_value(self):
        obj = {"binary": b"\x00\x01\x02"}
        assert safe_loads(safe_dumps(obj)) == obj


class TestSafeFileIO:
    def test_roundtrip_file(self, tmp_path):
        obj = {"file_key": [1, 2, 3], "meta": "test"}
        p = tmp_path / "test.pkl"
        assert safe_dump_to_file(obj, p)
        result = safe_load_from_file(p)
        assert result == obj

    def test_tampered_file_returns_none(self, tmp_path):
        obj = {"data": 42}
        p = tmp_path / "tampered.pkl"
        safe_dump_to_file(obj, p)
        raw = p.read_bytes()
        p.write_bytes(raw[:10] + b"Z" + raw[11:])
        assert safe_load_from_file(p) is None

    def test_nonexistent_file(self, tmp_path):
        p = tmp_path / "nonexistent.pkl"
        assert safe_load_from_file(p) is None

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.pkl"
        p.write_bytes(b"")
        assert safe_load_from_file(p) is None

    def test_corrupted_file(self, tmp_path):
        p = tmp_path / "corrupt.pkl"
        p.write_bytes(b"garbage_data")
        assert safe_load_from_file(p) is None

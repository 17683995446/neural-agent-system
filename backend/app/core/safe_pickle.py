"""
safe_pickle — HMAC-verified pickle serialization/deserialization
Prevents arbitrary code execution from tampered cache files
"""
import hashlib
import hmac
import pickle
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings

_PICKLE_KEY = settings.pickle_hmac_key.encode()


def safe_dumps(obj: Any) -> bytes:
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    mac = hmac.new(_PICKLE_KEY, data, hashlib.sha256).hexdigest()
    return f"{mac}:".encode() + data


def safe_loads(raw: bytes) -> Optional[Any]:
    sep = raw.find(b":")
    if sep < 0:
        return None
    mac_stored = raw[:sep].decode()
    data = raw[sep + 1:]
    mac_computed = hmac.new(_PICKLE_KEY, data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac_stored, mac_computed):
        return None
    return pickle.loads(data)


def safe_dump_to_file(obj: Any, path: Path) -> bool:
    try:
        path.write_bytes(safe_dumps(obj))
        return True
    except Exception:
        return False


def safe_load_from_file(path: Path) -> Optional[Any]:
    try:
        raw = path.read_bytes()
        return safe_loads(raw)
    except Exception:
        return None

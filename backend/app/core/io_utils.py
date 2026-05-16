"""统一的层输出保存工具"""
import json
from pathlib import Path
from typing import Any


def save_layer_output(task_id: str, layer_name: str, data: Any, filename: str = "result.json") -> Path:
    output_dir = Path("task_output") / task_id / layer_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return output_path

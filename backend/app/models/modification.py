"""
Modification models — 修改项与子需求的正式数据模型
替代自由Dict，提供类型安全、字段验证、结构化action
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ActionEnum(str, Enum):
    MODIFY = "modify"
    ADD = "add"
    DELETE = "delete"
    REFACTOR = "refactor"
    EXTRACT_METHOD = "extract_method"
    CASCADE_UPDATE = "cascade_update"
    ADD_TEST = "add_test"
    ANALYZE_AND_MODIFY = "analyze_and_modify"


class SubRequirement(BaseModel):
    id: str = Field(description="子需求唯一ID, 如 sub_0, sub_1")
    description: str = Field(description="子需求描述")
    scope_hint: str = Field(default="", description="涉及模块/文件关键词提示")
    priority: str = Field(default="medium", description="high/medium/low")
    status: str = Field(default="pending", description="pending/planning/executed/failed/skipped")


class ModificationItem(BaseModel):
    type: str = Field(default="function", description="function / class / file / module")
    target: str = Field(description="修改目标名称")
    file: str = Field(default="", description="文件路径")
    line: Optional[int] = Field(default=None, description="行号")
    action: str = Field(default=ActionEnum.ANALYZE_AND_MODIFY.value, description="修改动作")
    priority: str = Field(default="medium", description="high/medium/low")
    sub_requirement_id: Optional[str] = Field(default=None, description="来源子需求ID")
    depends_on: List[str] = Field(default_factory=list, description="依赖的其他modification target名")

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict) -> "ModificationItem":
        known = {f.alias or f_name for f_name, f in cls.model_fields.items()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

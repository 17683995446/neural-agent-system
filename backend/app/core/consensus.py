"""
ConsensusEngine — 多Agent结果共识引擎
基于语义相似度做等价类划分，区分共识/差异，输出ConsensusReport

辩证原则:
- 确定性任务(AST解析): 一致性=信号, 差异=噪声 → strict_match
- 语义提取(摘要/依赖): 高一致=高置信, 差异=互补 → embedding_similarity
- 代码修改: 共识=安全, 差异=需审核 → overlap_ratio + LLM判断
- 方案规划: 完全一致=从众, 完全差异=无共识 → 保留多样性+标注不确定区域
"""
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from app.core.logging import logger


class ConsensusStrategy(str, Enum):
    STRICT_MATCH = "strict_match"
    NORMALIZED_MATCH = "normalized_match"
    OVERLAP_RATIO = "overlap_ratio"
    STRUCTURE_SIMILARITY = "structure_similarity"


@dataclass
class EquivalenceClass:
    representative: Any
    members: List[int] = field(default_factory=list)
    member_results: List[Any] = field(default_factory=list)
    size: int = 0


@dataclass
class ConsensusReport:
    has_consensus: bool
    consensus_result: Optional[Any] = None
    consensus_ratio: float = 0.0
    equivalence_classes: List[EquivalenceClass] = field(default_factory=list)
    dissent_items: List[Dict[str, Any]] = field(default_factory=list)
    diversity_score: float = 0.0
    confidence_map: Dict[str, float] = field(default_factory=dict)
    total_candidates: int = 0
    strategy_used: str = ""


class ConsensusEngine:
    def __init__(
        self,
        strategy: ConsensusStrategy = ConsensusStrategy.OVERLAP_RATIO,
        consensus_threshold: float = 0.6,
        similarity_threshold: float = 0.7,
    ):
        self._strategy = strategy
        self._consensus_threshold = consensus_threshold
        self._similarity_threshold = similarity_threshold

    def evaluate(
        self,
        candidates: List[Any],
        strategy: Optional[ConsensusStrategy] = None,
        task_type: str = "",
    ) -> ConsensusReport:
        """评估候选结果的共识情况，返回ConsensusReport"""
        if not candidates:
            return ConsensusReport(
                has_consensus=False, total_candidates=0,
                strategy_used=strategy.value if strategy else self._strategy.value,
            )

        if len(candidates) == 1:
            return ConsensusReport(
                has_consensus=True, consensus_result=candidates[0],
                consensus_ratio=1.0, diversity_score=0.0,
                total_candidates=1, strategy_used="single_candidate",
                equivalence_classes=[EquivalenceClass(
                    representative=candidates[0], members=[0],
                    member_results=[candidates[0]], size=1,
                )],
            )

        effective_strategy = strategy or self._strategy
        if task_type == "deterministic":
            effective_strategy = ConsensusStrategy.STRICT_MATCH
        elif task_type == "semantic_extraction":
            effective_strategy = ConsensusStrategy.NORMALIZED_MATCH
        elif task_type == "code_modification":
            effective_strategy = ConsensusStrategy.OVERLAP_RATIO
        elif task_type == "planning":
            effective_strategy = ConsensusStrategy.STRUCTURE_SIMILARITY

        eq_classes = self._partition_equivalence(candidates, effective_strategy)

        eq_classes.sort(key=lambda c: c.size, reverse=True)

        largest = eq_classes[0] if eq_classes else None
        consensus_ratio = (largest.size / len(candidates)) if largest else 0.0
        has_consensus = consensus_ratio >= self._consensus_threshold

        consensus_result = largest.representative if has_consensus and largest else None

        dissent_items = []
        for eq_cls in eq_classes[1:]:
            for idx, result in zip(eq_cls.members, eq_cls.member_results):
                dissent_items.append({
                    "candidate_index": idx,
                    "result_preview": self._preview(result),
                    "equivalence_class_size": eq_cls.size,
                })

        diversity_score = self._compute_diversity(candidates, effective_strategy)

        confidence_map = self._build_confidence_map(candidates, eq_classes)

        report = ConsensusReport(
            has_consensus=has_consensus,
            consensus_result=consensus_result,
            consensus_ratio=consensus_ratio,
            equivalence_classes=eq_classes,
            dissent_items=dissent_items,
            diversity_score=diversity_score,
            confidence_map=confidence_map,
            total_candidates=len(candidates),
            strategy_used=effective_strategy.value,
        )

        logger.info(
            "ConsensusEngine: %d candidates → %d eq-classes, consensus=%s (ratio=%.2f, diversity=%.2f, strategy=%s)",
            len(candidates), len(eq_classes), has_consensus,
            consensus_ratio, diversity_score, effective_strategy.value,
        )
        return report

    def _partition_equivalence(
        self,
        candidates: List[Any],
        strategy: ConsensusStrategy,
    ) -> List[EquivalenceClass]:
        """基于相似度做等价类划分(Union-Find)"""
        n = len(candidates)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                if self._are_similar(candidates[i], candidates[j], strategy):
                    union(i, j)

        class_map: Dict[int, List[int]] = {}
        for i in range(n):
            root = find(i)
            class_map.setdefault(root, []).append(i)

        eq_classes = []
        for root, members in class_map.items():
            rep_idx = members[0]
            eq_classes.append(EquivalenceClass(
                representative=candidates[rep_idx],
                members=members,
                member_results=[candidates[i] for i in members],
                size=len(members),
            ))

        return eq_classes

    def _are_similar(
        self,
        a: Any,
        b: Any,
        strategy: ConsensusStrategy,
    ) -> bool:
        if strategy == ConsensusStrategy.STRICT_MATCH:
            return a == b

        if strategy == ConsensusStrategy.NORMALIZED_MATCH:
            return self._normalize(a) == self._normalize(b)

        if strategy == ConsensusStrategy.OVERLAP_RATIO:
            return self._overlap_similarity(a, b) >= self._similarity_threshold

        if strategy == ConsensusStrategy.STRUCTURE_SIMILARITY:
            return self._structure_similarity(a, b) >= self._similarity_threshold

        return a == b

    @staticmethod
    def _normalize(val: Any) -> str:
        if isinstance(val, dict):
            normalized_parts = []
            for k in sorted(val.keys()):
                v = val[k]
                if isinstance(v, str):
                    v = re.sub(r'\s+', ' ', v.strip())
                elif isinstance(v, list):
                    v = sorted(str(x) for x in v)
                normalized_parts.append(f"{k}={v}")
            return "|".join(normalized_parts)
        text = str(val)
        return re.sub(r'\s+', ' ', text.strip())

    @staticmethod
    def _overlap_similarity(a: Any, b: Any) -> float:
        a_text = ConsensusEngine._extract_code_text(a)
        b_text = ConsensusEngine._extract_code_text(b)
        if not a_text and not b_text:
            return 1.0
        if not a_text or not b_text:
            return 0.0

        a_lines = set(line.strip() for line in a_text.splitlines() if line.strip())
        b_lines = set(line.strip() for line in b_text.splitlines() if line.strip())
        if not a_lines or not b_lines:
            return 0.0

        intersection = a_lines & b_lines
        union = a_lines | b_lines
        return len(intersection) / len(union)

    @staticmethod
    def _structure_similarity(a: Any, b: Any) -> float:
        a_keys = ConsensusEngine._extract_structure_keys(a)
        b_keys = ConsensusEngine._extract_structure_keys(b)
        if not a_keys and not b_keys:
            return 1.0
        if not a_keys or not b_keys:
            return 0.0
        intersection = a_keys & b_keys
        union = a_keys | b_keys
        return len(intersection) / len(union)

    @staticmethod
    def _extract_code_text(val: Any) -> str:
        if isinstance(val, dict):
            for key in ("modified_code", "code", "test_code", "result"):
                v = val.get(key)
                if isinstance(v, str) and len(v) > 20:
                    return v
            return str(val)
        if isinstance(val, str) and len(val) > 20:
            return val
        return str(val)

    @staticmethod
    def _extract_structure_keys(val: Any) -> Set[str]:
        keys = set()
        if isinstance(val, dict):
            for k, v in val.items():
                keys.add(k)
                if isinstance(v, dict):
                    for sk in v.keys():
                        keys.add(f"{k}.{sk}")
                elif isinstance(v, list):
                    for item in v[:20]:
                        if isinstance(item, dict):
                            for ik in item.keys():
                                keys.add(f"{k}[].{ik}")
                        elif isinstance(item, str):
                            keys.add(f"{k}[]={item[:50]}")
        return keys

    @staticmethod
    def _compute_diversity(
        candidates: List[Any],
        strategy: ConsensusStrategy,
    ) -> float:
        """计算候选集的多样性分数(0=完全一致, 1=完全不同)"""
        n = len(candidates)
        if n <= 1:
            return 0.0

        engine = ConsensusEngine(similarity_threshold=0.7)
        dissimilar_pairs = 0
        total_pairs = n * (n - 1) // 2
        for i in range(n):
            for j in range(i + 1, n):
                if not engine._are_similar(candidates[i], candidates[j], strategy):
                    dissimilar_pairs += 1

        return dissimilar_pairs / total_pairs if total_pairs > 0 else 0.0

    @staticmethod
    def _build_confidence_map(
        candidates: List[Any],
        eq_classes: List[EquivalenceClass],
    ) -> Dict[str, float]:
        """构建每个区域/行的置信度: 多少Agent在此区域达成一致"""
        confidence: Dict[str, float] = {}
        if not eq_classes:
            return confidence

        total = sum(c.size for c in eq_classes)
        if total == 0:
            return confidence

        for cls_idx, eq_cls in enumerate(eq_classes):
            label = f"class_{cls_idx}"
            confidence[label] = eq_cls.size / total

        return confidence

    @staticmethod
    def _preview(val: Any, max_len: int = 200) -> str:
        text = str(val)
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def select_best(
        self,
        candidates: List[Any],
        trust_weights: Optional[Dict[str, float]] = None,
    ) -> Any:
        """基于共识+信任权重选择最佳结果
        有共识 → 返回共识结果
        无共识但有信任 → 返回最高信任Agent的结果
        无共识无信任 → 返回第一个候选
        """
        report = self.evaluate(candidates)

        if report.has_consensus:
            return report.consensus_result

        if trust_weights and report.equivalence_classes:
            best_cls = None
            best_score = -1.0
            for eq_cls in report.equivalence_classes:
                cls_score = eq_cls.size
                for idx in eq_cls.members:
                    agent_key = f"agent_{idx}"
                    if agent_key in trust_weights:
                        cls_score += trust_weights[agent_key]
                if cls_score > best_score:
                    best_score = cls_score
                    best_cls = eq_cls
            if best_cls:
                return best_cls.representative

        return candidates[0] if candidates else None

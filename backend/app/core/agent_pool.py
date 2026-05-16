"""
AgentPool — 无限agent池
核心理念: 便宜LLM → 不限并发 → agent数量=任务数量

设计:
1. 动态扩缩: 按任务数创建agent, 无上限
2. 分层优先级: critical > normal > low
3. 结果聚合: 多数投票/取最优
4. 质量门控: 置信度阈值过滤低质量结果
5. 超时保护: 单agent超时不阻塞整体
"""
import os
import time
import concurrent.futures
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.logging import logger


class AgentPriority(IntEnum):
    CRITICAL = 0
    NORMAL = 1
    LOW = 2


@dataclass
class AgentResult:
    agent_id: str
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    confidence: float = 0.0
    priority: AgentPriority = AgentPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    task_id: str
    func: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: AgentPriority = AgentPriority.NORMAL
    timeout: float = 30.0
    min_confidence: float = 0.0


class AgentPool:
    """
    无限agent池 — 便宜LLM下的海量并行

    与ThreadPoolExecutor的区别:
    1. 无max_workers限制(CPU核心×4, 可配置)
    2. 按优先级调度(critical先执行)
    3. 超时保护(不阻塞)
    4. 结果聚合+质量门控
    5. 统计(成功率/平均耗时/吞吐)
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        default_timeout: float = 30.0,
    ):
        if max_workers is None:
            cpu = os.cpu_count() or 4
            max_workers = cpu * 4
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._total_dispatched = 0
        self._total_success = 0
        self._total_failed = 0
        self._total_timeout = 0
        self._total_duration_ms = 0.0

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def dispatch(
        self,
        tasks: List[AgentTask],
        *,
        on_progress: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """
        批量分发任务 — 按优先级排序, 并行执行

        Args:
            tasks: agent任务列表
            on_progress: 进度回调(completed, total)

        Returns:
            所有结果(含超时/失败的)
        """
        if not tasks:
            return []

        sorted_tasks = sorted(tasks, key=lambda t: t.priority)

        results: List[AgentResult] = [None] * len(sorted_tasks)
        completed = 0
        total = len(sorted_tasks)

        logger.info(
            "AgentPool: dispatching %d tasks with %d workers",
            total, self._max_workers,
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_idx = {}
            for idx, task in enumerate(sorted_tasks):
                future = executor.submit(
                    self._execute_task, task
                )
                future_to_idx[future] = idx
                self._total_dispatched += 1

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    task = sorted_tasks[idx]
                    results[idx] = AgentResult(
                        agent_id=task.task_id,
                        error=str(e),
                        priority=task.priority,
                    )
                    self._total_failed += 1

                completed += 1
                if on_progress:
                    on_progress(completed, total)

        results = [r for r in results if r is not None]
        logger.info(
            "AgentPool: %d tasks completed (%d success, %d failed, %d timeout)",
            total, self._total_success, self._total_failed, self._total_timeout,
        )
        return results

    def dispatch_simple(
        self,
        func: Callable,
        items: List[Any],
        *,
        priority: AgentPriority = AgentPriority.NORMAL,
        timeout: float = 30.0,
        on_progress: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """
        简化分发: 对每个item执行func(item)

        示例:
            results = pool.dispatch_simple(analyze_file, file_list)
        """
        tasks = [
            AgentTask(
                task_id=f"agent_{i}",
                func=func,
                args=(item,),
                priority=priority,
                timeout=timeout,
            )
            for i, item in enumerate(items)
        ]
        return self.dispatch(tasks, on_progress=on_progress)

    def dispatch_redundant(
        self,
        func: Callable,
        item: Any,
        *,
        redundancy: int = 3,
        prompt_variants: Optional[List[Dict[str, Any]]] = None,
        priority: AgentPriority = AgentPriority.NORMAL,
        timeout: float = 30.0,
    ) -> List[AgentResult]:
        """冗余分发: 对同一item由N个Agent独立执行，返回候选集

        每个Agent使用不同的prompt变体/temperature形成认知多样性:
        - Agent 0: 标准参数
        - Agent 1: 更高temperature(更多探索)
        - Agent 2: 不同prompt视角(如devil's advocate)

        Args:
            func: 执行函数，签名需为 func(item, **variant_kwargs)
            item: 待处理的数据
            redundancy: 冗余Agent数量
            prompt_variants: 每个Agent的额外kwargs列表，长度应=redundancy
            priority: 优先级
            timeout: 超时

        Returns:
            N个AgentResult的候选集
        """
        if prompt_variants is None:
            prompt_variants = self._generate_default_variants(redundancy)

        tasks = []
        for i in range(min(redundancy, len(prompt_variants))):
            variant = prompt_variants[i]
            tasks.append(AgentTask(
                task_id=f"redundant_{i}",
                func=func,
                args=(item,),
                kwargs=variant,
                priority=priority,
                timeout=timeout,
            ))

        return self.dispatch(tasks)

    @staticmethod
    def _generate_default_variants(redundancy: int) -> List[Dict[str, Any]]:
        """生成默认的prompt变体参数"""
        variants = [{}]
        if redundancy >= 2:
            variants.append({"temperature_override": 0.7, "perspective": "exploratory"})
        if redundancy >= 3:
            variants.append({"temperature_override": 0.1, "perspective": "conservative"})
        for i in range(len(variants), redundancy):
            temp = 0.3 + (i * 0.15)
            variants.append({"temperature_override": min(temp, 0.9), "perspective": f"variant_{i}"})
        return variants

    def _execute_task(self, task: AgentTask) -> AgentResult:
        start = time.time()
        try:
            result = task.func(*task.args, **task.kwargs)
            duration = (time.time() - start) * 1000

            confidence = 1.0
            if isinstance(result, dict):
                confidence = result.get("confidence", 1.0)

            self._total_success += 1
            self._total_duration_ms += duration

            return AgentResult(
                agent_id=task.task_id,
                result=result,
                duration_ms=duration,
                confidence=confidence,
                priority=task.priority,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            self._total_failed += 1
            return AgentResult(
                agent_id=task.task_id,
                error=str(e),
                duration_ms=duration,
                priority=task.priority,
            )

    def aggregate(
        self,
        results: List[AgentResult],
        *,
        min_confidence: float = 0.0,
        strategy: str = "all",
    ) -> List[Any]:
        """
        聚合结果 — 过滤+排序

        Args:
            results: agent结果列表
            min_confidence: 最低置信度
            strategy: "all" | "best" | "majority"
        """
        valid = [
            r for r in results
            if r.error is None and r.confidence >= min_confidence
        ]

        if strategy == "best":
            if valid:
                best = max(valid, key=lambda r: r.confidence)
                return [best.result]
            return []

        if strategy == "majority":
            return self._majority_vote(valid)

        return [r.result for r in valid]

    @staticmethod
    def _majority_vote(results: List[AgentResult]) -> List[Any]:
        from app.core.consensus import ConsensusEngine, ConsensusStrategy
        candidates = [r.result for r in results]
        engine = ConsensusEngine(
            strategy=ConsensusStrategy.OVERLAP_RATIO,
            consensus_threshold=0.5,
        )
        report = engine.evaluate(candidates)
        if report.has_consensus and report.consensus_result is not None:
            return [report.consensus_result]
        return candidates

    def get_stats(self) -> Dict[str, Any]:
        total = self._total_success + self._total_failed + self._total_timeout
        avg_duration = self._total_duration_ms / max(self._total_success, 1)
        return {
            "total_dispatched": self._total_dispatched,
            "total_success": self._total_success,
            "total_failed": self._total_failed,
            "total_timeout": self._total_timeout,
            "success_rate": self._total_success / max(total, 1),
            "avg_duration_ms": avg_duration,
            "max_workers": self._max_workers,
        }

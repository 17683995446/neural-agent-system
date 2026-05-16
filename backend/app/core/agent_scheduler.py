"""
AgentScheduler — 分层调度器
将大任务拆成无数小任务 → AgentPool并行 → 结果聚合

架构:
┌─────────────┐
│ 大任务(1M行) │
└──────┬──────┘
       │ 分片(sharding)
┌──────┴──────┐
│ 1000个分片  │ ← 每分片=1个agent
└──────┬──────┘
       │ 调度(AgentPool)
┌──────┴──────────────┐
│ 1000 agents 并行    │ ← 每agent独立CheapLLMClient
└──────┬──────────────┘
       │ 聚合(aggregate)
┌──────┴──────┐
│ 合并结果    │ ← 去重+排序+质量门控
└─────────────┘
"""
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from app.core.agent_pool import AgentPool, AgentResult, AgentTask, AgentPriority
from app.core.logging import logger


@dataclass
class ShardInfo:
    shard_id: str
    items: List[Any]
    priority: AgentPriority = AgentPriority.NORMAL
    metadata: Dict[str, Any] = None


class AgentScheduler:
    """
    分层调度器 — 无限agent的协调者

    三层调度:
    L1 - 任务分片: 大任务→无数小任务
    L2 - 优先级调度: critical先执行
    L3 - 结果聚合: 过滤+合并+去重

    示例(1M行项目分析):
    1. 10000文件 → 按模块分100片 → 每片100文件
    2. 100片 → AgentPool调度(400 worker并发)
    3. 100个结果 → 去重+排序 → 合并
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        shard_size: int = 100,
    ):
        self._pool = AgentPool(max_workers=max_workers)
        self._shard_size = shard_size

    @property
    def pool(self) -> AgentPool:
        return self._pool

    def shard_items(
        self,
        items: List[Any],
        shard_size: Optional[int] = None,
    ) -> List[ShardInfo]:
        """
        分片: 将N个item分成ceil(N/shard_size)片

        每片是一个agent的任务单元
        """
        size = shard_size or self._shard_size
        shards = []
        for i in range(0, len(items), size):
            chunk = items[i : i + size]
            shards.append(ShardInfo(
                shard_id=f"shard_{i // size}",
                items=chunk,
                metadata={"offset": i, "size": len(chunk)},
            ))
        logger.info(
            "AgentScheduler: sharded %d items into %d shards (size=%d)",
            len(items), len(shards), size,
        )
        return shards

    def dispatch_sharded(
        self,
        func: Callable,
        items: List[Any],
        *,
        shard_size: Optional[int] = None,
        per_item: bool = False,
        priority: AgentPriority = AgentPriority.NORMAL,
        timeout: float = 30.0,
        on_progress: Optional[Callable] = None,
    ) -> List[AgentResult]:
        """
        分片调度: 分片→每片一个agent→聚合

        Args:
            func: 处理函数
            items: 待处理项列表
            shard_size: 每片大小
            per_item: True=每item一个agent, False=每shard一个agent
            priority: 优先级
            timeout: 单agent超时
            on_progress: 进度回调
        """
        start = time.time()

        if per_item:
            results = self._pool.dispatch_simple(
                func, items,
                priority=priority,
                timeout=timeout,
                on_progress=on_progress,
            )
        else:
            shards = self.shard_items(items, shard_size)

            def process_shard(shard: ShardInfo) -> List:
                shard_results = []
                for item in shard.items:
                    try:
                        r = func(item)
                        shard_results.append(r)
                    except Exception as e:
                        logger.debug("Shard %s item failed: %s", shard.shard_id, e)
                return shard_results

            results = self._pool.dispatch_simple(
                process_shard, shards,
                priority=priority,
                timeout=timeout,
                on_progress=on_progress,
            )

        elapsed = (time.time() - start) * 1000
        logger.info(
            "AgentScheduler: dispatched %d items in %.1fms",
            len(items), elapsed,
        )
        return results

    def dispatch_file_analysis(
        self,
        analyze_func: Callable,
        file_paths: List[str],
        *,
        max_workers: Optional[int] = None,
        on_progress: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        文件分析专用调度 — 每文件一个agent

        这是卷积层的核心: N个文件 → N个agent并行分析
        """
        if max_workers and max_workers != self._pool.max_workers:
            self._pool = AgentPool(max_workers=max_workers)

        results = self._pool.dispatch_simple(
            analyze_func,
            file_paths,
            priority=AgentPriority.NORMAL,
            timeout=30.0,
            on_progress=on_progress,
        )

        return self._pool.aggregate(results, min_confidence=0.0, strategy="all")

    def dispatch_modifications(
        self,
        modify_func: Callable,
        modifications: List[Dict],
        *,
        on_progress: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        修改调度 — 每修改一个agent, critical优先

        关键修改(high priority)先执行
        """
        tasks = []
        for i, mod in enumerate(modifications):
            prio = AgentPriority.CRITICAL if mod.get("priority") == "high" else AgentPriority.NORMAL
            tasks.append(AgentTask(
                task_id=f"mod_{i}",
                func=modify_func,
                args=(mod,),
                priority=prio,
                timeout=60.0,
            ))

        results = self._pool.dispatch(tasks, on_progress=on_progress)
        return self._pool.aggregate(results, min_confidence=0.0, strategy="all")

    def get_stats(self) -> Dict[str, Any]:
        return self._pool.get_stats()

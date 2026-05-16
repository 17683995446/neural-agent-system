"""
迭代状态管理器 - 管理前向传播→输出→用户反馈→反向传播的迭代循环
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import logger


class IterationState:
    """单次迭代的状态"""

    def __init__(self, iteration: int):
        self.iteration = iteration
        self.forward_result: Optional[Dict[str, Any]] = None
        self.backward_result: Optional[Dict[str, Any]] = None
        self.user_feedback: Optional[Dict[str, Any]] = None
        self.forward_time_ms: float = 0.0
        self.backward_time_ms: float = 0.0
        self.started_at: Optional[str] = None
        self.forward_completed_at: Optional[str] = None
        self.feedback_received_at: Optional[str] = None
        self.backward_completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "forward_result": self.forward_result,
            "backward_result": self.backward_result,
            "user_feedback": self.user_feedback,
            "forward_time_ms": self.forward_time_ms,
            "backward_time_ms": self.backward_time_ms,
            "started_at": self.started_at,
            "forward_completed_at": self.forward_completed_at,
            "feedback_received_at": self.feedback_received_at,
            "backward_completed_at": self.backward_completed_at,
        }


class IterationSession:
    """迭代会话 - 跟踪一个任务的完整迭代循环"""

    def __init__(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        max_iteration: int = 5,
    ):
        self.task_id = task_id
        self.user_requirement = user_requirement
        self.code_repo_path = code_repo_path
        self.max_iteration = max_iteration

        self.current_iteration: int = 0
        self.iterations: List[IterationState] = []
        self.status: str = "pending"
        self.should_continue: bool = True
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = datetime.now().isoformat()
        self.total_forward_time_ms: float = 0.0
        self.total_backward_time_ms: float = 0.0

    def start_iteration(self) -> IterationState:
        self.current_iteration += 1
        state = IterationState(self.current_iteration)
        state.started_at = datetime.now().isoformat()
        self.iterations.append(state)
        self.status = "running"
        self.updated_at = datetime.now().isoformat()
        logger.info(
            f"[ITERATION] Starting iteration {self.current_iteration}/{self.max_iteration} for task {self.task_id}"
        )
        return state

    def complete_forward(self, state: IterationState, result: Dict[str, Any], start_time: float = 0.0):
        state.forward_result = result
        if start_time > 0:
            state.forward_time_ms = (time.time() - start_time) * 1000
        state.forward_completed_at = datetime.now().isoformat()
        self.status = "awaiting_feedback"
        self.updated_at = datetime.now().isoformat()
        logger.info(
            f"[ITERATION] Forward propagation completed for iteration {state.iteration}, task {self.task_id} — awaiting user feedback"
        )

    def receive_feedback(self, state: IterationState, feedback: Dict[str, Any]):
        state.user_feedback = feedback
        state.feedback_received_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        logger.info(
            f"[ITERATION] User feedback received for iteration {state.iteration}, task {self.task_id} — satisfaction={feedback.get('satisfaction_score', 'N/A')}"
        )

    def complete_backward(self, state: IterationState, result: Dict[str, Any]):
        state.backward_result = result
        state.backward_completed_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        logger.info(
            f"[ITERATION] Backward propagation completed for iteration {state.iteration}, task {self.task_id}"
        )

    def should_stop(self, feedback: Dict[str, Any]) -> bool:
        stop = feedback.get("stop_iteration", False)
        if stop:
            logger.info(f"[ITERATION] User requested stop for task {self.task_id}")
            return True
        if self.current_iteration >= self.max_iteration:
            logger.info(
                f"[ITERATION] Max iteration ({self.max_iteration}) reached for task {self.task_id}"
            )
            return True
        satisfaction = feedback.get("satisfaction_score", 0)
        if satisfaction >= 5.0:
            logger.info(
                f"[ITERATION] Satisfaction score {satisfaction} >= 5.0, stopping for task {self.task_id}"
            )
            return True
        return False

    def mark_completed(self):
        self.status = "completed"
        self.should_continue = False
        self.updated_at = datetime.now().isoformat()
        logger.info(
            f"[ITERATION] Task {self.task_id} completed after {self.current_iteration} iterations"
        )

    def mark_iterating(self):
        self.status = "iterating"
        self.should_continue = True
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_requirement": self.user_requirement,
            "code_repo_path": self.code_repo_path,
            "max_iteration": self.max_iteration,
            "current_iteration": self.current_iteration,
            "status": self.status,
            "should_continue": self.should_continue,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "iterations": [it.to_dict() for it in self.iterations],
            "total_forward_time_ms": self.total_forward_time_ms,
            "total_backward_time_ms": self.total_backward_time_ms,
        }


class IterationManager:
    """迭代管理器 - 管理所有任务的迭代会话"""

    def __init__(self):
        self._sessions: Dict[str, IterationSession] = {}

    def create_session(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        max_iteration: int = 5,
    ) -> IterationSession:
        session = IterationSession(
            task_id=task_id,
            user_requirement=user_requirement,
            code_repo_path=code_repo_path,
            max_iteration=max_iteration,
        )
        self._sessions[task_id] = session
        logger.info(f"[ITERATION] Created session for task {task_id}, max_iteration={max_iteration}")
        return session

    def get_session(self, task_id: str) -> Optional[IterationSession]:
        return self._sessions.get(task_id)

    def get_or_create_session(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        max_iteration: int = 5,
    ) -> IterationSession:
        if task_id in self._sessions:
            return self._sessions[task_id]
        return self.create_session(task_id, user_requirement, code_repo_path, max_iteration)

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": s.task_id,
                "current_iteration": s.current_iteration,
                "max_iteration": s.max_iteration,
                "status": s.status,
                "updated_at": s.updated_at,
            }
            for s in self._sessions.values()
        ]

    def save_iteration_result(self, task_id: str):
        session = self._sessions.get(task_id)
        if not session:
            return
        output_dir = Path("task_output") / task_id / "iterations"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "iteration_state.json").write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


_iteration_manager: Optional[IterationManager] = None


def get_iteration_manager() -> IterationManager:
    global _iteration_manager
    if _iteration_manager is None:
        _iteration_manager = IterationManager()
    return _iteration_manager

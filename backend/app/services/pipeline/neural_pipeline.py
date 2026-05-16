"""
神经网络Pipeline调度器 - 整合所有层的前向传播流程
实现输入层 → 卷积层 → 池化层 → 全连接层1/2/3 → 输出层的完整流程
支持迭代循环: 前向传播→输出→用户反馈→反向传播→继续/停止
"""
import time
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.logging import logger
from app.core.scalability_profile import ScalabilityProfile
from app.core.llm_rate_limiter import LLMRateLimiter
from app.models.database import SessionLocal, TaskModel
from app.models.schemas import TaskStatus
from app.models.modification import SubRequirement
from app.services.input_layer.service import input_layer_service
from app.services.convolution.service import get_convolution_service
from app.services.pooling.service import get_pooling_service
from app.services.fullconnect import (
    get_global_understanding_service,
    get_code_generation_service,
    get_test_generation_service
)
from app.services.output.service import get_output_service
from app.services.backward.service import get_backward_service
from app.services.pipeline.iteration_manager import get_iteration_manager


class NeuralNetworkPipeline:
    """神经网络Pipeline调度器"""

    def __init__(self):
        self.input_service = input_layer_service
        self.conv_service = get_convolution_service()
        self.pool_service = get_pooling_service()
        self.fc1_service = get_global_understanding_service()
        self.fc2_service = get_code_generation_service()
        self.fc3_service = get_test_generation_service()
        self.output_service = get_output_service()
        self.backward_service = get_backward_service()

    def _update_task_status(self, task_id: str, status: TaskStatus, iteration: int = 0):
        """更新任务状态到数据库"""
        try:
            db = SessionLocal()
            try:
                task = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
                if task:
                    task.status = status.value
                    task.iteration_count = iteration
                    task.updated_at = datetime.now()
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")

    def _log_layer_timing(self, layer_name: str, start_time: float, task_id: str):
        """记录层执行时间和日志"""
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] {layer_name} completed in {elapsed:.2f}ms for task {task_id}")

    @staticmethod
    def _save_to_short_term_memory(task_id: str, agent_id: str, data: Dict[str, Any]):
        """将层输出保存到短期记忆(Redis)，供迭代时快速恢复"""
        try:
            from app.agents.memory.short_term import ShortTermMemory
            stm = ShortTermMemory(task_id=task_id, agent_id=agent_id)
            stm.save_message(agent_id, data)
        except Exception:
            pass

    def execute_forward_pipeline(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        max_iteration: int = 5
    ) -> Dict[str, Any]:
        """
        执行完整的前向传播流程

        Args:
            task_id: 任务ID
            user_requirement: 用户需求
            code_repo_path: 代码仓库路径
            max_iteration: 最大迭代次数

        Returns:
            执行结果包含所有层的输出
        """
        total_start_time = time.time()
        logger.info(f"[START] Neural Network Pipeline for task {task_id}")

        profile = ScalabilityProfile.detect(code_repo_path)
        logger.info(
            "Pipeline configured for %s project (%d files, %d lines)",
            profile.get("_profile", "UNKNOWN"),
            profile.get("_file_count", 0),
            profile.get("_total_lines", 0),
        )

        if profile.get("llm_max_qps") and profile.get("llm_max_concurrent"):
            LLMRateLimiter.configure(
                max_qps=profile["llm_max_qps"],
                max_concurrent=profile["llm_max_concurrent"],
            )

        self._update_task_status(task_id, TaskStatus.RUNNING)

        enable_module_partition = profile.get("enable_module_partition", False)
        enable_incremental = profile.get("enable_incremental", False)

        if enable_incremental:
            self.conv_service.enable_incremental()
            logger.info("Pipeline: incremental analysis enabled for convolution layer")

        if profile.get("enable_agent_pool"):
            workers = profile.get("agent_pool_workers", 0)
            self.conv_service.enable_agent_pool(max_workers=workers)
            self.fc2_service.enable_agent_pool(max_workers=workers)
            self.fc3_service.enable_agent_pool(max_workers=workers)
            self.fc1_service.enable_cheap_llm()
            logger.info("Pipeline: ALL layers in agent pool mode (cheap LLM)")

        # ==================== 阶段1: 输入层 ====================
        input_start = time.time()
        logger.info(f"[LAYER 0] Input Layer starting for task {task_id}")
        sub_requirements = []
        try:
            decomp = self.input_service.decompose_requirement(user_requirement)
            sub_requirements = decomp.get("sub_requirements", [])
            is_decomposed = decomp.get("is_decomposed", False)
            logger.info(
                "[LAYER 0] Input: %d sub-requirements (decomposed=%s)",
                len(sub_requirements), is_decomposed,
            )
        except Exception as e:
            logger.warning("[LAYER 0] Requirement decomposition failed: %s", e)
            from app.models.modification import SubRequirement
            sub_requirements = [SubRequirement(id="sub_0", description=user_requirement, priority="high")]
        self._log_layer_timing("Input Layer", input_start, task_id)

        # ==================== 阶段2: 卷积层 ====================
        conv_start = time.time()
        logger.info(f"[LAYER 1] Convolution Layer starting for task {task_id}")
        try:
            conv_output = self.conv_service.process_task(
                task_id, code_repo_path,
                enable_module_partition=enable_module_partition,
                enable_incremental=enable_incremental,
                user_requirement=user_requirement,
            )
            self._log_layer_timing("Convolution Layer", conv_start, task_id)
            logger.info(f"[LAYER 1] Convolution Layer output: {len(conv_output.get('analyzed_files', []))} files analyzed")
            self._save_to_short_term_memory(task_id, "conv_agent", conv_output)
        except Exception as e:
            logger.error(f"[LAYER 1] Convolution Layer failed: {e}")
            conv_output = {"error": str(e), "task_id": task_id}

        # ==================== 阶段3: 池化层 ====================
        pool_start = time.time()
        logger.info(f"[LAYER 2] Pooling Layer starting for task {task_id}")
        try:
            pool_output = self.pool_service.process_task(task_id, conv_output, user_requirement)
            self._log_layer_timing("Pooling Layer", pool_start, task_id)
            logger.info(f"[LAYER 2] Pooling Layer output: {pool_output.get('total_files_processed', 0)} files processed")
            self._save_to_short_term_memory(task_id, "pool_agent", pool_output)
        except Exception as e:
            logger.error(f"[LAYER 2] Pooling Layer failed: {e}")
            pool_output = {"error": str(e), "task_id": task_id}

        # ==================== 阶段4: 全连接层1 (全局理解) ====================
        fc1_start = time.time()
        logger.info(f"[LAYER 3] FC1 Global Understanding Layer starting for task {task_id}")
        try:
            fc1_output = self.fc1_service.process_task(task_id, pool_output, user_requirement, sub_requirements=sub_requirements)
            self._log_layer_timing("FC1 Global Understanding Layer", fc1_start, task_id)
            logger.info(f"[LAYER 3] FC1 output: solution generated with {len(fc1_output.get('solution', {}).get('modification_list', []))} modifications")
            self._save_to_short_term_memory(task_id, "fc1_agent", fc1_output)
        except Exception as e:
            logger.error(f"[LAYER 3] FC1 failed: {e}")
            fc1_output = {"error": str(e), "task_id": task_id}

        # ==================== 阶段5: 全连接层2 (代码生成) ====================
        fc2_start = time.time()
        logger.info(f"[LAYER 4] FC2 Code Generation Layer starting for task {task_id}")
        try:
            fc2_output = self.fc2_service.process_task(task_id, fc1_output, code_repo_path)
            self._log_layer_timing("FC2 Code Generation Layer", fc2_start, task_id)
            logger.info(f"[LAYER 4] FC2 output: {fc2_output.get('summary', {}).get('successful', 0)} successful modifications")
            self._save_to_short_term_memory(task_id, "fc2_agent", fc2_output)
        except Exception as e:
            logger.error(f"[LAYER 4] FC2 failed: {e}")
            fc2_output = {"error": str(e), "task_id": task_id}

        # ==================== 阶段6: 全连接层3 (测试生成) ====================
        fc3_start = time.time()
        logger.info(f"[LAYER 5] FC3 Test Generation Layer starting for task {task_id}")
        try:
            fc3_output = self.fc3_service.process_task(task_id, fc2_output)
            self._log_layer_timing("FC3 Test Generation Layer", fc3_start, task_id)
            logger.info(f"[LAYER 5] FC3 output: {fc3_output.get('summary', {}).get('total_tests', 0)} tests generated")
            self._save_to_short_term_memory(task_id, "fc3_agent", fc3_output)
        except Exception as e:
            logger.error(f"[LAYER 5] FC3 failed: {e}")
            fc3_output = {"error": str(e), "task_id": task_id}

        # ==================== 阶段7: 输出层 ====================
        output_start = time.time()
        logger.info(f"[LAYER 6] Output Layer starting for task {task_id}")
        execution_time = (time.time() - total_start_time) * 1000
        try:
            output_result = self.output_service.process_task(
                task_id,
                user_requirement,
                fc1_output,
                fc2_output,
                fc3_output,
                execution_time
            )
            self._log_layer_timing("Output Layer", output_start, task_id)
            logger.info(f"[LAYER 6] Output Layer: document saved to {output_result.get('document_path', 'unknown')}")
        except Exception as e:
            logger.error(f"[LAYER 6] Output Layer failed: {e}")
            output_result = {"error": str(e), "task_id": task_id}

        # 更新任务状态为完成
        self._update_task_status(task_id, TaskStatus.COMPLETED)

        # 汇总结果
        total_elapsed = (time.time() - total_start_time) * 1000
        logger.info(f"[COMPLETE] Neural Network Pipeline completed for task {task_id} in {total_elapsed:.2f}ms")

        return {
            "task_id": task_id,
            "status": "completed",
            "layer_outputs": {
                "convolution": conv_output,
                "pooling": pool_output,
                "fc1_global_understanding": fc1_output,
                "fc2_code_generation": fc2_output,
                "fc3_test_generation": fc3_output,
                "output": output_result
            },
            "scalability_profile": {
                "profile": profile.get("_profile"),
                "file_count": profile.get("_file_count"),
                "total_lines": profile.get("_total_lines"),
            },
            "execution_time_ms": total_elapsed,
            "completed_at": datetime.now().isoformat()
        }

    def execute_backward_pipeline(
        self,
        task_id: str,
        user_feedback: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行反向传播流程"""
        start_time = time.time()
        logger.info(f"[START] Backward Propagation for task {task_id}")

        try:
            result = self.backward_service.process_user_feedback(task_id, user_feedback)
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[COMPLETE] Backward propagation completed in {elapsed:.2f}ms")
            return result
        except Exception as e:
            logger.error(f"Backward propagation failed: {e}")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }

    def execute_iteration(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        iteration: int,
        max_iteration: int
    ) -> Dict[str, Any]:
        """执行单次迭代（包含前向和反向传播）"""
        start_time = time.time()
        logger.info(f"[ITERATION {iteration}/{max_iteration}] Starting for task {task_id}")

        forward_result = self.execute_forward_pipeline(
            task_id,
            user_requirement,
            code_repo_path,
            max_iteration
        )

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[ITERATION {iteration}/{max_iteration}] Forward completed in {elapsed:.2f}ms")

        return {
            "iteration": iteration,
            "forward_result": forward_result,
            "execution_time_ms": elapsed
        }

    def start_iterative_pipeline(
        self,
        task_id: str,
        user_requirement: str,
        code_repo_path: str,
        max_iteration: int = 5,
    ) -> Dict[str, Any]:
        """
        启动迭代式Pipeline — 执行第1次前向传播后等待用户反馈
        循环: 前向传播→输出→等待反馈→反向传播→(继续/停止)
        """
        mgr = get_iteration_manager()
        session = mgr.create_session(
            task_id, user_requirement, code_repo_path, max_iteration
        )

        iter_state = session.start_iteration()

        forward_start = time.time()
        forward_result = self.execute_forward_pipeline(
            task_id, user_requirement, code_repo_path, max_iteration
        )
        forward_elapsed = (time.time() - forward_start) * 1000

        iter_state.forward_result = forward_result
        iter_state.forward_time_ms = forward_elapsed
        session.complete_forward(iter_state, forward_result)
        session.total_forward_time_ms += forward_elapsed

        self._update_task_status(task_id, TaskStatus.ITERATING, session.current_iteration)
        mgr.save_iteration_result(task_id)

        return {
            "task_id": task_id,
            "iteration": session.current_iteration,
            "max_iteration": max_iteration,
            "status": "awaiting_feedback",
            "message": f"前向传播第{session.current_iteration}轮完成，请通过 /api/v1/pipeline/feedback 提交反馈 (stop_iteration=true 停止迭代)",
            "forward_result": forward_result,
            "session_state": session.to_dict(),
        }

    def process_iteration_feedback(
        self,
        task_id: str,
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        处理用户反馈 — 执行反向传播，然后判断是否继续迭代
        如果继续: 执行下一轮前向传播，再次等待反馈
        如果停止: 迭代结束
        """
        mgr = get_iteration_manager()
        session = mgr.get_session(task_id)
        if not session:
            raise ValueError(f"No iteration session found for task {task_id}")

        if session.status not in ("awaiting_feedback", "iterating"):
            raise ValueError(
                f"Task {task_id} is in status '{session.status}', cannot accept feedback"
            )

        current_iter_state = session.iterations[-1]
        session.receive_feedback(current_iter_state, feedback)

        backward_start = time.time()
        backward_result = self.execute_backward_pipeline(task_id, feedback)
        backward_elapsed = (time.time() - backward_start) * 1000

        session.complete_backward(current_iter_state, backward_result)
        session.total_backward_time_ms += backward_elapsed
        current_iter_state.backward_time_ms = backward_elapsed

        should_stop = session.should_stop(feedback)

        if should_stop:
            session.mark_completed()
            self._update_task_status(task_id, TaskStatus.COMPLETED, session.current_iteration)
            mgr.save_iteration_result(task_id)

            return {
                "task_id": task_id,
                "iteration": session.current_iteration,
                "max_iteration": session.max_iteration,
                "status": "completed",
                "message": f"迭代结束，共执行{session.current_iteration}轮",
                "backward_result": backward_result,
                "session_state": session.to_dict(),
            }

        session.mark_iterating()
        next_iter_state = session.start_iteration()

        forward_start = time.time()
        forward_result = self.execute_forward_pipeline(
            task_id, session.user_requirement, session.code_repo_path, session.max_iteration
        )
        forward_elapsed = (time.time() - forward_start) * 1000

        next_iter_state.forward_result = forward_result
        next_iter_state.forward_time_ms = forward_elapsed
        session.complete_forward(next_iter_state, forward_result)
        session.total_forward_time_ms += forward_elapsed

        self._update_task_status(task_id, TaskStatus.ITERATING, session.current_iteration)
        mgr.save_iteration_result(task_id)

        return {
            "task_id": task_id,
            "iteration": session.current_iteration,
            "max_iteration": session.max_iteration,
            "status": "awaiting_feedback",
            "message": f"第{session.current_iteration}轮前向传播完成，等待反馈",
            "backward_result": backward_result,
            "forward_result": forward_result,
            "session_state": session.to_dict(),
        }

    def stop_iteration(self, task_id: str) -> Dict[str, Any]:
        """强制停止迭代"""
        mgr = get_iteration_manager()
        session = mgr.get_session(task_id)
        if not session:
            raise ValueError(f"No iteration session found for task {task_id}")

        session.mark_completed()
        self._update_task_status(task_id, TaskStatus.COMPLETED, session.current_iteration)
        mgr.save_iteration_result(task_id)

        return {
            "task_id": task_id,
            "iteration": session.current_iteration,
            "status": "completed",
            "message": f"迭代已强制停止，共执行{session.current_iteration}轮",
            "session_state": session.to_dict(),
        }

    def get_iteration_status(self, task_id: str) -> Dict[str, Any]:
        """获取迭代状态"""
        mgr = get_iteration_manager()
        session = mgr.get_session(task_id)
        if not session:
            raise ValueError(f"No iteration session found for task {task_id}")
        return session.to_dict()


# Singleton instance
_neural_pipeline: Optional[NeuralNetworkPipeline] = None


def get_neural_pipeline() -> NeuralNetworkPipeline:
    """获取神经网络Pipeline实例"""
    global _neural_pipeline
    if _neural_pipeline is None:
        _neural_pipeline = NeuralNetworkPipeline()
    return _neural_pipeline
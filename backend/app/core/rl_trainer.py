"""
RL Trainer - 强化学习训练服务
通过Ray进行反向传播的强化学习训练，更新Agent信任度权重
"""
import time

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False

from app.agents.trust.backward import BackwardPropagation
from app.core.config import settings
from app.core.logging import logger
from app.models.database import SessionLocal, TaskModel
from app.models.schemas import TaskStatus


class RLTrainer:
    """强化学习训练器"""

    def __init__(self):
        self.backward_propagation = BackwardPropagation()
        self.is_running = False
        self.training_interval = 60  # 每60秒训练一次

    def connect_ray(self):
        """连接Ray集群"""
        if not RAY_AVAILABLE:
            logger.warning("Ray not available, skipping Ray connection")
            return

        ray_address = settings.redis_url.replace("redis://", "ray://").rsplit("/", 1)[0]

        try:
            ray.init(address=ray_address, ignore_reinit_error=True)
            logger.info(f"Connected to Ray cluster at {ray_address}")
        except Exception as e:
            logger.warning(f"Failed to connect to Ray cluster: {e}, running in local mode")
            ray.init(ignore_reinit_error=True)
            logger.info("Running Ray in local mode")

    def get_pending_tasks(self) -> list:
        """获取待训练的任务"""
        db = SessionLocal()
        try:
            tasks = db.query(TaskModel).filter(
                TaskModel.status.in_([
                    TaskStatus.COMPLETED.value,
                    TaskStatus.ITERATING.value,
                ])
            ).limit(10).all()

            return [
                {
                    "task_id": task.task_id,
                    "user_requirement": task.user_requirement,
                    "iteration_count": task.iteration_count,
                    "learning_rate": task.learning_rate or settings.default_learning_rate
                }
                for task in tasks
            ]
        finally:
            db.close()

    def train_on_task(self, task_data: dict) -> dict:
        """在单个任务上训练"""
        task_id = task_data["task_id"]
        learning_rate = task_data.get("learning_rate", settings.default_learning_rate)

        logger.info(f"Training on task {task_id} with learning_rate={learning_rate}")

        layer_agents = self._get_layer_agents(task_id)

        db = SessionLocal()
        try:
            task_model = db.query(TaskModel).filter(TaskModel.task_id == task_id).first()
            satisfaction = 4
            if task_model and task_model.llm_config:
                satisfaction = task_model.llm_config.get("satisfaction_score", 4)
        finally:
            db.close()

        updated_weights = self.backward_propagation.propagate_feedback(
            task_id=task_id,
            user_feedback={"satisfaction_score": satisfaction},
            layer_agents=layer_agents,
            current_iteration=task_data.get("iteration_count", 1)
        )

        return {
            "task_id": task_id,
            "weights_updated": len(updated_weights),
            "learning_rate": learning_rate
        }

    def _get_layer_agents(self, task_id: str) -> dict:
        """获取任务的Agent配置"""
        return {
            "convolution": [f"conv_agent_{i}" for i in range(1, 6)],
            "pooling": ["pool_agent_1"],
            "global_understanding": ["fc1_agent"],
            "code_generation": [f"fc2_agent_{i}" for i in range(1, 4)],
            "test_generation": ["fc3_agent"],
            "output": ["output_agent"]
        }

    def run_training_loop(self):
        """运行训练循环"""
        self.connect_ray()
        self.is_running = True

        logger.info("RL Trainer started, entering training loop")

        while self.is_running:
            try:
                # 获取待训练任务
                pending_tasks = self.get_pending_tasks()

                if pending_tasks:
                    logger.info(f"Found {len(pending_tasks)} tasks for training")

                    for task_data in pending_tasks:
                        try:
                            result = self.train_on_task(task_data)
                            logger.info(f"Training completed: {result}")
                        except Exception as e:
                            logger.error(f"Training failed for task {task_data['task_id']}: {e}")
                else:
                    logger.debug("No pending tasks for training")

                # 等待下一次训练
                time.sleep(self.training_interval)

            except KeyboardInterrupt:
                logger.info("RL Trainer interrupted by user")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Training loop error: {e}")
                time.sleep(self.training_interval)

        logger.info("RL Trainer stopped")

    def stop(self):
        """停止训练器"""
        self.is_running = False
        logger.info("RL Trainer stop requested")


def main():
    """RL Trainer入口"""
    logger.info("=" * 50)
    logger.info("Starting RL Trainer")
    logger.info("=" * 50)

    trainer = RLTrainer()

    try:
        trainer.run_training_loop()
    except Exception as e:
        logger.error(f"RL Trainer fatal error: {e}")
        raise
    finally:
        trainer.stop()
        if RAY_AVAILABLE:
            ray.shutdown()


if __name__ == "__main__":
    main()
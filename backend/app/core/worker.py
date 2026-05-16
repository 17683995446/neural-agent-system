"""
Celery Worker - Agent调度服务
用于异步处理Agent任务分发和执行
"""
from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from app.core.config import settings
from app.core.logging import logger

# Create Celery application
celery_app = Celery(
    "neural_agent_worker",
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3000,  # 50 minutes
    worker_prefetch_multiplier=1,
    worker_concurrency=10,
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Worker启动完成回调"""
    logger.info("Celery worker is ready and accepting tasks")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Worker关闭回调"""
    logger.info("Celery worker is shutting down")


@celery_app.task(bind=True, name="agent.dispatch")
def dispatch_agent_task(self, task_id: str, agent_type: str, params: dict):
    """
    分发Agent任务

    Args:
        task_id: 任务ID
        agent_type: Agent类型 (convolution, pooling, fullconnect等)
        params: 任务参数
    """
    logger.info(f"Dispatching {agent_type} task for {task_id}")

    try:
        # 根据agent_type分发到不同的处理函数
        handlers = {
            "convolution": _handle_convolution,
            "pooling": _handle_pooling,
            "fullconnect": _handle_fullconnect,
            "output": _handle_output,
            "backward": _handle_backward,
        }

        handler = handlers.get(agent_type)
        if not handler:
            raise ValueError(f"Unknown agent type: {agent_type}")

        result = handler(task_id, params)
        logger.info(f"Completed {agent_type} task for {task_id}")
        return result

    except Exception as e:
        logger.error(f"Failed to dispatch {agent_type} task for {task_id}: {e}")
        raise


@celery_app.task(bind=True, name="agent.process_pipeline")
def process_pipeline(self, task_id: str, start_layer: str = "convolution"):
    """
    处理完整的神经网络管道

    Args:
        task_id: 任务ID
        start_layer: 起始层 (默认convolution)
    """
    logger.info(f"Starting pipeline for task {task_id} from layer {start_layer}")

    layers = ["convolution", "pooling", "fullconnect1", "fullconnect2", "fullconnect3", "output"]
    start_idx = layers.index(start_layer) if start_layer in layers else 0

    results = {}
    for layer in layers[start_idx:]:
        try:
            logger.info(f"Processing layer {layer} for task {task_id}")
            result = dispatch_agent_task.apply(args=[task_id, layer, {}]).get()
            results[layer] = result
        except Exception as e:
            logger.error(f"Pipeline failed at layer {layer} for task {task_id}: {e}")
            results[layer] = {"error": str(e)}
            break

    return results


def _handle_convolution(task_id: str, params: dict) -> dict:
    """处理卷积层任务"""
    from app.services.convolution.service import get_convolution_service

    service = get_convolution_service()
    return service.process_task(task_id, params.get("code_repo_path", ""))


def _handle_pooling(task_id: str, params: dict) -> dict:
    """处理池化层任务"""
    from app.services.pooling.service import get_pooling_service

    service = get_pooling_service()
    return service.process_task(task_id)


def _handle_fullconnect(task_id: str, params: dict) -> dict:
    """处理全连接层任务"""
    from app.services.fullconnect.service_fc1 import get_global_understanding_service
    from app.services.fullconnect.service_fc2 import get_code_generation_service
    from app.services.fullconnect.service_fc3 import get_test_generation_service

    global_understanding = get_global_understanding_service()
    code_generation = get_code_generation_service()
    test_generation = get_test_generation_service()

    fc1_result = global_understanding.process_task(task_id, params)
    fc2_result = code_generation.process_task(task_id, fc1_result)
    fc3_result = test_generation.process_task(task_id, fc2_result)

    return fc3_result


def _handle_output(task_id: str, params: dict) -> dict:
    """处理输出层任务"""
    from app.services.output.service import get_output_service

    service = get_output_service()
    return service.process_task(task_id, params)


def _handle_backward(task_id: str, params: dict) -> dict:
    """处理反向传播层任务"""
    from app.services.backward.service import get_backward_service

    service = get_backward_service()
    return service.process_task(task_id, params)


# Auto-discover tasks
celery_app.autodiscover_tasks(["app.services"])

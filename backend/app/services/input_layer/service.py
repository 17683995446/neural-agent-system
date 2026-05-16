"""
输入层服务 - 接收用户输入的任务需求与目标代码工程信息，完成任务初始化、参数校验、上下文构建
需求预分解：LLM将复合需求拆分为SubRequirement列表，单条需求直接返回
"""
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import git
from fastapi import HTTPException

from app.core.llm_client import create_llm_client
from app.core.llm_utils import extract_json_from_llm_response
from app.core.logging import logger
from app.models.database import SessionLocal, TaskModel
from app.models.schemas import TaskInput, TaskContext, TaskStatus
from app.models.modification import SubRequirement


class InputLayerService:
    """输入层服务"""

    def __init__(self):
        self.code_repos_dir = Path("code_repos")
        self.task_output_dir = Path("task_output")
        self.code_repos_dir.mkdir(exist_ok=True)
        self.task_output_dir.mkdir(exist_ok=True)
        self.llm_client = create_llm_client()

    def decompose_requirement(self, user_requirement: str) -> Dict[str, any]:
        """需求预分解：LLM将复合需求拆分为SubRequirement列表
        单条需求（无法再拆分）直接返回单个子需求
        返回 {"sub_requirements": [SubRequirement, ...], "is_decomposed": bool}
        """
        if not self.llm_client.is_available:
            return self._single_sub_requirement(user_requirement)

        if not self._is_likely_composite(user_requirement):
            return self._single_sub_requirement(user_requirement)

        try:
            prompt = f"""你是需求分析专家。请将以下用户需求拆分为独立的子需求。
每个子需求应该是可以独立规划和执行的。

用户需求: {user_requirement}

请严格按JSON格式返回:
{{
  "sub_requirements": [
    {{"id": "sub_0", "description": "子需求描述", "scope_hint": "涉及的模块/文件关键词(逗号分隔)", "priority": "high/medium/low"}}
  ]
}}

拆分规则:
- 如果需求本身就是单一的，返回一个子需求即可
- 如果需求包含"和"、"以及"、"同时"、"并且"等连接词连接的不同关注点，按关注点拆分
- 每个子需求应当有明确的、独立的修改目标
- scope_hint填入涉及的代码区域关键词(如auth,routing,database等)

只返回JSON，不要其他内容。"""

            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=2048
            )
            text = self.llm_client.get_response_text(response)
            if not text:
                return self._single_sub_requirement(user_requirement)

            result = extract_json_from_llm_response(text, fallback=None)
            if not result or "sub_requirements" not in result:
                return self._single_sub_requirement(user_requirement)

            subs = []
            for i, item in enumerate(result["sub_requirements"]):
                item.setdefault("id", f"sub_{i}")
                item.setdefault("scope_hint", "")
                item.setdefault("priority", "medium")
                try:
                    subs.append(SubRequirement(**item))
                except Exception:
                    subs.append(SubRequirement(
                        id=f"sub_{i}",
                        description=item.get("description", str(item)),
                        scope_hint=item.get("scope_hint", ""),
                        priority=item.get("priority", "medium"),
                    ))

            if not subs:
                return self._single_sub_requirement(user_requirement)

            is_decomposed = len(subs) > 1
            logger.info(
                "[LLM] Input: requirement decomposed into %d sub-requirements (decomposed=%s)",
                len(subs), is_decomposed,
            )
            return {"sub_requirements": subs, "is_decomposed": is_decomposed}

        except Exception as e:
            logger.warning(f"[LLM] Input requirement decomposition failed: {e}")
            return self._single_sub_requirement(user_requirement)

    @staticmethod
    def _single_sub_requirement(user_requirement: str) -> Dict[str, any]:
        return {
            "sub_requirements": [SubRequirement(
                id="sub_0", description=user_requirement, scope_hint="", priority="high"
            )],
            "is_decomposed": False,
        }

    @staticmethod
    def _is_likely_composite(requirement: str) -> bool:
        composite_indicators = [
            r"[，,]\s*(?:以及|并且|同时|另外|此外|还有|且)",
            r"(?:以及|并且|同时|另外|此外|还有|且)\s",
            r"(?:add|implement|refactor|fix|update|remove)\s.+?(?:and|plus|also|as well as)\s",
            r"\d+\.\s",
        ]
        for pattern in composite_indicators:
            if re.search(pattern, requirement, re.IGNORECASE):
                return True
        sentences = re.split(r'[。.！!？?]', requirement)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
        if len(meaningful) >= 3:
            return True
        return False

    def validate_task_input(self, task_input: TaskInput) -> bool:
        """验证任务输入参数"""
        if not task_input.user_requirement:
            raise HTTPException(status_code=400, detail="user_requirement cannot be empty")

        if not task_input.code_repo_url and not task_input.local_code_path:
            raise HTTPException(
                status_code=400,
                detail="Either code_repo_url or local_code_path must be provided"
            )

        if task_input.code_repo_url and task_input.local_code_path:
            raise HTTPException(
                status_code=400,
                detail="Only one of code_repo_url or local_code_path should be provided"
            )

        return True

    def clone_or_copy_code_repo(
        self,
        repo_url: Optional[str],
        local_path: Optional[str],
        task_id: str,
        target_branch: str
    ) -> str:
        """克隆远程仓库或复制本地仓库到临时目录"""
        task_repo_dir = self.code_repos_dir / task_id

        if repo_url:
            try:
                logger.info(f"Cloning repository {repo_url} to {task_repo_dir}")
                git.Repo.clone_from(
                    repo_url,
                    task_repo_dir,
                    branch=target_branch,
                    depth=1
                )
                logger.info(f"Successfully cloned repository to {task_repo_dir}")
                return str(task_repo_dir)
            except git.GitCommandError as e:
                logger.error(f"Failed to clone repository: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to clone repository: {str(e)}")

        elif local_path:
            local_path_obj = Path(local_path).resolve()
            if not local_path_obj.exists():
                raise HTTPException(status_code=400, detail=f"Local path does not exist: {local_path}")
            workspace_root = Path.cwd().resolve()
            try:
                local_path_obj.relative_to(workspace_root)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Local path must be within workspace: {local_path_obj} (root: {workspace_root})"
                )

            try:
                logger.info(f"Copying local repository from {local_path} to {task_repo_dir}")
                # Remove existing directory if it exists to prevent nested copies
                if task_repo_dir.exists():
                    shutil.rmtree(task_repo_dir)
                shutil.copytree(local_path, task_repo_dir, dirs_exist_ok=True)
                logger.info(f"Successfully copied repository to {task_repo_dir}")
                return str(task_repo_dir)
            except Exception as e:
                logger.error(f"Failed to copy local repository: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to copy local repository: {str(e)}")

    def create_task_context(
        self,
        task_input: TaskInput,
        code_repo_path: str
    ) -> TaskContext:
        """创建任务上下文"""
        context = TaskContext(
            task_id=task_input.task_id,
            user_requirement=task_input.user_requirement,
            code_repo_path=code_repo_path,
            target_branch=task_input.target_branch,
            max_iteration=task_input.max_iteration,
            learning_rate=task_input.learning_rate,
            llm_config=task_input.llm_config,
            current_iteration=0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        return context

    def save_task_to_db(self, task_input: TaskInput, code_repo_path: str) -> TaskModel:
        """保存任务元数据到数据库"""
        db = SessionLocal()
        try:
            task_model = TaskModel(
                task_id=task_input.task_id,
                user_requirement=task_input.user_requirement,
                code_repo_url=str(task_input.code_repo_url) if task_input.code_repo_url else None,
                local_code_path=task_input.local_code_path,
                target_branch=task_input.target_branch,
                max_iteration=task_input.max_iteration,
                learning_rate=task_input.learning_rate,
                llm_config=task_input.llm_config,
                status=TaskStatus.PENDING.value,
                md_document_path=None,
                iteration_count=0,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(task_model)
            db.commit()
            db.refresh(task_model)
            logger.info(f"Task {task_input.task_id} saved to database")
            return task_model
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save task to database: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save task: {str(e)}")
        finally:
            db.close()

    def create_task_output_dir(self, task_id: str) -> Path:
        """创建任务输出目录结构"""
        output_dir = self.task_output_dir / task_id
        subdirs = [
            "convolution",
            "pooling",
            "global_understanding",
            "code_generation",
            "test_generation",
            "output"
        ]
        for subdir in subdirs:
            (output_dir / subdir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created task output directory: {output_dir}")
        return output_dir

    def initialize_task(self, task_input: TaskInput) -> TaskContext:
        """初始化任务的完整流程"""
        logger.info(f"Initializing task {task_input.task_id}")

        # 1. 验证输入参数
        self.validate_task_input(task_input)

        # 2. 克隆或复制代码仓库
        code_repo_path = self.clone_or_copy_code_repo(
            repo_url=str(task_input.code_repo_url) if task_input.code_repo_url else None,
            local_path=task_input.local_code_path,
            task_id=task_input.task_id,
            target_branch=task_input.target_branch
        )

        # 3. 创建任务上下文
        task_context = self.create_task_context(task_input, code_repo_path)

        # 4. 保存任务元数据到数据库
        self.save_task_to_db(task_input, code_repo_path)

        # 5. 创建任务输出目录
        self.create_task_output_dir(task_input.task_id)

        logger.info(f"Task {task_input.task_id} initialized successfully")
        return task_context


# Singleton instance
input_layer_service = InputLayerService()
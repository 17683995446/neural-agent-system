"""
池化层服务 - 信息压缩层
对应CNN的池化操作，对卷积层输出进行信息微压缩
LLM优先语义压缩，降级到关键词匹配
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.llm_client import create_llm_client, get_llm_client
from app.core.llm_utils import extract_json_from_llm_response
from app.core.io_utils import save_layer_output
from app.core.logging import logger
from app.services.pooling.hierarchical_compressor import HierarchicalCompressor


class PoolingConfig:
    """池化配置"""
    def __init__(
        self,
        compression_threshold: float = 0.76,
        max_output_items: int = 20,
        use_llm: bool = True
    ):
        self.compression_threshold = compression_threshold
        self.max_output_items = max_output_items
        self.use_llm = use_llm and get_llm_client().is_available


class SemanticCompressor:
    """语义压缩器 - 简化版上下文压缩"""

    def __init__(self, threshold: float = 0.76, max_output_items: int = 20):
        self.threshold = threshold
        self.max_output_items = max_output_items

    def compress(self, items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        基于语义相似度压缩信息
        简化实现：按关键词匹配度过滤
        """
        if not items:
            return []

        query_keywords = self._extract_keywords(query)
        scored_items = []

        for item in items:
            score = self._calculate_relevance(item, query_keywords)
            if score >= self.threshold:
                scored_items.append({
                    "item": item,
                    "score": score
                })

        # 按分数排序，取前N个
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        return [s["item"] for s in scored_items[:self.max_output_items]]

    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be",
            "been", "being", "have", "has", "had", "do", "does",
            "did", "will", "would", "could", "should", "may",
            "might", "must", "shall", "can", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into",
            "through", "during", "before", "after", "above", "below",
            "between", "under", "again", "further", "then", "once"
        }

        words = text.lower().split()
        return [w for w in words if w not in stop_words and len(w) > 2]

    def _calculate_relevance(self, item: Dict[str, Any], keywords: List[str]) -> float:
        """计算项目与查询的相关度 — AST增强版"""
        return self.calculate_relevance_enhanced(item, keywords)

    def calculate_relevance_enhanced(self, item: Dict[str, Any], keywords: List[str]) -> float:
        """AST增强相关性评分：函数名+类名+imports+summary+路径"""
        score = 0.0

        for func in item.get("functions", []):
            func_name = func.get("name", "")
            for kw in keywords:
                if kw in func_name.lower():
                    score += 0.3

        for cls in item.get("classes", []):
            class_name = cls.get("name", "")
            for kw in keywords:
                if kw in class_name.lower():
                    score += 0.3

        for imp in item.get("imports", []):
            imp_str = imp.lower() if isinstance(imp, str) else ""
            for kw in keywords:
                if kw in imp_str:
                    score += 0.15

        summary = item.get("summary", "").lower() if item.get("summary") else ""
        if summary:
            for kw in keywords:
                if kw in summary:
                    score += 0.2

        file_path = item.get("file_path", "").lower()
        if file_path:
            for kw in keywords:
                if kw in file_path:
                    score += 0.25

        score = min(score, 2.0)

        has_content = (
            len(item.get("functions", [])) > 0
            or len(item.get("classes", [])) > 0
            or len(item.get("imports", [])) > 0
        )
        if not has_content and score == 0:
            score = 0.01

        return score


class InformationAggregator:
    """信息聚合器 - 将多个分析结果聚合成全局特征"""

    @staticmethod
    def aggregate(analysis_results: List[Dict[str, Any]], keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """聚合卷积层输出 — 按相关性排序后截断"""
        if not analysis_results:
            return {"error": "No results to aggregate"}

        all_functions = []
        all_classes = []
        all_imports = []

        for result in analysis_results:
            if "error" in result:
                continue

            relevance = result.get("_relevance", 0)

            all_functions.extend([
                {
                    "name": f.get("name"),
                    "file": result.get("file_path", ""),
                    "line": f.get("start_line"),
                    "relevance": relevance,
                }
                for f in result.get("functions", [])
            ])

            all_classes.extend([
                {
                    "name": c.get("name"),
                    "file": result.get("file_path", ""),
                    "line": c.get("start_line"),
                    "relevance": relevance,
                }
                for c in result.get("classes", [])
            ])

            all_imports.extend(result.get("imports", []))

        seen_funcs = set()
        unique_functions = []
        for f in all_functions:
            key = f"{f['name']}:{f['file']}"
            if key not in seen_funcs:
                seen_funcs.add(key)
                unique_functions.append(f)

        seen_classes = set()
        unique_classes = []
        for c in all_classes:
            key = f"{c['name']}:{c['file']}"
            if key not in seen_classes:
                seen_classes.add(key)
                unique_classes.append(c)

        unique_functions.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        unique_classes.sort(key=lambda x: x.get("relevance", 0), reverse=True)

        return {
            "total_files": len(analysis_results),
            "total_functions": len(unique_functions),
            "total_classes": len(unique_classes),
            "unique_imports": list(set(all_imports))[:100],
            "top_functions": unique_functions[:50],
            "top_classes": unique_classes[:50]
        }


class PoolingLayerService:
    """池化层服务"""

    def __init__(self, config: Optional[PoolingConfig] = None):
        self.config = config or PoolingConfig()
        self.compressor = SemanticCompressor(
            threshold=self.config.compression_threshold
        )
        self.aggregator = InformationAggregator()
        self.llm_client = create_llm_client()
        self._hierarchical_compressor = HierarchicalCompressor()

    def compress_with_llm(
        self,
        analysis_results: List[Dict[str, Any]],
        user_requirement: str
    ) -> Optional[List[Dict[str, Any]]]:
        """AST增强评分 + LLM辅助筛选：先对全量数据评分排序，再让LLM辅助判断"""
        if not self.llm_client.is_available or not analysis_results:
            return None
        try:
            keywords = self.compressor.extract_keywords(user_requirement)
            scored = []
            for r in analysis_results:
                score = self.compressor.calculate_relevance_enhanced(r, keywords)
                r["_relevance"] = score
                scored.append(r)
            scored.sort(key=lambda x: x.get("_relevance", 0), reverse=True)

            top_n = min(len(scored), max(20, self.config.max_output_items))
            top_items = scored[:top_n]
            items_summary = []
            for r in top_items[:30]:
                fns = [f.get("name", "") for f in r.get("functions", [])[:8]]
                cls = [c.get("name", "") for c in r.get("classes", [])[:5]]
                imp_summary = r.get("summary", "")[:60]
                items_summary.append(
                    f"File {r.get('file_path', '?')} (score={r.get('_relevance', 0):.2f}): "
                    f"fns={fns}, cls={cls}, summary={imp_summary}"
                )

            prompt = f"""从以下按相关性排序的代码分析结果中，选出与用户需求最相关的文件路径。

用户需求: {user_requirement}

代码分析(top {len(top_items)}):
{chr(10).join(items_summary)}

返回JSON: {{"relevant_files": ["文件路径1", ...]}}
只返回JSON，最多返回{self.config.max_output_items}个文件。"""
            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=1024
            )
            text = self.llm_client.get_response_text(response)
            if text:
                result = extract_json_from_llm_response(text, fallback=None)
                if result:
                    relevant_paths = set(result.get("relevant_files", []))
                    relevant = [
                        r for r in top_items
                        if r.get("file_path") in relevant_paths
                    ]
                    if relevant:
                        for r in relevant:
                            r.pop("_relevance", None)
                        logger.info(f"[LLM] Pooling: LLM selected {len(relevant)} from top {top_n}")
                        return relevant

            for r in top_items:
                r.pop("_relevance", None)
            logger.info(f"[Pooling] AST-scored top {len(top_items)} items (LLM fallback)")
            return top_items
        except Exception as e:
            logger.warning(f"[LLM] Pooling compression failed: {e}")
            return None

    def compress_features(
        self,
        analysis_results: List[Dict[str, Any]],
        user_requirement: str
    ) -> List[Dict[str, Any]]:
        """压缩特征 - 优先关键词匹配，降级到LLM"""
        logger.info(f"Compressing {len(analysis_results)} analysis results")

        if self.config.use_llm:
            llm_result = self.compress_with_llm(analysis_results, user_requirement)
            if llm_result is not None:
                return llm_result

        compressed = self.compressor.compress(
            analysis_results,
            user_requirement
        )

        logger.info(f"Compressed to {len(compressed)} relevant items")
        return compressed

    def aggregate_information(
        self,
        analysis_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """聚合信息 - 生成全局特征"""
        return self.aggregator.aggregate(analysis_results)

    def create_pooling_output(
        self,
        compressed_results: List[Dict[str, Any]],
        global_features: Dict[str, Any],
        task_id: str,
        user_requirement: str
    ) -> Dict[str, Any]:
        """创建池化层输出"""
        output = {
            "task_id": task_id,
            "layer": "pooling",
            "user_requirement": user_requirement,
            "compressed_features": compressed_results,
            "global_features": global_features,
            "total_files_processed": len(compressed_results),
            "created_at": datetime.now().isoformat()
        }

        return output

    def process_task(
        self,
        task_id: str,
        convolution_output: Dict[str, Any],
        user_requirement: str,
        *,
        enable_hierarchical: bool = True,
    ) -> Dict[str, Any]:
        logger.info("Pooling layer processing task %s", task_id)

        analyzed_files = convolution_output.get("analyzed_files", [])
        modules = convolution_output.get("modules")

        if enable_hierarchical and len(analyzed_files) > 20:
            compressed_output = self._hierarchical_compressor.compress(
                analyzed_files,
                user_requirement=user_requirement,
                modules=modules,
            )
            relevant_paths = set()
            for fd in compressed_output.function_details:
                fp = fd.get("file_path")
                if fp:
                    relevant_paths.add(fp)
            for fs in compressed_output.file_summaries:
                fp = fs.get("file_path") if isinstance(fs, dict) else None
                if fp:
                    relevant_paths.add(fp)
            if relevant_paths:
                compressed = [
                    r for r in analyzed_files
                    if r.get("file_path") in relevant_paths
                ]
            else:
                compressed = self.compressor.compress(analyzed_files, user_requirement)
            if len(compressed) > self.config.max_output_items:
                compressed = compressed[:self.config.max_output_items]
            global_features = {
                "hierarchical": True,
                "module_summaries": compressed_output.module_summaries,
                "file_summaries": compressed_output.file_summaries,
                "function_details": compressed_output.function_details,
                "total_modules": compressed_output.total_modules,
                "total_files_scanned": compressed_output.total_files_scanned,
                "total_functions_scanned": compressed_output.total_functions_scanned,
            }
        else:
            compressed = self.compress_features(analyzed_files, user_requirement)
            global_features = self.aggregate_information(analyzed_files)

        output = self.create_pooling_output(
            compressed, global_features, task_id, user_requirement
        )

        save_layer_output(task_id, "pooling", output, "pooling_results.json")

        logger.info("Pooling layer completed for task %s", task_id)
        return output


# Singleton instance
_pooling_service: Optional[PoolingLayerService] = None


def get_pooling_service() -> PoolingLayerService:
    """获取池化层服务实例"""
    global _pooling_service
    if _pooling_service is None:
        _pooling_service = PoolingLayerService()
    return _pooling_service
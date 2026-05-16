import json
from typing import Optional

from app.core.llm import llm_generate
from app.models.models import Question


def grade_objective(question: Question, user_answer: str) -> dict:
    is_correct = user_answer.strip().upper() == question.answer.strip().upper()
    score = 100 if is_correct else 0
    return {
        "score": score,
        "is_correct": is_correct,
        "user_answer": user_answer,
        "correct_answer": question.answer,
        "feedback": "回答正确！" if is_correct else f"回答错误，正确答案是 {question.answer}",
    }


async def grade_subjective(question: Question, user_answer: str) -> dict:
    prompt = (
        f"你是CPA考试阅卷专家。请按照CPA考试评分标准对以下主观题进行评分：\n\n"
        f"科目：{question.subject}\n"
        f"章节：{question.chapter or '未知'}\n"
        f"题目：{question.content}\n"
        f"参考答案：{question.answer}\n"
        f"考生答案：{user_answer}\n\n"
        f"请严格按以下JSON格式返回评分结果，不要添加任何其他文字：\n"
        '{\n'
        '  "score": 0-100,\n'
        '  "key_points": ["得分点1", "得分点2"],\n'
        '  "missed_points": ["遗漏点1", "遗漏点2"],\n'
        '  "feedback": "详细评语",\n'
        '  "suggestions": ["改进建议1", "改进建议2"]\n'
        '}'
    )
    response = await llm_generate(prompt, max_tokens=2048)
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        result = json.loads(text)
        return {
            "score": result.get("score", 0),
            "key_points": result.get("key_points", []),
            "missed_points": result.get("missed_points", []),
            "feedback": result.get("feedback", ""),
            "suggestions": result.get("suggestions", []),
            "is_correct": result.get("score", 0) >= 60,
        }
    except (json.JSONDecodeError, TypeError):
        return {
            "score": 0,
            "key_points": [],
            "missed_points": [],
            "feedback": "评分服务暂时不可用，请稍后重试",
            "suggestions": [],
            "is_correct": False,
        }

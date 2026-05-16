import json
from typing import Optional

from app.core.llm import llm_generate

CPA_SYSTEM_PROMPT = (
    "你是CPA（注册会计师）考试辅导专家，精通会计、审计、税法、经济法、财务成本管理、公司战略与风险管理六大科目。"
    "你的职责是：\n"
    "1. 准确回答CPA考试相关问题\n"
    "2. 提供权威、准确的会计准则和法规依据\n"
    "3. 给出清晰的解题思路和方法\n"
    "4. 指出易混淆和易错的知识点\n"
    "5. 适当拓展相关知识，帮助学员建立知识体系\n\n"
    "回答要求：\n"
    "- 内容准确，符合最新会计准则和税法规定\n"
    "- 条理清晰，分点阐述\n"
    "- 适当举例帮助理解\n"
    "- 标注重要程度和考试频率"
)


async def answer_question(question: str, context: Optional[str] = None) -> str:
    messages = [
        {"role": "system", "content": CPA_SYSTEM_PROMPT},
    ]
    if context:
        messages.append({"role": "system", "content": f"参考资料：\n{context}"})
    messages.append({"role": "user", "content": question})
    from app.core.llm import llm_chat
    answer = await llm_chat(messages, max_tokens=2048)
    return answer if answer else "抱歉，暂时无法回答该问题，请稍后重试。"


async def analyze_wrong_answer(
    question_content: str,
    user_answer: str,
    correct_answer: str,
) -> dict:
    prompt = (
        f"你是CPA考试错题分析专家。请分析以下错题：\n\n"
        f"题目：{question_content}\n"
        f"考生答案：{user_answer}\n"
        f"正确答案：{correct_answer}\n\n"
        f"请严格按以下JSON格式返回分析结果，不要添加任何其他文字：\n"
        '{\n'
        '  "error_type": "概念混淆/计算错误/审题不清/知识盲区/逻辑错误",\n'
        '  "error_analysis": "详细分析错误原因",\n'
        '  "knowledge_gap": ["缺失的知识点1", "缺失的知识点2"],\n'
        '  "remedy": ["补救措施1", "补救措施2"],\n'
        '  "similar_mistakes": "类似常见错误提醒",\n'
        '  "review_priority": "high/medium/low"\n'
        '}'
    )
    response = await llm_generate(prompt, max_tokens=2048)
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        result = json.loads(text)
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "error_type": "未知",
            "error_analysis": "分析服务暂时不可用",
            "knowledge_gap": [],
            "remedy": ["建议重新复习相关知识点"],
            "similar_mistakes": "",
            "review_priority": "medium",
        }

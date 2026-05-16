import json
from typing import List, Optional

from app.core.llm import llm_generate

SUBJECT_PROMPTS = {
    "会计": "会计（含财务会计、管理会计）",
    "审计": "审计",
    "税法": "税法",
    "经济法": "经济法",
    "财务成本管理": "财务成本管理",
    "公司战略与风险管理": "公司战略与风险管理",
}

LEVEL_CONFIG = {
    "beginner": {"count": 5, "difficulty": "基础", "prompt": "适合零基础或刚开始备考的学员"},
    "intermediate": {"count": 8, "difficulty": "中等", "prompt": "适合有一定基础、正在强化阶段的学员"},
    "advanced": {"count": 10, "difficulty": "较难", "prompt": "适合冲刺阶段、基础较好的学员"},
}


async def generate_diagnosis_questions(
    subjects: List[str],
    level: str = "beginner",
    quick_mode: bool = False,
) -> List[dict]:
    config = LEVEL_CONFIG.get(level, LEVEL_CONFIG["beginner"])
    count = 3 if quick_mode else config["count"]
    all_questions = []
    for subject in subjects:
        subject_name = SUBJECT_PROMPTS.get(subject, subject)
        prompt = (
            f"你是CPA（注册会计师）考试命题专家。请为「{subject_name}」科目生成{count}道诊断测试题。\n\n"
            f"要求：\n"
            f"- 难度：{config['difficulty']}，{config['prompt']}\n"
            f"- 题型：单选题为主，每题4个选项（A/B/C/D）\n"
            f"- 覆盖该科目核心知识点，用于评估学员对该科目的掌握程度\n"
            f"- 题目应从易到难排列\n\n"
            f"请严格按以下JSON格式返回，不要添加任何其他文字：\n"
            f'[{{"content": "题干", "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}}, "answer": "正确选项字母", "knowledge_point": "知识点", "difficulty": 1-5}}]'
        )
        response = await llm_generate(prompt, max_tokens=2048)
        try:
            text = response.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])
            questions = json.loads(text)
            for q in questions:
                q["subject"] = subject
                q["q_type"] = "single_choice"
            all_questions.extend(questions)
        except (json.JSONDecodeError, TypeError):
            all_questions.append({
                "content": f"{subject_name}诊断题 - 数据解析失败，请重试",
                "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
                "answer": "A", "knowledge_point": "综合", "difficulty": 3,
                "subject": subject, "q_type": "single_choice",
            })
    return all_questions


async def analyze_diagnosis_results(
    answers: List[dict],
    user_id: int,
    db=None,
) -> dict:
    results_summary = []
    for ans in answers:
        results_summary.append(
            f"题目：{ans.get('content', '未知')[:80]}\n"
            f"用户答案：{ans.get('user_answer', '未作答')}\n"
            f"正确答案：{ans.get('correct_answer', '未知')}\n"
            f"是否正确：{'是' if ans.get('is_correct') else '否'}\n"
            f"知识点：{ans.get('knowledge_point', '未知')}"
        )
    prompt = (
        "你是CPA考试备考诊断分析专家。请根据以下诊断测试结果，生成详细的学习画像分析：\n\n"
        + "\n---\n".join(results_summary)
        + "\n\n请严格按以下JSON格式返回分析结果，不要添加任何其他文字：\n"
        '{\n'
        '  "overall_level": "beginner/intermediate/advanced",\n'
        '  "overall_score": 0-100,\n'
        '  "subject_analysis": [{"subject": "科目", "mastery": 0-100, "weak_points": ["知识点1"], "strong_points": ["知识点2"]}],\n'
        '  "study_suggestions": ["建议1", "建议2", "建议3"],\n'
        '  "priority_subjects": ["最需优先复习的科目"],\n'
        '  "estimated_study_hours": 预计需要的学习小时数,\n'
        '  "knowledge_map": {"知识点": "掌握程度(0-100)"}\n'
        '}'
    )
    response = await llm_generate(prompt, max_tokens=2048)
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        profile = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        correct = sum(1 for a in answers if a.get("is_correct"))
        total = len(answers) if answers else 1
        profile = {
            "overall_level": "beginner",
            "overall_score": round(correct / total * 100),
            "subject_analysis": [],
            "study_suggestions": ["建议从基础知识开始系统学习"],
            "priority_subjects": [],
            "estimated_study_hours": 200,
            "knowledge_map": {},
        }
    return profile

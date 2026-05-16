from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.models import User, Question, StudyRecord
from app.ai.diagnosis import generate_diagnosis_questions, analyze_diagnosis_results
from app.ai.recommend import get_recommendations
from app.ai.grader import grade_objective, grade_subjective
from app.ai.qa import answer_question, analyze_wrong_answer
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/ai", tags=["ai"])


class DiagnosisReq(BaseModel):
    subjects: List[str] = ["会计"]
    level: str = "beginner"
    quick_mode: bool = False


class DiagnosisSubmitReq(BaseModel):
    answers: List[dict]


class GradeReq(BaseModel):
    question_id: int
    user_answer: str
    q_type: str = "subjective"


class ExplainReq(BaseModel):
    question_id: int


class QAReq(BaseModel):
    question: str
    context: Optional[str] = None


class WrongAnalysisReq(BaseModel):
    question_id: int
    user_answer: str
    correct_answer: str


class StudyPlanReq(BaseModel):
    subjects: List[str] = ["会计"]
    available_hours: int = 2
    months: int = 3


@router.post("/diagnosis")
async def diagnosis(
    req: DiagnosisReq,
    user: User = Depends(get_current_user),
):
    questions = await generate_diagnosis_questions(req.subjects, req.level, req.quick_mode)
    return {"questions": questions}


@router.post("/diagnosis/submit")
async def diagnosis_submit(
    req: DiagnosisSubmitReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await analyze_diagnosis_results(req.answers, user.id, db)
    return profile


@router.get("/recommend")
async def recommend(
    count: int = 10,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    questions = await get_recommendations(user.id, count, db)
    return {"questions": questions}


@router.post("/grade")
async def grade(
    req: GradeReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == req.question_id))
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if req.q_type in ("single_choice", "multi_choice", "judge"):
        result_data = grade_objective(question, req.user_answer)
    else:
        result_data = await grade_subjective(question, req.user_answer)
    return result_data


@router.post("/explain")
async def explain(
    req: ExplainReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == req.question_id))
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    prompt = (
        f"你是一位CPA考试辅导专家。请对以下题目进行详细解析：\n\n"
        f"科目：{question.subject}\n"
        f"章节：{question.chapter or '未知'}\n"
        f"题目：{question.content}\n"
    )
    if question.options:
        options_text = "\n".join([f"  {k}. {v}" for k, v in question.options.items()]) if isinstance(question.options, dict) else str(question.options)
        prompt += f"选项：\n{options_text}\n"
    prompt += (
        f"正确答案：{question.answer}\n"
        f"已有解析：{question.analysis or '无'}\n\n"
        f"请提供更深入、更易懂的解析，包括：\n"
        f"1. 知识点梳理\n2. 解题思路\n3. 易错点提醒\n4. 相关拓展知识"
    )
    from app.core.llm import llm_generate
    explanation = await llm_generate(prompt, max_tokens=2048)
    return {"explanation": explanation}


@router.post("/qa")
async def qa(
    req: QAReq,
    user: User = Depends(get_current_user),
):
    answer = await answer_question(req.question, req.context)
    return {"answer": answer}


@router.post("/wrong-analysis")
async def wrong_analysis(
    req: WrongAnalysisReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id == req.question_id))
    question = result.scalar_one_or_none()
    question_content = question.content if question else "未知题目"
    analysis_result = await analyze_wrong_answer(
        question_content, req.user_answer, req.correct_answer,
    )
    return analysis_result


@router.get("/study-plan")
async def study_plan(
    subjects: str = "会计",
    available_hours: int = 2,
    months: int = 3,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    subject_list = [s.strip() for s in subjects.split(",")]
    weak_points = []
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == user.id,
            StudyRecord.is_correct == False,
        ).order_by(StudyRecord.created_at.desc()).limit(50)
    )
    wrong_records = result.scalars().all()
    for wr in wrong_records:
        qr = await db.execute(select(Question).where(Question.id == wr.question_id))
        q = qr.scalar_one_or_none()
        if q and q.knowledge_point:
            weak_points.append(q.knowledge_point)

    prompt = (
        f"你是一位CPA考试备考规划专家。请根据以下信息生成个性化学习计划：\n\n"
        f"学员等级：{user.level}\n"
        f"CPA阶段：{user.cpa_stage or '未设定'}\n"
        f"备考科目：{', '.join(subject_list)}\n"
        f"每天可用学习时间：{available_hours}小时\n"
        f"备考周期：{months}个月\n"
        f"薄弱知识点：{', '.join(set(weak_points[:10])) if weak_points else '暂无数据'}\n\n"
        f"请生成详细的学习计划，包括：\n"
        f"1. 每个科目的时间分配建议\n"
        f"2. 每周学习目标\n"
        f"3. 薄弱知识点强化策略\n"
        f"4. 模拟考试安排\n"
        f"5. 复习和冲刺建议"
    )
    from app.core.llm import llm_generate
    plan = await llm_generate(prompt, max_tokens=2048)
    return {"plan": plan}

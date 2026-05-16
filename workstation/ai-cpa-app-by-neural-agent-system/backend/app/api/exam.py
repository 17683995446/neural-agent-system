from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import ExamPaper, ExamResult, Question
from app.api.auth import get_current_user
from app.models.models import User
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

router = APIRouter(prefix="/exam", tags=["exam"])


class SubmitExamReq(BaseModel):
    answers: dict
    time_used: int = 0


@router.get("/papers")
async def list_papers(
    subject: Optional[str] = None,
    is_mock: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ExamPaper)
    if subject:
        stmt = stmt.where(ExamPaper.subject == subject)
    if is_mock is not None:
        stmt = stmt.where(ExamPaper.is_mock == is_mock)
    result = await db.execute(stmt)
    papers = result.scalars().all()
    return [
        {
            "id": p.id, "title": p.title, "subject": p.subject,
            "duration": p.duration, "total_score": p.total_score,
            "is_mock": p.is_mock, "year": p.year,
            "question_count": len(p.questions) if p.questions else 0,
        }
        for p in papers
    ]


@router.get("/papers/{paper_id}")
async def get_paper(paper_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExamPaper).where(ExamPaper.id == paper_id))
    paper = result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    question_details = []
    if paper.questions:
        for qid in paper.questions:
            qr = await db.execute(select(Question).where(Question.id == qid))
            q = qr.scalar_one_or_none()
            if q:
                question_details.append({
                    "id": q.id, "subject": q.subject, "q_type": q.q_type,
                    "difficulty": q.difficulty, "content": q.content, "options": q.options,
                })
    return {
        "id": paper.id, "title": paper.title, "subject": paper.subject,
        "duration": paper.duration, "total_score": paper.total_score,
        "is_mock": paper.is_mock, "year": paper.year,
        "questions": question_details,
    }


@router.post("/papers/{paper_id}/submit")
async def submit_exam(
    paper_id: int,
    req: SubmitExamReq,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExamPaper).where(ExamPaper.id == paper_id))
    paper = result.scalar_one_or_none()
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    correct_count = 0
    total_count = 0
    details = []
    if paper.questions:
        for qid in paper.questions:
            qr = await db.execute(select(Question).where(Question.id == qid))
            q = qr.scalar_one_or_none()
            if q:
                total_count += 1
                user_ans = req.answers.get(str(q.id), "")
                is_correct = user_ans.strip().upper() == q.answer.strip().upper()
                if is_correct:
                    correct_count += 1
                details.append({
                    "question_id": q.id,
                    "user_answer": user_ans,
                    "correct_answer": q.answer,
                    "is_correct": is_correct,
                })
    score = round((correct_count / total_count * 100) if total_count > 0 else 0, 2)
    exam_result = ExamResult(
        user_id=user.id, paper_id=paper_id,
        answers=req.answers, score=score, time_used=req.time_used,
        report={"correct": correct_count, "total": total_count, "details": details},
    )
    db.add(exam_result)
    await db.commit()
    await db.refresh(exam_result)
    return {
        "result_id": exam_result.id, "score": score,
        "correct": correct_count, "total": total_count,
        "details": details,
    }


@router.get("/results/{result_id}")
async def get_result(result_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExamResult).where(ExamResult.id == result_id))
    exam_result = result.scalar_one_or_none()
    if exam_result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return {
        "id": exam_result.id, "user_id": exam_result.user_id,
        "paper_id": exam_result.paper_id, "score": exam_result.score,
        "time_used": exam_result.time_used, "report": exam_result.report,
        "created_at": exam_result.created_at.isoformat() if exam_result.created_at else None,
    }


@router.get("/my-results")
async def my_results(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExamResult).where(ExamResult.user_id == user.id).order_by(ExamResult.created_at.desc())
    )
    results = result.scalars().all()
    return [
        {
            "id": r.id, "paper_id": r.paper_id, "score": r.score,
            "time_used": r.time_used,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in results
    ]

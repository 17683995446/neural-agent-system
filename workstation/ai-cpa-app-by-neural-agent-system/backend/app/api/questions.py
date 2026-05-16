from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.models import Question
from app.api.auth import get_current_user
from app.models.models import User
from pydantic import BaseModel
from typing import Optional, List, Any

router = APIRouter(prefix="/questions", tags=["questions"])


class QuestionCreate(BaseModel):
    subject: str
    chapter: Optional[str] = None
    knowledge_point: Optional[str] = None
    q_type: str = "single_choice"
    difficulty: int = 3
    content: str
    options: Optional[Any] = None
    answer: str
    analysis: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None
    tags: Optional[Any] = None


class QuestionOut(BaseModel):
    id: int
    subject: str
    chapter: Optional[str] = None
    knowledge_point: Optional[str] = None
    q_type: str
    difficulty: int
    content: str
    options: Optional[Any] = None
    answer: str
    analysis: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None
    tags: Optional[Any] = None

    class Config:
        from_attributes = True


@router.get("", response_model=List[QuestionOut])
async def list_questions(
    subject: Optional[str] = Query(None),
    chapter: Optional[str] = Query(None),
    q_type: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Question)
    if subject:
        stmt = stmt.where(Question.subject == subject)
    if chapter:
        stmt = stmt.where(Question.chapter == chapter)
    if q_type:
        stmt = stmt.where(Question.q_type == q_type)
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if keyword:
        stmt = stmt.where(Question.content.contains(keyword))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    questions = result.scalars().all()
    return [QuestionOut(
        id=q.id, subject=q.subject, chapter=q.chapter, knowledge_point=q.knowledge_point,
        q_type=q.q_type, difficulty=q.difficulty, content=q.content,
        options=q.options, answer=q.answer, analysis=q.analysis,
        year=q.year, source=q.source, tags=q.tags,
    ) for q in questions]


@router.get("/count")
async def count_questions(
    subject: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(func.count(Question.id))
    if subject:
        stmt = stmt.where(Question.subject == subject)
    result = await db.execute(stmt)
    total = result.scalar()
    return {"total": total}


@router.get("/{question_id}", response_model=QuestionOut)
async def get_question(question_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Question).where(Question.id == question_id))
    q = result.scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return QuestionOut(
        id=q.id, subject=q.subject, chapter=q.chapter, knowledge_point=q.knowledge_point,
        q_type=q.q_type, difficulty=q.difficulty, content=q.content,
        options=q.options, answer=q.answer, analysis=q.analysis,
        year=q.year, source=q.source, tags=q.tags,
    )


@router.post("", response_model=QuestionOut)
async def create_question(
    req: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    q = Question(
        subject=req.subject, chapter=req.chapter, knowledge_point=req.knowledge_point,
        q_type=req.q_type, difficulty=req.difficulty, content=req.content,
        options=req.options, answer=req.answer, analysis=req.analysis,
        year=req.year, source=req.source, tags=req.tags,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return QuestionOut(
        id=q.id, subject=q.subject, chapter=q.chapter, knowledge_point=q.knowledge_point,
        q_type=q.q_type, difficulty=q.difficulty, content=q.content,
        options=q.options, answer=q.answer, analysis=q.analysis,
        year=q.year, source=q.source, tags=q.tags,
    )

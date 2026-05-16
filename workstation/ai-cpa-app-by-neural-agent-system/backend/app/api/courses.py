from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Course, UserNote
from app.api.auth import get_current_user
from app.models.models import User
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter(prefix="/courses", tags=["courses"])


class NoteCreate(BaseModel):
    content: str
    timestamp: int = 0


@router.get("")
async def list_courses(
    subject: Optional[str] = None,
    stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Course)
    if subject:
        stmt = stmt.where(Course.subject == subject)
    if stage:
        stmt = stmt.where(Course.stage == stage)
    result = await db.execute(stmt)
    courses = result.scalars().all()
    return [
        {
            "id": c.id, "title": c.title, "subject": c.subject,
            "stage": c.stage, "chapters": c.chapters,
            "cover_url": c.cover_url, "price": c.price, "is_free": c.is_free,
        }
        for c in courses
    ]


@router.get("/{course_id}")
async def get_course(course_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return {
        "id": course.id, "title": course.title, "subject": course.subject,
        "stage": course.stage, "chapters": course.chapters,
        "cover_url": course.cover_url, "price": course.price, "is_free": course.is_free,
    }


@router.post("/{course_id}/note")
async def create_note(
    course_id: int,
    req: NoteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Course not found")
    note = UserNote(user_id=user.id, course_id=course_id, content=req.content, timestamp=req.timestamp)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {"id": note.id, "message": "Note created"}


@router.get("/{course_id}/progress")
async def get_progress(
    course_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.id == course_id))
    course = result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    notes_result = await db.execute(
        select(UserNote).where(UserNote.user_id == user.id, UserNote.course_id == course_id)
    )
    notes = notes_result.scalars().all()
    total_chapters = len(course.chapters) if course.chapters else 0
    return {
        "course_id": course_id, "total_chapters": total_chapters,
        "notes_count": len(notes),
        "notes": [{"id": n.id, "content": n.content[:100], "timestamp": n.timestamp} for n in notes],
    }

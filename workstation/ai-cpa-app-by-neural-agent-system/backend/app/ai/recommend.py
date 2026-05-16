from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.models import Question, StudyRecord


async def get_recommendations(
    user_id: int,
    count: int = 10,
    db: AsyncSession = None,
) -> List[dict]:
    wrong_knowledge_points = {}
    result = await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == user_id,
            StudyRecord.is_correct == False,
        ).order_by(StudyRecord.created_at.desc()).limit(100)
    )
    wrong_records = result.scalars().all()
    for wr in wrong_records:
        qr = await db.execute(select(Question).where(Question.id == wr.question_id))
        q = qr.scalar_one_or_none()
        if q and q.knowledge_point:
            wrong_knowledge_points[q.knowledge_point] = wrong_knowledge_points.get(q.knowledge_point, 0) + 1

    total_recent = await db.execute(
        select(func.count(StudyRecord.id)).where(StudyRecord.user_id == user_id)
    )
    total_count = total_recent.scalar() or 0
    correct_recent = await db.execute(
        select(func.count(StudyRecord.id)).where(
            StudyRecord.user_id == user_id,
            StudyRecord.is_correct == True,
        )
    )
    correct_count = correct_recent.scalar() or 0
    correct_rate = correct_count / total_count if total_count > 0 else 0.5

    if correct_rate < 0.3:
        target_difficulty = 2
    elif correct_rate < 0.5:
        target_difficulty = 3
    elif correct_rate < 0.7:
        target_difficulty = 4
    else:
        target_difficulty = 5

    recommended = []
    sorted_weak = sorted(wrong_knowledge_points.items(), key=lambda x: x[1], reverse=True)
    for kp, _ in sorted_weak[:5]:
        stmt = select(Question).where(
            Question.knowledge_point == kp,
            Question.difficulty <= target_difficulty,
        ).limit(2)
        qr = await db.execute(stmt)
        questions = qr.scalars().all()
        for q in questions:
            recommended.append(_question_to_dict(q))

    if len(recommended) < count:
        weak_subjects = set()
        for wr in wrong_records[:20]:
            qr = await db.execute(select(Question).where(Question.id == wr.question_id))
            q = qr.scalar_one_or_none()
            if q:
                weak_subjects.add(q.subject)
        for subject in weak_subjects:
            remaining = count - len(recommended)
            if remaining <= 0:
                break
            stmt = select(Question).where(
                Question.subject == subject,
                Question.difficulty <= target_difficulty,
            ).order_by(Question.difficulty.desc()).limit(remaining)
            qr = await db.execute(stmt)
            questions = qr.scalars().all()
            for q in questions:
                if not any(r["id"] == q.id for r in recommended):
                    recommended.append(_question_to_dict(q))

    if len(recommended) < count:
        remaining = count - len(recommended)
        existing_ids = [r["id"] for r in recommended]
        stmt = select(Question)
        if existing_ids:
            stmt = stmt.where(Question.id.notin_(existing_ids))
        stmt = stmt.order_by(func.random()).limit(remaining)
        qr = await db.execute(stmt)
        questions = qr.scalars().all()
        for q in questions:
            recommended.append(_question_to_dict(q))

    return recommended[:count]


def _question_to_dict(q: Question) -> dict:
    return {
        "id": q.id, "subject": q.subject, "chapter": q.chapter,
        "knowledge_point": q.knowledge_point, "q_type": q.q_type,
        "difficulty": q.difficulty, "content": q.content,
        "options": q.options, "answer": q.answer, "analysis": q.analysis,
    }

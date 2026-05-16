from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), default="用户")
    role: Mapped[str] = mapped_column(String(20), default="student")
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpa_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subjects: Mapped[str | None] = mapped_column(Text, nullable=True)
    study_hours: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    study_records = relationship("StudyRecord", back_populates="user")
    exam_results = relationship("ExamResult", back_populates="user")
    notes = relationship("UserNote", back_populates="user")
    orders = relationship("Order", back_populates="user")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(50), index=True)
    chapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    knowledge_point: Mapped[str | None] = mapped_column(String(100), nullable=True)
    q_type: Mapped[str] = mapped_column(String(20), default="single_choice")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[str | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[str | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    study_records = relationship("StudyRecord", back_populates="question")


class StudyRecord(Base):
    __tablename__ = "study_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), index=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    user_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_spent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="study_records")
    question = relationship("Question", back_populates="study_records")


class ExamPaper(Base):
    __tablename__ = "exam_papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(50))
    duration: Mapped[int] = mapped_column(Integer, default=120)
    total_score: Mapped[int] = mapped_column(Integer, default=100)
    questions: Mapped[str | None] = mapped_column(JSON, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    results = relationship("ExamResult", back_populates="paper")


class ExamResult(Base):
    __tablename__ = "exam_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    paper_id: Mapped[int] = mapped_column(Integer, ForeignKey("exam_papers.id"), index=True)
    answers: Mapped[str | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    time_used: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[str | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="exam_results")
    paper = relationship("ExamPaper", back_populates="results")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(50))
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chapters: Mapped[str | None] = mapped_column(JSON, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    notes = relationship("UserNote", back_populates="course")


class UserNote(Base):
    __tablename__ = "user_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="notes")
    course = relationship("Course", back_populates="notes")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    product_type: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pay_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="orders")


class KnowledgeGraph(Base):
    __tablename__ = "knowledge_graph"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(50))
    chapter: Mapped[str | None] = mapped_column(String(100), nullable=True)
    point: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("knowledge_graph.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

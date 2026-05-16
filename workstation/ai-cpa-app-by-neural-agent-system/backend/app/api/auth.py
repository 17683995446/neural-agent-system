from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models.models import User
from pydantic import BaseModel, EmailStr
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()


class RegisterReq(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str
    nickname: str = "用户"
    subjects: Optional[list] = None
    level: Optional[str] = None
    study_hours: Optional[int] = None


class LoginReq(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str


class UserUpdateReq(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    cpa_stage: Optional[str] = None
    subjects: Optional[str] = None
    study_hours: Optional[int] = None
    level: Optional[str] = None


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register", response_model=TokenResp)
async def register(req: RegisterReq, db: AsyncSession = Depends(get_db)):
    if not req.phone and not req.email:
        raise HTTPException(status_code=400, detail="phone or email required")
    if req.phone:
        existing = await db.execute(select(User).where(User.phone == req.phone))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone already registered")
    if req.email:
        existing = await db.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        phone=req.phone,
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=req.nickname,
        subjects=",".join(req.subjects) if req.subjects else None,
        level=req.level or "zero",
        study_hours=req.study_hours or 0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResp(
        access_token=token,
        user={"id": user.id, "nickname": user.nickname, "phone": user.phone, "email": user.email, "role": user.role, "level": user.level},
    )


@router.post("/login", response_model=TokenResp)
async def login(req: LoginReq, db: AsyncSession = Depends(get_db)):
    user = None
    if req.phone:
        result = await db.execute(select(User).where(User.phone == req.phone))
        user = result.scalar_one_or_none()
    elif req.email:
        result = await db.execute(select(User).where(User.email == req.email))
        user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return TokenResp(
        access_token=token,
        user={"id": user.id, "nickname": user.nickname, "phone": user.phone, "email": user.email, "role": user.role, "level": user.level},
    )


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "phone": user.phone, "email": user.email,
        "nickname": user.nickname, "role": user.role, "avatar": user.avatar,
        "cpa_stage": user.cpa_stage, "subjects": user.subjects,
        "study_hours": user.study_hours, "level": user.level,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.put("/me")
async def update_me(req: UserUpdateReq, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if req.nickname is not None:
        user.nickname = req.nickname
    if req.avatar is not None:
        user.avatar = req.avatar
    if req.cpa_stage is not None:
        user.cpa_stage = req.cpa_stage
    if req.subjects is not None:
        user.subjects = req.subjects
    if req.study_hours is not None:
        user.study_hours = req.study_hours
    if req.level is not None:
        user.level = req.level
    await db.commit()
    await db.refresh(user)
    return {"message": "updated", "id": user.id}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Order
from app.api.auth import get_current_user
from app.models.models import User
from pydantic import BaseModel
from typing import Optional
import time

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreate(BaseModel):
    product_type: str
    product_id: int
    amount: float
    pay_method: Optional[str] = None


@router.post("")
async def create_order(
    req: OrderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = Order(
        user_id=user.id,
        product_type=req.product_type,
        product_id=req.product_id,
        amount=req.amount,
        status="pending",
        pay_method=req.pay_method,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return {
        "id": order.id, "status": order.status,
        "amount": order.amount, "message": "Order created",
    }


@router.get("")
async def list_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    return [
        {
            "id": o.id, "product_type": o.product_type,
            "product_id": o.product_id, "amount": o.amount,
            "status": o.status, "pay_method": o.pay_method,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "id": order.id, "product_type": order.product_type,
        "product_id": order.product_id, "amount": order.amount,
        "status": order.status, "pay_method": order.pay_method,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }

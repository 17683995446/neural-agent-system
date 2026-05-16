from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import hash_password
from app.models.models import (
    User, Question, ExamPaper, Course, KnowledgeGraph,
)
from app.services.question_bank import CPA_QUESTIONS


async def init_data(db: AsyncSession):
    result = await db.execute(select(User).where(User.phone == "admin"))
    if result.scalar_one_or_none():
        return

    admin = User(
        phone="admin", email="admin@cpa.com",
        password_hash=hash_password("admin123"),
        nickname="管理员", role="admin", level="advanced",
        cpa_stage="综合阶段", subjects="会计,审计,税法,经济法,财务成本管理,公司战略与风险管理",
    )
    db.add(admin)

    demo_user = User(
        phone="13800138000", email="demo@cpa.com",
        password_hash=hash_password("demo123"),
        nickname="CPA备考学员", role="student", level="beginner",
        cpa_stage="专业阶段", subjects="会计,税法",
        study_hours=0,
    )
    db.add(demo_user)
    await db.flush()

    question_ids = []
    for q_data in CPA_QUESTIONS:
        q = Question(**q_data)
        db.add(q)
        await db.flush()
        question_ids.append(q.id)

    accounting_ids = []
    audit_ids = []
    tax_ids = []
    for i, q_data in enumerate(CPA_QUESTIONS):
        qid = question_ids[i]
        if q_data["subject"] == "会计":
            accounting_ids.append(qid)
        elif q_data["subject"] == "审计":
            audit_ids.append(qid)
        elif q_data["subject"] == "税法":
            tax_ids.append(qid)

    if accounting_ids:
        paper1 = ExamPaper(
            title="会计科目模拟试卷", subject="会计", duration=120,
            total_score=100, questions=accounting_ids, is_mock=True, year=2024,
        )
        db.add(paper1)

    if audit_ids:
        paper2 = ExamPaper(
            title="审计科目模拟试卷", subject="审计", duration=120,
            total_score=100, questions=audit_ids, is_mock=True, year=2024,
        )
        db.add(paper2)

    if tax_ids:
        paper3 = ExamPaper(
            title="税法科目模拟试卷", subject="税法", duration=120,
            total_score=100, questions=tax_ids, is_mock=True, year=2024,
        )
        db.add(paper3)

    all_ids = question_ids
    if len(all_ids) >= 10:
        paper4 = ExamPaper(
            title="CPA综合模拟试卷", subject="综合", duration=180,
            total_score=100, questions=all_ids[:10], is_mock=True, year=2024,
        )
        db.add(paper4)

    courses_data = [
        {
            "title": "会计-零基础入门到精通", "subject": "会计", "stage": "基础",
            "chapters": ["总论", "存货", "固定资产", "无形资产", "投资性房地产", "金融资产", "长期股权投资", "收入", "所得税", "财务报告"],
            "price": 0, "is_free": True,
        },
        {
            "title": "审计-系统精讲课程", "subject": "审计", "stage": "基础",
            "chapters": ["审计概述", "审计计划", "风险评估", "风险应对", "审计抽样", "审计报告"],
            "price": 0, "is_free": True,
        },
        {
            "title": "税法-核心考点突破", "subject": "税法", "stage": "强化",
            "chapters": ["增值税", "消费税", "企业所得税", "个人所得税", "土地增值税", "国际税收"],
            "price": 99, "is_free": False,
        },
        {
            "title": "经济法-重点法条精讲", "subject": "经济法", "stage": "基础",
            "chapters": ["基本民事法律制度", "物权法律制度", "合同法律制度", "公司法律制度", "证券法律制度"],
            "price": 0, "is_free": True,
        },
        {
            "title": "财务成本管理-公式与计算专项", "subject": "财务成本管理", "stage": "强化",
            "chapters": ["财务分析", "财务预测", "价值评估", "资本成本", "资本结构", "营运资本管理"],
            "price": 129, "is_free": False,
        },
        {
            "title": "公司战略与风险管理-知识框架", "subject": "公司战略与风险管理", "stage": "基础",
            "chapters": ["战略分析", "战略选择", "战略实施", "风险管理", "内部控制"],
            "price": 0, "is_free": True,
        },
    ]
    for cd in courses_data:
        course = Course(**cd)
        db.add(course)

    knowledge_data = [
        {"subject": "会计", "chapter": "总论", "point": "会计基本假设", "level": 0, "description": "会计主体、持续经营、会计分期、货币计量"},
        {"subject": "会计", "chapter": "总论", "point": "会计信息质量要求", "level": 0, "description": "可靠性、相关性、可理解性、可比性、实质重于形式、重要性、谨慎性、及时性"},
        {"subject": "会计", "chapter": "金融资产", "point": "金融资产分类与计量", "level": 0, "description": "三类金融资产的分类标准与后续计量"},
        {"subject": "审计", "chapter": "风险评估", "point": "重大错报风险", "level": 0, "description": "财务报表层次与认定层次重大错报风险"},
        {"subject": "税法", "chapter": "增值税", "point": "增值税税率与征收率", "level": 0, "description": "13%、9%、6%三档税率及5%、3%征收率"},
        {"subject": "税法", "chapter": "企业所得税", "point": "应纳税所得额调整", "level": 0, "description": "税前扣除项目、不得扣除项目、加计扣除"},
    ]
    for kd in knowledge_data:
        kg = KnowledgeGraph(**kd)
        db.add(kg)

    await db.commit()

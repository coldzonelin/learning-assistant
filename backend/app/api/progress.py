from collections import defaultdict

from flask import Blueprint, request
from sqlalchemy import select, func

from ..errors import ApiError, ok
from ..extensions import db
from ..identity import get_current_user_id
from ..models import Material, Assessment, AssessmentMaterial, Question, Answer, KnowledgePoint, QuestionKnowledgePoint, Conversation, Message
from .ai import owned, page, stamp

progress_api = Blueprint('progress', __name__)


def point_rows(material_id=None, point_id=None):
    uid = get_current_user_id()
    query = (select(KnowledgePoint.id, KnowledgePoint.name, Assessment.id, Assessment.completed_at, Answer.score, Question.max_score)
        .select_from(KnowledgePoint).join(QuestionKnowledgePoint, QuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .join(Question, Question.id == QuestionKnowledgePoint.question_id)
        .join(Assessment, Assessment.id == Question.assessment_id)
        .join(Answer, Answer.question_id == Question.id)
        .where(KnowledgePoint.user_id == uid, Assessment.user_id == uid, Assessment.status == 'completed'))
    if material_id:
        owned(Material, material_id)
        query = query.join(AssessmentMaterial, AssessmentMaterial.assessment_id == Assessment.id).where(AssessmentMaterial.material_id == material_id)
    if point_id: query = query.where(KnowledgePoint.id == point_id)
    return db.session.execute(query).all()


def points(material_id=None):
    uid = get_current_user_id()
    totals = defaultdict(lambda: [0.0, 0.0, 0])
    for point_id, _name, _aid, _date, score, maximum in point_rows(material_id):
        if score is not None:
            totals[point_id][0] += float(score); totals[point_id][1] += float(maximum); totals[point_id][2] += 1
    query = select(KnowledgePoint).where(KnowledgePoint.user_id == uid)
    all_points = db.session.scalars(query.order_by(KnowledgePoint.name)).all()
    result = []
    for point in all_points:
        if material_id and point.id not in totals: continue
        score, maximum, count = totals[point.id]
        rate = score / maximum if maximum else None
        level = '暂无测评' if rate is None else '待加强' if rate < 0.6 else '继续巩固' if rate < 0.8 else '掌握较好'
        result.append({'id':point.id,'name':point.name,'total_score':score,'max_score':maximum,'score_rate':rate,'status':level,'question_count':count})
    return result


@progress_api.get('/progress/knowledge-points')
def knowledge_points(): return ok(page(points(request.args.get('material_id'))))


@progress_api.get('/progress/weak-points')
def weak_points(): return ok(page([p for p in points(request.args.get('material_id')) if p['status'] == '待加强']))


@progress_api.get('/progress/knowledge-points/<point_id>/history')
def knowledge_history(point_id):
    owned(KnowledgePoint, point_id)
    totals = {}
    for _id, _name, assessment_id, completed_at, score, maximum in point_rows(point_id=point_id):
        item = totals.setdefault(assessment_id, {'assessment_id':assessment_id,'completed_at':stamp(completed_at),'score':0.0,'max_score':0.0})
        item['score'] += float(score); item['max_score'] += float(maximum)
    return ok(page(sorted(totals.values(), key=lambda item: item['completed_at'] or '', reverse=True)))


@progress_api.get('/progress/summary')
def summary():
    uid = get_current_user_id()
    materials = db.session.scalars(select(Material).where(Material.user_id == uid)).all()
    assessments = db.session.scalars(select(Assessment).where(Assessment.user_id == uid,Assessment.status == 'completed')).all()
    conversation_count = db.session.scalar(select(func.count(func.distinct(Conversation.id))).join(Message).where(Conversation.user_id == uid, Message.role == 'user')) or 0
    total_score = sum(float(a.total_score) for a in assessments if a.total_score is not None)
    max_score = sum(float(a.max_score) for a in assessments if a.total_score is not None)
    mastered = 0
    for material in materials:
        rows = db.session.scalars(select(Assessment).join(AssessmentMaterial).where(AssessmentMaterial.material_id == material.id,Assessment.user_id == uid,Assessment.status == 'completed')).all()
        score = sum(float(a.total_score) for a in rows if a.total_score is not None)
        maximum = sum(float(a.max_score) for a in rows if a.total_score is not None)
        if maximum and score / maximum >= 0.8: mastered += 1
    return ok({'material_count':len(materials),'ready_material_count':sum(m.status=='ready' for m in materials),'mastered_material_count':mastered,'study_count':conversation_count+len(assessments),'assessment_count':len(assessments),'average_score':round(total_score/max_score*100,1) if max_score else None,'weak_point_count':sum(p['status']=='待加强' for p in points())})

from datetime import date, datetime, timedelta, timezone
from collections import Counter
import re

from flask import Blueprint, request
from sqlalchemy import select, update

from ..errors import ApiError, ok
from ..extensions import db
from ..identity import get_current_user_id
from ..models import (Material, MaterialChunk, Conversation, ConversationMaterial, Message, MessageSource, Assessment, AssessmentMaterial, Question, QuestionSource, KnowledgePoint, QuestionKnowledgePoint, Answer, WeeklyReport, CustomReport)
from ..services import llm

ai = Blueprint('ai', __name__)


def data():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError('INVALID_REQUEST', '请求必须是 JSON 对象')
    return value


def owned(model, identifier):
    result = db.session.scalar(select(model).where(model.id == identifier, model.user_id == get_current_user_id()))
    if result is None:
        raise ApiError('NOT_FOUND', '资源不存在', 404)
    return result


def materials(ids):
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise ApiError('INVALID_REQUEST', '资料 ID 列表无效')
    found = [owned(Material, i) for i in ids]
    if any(m.status != 'ready' for m in found):
        raise ApiError('MATERIAL_NOT_READY', '资料尚未处理完成')
    return found


def chunks_for(ids):
    if not ids:
        return []
    rows = db.session.execute(select(MaterialChunk, Material).join(Material, Material.id == MaterialChunk.material_id).where(Material.id.in_(ids)).order_by(Material.id, MaterialChunk.chunk_order)).all()
    return [{'id': c.id, 'material_id': m.id, 'material_name': m.name, 'page_number': c.page_number, 'section_title': c.section_title, 'content': c.content} for c,m in rows]


def page(items):
    try:
        number = int(request.args.get('page', 1)); size = int(request.args.get('page_size', 20))
        if number < 1 or size < 1 or size > 100:
            raise ValueError
    except ValueError:
        raise ApiError('INVALID_REQUEST', '分页参数无效')
    return {'items': items[(number-1)*size:number*size], 'total': len(items)}


def stamp(value):
    return value.isoformat() if value else None


def conversation_json(c):
    ids = db.session.scalars(select(ConversationMaterial.material_id).where(ConversationMaterial.conversation_id == c.id)).all()
    return {'id': c.id, 'material_ids': list(ids), 'created_at': stamp(c.created_at)}


def source_json(c):
    return {'chunk_id':c['id'], 'material_id':c['material_id'], 'material_name':c['material_name'], 'page_number':c['page_number'], 'section_title':c['section_title'], 'excerpt':c['content']}


def message_json(message):
    ids = db.session.scalars(select(MessageSource.chunk_id).where(MessageSource.message_id == message.id)).all()
    rows = db.session.execute(select(MaterialChunk,Material).join(Material).where(MaterialChunk.id.in_(ids))).all() if ids else []
    sources = [source_json({'id':c.id,'material_id':m.id,'material_name':m.name,'page_number':c.page_number,'section_title':c.section_title,'content':c.content}) for c,m in rows]
    return {'id':message.id,'role':message.role,'content':message.content,'sources':sources,'created_at':stamp(message.created_at)}


def relevant(question, chunks):
    # 仅用字词重合筛选，不调用向量模型；小资料完整发送，未命中时也完整发送。
    total = sum(len(c['content']) for c in chunks)
    if total <= current_limit(): return chunks
    terms = set(re.findall(r'[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2}', question.lower()))
    ranked = sorted(chunks, key=lambda c: sum(term in c['content'].lower() for term in terms), reverse=True)
    selected = []; length = 0
    for chunk in ranked:
        score = sum(term in chunk['content'].lower() for term in terms)
        if score and length + len(chunk['content']) <= current_limit() // 2:
            selected.append(chunk); length += len(chunk['content'])
    if not selected:
        raise ApiError('MATERIAL_TOO_LONG', '资料较长且未找到匹配段落，请缩小资料范围或调整问题')
    return selected


def current_limit():
    from flask import current_app
    return current_app.config['LLM_MAX_CONTEXT_CHARS']


@ai.route('/conversations', methods=['GET','POST'])
def conversations():
    if request.method == 'GET':
        rows = db.session.scalars(select(Conversation).where(Conversation.user_id == get_current_user_id()).order_by(Conversation.created_at.desc())).all()
        return ok(page([conversation_json(c) for c in rows]))
    ids = data().get('material_ids', [])
    materials(ids)
    c = Conversation(user_id=get_current_user_id()); db.session.add(c); db.session.flush()
    db.session.add_all([ConversationMaterial(conversation_id=c.id,material_id=i) for i in ids]); db.session.commit()
    return ok(conversation_json(c))


@ai.route('/conversations/<conversation_id>/messages', methods=['GET','POST'])
def messages(conversation_id):
    c = owned(Conversation, conversation_id)
    existing = db.session.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at,Message.id)).all()
    if request.method == 'GET': return ok(page([message_json(m) for m in existing]))
    content = data().get('content')
    if not isinstance(content,str) or not content.strip(): raise ApiError('INVALID_REQUEST','消息不能为空')
    ids = conversation_json(c)['material_ids']; materials(ids); chunks = chunks_for(ids)
    if ids and not chunks: raise ApiError('MATERIAL_EMPTY','资料没有可用内容')
    selected = relevant(content, chunks)
    history = [{'role':m.role,'content':m.content} for m in existing]
    answer = llm.chat(content, selected, history)
    user = Message(conversation_id=c.id,role='user',content=content); assistant = Message(conversation_id=c.id,role='assistant',content=answer['answer'])
    db.session.add_all([user,assistant]); db.session.flush()
    db.session.add_all([MessageSource(message_id=assistant.id,chunk_id=i) for i in set(answer['source_chunk_ids'])]); c.updated_at=datetime.now(timezone.utc); db.session.commit()
    return ok({'user_message':message_json(user),'assistant_message':message_json(assistant)})


def assessment_json(a, include_questions=False):
    result={'id':a.id,'status':a.status,'failure_reason':a.failure_reason,'total_score':float(a.total_score) if a.total_score is not None else None,'max_score':float(a.max_score),'created_at':stamp(a.created_at),'material_ids':list(db.session.scalars(select(AssessmentMaterial.material_id).where(AssessmentMaterial.assessment_id==a.id)).all())}
    if include_questions:
        result['questions']=[{'id':q.id,'type':q.type,'content':q.content,'options':{'A':'正确','B':'错误'} if q.type == 'true_false' else q.options,'difficulty':q.difficulty} for q in db.session.scalars(select(Question).where(Question.assessment_id==a.id).order_by(Question.question_order)).all()]
    return result


@ai.route('/assessments', methods=['GET','POST'])
def assessments():
    if request.method=='GET':
        rows=db.session.scalars(select(Assessment).where(Assessment.user_id==get_current_user_id()).order_by(Assessment.created_at.desc())).all()
        return ok(page([assessment_json(a) for a in rows]))
    value=data(); ids=value.get('material_ids'); materials(ids)
    if not ids: raise ApiError('INVALID_REQUEST','请选择资料')
    counts=value.get('question_counts')
    if not isinstance(counts,dict) or set(counts)!={'single_choice','true_false','short_answer'} or any(type(v) is not int or v<0 for v in counts.values()) or not 1<=sum(counts.values())<=30:
        raise ApiError('INVALID_REQUEST','题目数量无效')
    chunks=chunks_for(ids)
    if not chunks: raise ApiError('MATERIAL_EMPTY','资料没有可用内容')
    existing=db.session.scalars(select(KnowledgePoint.name).where(KnowledgePoint.user_id==get_current_user_id())).all()
    output=llm.generate_questions(chunks,counts,list(existing)); questions=output['questions']
    if not questions: raise ApiError('NO_QUESTIONS','资料不足以生成题目')
    a=Assessment(user_id=get_current_user_id(),status='ready',max_score=len(questions));db.session.add(a);db.session.flush()
    db.session.add_all([AssessmentMaterial(assessment_id=a.id,material_id=i) for i in ids])
    actual=Counter()
    for index,item in enumerate(questions):
        q=Question(assessment_id=a.id,question_order=index,type=item['type'],content=item['content'],options=item.get('options'),correct_answer=item['correct_answer'],grading_points=item.get('grading_points'),difficulty=item['difficulty']);db.session.add(q);db.session.flush();actual[q.type]+=1
        db.session.add_all([QuestionSource(question_id=q.id,chunk_id=i) for i in set(item['source_chunk_ids'])])
        for name in set(item['knowledge_points']):
            kp=db.session.scalar(select(KnowledgePoint).where(KnowledgePoint.user_id==get_current_user_id(),KnowledgePoint.name==name))
            if kp is None: kp=KnowledgePoint(user_id=get_current_user_id(),name=name);db.session.add(kp);db.session.flush()
            db.session.add(QuestionKnowledgePoint(question_id=q.id,knowledge_point_id=kp.id))
    db.session.commit()
    return ok({'id':a.id,'status':a.status,'question_counts':dict(actual),'shortfalls':output.get('shortfalls',[])})


@ai.get('/assessments/<assessment_id>')
def assessment(assessment_id): return ok(assessment_json(owned(Assessment,assessment_id),True))


@ai.post('/assessments/<assessment_id>/submit')
def submit(assessment_id):
    a=owned(Assessment,assessment_id)
    if a.status!='ready': raise ApiError('INVALID_STATE','测评已提交或不可用',409)
    supplied=data().get('answers')
    if not isinstance(supplied,list) or any(not isinstance(x,dict) or not isinstance(x.get('question_id'),str) for x in supplied): raise ApiError('INVALID_REQUEST','答案格式无效')
    questions=db.session.scalars(select(Question).where(Question.assessment_id==a.id).order_by(Question.question_order)).all(); ids={q.id for q in questions}; answers={x['question_id']:x.get('answer') for x in supplied}
    if len(answers)!=len(supplied) or not set(answers)<=ids: raise ApiError('INVALID_REQUEST','存在重复或不属于本次测评的题目')
    claimed = db.session.execute(update(Assessment).where(Assessment.id == a.id, Assessment.user_id == get_current_user_id(), Assessment.status == 'ready').values(status='grading'))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise ApiError('INVALID_STATE','测评已提交或正在评分',409)
    db.session.commit()
    graded=[]
    try:
        for q in questions:
            chunk_ids=db.session.scalars(select(QuestionSource.chunk_id).where(QuestionSource.question_id==q.id)).all()
            rows=db.session.execute(select(MaterialChunk,Material).join(Material).where(MaterialChunk.id.in_(chunk_ids))).all()
            chunks=[{'id':c.id,'material_id':m.id,'material_name':m.name,'page_number':c.page_number,'section_title':c.section_title,'content':c.content} for c,m in rows]
            graded.append((q,answers.get(q.id),llm.grade(q,answers.get(q.id),chunks)))
    except Exception:
        db.session.rollback()
        db.session.execute(update(Assessment).where(Assessment.id==assessment_id,Assessment.status=='grading').values(status='ready'))
        db.session.commit()
        raise
    for q,answer,result in graded: db.session.add(Answer(question_id=q.id,answer=answer,score=result['score'],feedback=result['feedback'],needs_review=result['needs_review'],review_reason=result['review_reason'],graded_at=datetime.now(timezone.utc)))
    review=any(result['needs_review'] for _,_,result in graded); a.status='needs_review' if review else 'completed';a.submitted_at=datetime.now(timezone.utc);a.total_score=None if review else sum(result['score'] for _,_,result in graded);a.completed_at=None if review else datetime.now(timezone.utc);db.session.commit()
    return ok({'assessment_id':a.id,'status':a.status})


@ai.get('/assessments/<assessment_id>/result')
def result(assessment_id):
    a=owned(Assessment,assessment_id)
    if a.status not in ('completed','needs_review'): raise ApiError('INVALID_STATE','测评结果尚未完成',409)
    questions=db.session.scalars(select(Question).where(Question.assessment_id==a.id).order_by(Question.question_order)).all(); items=[]
    for q in questions:
        ans=db.session.scalar(select(Answer).where(Answer.question_id==q.id)); ids=db.session.scalars(select(QuestionSource.chunk_id).where(QuestionSource.question_id==q.id)).all(); points=db.session.scalars(select(KnowledgePoint.name).join(QuestionKnowledgePoint).where(QuestionKnowledgePoint.question_id==q.id)).all()
        rows=db.session.execute(select(MaterialChunk,Material).join(Material).where(MaterialChunk.id.in_(ids))).all()
        sources=[source_json({'id':c.id,'material_id':m.id,'material_name':m.name,'page_number':c.page_number,'section_title':c.section_title,'content':c.content}) for c,m in rows]
        items.append({'question_id':q.id,'type':q.type,'content':q.content,'correct_answer':q.correct_answer,'grading_points':q.grading_points,'answer':ans.answer,'score':float(ans.score) if ans.score is not None else None,'feedback':ans.feedback,'needs_review':ans.needs_review,'review_reason':ans.review_reason,'knowledge_points':list(points),'sources':sources})
    return ok({'assessment_id':a.id,'status':a.status,'total_score':float(a.total_score) if a.total_score is not None else None,'max_score':float(a.max_score),'questions':items})


@ai.route('/weekly-reports', methods=['GET','POST'])
def weekly_reports():
    if request.method=='GET':
        rows=db.session.scalars(select(WeeklyReport).where(WeeklyReport.user_id==get_current_user_id()).order_by(WeeklyReport.week_start.desc())).all()
        custom=db.session.scalars(select(CustomReport).where(CustomReport.user_id==get_current_user_id())).all()
        items=[{'id':r.id,'week_start':r.week_start.isoformat(),'created_at':stamp(r.created_at)} for r in rows]
        items += [{'id':r.id,'start_date':r.start_date.isoformat(),'end_date':r.end_date.isoformat(),'created_at':stamp(r.created_at)} for r in custom]
        return ok(page(sorted(items,key=lambda item:item['created_at'] or '',reverse=True)))
    from zoneinfo import ZoneInfo
    from flask import current_app
    value=data()
    custom = 'start_date' in value or 'end_date' in value
    try:
        if custom:
            start = date.fromisoformat(value['start_date']); finish = date.fromisoformat(value['end_date'])
            if finish < start: raise ValueError
        else:
            start=date.fromisoformat(value['week_start'])
            if start.weekday()!=0: raise ValueError
            finish=start+timedelta(days=6)
    except (ValueError,KeyError,TypeError): raise ApiError('INVALID_REQUEST','报告日期范围无效')
    zone=ZoneInfo(current_app.config['DEFAULT_TIMEZONE'])
    begin=datetime.combine(start,datetime.min.time(),zone).astimezone(timezone.utc)
    end=datetime.combine(finish+timedelta(days=1),datetime.min.time(),zone).astimezone(timezone.utc)
    uid=get_current_user_id()
    conversations=db.session.scalars(select(Conversation).join(Message).where(Conversation.user_id==uid,Message.role=='user',Message.created_at>=begin,Message.created_at<end).distinct()).all()
    material_ids=set()
    for conversation in conversations: material_ids.update(conversation_json(conversation)['material_ids'])
    assessments=db.session.scalars(select(Assessment).where(Assessment.user_id==uid,Assessment.status=='completed',Assessment.completed_at>=begin,Assessment.completed_at<end)).all()
    for a in assessments: material_ids.update(db.session.scalars(select(AssessmentMaterial.material_id).where(AssessmentMaterial.assessment_id==a.id)).all())
    material_names=db.session.scalars(select(Material.name).where(Material.id.in_(material_ids),Material.user_id==uid)).all() if material_ids else []
    scores={}
    for a in assessments:
        rows=db.session.execute(select(KnowledgePoint.name,Answer.score,Question.max_score).join(QuestionKnowledgePoint,QuestionKnowledgePoint.knowledge_point_id==KnowledgePoint.id).join(Question,Question.id==QuestionKnowledgePoint.question_id).join(Answer,Answer.question_id==Question.id).where(Question.assessment_id==a.id)).all()
        for name,score,max_score in rows:
            if score is not None:
                sums=scores.setdefault(name,[0,0]);sums[0]+=float(score);sums[1]+=float(max_score)
    weak=[{'name':name,'score_rate':round(score/maximum,2)} for name,(score,maximum) in scores.items() if maximum and score/maximum<0.6]
    questions_asked = list(db.session.scalars(select(Message.content).join(Conversation).where(Conversation.user_id==uid,Message.role=='user',Message.created_at>=begin,Message.created_at<end).order_by(Message.created_at)).all())
    report_data={'start_date':start.isoformat(),'end_date':finish.isoformat(),'materials':list(material_names),'questions_asked':questions_asked,'conversation_count':len(conversations),'assessment_count':len(assessments),'knowledge_points':[{'name':name,'score_rate':round(score/maximum,2)} for name,(score,maximum) in scores.items() if maximum], 'weak_points':weak}
    report_data['content']=llm.weekly_report(report_data)
    if custom:
        report=db.session.scalar(select(CustomReport).where(CustomReport.user_id==uid,CustomReport.start_date==start,CustomReport.end_date==finish))
        if report is None: report=CustomReport(user_id=uid,start_date=start,end_date=finish,timezone=str(zone));db.session.add(report)
    else:
        report=db.session.scalar(select(WeeklyReport).where(WeeklyReport.user_id==uid,WeeklyReport.week_start==start))
        if report is None: report=WeeklyReport(user_id=uid,week_start=start,timezone=str(zone));db.session.add(report)
    report.report_data=report_data;db.session.commit()
    return ok({'id':report.id,'start_date':start.isoformat(),'end_date':finish.isoformat(),'week_start':None if custom else start.isoformat(),'report_data':report_data})



@ai.get('/weekly-reports/<report_id>')
def weekly_report_detail(report_id):
    report = find_report(report_id)
    return ok(report_json(report))


@ai.delete('/conversations/<conversation_id>')
def delete_conversation(conversation_id):
    conversation = owned(Conversation, conversation_id)
    db.session.delete(conversation); db.session.commit()
    return ok({'id':conversation_id,'deleted':True})


@ai.get('/weekly-reports/<report_id>/download')
def download_weekly_report(report_id):
    from flask import Response
    report=find_report(report_id)
    content = (report.report_data or {}).get('content', '')
    response = Response(content, mimetype='text/markdown; charset=utf-8')
    report_date = report_json(report)['start_date']
    response.headers['Content-Disposition'] = f'attachment; filename="weekly-report-{report_date}.md"'
    return response


def find_report(report_id):
    for model in (WeeklyReport, CustomReport):
        report = db.session.scalar(select(model).where(model.id == report_id, model.user_id == get_current_user_id()))
        if report is not None: return report
    raise ApiError('NOT_FOUND', '资源不存在', 404)


def report_json(report):
    if isinstance(report, WeeklyReport):
        start = report.week_start
        return {'id':report.id, 'week_start':start.isoformat(), 'start_date':start.isoformat(), 'end_date':(start+timedelta(days=6)).isoformat(), 'report_data':report.report_data}
    return {'id':report.id, 'start_date':report.start_date.isoformat(), 'end_date':report.end_date.isoformat(), 'report_data':report.report_data}

import uuid
from pathlib import Path

from flask import Blueprint, current_app, request
from sqlalchemy import select

from ..errors import ApiError, ok
from ..extensions import db
from ..identity import get_current_user_id
from ..models import Material, MaterialChunk
from ..services.materials import extract
from .ai import owned, page, stamp

material_api = Blueprint('materials', __name__)
ALLOWED = {'pdf','ppt','pptx','doc','docx','md','markdown','txt'}


def serialize(material):
    return {'id': material.id, 'name': material.name, 'file_type': material.file_type, 'file_size': material.file_size, 'status': material.status, 'failure_reason': material.failure_reason, 'created_at': stamp(material.created_at), 'updated_at': stamp(material.updated_at)}


def parse(material):
    try:
        chunks = extract(Path(material.file_path), material.file_type)
        for index, (content, page_number, section_title) in enumerate(chunks):
            db.session.add(MaterialChunk(material_id=material.id, content=content, chunk_order=index, page_number=page_number, section_title=section_title))
        material.status = 'ready'; material.failure_reason = None
    except Exception as exc:
        current_app.logger.warning('资料解析失败：%s', type(exc).__name__)
        material.status = 'failed'
        material.failure_reason = str(exc) if isinstance(exc, ValueError) else '文件无法解析或格式不正确'
    db.session.commit()


@material_api.route('/materials', methods=['GET','POST'])
def materials():
    if request.method == 'GET':
        query = select(Material).where(Material.user_id == get_current_user_id())
        status = request.args.get('status')
        if status:
            if status not in ('processing','ready','failed'): raise ApiError('INVALID_REQUEST','资料状态无效')
            query = query.where(Material.status == status)
        return ok(page([serialize(m) for m in db.session.scalars(query.order_by(Material.created_at.desc())).all()]))
    upload = request.files.get('file')
    if upload is None or not upload.filename: raise ApiError('INVALID_REQUEST','请选择文件')
    name = upload.filename.replace('\\','/').rsplit('/',1)[-1]
    file_type = Path(name).suffix.lower().lstrip('.')
    if file_type not in ALLOWED: raise ApiError('UNSUPPORTED_FILE_TYPE','不支持的文件格式')
    directory = Path(current_app.config['UPLOAD_FOLDER']); directory.mkdir(parents=True,exist_ok=True)
    path = directory / f'{uuid.uuid4().hex}.{file_type}'
    upload.save(path)
    material = Material(user_id=get_current_user_id(),name=name,file_type=file_type,file_path=str(path),file_size=path.stat().st_size,status='processing')
    try:
        db.session.add(material); db.session.commit()
    except Exception:
        db.session.rollback(); path.unlink(missing_ok=True); raise
    parse(material)
    return ok(serialize(material))


@material_api.route('/materials/<material_id>', methods=['GET','DELETE'])
def material_detail(material_id):
    material = owned(Material, material_id)
    if request.method == 'GET': return ok(serialize(material))
    path = Path(material.file_path)
    db.session.delete(material); db.session.commit()
    path.unlink(missing_ok=True)
    return ok({'id':material_id,'deleted':True})


@material_api.post('/materials/<material_id>/retry')
def retry(material_id):
    material = owned(Material, material_id)
    if material.status != 'failed': raise ApiError('INVALID_STATE','只有解析失败的资料可重试',409)
    material.status = 'processing'; material.failure_reason = None; db.session.commit()
    parse(material)
    return ok(serialize(material))

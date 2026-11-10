import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from .extensions import db


def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _utcnow():
    return datetime.now(timezone.utc)


class Material(db.Model):
    __tablename__ = "materials"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("mat"))
    user_id = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(512), nullable=False)
    file_type = db.Column(db.String(16), nullable=False)
    file_path = db.Column(db.String(1024), nullable=False)
    file_size = db.Column(db.BigInteger)
    status = db.Column(db.String(20), nullable=False, default="processing")
    failure_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "file_type IN ('pdf', 'ppt', 'pptx', 'doc', 'docx', 'md', 'markdown', 'txt')", name="ck_materials_file_type"
        ),
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed')", name="ck_materials_status"
        ),
        Index("ix_materials_user_status", "user_id", "status"),
    )


class MaterialChunk(db.Model):
    __tablename__ = "material_chunks"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("chunk"))
    material_id = db.Column(
        db.String(64), db.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    content = db.Column(db.Text, nullable=False)
    chunk_order = db.Column(db.Integer, nullable=False)
    page_number = db.Column(db.Integer)
    section_title = db.Column(db.String(512))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_material_chunks_material_order", "material_id", "chunk_order"),
    )


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("conv"))
    user_id = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (Index("ix_conversations_user_created", "user_id", "created_at"),)


class ConversationMaterial(db.Model):
    __tablename__ = "conversation_materials"

    conversation_id = db.Column(
        db.String(64),
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    material_id = db.Column(
        db.String(64), db.ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True
    )


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("msg"))
    conversation_id = db.Column(
        db.String(64), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class MessageSource(db.Model):
    __tablename__ = "message_sources"

    message_id = db.Column(
        db.String(64), db.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id = db.Column(
        db.String(64),
        db.ForeignKey("material_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Assessment(db.Model):
    __tablename__ = "assessments"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("asm"))
    user_id = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="generating")
    failure_reason = db.Column(db.Text)
    total_score = db.Column(db.Numeric(8, 1))
    max_score = db.Column(db.Numeric(8, 1), nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    submitted_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('generating', 'ready', 'grading', 'needs_review', 'completed', 'failed')",
            name="ck_assessments_status",
        ),
        Index("ix_assessments_user_status", "user_id", "status"),
    )


class AssessmentMaterial(db.Model):
    __tablename__ = "assessment_materials"

    assessment_id = db.Column(
        db.String(64),
        db.ForeignKey("assessments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    material_id = db.Column(
        db.String(64), db.ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True
    )


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("q"))
    assessment_id = db.Column(
        db.String(64), db.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    question_order = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.String(16))
    type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON)
    correct_answer = db.Column(db.JSON, nullable=False)
    grading_points = db.Column(db.JSON)
    max_score = db.Column(db.Numeric(4, 1), nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "type IN ('single_choice', 'true_false', 'short_answer')",
            name="ck_questions_type",
        ),
        Index("ix_questions_assessment_order", "assessment_id", "question_order"),
    )


class QuestionSource(db.Model):
    __tablename__ = "question_sources"

    question_id = db.Column(
        db.String(64), db.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id = db.Column(
        db.String(64),
        db.ForeignKey("material_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class KnowledgePoint(db.Model):
    __tablename__ = "knowledge_points"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("kp"))
    user_id = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_knowledge_points_user_name"),
    )


class QuestionKnowledgePoint(db.Model):
    __tablename__ = "question_knowledge_points"

    question_id = db.Column(
        db.String(64), db.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_point_id = db.Column(
        db.String(64),
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Answer(db.Model):
    __tablename__ = "answers"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("ans"))
    question_id = db.Column(
        db.String(64),
        db.ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    answer = db.Column(db.JSON)
    score = db.Column(db.Numeric(4, 1))
    feedback = db.Column(db.Text)
    needs_review = db.Column(db.Boolean, nullable=False, default=False)
    review_reason = db.Column(db.Text)
    graded_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "score IS NULL OR score IN (0, 0.5, 1)", name="ck_answers_score"
        ),
    )


class WeeklyReport(db.Model):
    __tablename__ = "weekly_reports"

    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id("wr"))
    user_id = db.Column(db.String(64), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default="Asia/Shanghai")
    report_data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_reports_user_week"),
    )


class CustomReport(db.Model):
    __tablename__ = 'custom_reports'
    id = db.Column(db.String(64), primary_key=True, default=lambda: _new_id('cr'))
    user_id = db.Column(db.String(64), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default='Asia/Shanghai')
    report_data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    __table_args__ = (UniqueConstraint('user_id', 'start_date', 'end_date', name='uq_custom_reports_user_range'),)

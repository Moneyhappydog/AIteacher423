"""
models/orm_models.py — Flask-SQLAlchemy ORM 模型层

对应 maogangedu.sql 中的 11 张表。
使用前请确保已执行：
    pip install flask-sqlalchemy pymysql bcrypt
"""
from __future__ import annotations

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def hash_password(raw: str) -> str:
    """对明文密码做 bcrypt hash，供注册和密码重置使用。"""
    return generate_password_hash(raw)


def verify_password(pwhash: str, raw: str) -> bool:
    """校验密码，返回 True/False。"""
    return check_password_hash(pwhash, raw)


# ──────────────────────────────────────────────────────────────────────────────
# 1. users — 用户表（超级管理员 / 教师 / 学生小组）
# ──────────────────────────────────────────────────────────────────────────────

class User(db.Model):
    """用户表：超级管理员 / 教师 / 学生小组"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    role = db.Column(
        db.Enum('super_admin', 'teacher', 'group', name='user_role'),
        nullable=False
    )
    avatar = db.Column(db.String(255), default=None)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    remark = db.Column(db.Text, default=None)

    # 关联
    group = db.relationship('Group', backref='user', uselist=False, lazy=True)
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True, passive_deletes=True)
    reviewed_face_records = db.relationship(
        'FaceDataset', backref='reviewer', lazy=True,
        foreign_keys='FaceDataset.reviewed_by'
    )
    reviewed_audio_records = db.relationship(
        'AudioDataset', backref='reviewer', lazy=True,
        foreign_keys='AudioDataset.reviewed_by'
    )
    reviewed_eco_records = db.relationship(
        'EcobottleDataset', backref='reviewer', lazy=True,
        foreign_keys='EcobottleDataset.reviewed_by'
    )
    announcements = db.relationship('Announcement', backref='publisher', lazy=True)

    def set_password(self, raw: str):
        self.password_hash = hash_password(raw)

    def check_password(self, raw: str) -> bool:
        return verify_password(self.password_hash, raw)

    def is_admin(self) -> bool:
        return self.role == 'super_admin'

    def is_teacher(self) -> bool:
        return self.role == 'teacher'

    def is_group(self) -> bool:
        return self.role == 'group'

    def can_manage_users(self) -> bool:
        return self.role in ('super_admin', 'teacher')

    def can_review_data(self) -> bool:
        return self.role in ('super_admin', 'teacher')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'role': self.role,
            'avatar': self.avatar,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'remark': self.remark,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 2. groups — 学生小组扩展信息表
# ──────────────────────────────────────────────────────────────────────────────

class Group(db.Model):
    """学生小组扩展信息，一对一关联 users"""
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        unique=True, nullable=False
    )
    group_code = db.Column(db.String(10), unique=True, nullable=False)
    course = db.Column(db.String(50), default=None)
    member_count = db.Column(db.Integer, nullable=False, default=1)
    experience = db.Column(db.Integer, nullable=False, default=0)
    skill_tree = db.Column(db.JSON, default=None)
    last_active_at = db.Column(db.DateTime, default=None)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # 关联
    leaderboard_records = db.relationship('LeaderboardRecord', backref='group', lazy=True)
    face_datasets = db.relationship('FaceDataset', backref='group', lazy=True)
    audio_datasets = db.relationship('AudioDataset', backref='group', lazy=True)
    ecobottle_datasets = db.relationship('EcobottleDataset', backref='group', lazy=True)
    model_files = db.relationship('ModelFile', backref='group', lazy=True)
    notebooks = db.relationship('Notebook', backref='group', lazy=True)
    skill_progress = db.relationship('SkillProgress', backref='group', uselist=False, lazy=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'group_code': self.group_code,
            'course': self.course,
            'member_count': self.member_count,
            'experience': self.experience,
            'skill_tree': self.skill_tree,
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 3. leaderboard_records — 排行榜提交记录表
# ──────────────────────────────────────────────────────────────────────────────

class LeaderboardRecord(db.Model):
    """排行榜提交记录"""
    __tablename__ = 'leaderboard_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    course = db.Column(db.String(30), nullable=False)
    accuracy = db.Column(db.Numeric(6, 4), nullable=False)
    correct_count = db.Column(db.Integer, nullable=False, default=0)
    total_count = db.Column(db.Integer, nullable=False, default=0)
    time_cost_seconds = db.Column(db.Integer, nullable=False, default=0)
    model_file = db.Column(db.String(255), nullable=False)
    model_config = db.Column(db.JSON, default=None)
    composite_score = db.Column(db.Numeric(6, 2), default=None)
    innovation_score = db.Column(db.Integer, default=None)
    awards = db.Column(db.JSON, default=None)
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'course': self.course,
            'accuracy': float(self.accuracy) if self.accuracy else None,
            'correct_count': self.correct_count,
            'total_count': self.total_count,
            'time_cost_seconds': self.time_cost_seconds,
            'model_file': self.model_file,
            'model_config': self.model_config,
            'composite_score': float(self.composite_score) if self.composite_score else None,
            'innovation_score': self.innovation_score,
            'awards': self.awards,
            'is_public': self.is_public,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 4. face_datasets — 表情数据集元数据表
# ──────────────────────────────────────────────────────────────────────────────

class FaceDataset(db.Model):
    """表情数据集元数据"""
    __tablename__ = 'face_datasets'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    label = db.Column(db.String(20), nullable=False)
    label_source = db.Column(
        db.Enum('ai_auto', 'teacher', 'group', name='label_source'),
        nullable=False, default='ai_auto'
    )
    confidence = db.Column(db.Numeric(5, 4), default=None)
    dataset_type = db.Column(
        db.Enum('train', 'test', name='dataset_type'),
        nullable=False
    )
    status = db.Column(
        db.Enum('pending', 'confirmed', 'rejected', name='face_status'),
        nullable=False, default='pending'
    )
    reviewed_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        default=None
    )
    reviewed_at = db.Column(db.DateTime, default=None)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'label': self.label,
            'label_source': self.label_source,
            'confidence': float(self.confidence) if self.confidence else None,
            'dataset_type': self.dataset_type,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 5. audio_datasets — 声音数据集元数据表
# ──────────────────────────────────────────────────────────────────────────────

class AudioDataset(db.Model):
    """声音数据集元数据"""
    __tablename__ = 'audio_datasets'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    duration_sec = db.Column(db.Numeric(6, 2), default=None)
    label = db.Column(db.String(20), nullable=False)
    label_source = db.Column(
        db.Enum('ai_auto', 'teacher', 'group', name='label_source'),
        nullable=False, default='ai_auto'
    )
    confidence = db.Column(db.Numeric(5, 4), default=None)
    dataset_type = db.Column(
        db.Enum('train', 'test', name='dataset_type'),
        nullable=False
    )
    status = db.Column(
        db.Enum('pending', 'confirmed', 'rejected', name='audio_status'),
        nullable=False, default='pending'
    )
    reviewed_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        default=None
    )
    reviewed_at = db.Column(db.DateTime, default=None)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'duration_sec': float(self.duration_sec) if self.duration_sec else None,
            'label': self.label,
            'label_source': self.label_source,
            'confidence': float(self.confidence) if self.confidence else None,
            'dataset_type': self.dataset_type,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 6. ecobottle_datasets — 生态瓶/传感器数据集元数据表
# ──────────────────────────────────────────────────────────────────────────────

class EcobottleDataset(db.Model):
    """生态瓶/传感器数据集元数据"""
    __tablename__ = 'ecobottle_datasets'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    record_count = db.Column(db.Integer, nullable=False, default=0)
    feature_cols = db.Column(db.JSON, default=None)
    target_col = db.Column(db.String(50), default=None)
    dataset_type = db.Column(
        db.Enum('train', 'test', name='dataset_type'),
        nullable=False
    )
    status = db.Column(
        db.Enum('pending', 'confirmed', 'rejected', name='eco_status'),
        nullable=False, default='pending'
    )
    reviewed_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
        default=None
    )
    reviewed_at = db.Column(db.DateTime, default=None)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'record_count': self.record_count,
            'feature_cols': self.feature_cols,
            'target_col': self.target_col,
            'dataset_type': self.dataset_type,
            'status': self.status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 7. model_files — 模型文件表
# ──────────────────────────────────────────────────────────────────────────────

class ModelFile(db.Model):
    """模型文件表"""
    __tablename__ = 'model_files'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    course = db.Column(db.String(30), nullable=False)
    model_name = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size_bytes = db.Column(db.BigInteger, default=None)
    model_type = db.Column(db.String(50), default=None)
    config = db.Column(db.JSON, default=None)
    accuracy = db.Column(db.Numeric(6, 4), default=None)
    metrics = db.Column(db.JSON, default=None)
    is_pretrained = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'course': self.course,
            'model_name': self.model_name,
            'file_path': self.file_path,
            'file_size_bytes': self.file_size_bytes,
            'model_type': self.model_type,
            'config': self.config,
            'accuracy': float(self.accuracy) if self.accuracy else None,
            'metrics': self.metrics,
            'is_pretrained': self.is_pretrained,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 8. notebooks — 代码笔记本/脚本表
# ──────────────────────────────────────────────────────────────────────────────

class Notebook(db.Model):
    """代码笔记本/脚本表"""
    __tablename__ = 'notebooks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    course = db.Column(db.String(30), nullable=False)
    file_name = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default=None)
    language = db.Column(db.String(20), nullable=False, default='python')
    version = db.Column(db.Integer, nullable=False, default=1)
    is_template = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint('group_id', 'file_name', name='uk_group_filename'),
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'course': self.course,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'language': self.language,
            'version': self.version,
            'is_template': self.is_template,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 9. audit_logs — 操作审计日志表
# ──────────────────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    """操作审计日志表"""
    __tablename__ = 'audit_logs'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(50), default=None)
    target_id = db.Column(db.String(100), default=None)
    detail = db.Column(db.JSON, default=None)
    ip_address = db.Column(db.String(45), default=None)
    user_agent = db.Column(db.String(500), default=None)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # 常用 action 常量
    ACTION_LOGIN = 'LOGIN'
    ACTION_LOGOUT = 'LOGOUT'
    ACTION_SUBMIT_LEADERBOARD = 'SUBMIT_LEADERBOARD'
    ACTION_UPLOAD_DATA = 'UPLOAD_DATA'
    ACTION_TRAIN_MODEL = 'TRAIN_MODEL'
    ACTION_REVIEW_DATA = 'REVIEW_DATA'
    ACTION_CREATE_GROUP = 'CREATE_GROUP'
    ACTION_DELETE_GROUP = 'DELETE_GROUP'

    @classmethod
    def log(cls, user_id: int, action: str, target_type: str = None,
            target_id: str = None, detail: dict = None,
            ip_address: str = None, user_agent: str = None) -> 'AuditLog':
        entry = cls(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(entry)
        return entry

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'detail': self.detail,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 10. skill_progress — 技能树进度表
# ──────────────────────────────────────────────────────────────────────────────

class SkillProgress(db.Model):
    """技能树进度表，每小组一条记录"""
    __tablename__ = 'skill_progress'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        unique=True, nullable=False
    )
    skills = db.Column(db.JSON, nullable=False, default=dict)
    total_xp = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'skills': self.skills,
            'total_xp': self.total_xp,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 11. announcements — 系统公告表
# ──────────────────────────────────────────────────────────────────────────────

class Announcement(db.Model):
    """系统公告/活动消息表"""
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(
        db.Enum('normal', 'important', 'urgent', name='ann_priority'),
        nullable=False, default='normal'
    )
    target_role = db.Column(
        db.Enum('all', 'teacher', 'group', name='target_role'),
        nullable=False, default='all'
    )
    course = db.Column(db.String(30), default=None)
    published_by = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'priority': self.priority,
            'target_role': self.target_role,
            'course': self.course,
            'published_by': self.published_by,
            'is_pinned': self.is_pinned,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 便利查询函数
# ──────────────────────────────────────────────────────────────────────────────

class AiTutorSession(db.Model):
    """Current AI tutor course session."""
    __tablename__ = 'ai_tutor_sessions'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    member_id = db.Column(db.String(20), default=None)
    page = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(50), nullable=False)
    step_code = db.Column(db.String(50), default=None)
    latest_snapshot = db.Column(db.JSON, default=None)
    latest_diagnosis = db.Column(db.JSON, default=None)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_active_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, default=None)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'group_id': self.group_id,
            'member_id': self.member_id,
            'page': self.page,
            'course': self.course,
            'step_code': self.step_code,
            'latest_snapshot': self.latest_snapshot,
            'latest_diagnosis': self.latest_diagnosis,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AiTutorEvent(db.Model):
    """Persisted AI tutor page event."""
    __tablename__ = 'ai_tutor_events'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    member_id = db.Column(db.String(20), default=None)
    page = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(50), nullable=False)
    step_code = db.Column(db.String(50), default=None)
    event_type = db.Column(db.String(50), nullable=False)
    event_name = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, default=None)
    summary_text = db.Column(db.String(255), default=None)
    dedupe_key = db.Column(db.String(120), default=None)
    event_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'group_id': self.group_id,
            'member_id': self.member_id,
            'page': self.page,
            'course': self.course,
            'step_code': self.step_code,
            'event_type': self.event_type,
            'event_name': self.event_name,
            'payload': self.payload,
            'summary_text': self.summary_text,
            'dedupe_key': self.dedupe_key,
            'event_time': self.event_time.isoformat() if self.event_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AiTutorMemorySummary(db.Model):
    """Longer-lived AI tutor memory summary for a group."""
    __tablename__ = 'ai_tutor_memory_summaries'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    summary_type = db.Column(db.String(50), nullable=False)
    course = db.Column(db.String(50), default=None)
    summary_json = db.Column(db.JSON, nullable=False)
    window_start = db.Column(db.DateTime, default=None)
    window_end = db.Column(db.DateTime, default=None)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'group_id': self.group_id,
            'summary_type': self.summary_type,
            'course': self.course,
            'summary_json': self.summary_json,
            'window_start': self.window_start.isoformat() if self.window_start else None,
            'window_end': self.window_end.isoformat() if self.window_end else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AiTutorMessage(db.Model):
    """Persisted AI tutor question and answer text."""
    __tablename__ = 'ai_tutor_messages'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('groups.user_id', ondelete='CASCADE'),
        nullable=False
    )
    role = db.Column(db.String(20), nullable=False)
    user_question_text = db.Column(db.Text, default=None)
    answer_text = db.Column(db.Text, default=None)
    diagnosis = db.Column(db.String(100), default=None)
    next_step = db.Column(db.String(255), default=None)
    tips = db.Column(db.JSON, default=None)
    context_used = db.Column(db.JSON, default=None)
    source = db.Column(db.String(30), default=None)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'session_id': self.session_id,
            'group_id': self.group_id,
            'role': self.role,
            'user_question_text': self.user_question_text,
            'answer_text': self.answer_text,
            'diagnosis': self.diagnosis,
            'next_step': self.next_step,
            'tips': self.tips,
            'context_used': self.context_used,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


def get_group_by_code(code: str) -> Group | None:
    return Group.query.filter_by(group_code=code).first()


def get_group_leaderboard(course: str, limit: int = 20,
                            is_public: bool = True) -> list[LeaderboardRecord]:
    return (
        LeaderboardRecord.query
        .filter_by(course=course, is_public=is_public)
        .order_by(LeaderboardRecord.accuracy.desc())
        .limit(limit)
        .all()
    )


def get_group_pending_face_records(group_id: int) -> list[FaceDataset]:
    return (
        FaceDataset.query
        .filter_by(group_id=group_id, status='pending')
        .order_by(FaceDataset.uploaded_at.desc())
        .all()
    )

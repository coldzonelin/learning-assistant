"""给现有 SQLite questions 表增加可选难度字段，保留已有数据。"""
from sqlalchemy import inspect, text
from run import app
from app.extensions import db

with app.app_context():
    if db.engine.dialect.name != 'sqlite':
        raise SystemExit('请为当前数据库使用对应的迁移工具增加 questions.difficulty 字段。')
    inspector = inspect(db.engine)
    if 'questions' not in inspector.get_table_names():
        raise SystemExit('数据库尚未初始化，请先运行 init-db。')
    if 'difficulty' not in {column['name'] for column in inspector.get_columns('questions')}:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE questions ADD COLUMN difficulty VARCHAR(16)'))
        print('已添加难度字段。')
    else:
        print('难度字段已存在。')

from pathlib import Path

import click
from flask import Flask, send_from_directory

from .config import Config
from .errors import register_error_handlers
from .extensions import db


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    from . import models  # noqa: F401 - 注册数据库模型
    from .api import api

    app.register_blueprint(api, url_prefix="/api/v1")
    from .api.ai import ai
    app.register_blueprint(ai, url_prefix="/api/v1")
    from .api.materials import material_api
    from .api.progress import progress_api
    app.register_blueprint(material_api, url_prefix="/api/v1")
    app.register_blueprint(progress_api, url_prefix="/api/v1")
    register_error_handlers(app)

    frontend = Path(__file__).resolve().parents[2] / "frontend"

    @app.get("/")
    def index():
        return send_from_directory(frontend, "index.html")

    @app.get("/<path:filename>")
    def frontend_file(filename):
        return send_from_directory(frontend, filename)

    @app.cli.command("init-db")
    def init_db():
        """创建缺失的数据表，不删除已有数据。"""
        db.create_all()
        click.echo("数据库表已初始化。")

    return app

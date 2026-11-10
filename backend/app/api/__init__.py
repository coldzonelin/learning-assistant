from flask import Blueprint

from ..errors import not_implemented, ok

api = Blueprint("api", __name__)


@api.get("/health")
def health():
    return ok({"status": "ok"})

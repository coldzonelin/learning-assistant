from flask import jsonify


class ApiError(Exception):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def ok(data=None):
    return jsonify({"data": data, "error": None})


def fail(code, message, status_code=400):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status_code


def not_implemented():
    raise ApiError("NOT_IMPLEMENTED", "该接口尚未实现", 501)


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return fail(exc.code, exc.message, exc.status_code)

    @app.errorhandler(404)
    def handle_not_found(_exc):
        return fail("NOT_FOUND", "资源不存在", 404)

    @app.errorhandler(405)
    def handle_method_not_allowed(_exc):
        return fail("METHOD_NOT_ALLOWED", "请求方法不被允许", 405)

    @app.errorhandler(413)
    def handle_file_too_large(_exc):
        return fail("FILE_TOO_LARGE", "上传文件超过大小限制", 413)

    @app.errorhandler(500)
    def handle_internal_error(exc):
        app.logger.exception("Unhandled error", exc_info=exc)
        return fail("INTERNAL_ERROR", "服务内部错误", 500)

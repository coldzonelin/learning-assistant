from flask import current_app


def get_current_user_id():
    # 登录体系接入前固定为开发用户；接入后只在这里替换为真实身份来源。
    return current_app.config["DEV_USER_ID"]

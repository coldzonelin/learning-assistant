#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR/backend"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装 Python 3。"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "正在创建 Python 虚拟环境..."
  python3 -m venv .venv
fi

echo "正在检查并安装依赖..."
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 backend/.env；使用 AI 功能前请配置模型 API Key。"
fi

echo "正在初始化数据库..."
.venv/bin/flask --app run:app init-db
.venv/bin/python migrate_difficulty.py

echo ""
echo "学习助手即将启动：http://127.0.0.1:${PORT:-5000}/"
echo "关闭此终端窗口或按 Ctrl+C 可停止服务。"
exec .venv/bin/python run.py

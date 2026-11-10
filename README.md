# 学习助手

一个面向课程学习的本地应用：上传资料，围绕资料与 AI 对话，通过测评查看知识点表现，并生成学习报告。前端使用原生 HTML、CSS 和 JavaScript，后端使用 Flask、SQLite 和 DeepSeek 兼容接口。

## 功能

- 上传 PDF、PPT、Word、Markdown 和 TXT，并查看解析状态。
- 选择资料进行多轮对话，查看回答引用的资料段落；不选择资料时可普通对话。
- 根据资料生成选择题、判断题和简答题，提交后查看评分。
- 查看知识点表现、薄弱点、资料统计以及学习周报。

## 运行前准备

- Python 3.10 或更新版本，及可用的 `pip` 和网络连接。
- DeepSeek API Key：用于聊天、出题、简答题评分和生成报告。每位使用者都需要配置自己的密钥，并自行承担模型服务费用。
- 解析旧版 `.doc` 和 `.ppt` 文件需要安装 LibreOffice，并确保 `soffice` 或 `libreoffice` 命令在 PATH 中。纯图片扫描版 PDF 暂不支持文字识别。

## 获取项目

从 GitHub 克隆仓库：

```bash
git clone https://github.com/coldzonelin/learning-assistant.git
cd learning-assistant
```

## 配置模型

首次启动会从 `backend/.env.example` 创建 `backend/.env`。也可以先手动复制：

```bash
cp backend/.env.example backend/.env
```

用文本编辑器打开 `backend/.env`，填写自己的配置，例如：

```ini
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=填写你自己的密钥
LLM_MODEL=deepseek-flash
```

模型地址、密钥和模型名称可单独调整；模型服务需支持 Chat Completions 接口。不要提交 `.env` 或把密钥放进前端代码。修改配置后需要重启服务。

## 启动

### macOS 一键启动

双击项目根目录的 `启动学习助手.command`。脚本会创建虚拟环境、安装依赖、创建缺失的数据表并启动服务。若首次运行时尚未配置密钥，请关闭服务、编辑 `backend/.env` 后重新启动。

### macOS / Linux 手动启动

在项目根目录执行：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# 仅在 .env 不存在时创建；不要覆盖已有配置
test -f .env || cp .env.example .env
# 编辑 .env，填入自己的模型配置
flask --app run:app init-db
python migrate_difficulty.py
python run.py
```

### Windows 手动启动（PowerShell）

在项目根目录执行：

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填入自己的模型配置
flask --app run:app init-db
python migrate_difficulty.py
python run.py
```

启动后访问 [http://127.0.0.1:5000/](http://127.0.0.1:5000/)。在运行服务的终端按 `Ctrl+C` 停止服务。端口被占用时，可设置 `PORT` 环境变量后重新启动；例如 macOS/Linux 使用 `PORT=5001 python run.py`，PowerShell 使用 `$env:PORT=5001; python run.py`。

可访问 `http://127.0.0.1:5000/api/v1/health` 检查后台；如果使用了其他端口，请相应修改地址。

## 数据与使用边界

- 默认数据库为 `backend/instance/study_assistant.db`，上传文件保存在 `backend/uploads/`。这两个目录和 `.env` 不会提交到 GitHub。
- 应用当前面向本机单用户使用，尚无登录和完整多用户隔离，请勿直接部署为多人公开服务。
- 资料内容会发送到配置的模型服务处理。聊天对较长资料使用本地字词匹配，不使用向量模型；出题资料超过配置的字符数上限时会提示。
- 简答题无法可靠评分时会标记为待核查，目前尚无人工核查入口。学习笔记保存在当前浏览器本地。
- 报告、进度和测评结果依赖已有学习记录；没有记录时不会凭空生成统计数据。

## 测试

安装依赖后，在 `backend` 目录运行：

```bash
python -m unittest discover -s tests -v
```

测试使用模拟模型响应，不需要真实 API Key。更详细的后端配置见 [backend/README.md](backend/README.md)。

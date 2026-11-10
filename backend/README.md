# 学习助手后端

已实现资料上传、解析、列表、详情、删除和重试；对话、测评、进度统计及报告接口已接入。解析采用同步处理，上传响应包含最终解析状态。

## 本地启动

在 `backend` 目录中执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -f .env || cp .env.example .env
flask --app run:app init-db
python migrate_difficulty.py
python run.py
```

打开 `http://127.0.0.1:5000/` 使用前端，或访问 `/api/v1/health` 检查服务。数据库默认保存在 `backend/instance/study_assistant.db`，`init-db` 只创建缺失的表，不删除已有表或数据；后续修改表结构需要迁移，不能依赖该命令修改已有表。

## 模型配置

在本地 `.env` 中分别设置 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`。默认示例地址指向 DeepSeek，API Key 留空，需由使用者自行配置；不要将 `.env` 提交到版本库。模型服务使用兼容 Chat Completions 的接口约定。网络错误、限流和服务端错误最多重试三次（首次请求之外）。

不使用向量模型。聊天时短资料直接提供全部片段，长资料使用字词匹配挑选相关片段；未匹配时明确报错。出题提供完整资料，超出配置上限时明确提示。`material_chunks` 也用于记录引用位置。自然周和自定义日期报告依赖已有聊天和已完成测评记录。

## 数据和身份

默认使用 SQLite。当前 `DEV_USER_ID` 是单用户本地开发占位值，并非登录或用户隔离方案，不能用于多用户部署。配置文件中的数据库连接示例需要对应的数据库驱动。Flask 提供同源前端和 API。`doc`、`ppt` 等旧版文件需要系统安装 LibreOffice，纯图片扫描 PDF 尚不支持文字识别。笔记目前保存在浏览器本地。

知识点状态依据已完成测评的得分率；资料掌握数按该资料关联的已完成测评累计得分率不低于 80% 统计。学习次数为有用户消息的对话数与已完成测评数之和。

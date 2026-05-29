# DEVELOPMENT.md

## 项目定位

这是一个面向企业劳动合规场景的 RAG + Agent 项目，当前发布版本的核心是：

- React + Vite 前端控制台
- FastAPI 后端接口
- 基于 LlamaIndex 的法律问答
- 基于 LangGraph 的 tool-calling 工作流
- 企业制度知识库问答
- 法律 + 制度组合问答
- 劳动合同风险审查与人工审批

## 运行主路径

- FastAPI 入口：`app/main.py`
- 前端控制台：`frontend/`
- Agent 编排：`app/agent/graph.py`
- 法律 RAG：`app/rag/llama_index_pipeline.py`
- 业务服务：`app/services/`

本地开发通常分两个进程启动：

```bash
uvicorn app.main:app --reload
cd frontend && npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

`/api/chat` 会先进入 LangGraph Agent。当前不是简单固定路由，而是：

1. `guardrail_node` 用本地规则处理合同审查、拒答和明显组合问题。
2. `tool_planner_node` 使用 DeepSeek/OpenAI-compatible tool calling 选择工具。
3. 远程 planner 不可用时，回退到本地 `IntentClassifier`。
4. `tool_executor_node` 执行工具并记录 `tool_trace`。
5. `answer_node` 汇总单工具或多工具结果。

当前结果类型包括：

- `law_qa`
- `policy_qa`
- `compliance_qa`
- `contract_review`
- `refusal`

当前工具包括：

- `search_law_articles`
- `search_company_policy`
- `contract_review_rules`
- `refuse_out_of_scope`

## 当前主要能力

### 法律问答

- 使用法律文本做分块、向量检索、BM25、RRF、rerank 和回答生成
- 支持 `LEGAL_RAG_CRAG_MODE=llm|reranker|off`
- 当前发布版保留评估 warmup 修复，避免第一条法律问题承担全部冷启动耗时

### 企业制度问答

- 上传文件保存在 `storage/uploads/`
- 企业制度向量索引独立于法律库
- 企业制度问答默认不与法律库混用；当用户明确比较法律要求和内部制度时，Agent 会返回 `compliance_qa` 并同时调用法律检索与制度检索

### 合同审查

- 规则驱动识别条款缺失、不明确和高风险模式
- 高风险结果进入审批队列
- 支持按需补充法律依据

### 人工审批

- 审批状态保存在本地存储
- 高风险合同不直接返回完整 findings

## API 入口

- `POST /api/chat`
- `POST /api/review/contract`
- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/reviews/pending`
- `POST /api/reviews/{review_id}/approve`
- `POST /api/reviews/{review_id}/reject`

## 仓库边界

- 包含生产化 Docker Compose 样例，但不提交真实 `.env`、本地 Chroma 数据、上传文件、模型缓存和历史评估结果
- 本地开发默认仍可使用 Chroma + JSON fallback；配置 `DATABASE_URL`、`REDIS_URL`、`CHROMA_HOST` 后切换到 PostgreSQL、Redis worker 和 Chroma Server
- 不包含旧实验目录 `experiments/`
- 不包含历史兼容入口 `src/`

## 维护建议

- 生产路径优先关注 `app/`
- 评估只保留最小 Agent Eval 能力，入口在 `evaluation/run_agent_eval_suite.py`
- 如果后续继续扩展知识库或 Agent 行为，优先保证 `/api/chat` 契约稳定
- `tools_used` 是稳定摘要字段；`tool_trace` 是调试轨迹字段，可用于查看工具名、参数摘要、状态和耗时

# AGENTS.md

## 项目定位

这是一个面向企业劳动合规场景的 RAG + Agent 项目，当前发布版本的核心是：

- 基于 LlamaIndex 的法律问答
- 基于 LangGraph 的四路由工作流
- 企业制度知识库问答
- 劳动合同风险审查与人工审批

## 运行主路径

- FastAPI 入口：`app/main.py`
- Agent 路由：`app/agent/graph.py`
- 法律 RAG：`app/rag/llama_index_pipeline.py`
- 业务服务：`app/services/`

`/api/chat` 会将请求路由到以下四类之一：

- `law_qa`
- `policy_qa`
- `contract_review`
- `refusal`

## 当前主要能力

### 法律问答

- 使用法律文本做分块、向量检索、BM25、RRF、rerank 和回答生成
- 支持 `LEGAL_RAG_CRAG_MODE=llm|reranker|off`
- 当前发布版保留评估 warmup 修复，避免第一条法律问题承担全部冷启动耗时

### 企业制度问答

- 上传文件保存在 `storage/uploads/`
- 企业制度向量索引独立于法律库
- 企业制度问答不与法律库混用

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

- 本发布版本不包含 Docker 配置
- 不包含本地 Chroma 数据、上传文件、模型缓存和历史评估结果
- 不包含旧实验目录 `experiments/`
- 不包含历史兼容入口 `src/`

## 维护建议

- 生产路径优先关注 `app/`
- 评估只保留最小 Agent Eval 能力，入口在 `evaluation/run_agent_eval_suite.py`
- 如果后续继续扩展知识库或 Agent 行为，优先保证 `/api/chat` 契约稳定

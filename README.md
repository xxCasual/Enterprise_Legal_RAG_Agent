# Enterprise Legal RAG Agent

面向中国企业劳动合规场景的 RAG + Agent 平台。项目把法律问答、企业制度问答、劳动合同风险审查和高风险人工复核组织到一个 FastAPI 后端和 React 控制台里，适合作为企业合规助手、RAG Agent 工程化样例和评估实验基座。

当前版本不是一个单纯的向量检索 Demo，而是一个可控的工具调用工作流：

- 法律问题进入劳动法律法规 RAG 链路
- 企业制度问题检索用户上传的内部制度文档
- 法律 + 制度对比问题可以同时调用多个工具
- 劳动合同文本进入结构化风险审查
- 高风险合同审查结果进入人工复核队列
- React 前端控制台用于本地验收和演示完整流程

## 功能亮点

| 能力 | 说明 |
|---|---|
| 统一问答入口 | `POST /api/chat` 自动路由到法律问答、企业制度问答、合同审查或拒答 |
| Tool-calling Agent | LangGraph 编排 guardrail、LLM planner、本地 fallback、工具执行和答案汇总 |
| 法律 RAG | 基于 LlamaIndex、Chroma、BGE embedding、reranker 的中文劳动法律问答链路 |
| 企业制度问答 | 支持上传 `.txt`、`.md`、`.pdf`、`.docx`，独立写入企业制度向量库 |
| 组合合规问答 | 同一个问题可同时检索法律依据和企业制度，返回 `compliance_qa` |
| 合同风险审查 | 规则驱动识别试用期、期限、工资、工时、社保、解除、竞业限制等条款风险 |
| 人工审批 | 高风险合同不直接输出完整结论，进入 `pending_review` 后由人工通过或拒绝 |
| 前端控制台 | React + Vite + TypeScript 实现聊天、文档上传、合同审查、审批和健康状态视图 |
| Agent Eval | 保留路由、工具调用、拒答和风险识别的自动评估脚本 |

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | React 19, Vite, TypeScript, lucide-react, CSS |
| API | FastAPI, Pydantic, Uvicorn |
| Agent | LangGraph, LangChain tool calling, DeepSeek/OpenAI-compatible API |
| RAG | LlamaIndex, Chroma, BM25, BGE embedding, BGE reranker |
| 文档解析 | pypdf, python-docx |
| 状态存储 | Chroma + 本地 JSON 文件 |
| 测试评估 | pytest, Agent Eval, RAGAS 兼容依赖 |

## 架构概览

```text
React Console
  |
  | /api/*
  v
FastAPI
  |
  v
LangGraph Agent
  |
  +-- guardrail_node: 规则拦截合同审查、拒答和组合合规问题
  +-- tool_planner_node: LLM function calling 规划工具；失败时回退本地分类器
  +-- tool_executor_node: 执行工具并记录 tool_trace
  +-- answer_node: 汇总单工具或多工具结果
        |
        +-- search_law_articles: 法律 RAG
        +-- search_company_policy: 企业制度检索与回答
        +-- contract_review_rules: 劳动合同风险审查
        +-- refuse_out_of_scope: 范围外拒答
```

本项目保留本地 JSON 开发模式，同时提供生产化部署路径：配置 `DATABASE_URL` 后，上传文档登记、索引任务和人工审批队列会写入 PostgreSQL；配置 `REDIS_URL` 后，制度文档索引会进入后台 worker；配置 `CHROMA_HOST` 后，向量库使用 Chroma Server。详见 [PRODUCTION.md](PRODUCTION.md)。

## 项目结构

```text
.
├── app/
│   ├── main.py                    # FastAPI 入口与 OpenAPI 元数据
│   ├── agent/                     # LangGraph Agent、工具规划、执行与答案汇总
│   ├── core/config.py             # 环境变量和路径配置
│   ├── rag/                       # LlamaIndex 法律 RAG 主链路
│   ├── schemas/                   # Pydantic 请求/响应模型
│   └── services/                  # 文档、合同审查、审批、RAG 服务封装
├── frontend/                      # React + Vite 前端控制台
├── evaluation/                    # Agent Eval 脚本
├── tests/                         # API、Agent、服务和 RAG 单元测试
├── data/                          # 默认法律文本与评估数据
├── requirements.txt
└── .env.example
```

## 快速开始

### 1. 准备后端环境

本仓库可以复用兄弟项目 `legal-rag-system` 的虚拟环境：

```bash
../legal-rag-system/venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
../legal-rag-system/venv/bin/python -m uvicorn app.main:app --reload
```

也可以单独创建虚拟环境：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

后端默认地址：

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health`

### 2. 启动前端控制台

```bash
cd frontend
npm install
npm run dev
```

前端默认地址：

- `http://127.0.0.1:5173`

Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 环境变量

最少需要配置：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LEGAL_RAG_LLM_MODEL=deepseek-chat
LEGAL_RAG_CRAG_MODE=reranker
```

常用路径配置：

```env
LEGAL_RAG_STORAGE_DIR=storage
LEGAL_RAG_UPLOADS_DIR=storage/uploads
LEGAL_RAG_DOCUMENT_REGISTRY=storage/documents.json
LEGAL_RAG_PENDING_REVIEWS=storage/pending_reviews.json
LEGAL_RAG_LLAMA_LAW_CHROMA_DIR=chroma_llama_law
LEGAL_RAG_LLAMA_COMPANY_CHROMA_DIR=chroma_llama_company
```

生产化配置：

```env
DATABASE_URL=postgresql+psycopg://legal_rag:legal_rag@postgres:5432/legal_rag
REDIS_URL=redis://redis:6379/0
CHROMA_HOST=chroma
CHROMA_PORT=8000
CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
MAX_UPLOAD_MB=20
INDEXING_MAX_ATTEMPTS=3
API_AUTH_TOKEN=change-me
LOG_LEVEL=INFO
```

`LEGAL_RAG_CRAG_MODE` 支持：

| 值 | 说明 |
|---|---|
| `reranker` | 默认推荐，使用本地 reranker 排序结果，适合本地验收和评估 |
| `llm` | 使用 LLM 做相关性判断，更接近早期 CRAG 行为 |
| `off` | 跳过 CRAG，适合调试 |

## API 速览

### 统一问答

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"试用期最长多久？"}'
```

典型返回字段：

- `answer`
- `citations`
- `intent`
- `route`
- `tools_used`
- `tool_trace`
- `result_type`
- `risk_level`
- `review_status`
- `review_id`
- `contract_review`
- `latency`

### 上传企业制度文档

```bash
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "file=@员工手册.pdf"
```

```bash
curl http://127.0.0.1:8000/api/documents
```

### 合同审查

```bash
curl -X POST http://127.0.0.1:8000/api/review/contract \
  -H "Content-Type: application/json" \
  -d '{"contract_text":"甲方可随时解除合同且不支付经济补偿。乙方自愿放弃社保。"}'
```

高风险合同会返回 `review_status = pending_review` 和 `review_id`，完整结果需要人工审批后再输出。

### 人工审批

```bash
curl http://127.0.0.1:8000/api/reviews/pending

curl -X POST http://127.0.0.1:8000/api/reviews/{review_id}/approve

curl -X POST http://127.0.0.1:8000/api/reviews/{review_id}/reject
```

## 前端控制台

控制台包含五个工作区：

- 统一问答：展示答案、引用、意图、工具调用轨迹、耗时和风险状态
- 制度文档：上传企业制度文档，刷新文档列表，查看 chunk 数和创建时间
- 合同审查：提交合同文本，查看整体风险、条款 findings、建议和免责声明
- 人工审批：查看待复核记录，通过或拒绝高风险合同审查结果
- 系统状态：查看 FastAPI、制度文档和待审批数量

前端常用命令：

```bash
cd frontend
npm run typecheck
npm run build
npm run preview
```

## 测试与评估

### 后端测试

```bash
../legal-rag-system/venv/bin/python -m pytest -q
```

### 前端检查

```bash
cd frontend
npm run typecheck
npm run build
```

### Agent Eval

项目保留了最小 Agent Eval 能力，用于验证路由、工具选择、拒答和风险识别：

```bash
../legal-rag-system/venv/bin/python evaluation/run_agent_eval_suite.py \
  --testset data/eval/agent_testset.json \
  --suite split \
  --routing-only
```

评估字段包括：

- `expected_intent`
- `expected_tools`
- `should_refuse`
- `expected_risk_level`

## 当前边界

- 本仓库不提交本地 Chroma 索引、上传文件、模型缓存和评估输出。
- 企业制度问答在没有 DeepSeek API key 或 LLM 调用失败时，会返回检索片段 fallback，并在 `tool_trace` 标记 `answer_source = retrieval_fallback`。
- 合同审查是规则驱动的风险提示，不构成确定性法律意见；审查结果固定包含“仅供参考，需人工复核”。
- 高风险审查结果会进入本地 JSON 审批队列；当前没有鉴权、多租户或并发审批设计。

## 适合用来学习什么

- 如何把 RAG pipeline 包成 Agent 工具
- 如何为企业制度文档建立独立知识库
- 如何设计 guardrail + planner + executor + answer 的可控 Agent 工作流
- 如何让高风险法律输出进入人工复核流程
- 如何把后端 API、React 控制台和 Agent Eval 放到同一个项目里协同演进

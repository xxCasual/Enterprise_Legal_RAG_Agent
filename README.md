# Enterprise Legal RAG Agent

面向中国企业劳动合规场景的 RAG + Agent 项目。它不是完整 SaaS，而是一个“企业试点级生产化”样例：保留简历项目的可演示性，同时补齐容器化部署、数据库持久化、异步文档索引、服务状态检查、基础指标、简单管理鉴权和失败恢复能力。

当前项目继续使用 Python/FastAPI 做业务后端，没有引入 Java。并发目标按小规模企业内部试点设计：几十个内部用户、少量同时上传、问答延迟主要受 LLM 和 embedding 检索链路影响。

## 核心能力

| 能力 | 说明 |
|---|---|
| 统一问答 | `POST /api/chat` 自动路由到法律问答、企业制度问答、合同审查或范围外拒答 |
| Tool-calling Agent | LangGraph 编排 guardrail、LLM planner、fallback 分类器、工具执行和答案汇总 |
| 法律 RAG | LlamaIndex + Chroma + BM25 + bge embedding，检索劳动法、劳动合同法等内置法律文本 |
| 企业制度 RAG | 上传 `.txt`、`.md`、`.pdf`、`.docx` 后写入独立企业制度知识库 |
| 异步索引 | 生产模式下上传只创建任务，worker 从 Redis 消费并完成解析、切分、embedding、写入 Chroma |
| 合同审查 | 规则驱动识别试用期、工资、工时、社保、解除、竞业限制等劳动合同风险 |
| 人工复核 | 高风险合同进入审批队列，人工通过后才返回完整审查结果 |
| 生产依赖 | Docker Compose 编排 FastAPI、worker、PostgreSQL、Redis、Chroma、Nginx 前端 |
| 可观测性 | 结构化请求日志、`X-Request-ID`、接口耗时、工具调用耗时、`/api/ready`、`/api/metrics` |
| 前端控制台 | React + Vite + TypeScript，覆盖问答、文档、合同审查、人工审批和系统状态 |

## 验证状态（2026-10-06，macOS Apple Silicon，全新 clone）

| 范围 | 状态 | 记录 |
|---|---|---|
| 本地开发路径（JSON fallback，无 PostgreSQL / Redis） | 已验证 | Python 3.11 venv 按 `requirements.txt` 安装；`/api/health`、`/api/ready` 正常；首次问答下载 `BAAI/bge-small-zh-v1.5` 并建索引约 83 s，之后检索约 0.3 s |
| 法律问答：路由、检索与引用 | 已验证 | “试用期最长多久？”路由为法条查询，调用 `search_law_articles`，引用含《劳动合同法》第十九条 |
| 法律问答：真实模型生成回答 | 已验证（n=1） | `deepseek-chat`：planner 以工具调用选择 `search_law_articles`，返回 4 条引用，回答依据第十九条给出 1 / 2 / 6 个月三档上限；2 次模型请求，接口耗时约 15 s。无有效 Key 时模型返回 401，接口降级为直接返回检索到的法条原文 |
| 合同审查与人工复核 | 已验证 | 高风险样例返回 `pending_review`，管理员登录并批准后返回逐条款 `risk_level`、`analysis`、`suggestion` |
| 自动检查 | 已验证 | Python 3.11 轻量锁定依赖环境：`pytest` 87 passed；Agent Eval `evaluation.agent.suite --routing-only` 59 条全部通过；前端 `npm ci`、类型检查、构建通过。已配置 CI，远端执行结果见 Actions |
| Docker Compose 生产栈、迁移、worker、PostgreSQL / Chroma | 已验证 | 从空 volumes 启动；真实 embedding 索引与制度查询、审批、鉴权、指标、API/worker 重启持久化通过；[冷启动记录](docs/validation/production-smoke-20261006.json)、[最终配置复验](docs/validation/default-final-smoke-20261006.json) |
| 离线 embedding override | 已验证 | 完整 bge-small 模型文件挂载，offline 标志开启，上传→worker→Chroma→制度查询通过；未做网络断开测试；[运行记录](docs/validation/offline-smoke-20261006.json) |

已知限制：合同审查是关键词规则，覆盖有限。例如“一年期合同约定六个月试用期”“每天 10 小时不付加班费”只被标为低风险；含“劳动合同”“试用期”等词的法律问题（如“劳动合同期限一年的，试用期最长可以约定多久？”）会被 guardrail 直接路由到合同审查。运行依赖仅 Chroma 固定版本，其余尚未全部锁定；本次容器解析结果见 [依赖快照](docs/validation/runtime-packages-20261006.txt)。

[配置与持久化边界](docs/configuration-and-boundaries.md) 对比开发、生产和离线模式。JSON fallback 限单 API 进程；Redis BLPOP 队列的可捕获异常重试已有回归，进程崩溃后的在途回收尚未实现。`/api/ready` 应检查 JSON body；模型项只检查 Key 配置，指标是各 API 进程的内存计数。

低成本 CI 使用 `requirements-ci.txt` 锁定完整轻量依赖，检查语法/无效构造、确定性测试、无 Key 路由和前端类型/构建，不安装模型权重。它不替代真实 embedding/Chroma 的集成验证。

## 评测与历史指标

检索链路的 RAGAS 评测（五个版本、两种重排配置在相同 48 题上 Context Recall 0.828 → 0.889）是在本项目的前身 LangChain 原型 [legal-rag-system](https://github.com/xxCasual/legal-rag-system) 上完成的，原始结果与复算方法见其 [evaluation/published-results](https://github.com/xxCasual/legal-rag-system/tree/main/evaluation/published-results)。这些数字不代表本重构版的效果。

本仓库 `evaluation/rag` 中的 `context_recall` 是自定义文本匹配指标（参考上下文是否出现在检索结果中），不是 RAGAS 的 `LLMContextRecall`，两者数值不能比较。

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | React 19, Vite, TypeScript, lucide-react, Nginx |
| API | FastAPI, Pydantic, Uvicorn |
| Agent | LangGraph, LangChain tool calling, DeepSeek/OpenAI-compatible API |
| RAG | LlamaIndex, Chroma, BM25, bge embedding, optional bge reranker |
| 文档解析 | pypdf, python-docx |
| 持久化 | PostgreSQL, SQLAlchemy, Alembic；本地开发保留 JSON fallback |
| 异步任务 | Redis queue + Python worker |
| 测试评估 | pytest, Agent Eval, RAG Eval |

## 架构

```mermaid
flowchart LR
  U["Browser"] --> N["Nginx / React Console"]
  N --> A["FastAPI API"]
  A --> G["LangGraph Agent"]
  G --> LA["Law RAG Tool"]
  G --> PA["Company Policy Tool"]
  G --> CA["Contract Review Tool"]
  A --> P["PostgreSQL"]
  A --> R["Redis"]
  A --> C["Chroma Server"]
  W["Indexing Worker"] --> R
  W --> P
  W --> C
  A --> L["DeepSeek / OpenAI-compatible LLM"]
```

开发模式可以只跑 FastAPI + React，本地用 JSON 文件记录文档和审批队列；生产化 Compose 模式会启用 PostgreSQL、Redis、Chroma server 和 worker。

## 项目结构

```text
.
├── app/
│   ├── main.py                     # FastAPI API 入口
│   ├── worker.py                   # Redis 文档索引 worker
│   ├── agent/                      # Agent graph、planner、executor、answer 聚合
│   ├── core/                       # 配置、数据库、鉴权、日志、指标、ready check
│   ├── rag/                        # LlamaIndex 法律 RAG 与 Chroma client
│   ├── schemas/                    # Pydantic API 模型
│   └── services/                   # 文档、审批、合同审查、RAG service
├── alembic/                        # PostgreSQL 迁移
├── data/                           # 内置法律文本与评估集
├── evaluation/                     # Agent/RAG Eval 与共享评估工具
├── frontend/                       # React 控制台和 Nginx 配置
├── scripts/production_smoke.sh     # 生产化冒烟测试
├── docker-compose.prod.yml         # 生产化 Compose 栈
├── Dockerfile                      # API/worker 镜像
├── PRODUCTION.md                   # 部署、备份、验收说明
└── requirements.txt
```

## 快速开始：Docker 生产化演示

Docker Compose 用于启动完整链路，验证范围见上表。只想快速体验可先用下方[本地开发](#快速开始本地开发)路径。

1. 准备环境变量：

```bash
cp .env.production.example .env
```

至少配置模型 Key（真实模型问答时需要）和管理 token：

```env
DEEPSEEK_API_KEY=your_key
API_AUTH_TOKEN=replace_with_a_random_token
```

2. 选择 embedding 模型。

默认使用公开模型 `BAAI/bge-small-zh-v1.5`，首次使用时联网下载到容器内 `hf_cache` volume，不挂载宿主机目录。已有完整离线模型时，准备实际文件目录并使用单独 override：

```env
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1
LOCAL_EMBEDDING_MODEL_DIR=./.cache/embedding-model
LEGAL_RAG_EMBEDDING_MODEL=/models/embedding
```

两种模型的检索效果不同，更换后不能沿用另一种配置下的评测结论。

离线启动命令为 `docker compose -f docker-compose.prod.yml -f docker-compose.offline.yml up -d --build`。模型目录必须存在，包含完整文件，不能有指向挂载范围外的软链接。Apple Silicon 的 CPU 容器不会自动使用 Metal/MPS。

3. 启动完整栈：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. 打开服务：

- 前端控制台：`http://localhost:8080`
- API health：`http://localhost:8080/api/health`
- Ready check：`http://localhost:8080/api/ready`
- Metrics：`http://localhost:8080/api/metrics`
- Chroma：`http://localhost:8001`

5. 查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f api worker
```

本地 Colima 推荐给 bge-m3 至少 8G 内存：

```bash
docker compose -f docker-compose.prod.yml down
colima stop
colima start --cpu 4 --memory 10 --disk 100
docker compose -f docker-compose.prod.yml up -d
```

## 快速开始：本地开发

如果不跑 Docker，可以只启动 FastAPI 和 Vite。此时不配置 `DATABASE_URL`、`REDIS_URL`、`CHROMA_HOST` 时，系统会使用本地 JSON fallback 和本地 Chroma 目录。

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` 中填入 `DEEPSEEK_API_KEY`，并把 `API_AUTH_TOKEN` 换成随机值（如 `openssl rand -hex 32`）。默认 embedding 为 `BAAI/bge-small-zh-v1.5`，首次问答时从 `HF_ENDPOINT` 下载（约 100 MB）。

启动 API：

```bash
uvicorn app.main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

本地开发地址：

- API：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`
- 前端：`http://127.0.0.1:5173`

## 环境变量

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 或 OpenAI-compatible API key |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `LEGAL_RAG_LLM_MODEL` | 默认 `deepseek-chat` |
| `LEGAL_RAG_LLM_TIMEOUT_SECONDS` | LLM 调用超时 |
| `LEGAL_RAG_EMBEDDING_MODEL` | embedding 模型 id 或本地模型路径 |
| `LEGAL_RAG_RERANKER_MODEL` | reranker 模型；设为 `off` 可关闭 |
| `LEGAL_RAG_CRAG_MODE` | `reranker`、`llm`、`off` |
| `DATABASE_URL` | 配置后启用 PostgreSQL repository |
| `REDIS_URL` | 配置后启用 Redis 异步索引队列 |
| `CHROMA_HOST` / `CHROMA_PORT` | 配置后使用 Chroma server |
| `CORS_ORIGINS` | 允许访问 API 的前端地址 |
| `MAX_UPLOAD_MB` | 上传文件大小限制 |
| `INDEXING_MAX_ATTEMPTS` | 索引任务最大重试次数 |
| `API_AUTH_TOKEN` | 管理接口 token；前端通过登录换取 HttpOnly cookie |
| `ADMIN_SESSION_TTL_SECONDS` | 管理员 cookie 会话有效期 |
| `LEGAL_RAG_WARMUP_ON_STARTUP` | 启动后是否后台预热法律 RAG |
| `VITE_API_BASE_URL` | 前端构建时 API base；Compose 下保持空 |
| `LOCAL_EMBEDDING_MODEL_DIR` | 离线 override 挂载的完整模型文件目录 |

`LEGAL_RAG_CRAG_MODE` 的含义：

| 值 | 行为 |
|---|---|
| `reranker` | 使用 reranker 后处理；如果 `LEGAL_RAG_RERANKER_MODEL=off`，则只做 RRF 融合后取 top-N |
| `llm` | 使用 LLM 对候选 chunk 做相关性过滤 |
| `off` | 跳过 CRAG 过滤，适合调试 |

## API 速览

### 系统状态

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/ready
curl http://localhost:8080/api/metrics
```

### 统一问答

```bash
curl -sS http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"试用期最长多久？"}'
```

典型响应字段：

- `answer`
- `citations`
- `route`
- `intent`
- `tools_used`
- `tool_trace`
- `result_type`
- `risk_level`
- `review_status`
- `review_id`
- `contract_review`
- `latency`

### 上传企业制度

管理接口需要 token：

```bash
TOKEN=replace_with_a_random_token

curl -sS http://localhost:8080/api/documents/upload \
  -H "X-API-Key: $TOKEN" \
  -F "file=@员工手册.pdf"

curl -sS http://localhost:8080/api/documents \
  -H "X-API-Key: $TOKEN"
```

文档记录包含：

- `status`: `pending`、`indexing`、`ready`、`failed`
- `error_message`
- `indexed_at`
- `task_id`
- `chunk_count`

### 合同审查

```bash
curl -sS http://localhost:8080/api/review/contract \
  -H "Content-Type: application/json" \
  -d '{"contract_text":"甲方可随时解除合同且不支付经济补偿。乙方自愿放弃社保。"}'
```

高风险合同会返回 `review_status=pending_review` 和 `review_id`。

### 人工审批

```bash
TOKEN=replace_with_a_random_token

curl -sS http://localhost:8080/api/reviews/pending \
  -H "X-API-Key: $TOKEN"

curl -sS -X POST http://localhost:8080/api/reviews/{review_id}/approve \
  -H "X-API-Key: $TOKEN"

curl -sS -X POST http://localhost:8080/api/reviews/{review_id}/reject \
  -H "X-API-Key: $TOKEN"
```

## RAG 流程

法律问答的主流程：

```text
用户问题
  -> Agent planner 选择 search_law_articles
  -> 法律 RAG pipeline
  -> 路由判断：法条查询 / 法律咨询 / 知识库外
  -> BM25 检索 topK
  -> bge embedding + Chroma 向量检索 topK
  -> RRF 融合
  -> 可选 reranker 或 LLM CRAG 过滤
  -> 取 top contexts
  -> LLM 根据法律条文生成回答
```

按 `.env.example` 默认配置，embedding 为 `BAAI/bge-small-zh-v1.5`，`LEGAL_RAG_RERANKER_MODEL=off`。因此默认链路是 BM25 + 向量检索 + RRF 融合，不加载 reranker；离线配置下向量模型为 bge-m3。首次请求可能触发法律库 embedding 和 Chroma 写入，会比较慢；索引建立后后续请求会明显变快。

企业制度问答的主流程：

```text
上传文档
  -> API 保存文件和文档记录
  -> Redis indexing task
  -> worker 解析文档、切 chunk、embedding、写入 Chroma
  -> 文档状态 ready
  -> search_company_policy 检索 ready 文档
  -> LLM 生成制度问答
```

## 前端控制台

前端包含 5 个主要工作区：

- 统一问答：展示答案、引用、工具调用、耗时和风险状态
- 制度文档：上传文档、刷新状态、查看索引结果
- 合同审查：提交合同文本并查看结构化风险
- 人工审批：处理高风险合同复核
- 系统状态：查看 API、DB、Redis、Chroma、文档任务和待审批数量

前端命令：

```bash
cd frontend
npm run typecheck
npm run build
npm run preview
```

## 测试与验收

后端单元测试：

```bash
./venv/bin/python -m pytest
```

重点测试：

```bash
./venv/bin/python -m pytest tests/test_config.py tests/test_llama_index_pipeline.py
```

Agent Eval 用于评估路由、工具选择、拒答和合同风险。快速检查本地规则链路时使用
`--routing-only`，不触发 RAG/LLM 生成：

```bash
./venv/bin/python evaluation/run_agent_eval_suite.py \
  --testset data/eval/agent_testset.json \
  --suite split \
  --routing-only
```

也可以使用新的模块入口：

```bash
./venv/bin/python -m evaluation.agent.suite \
  --testset data/eval/agent_testset.json \
  --suite split \
  --routing-only
```

RAG Eval 用于评估法律 RAG 的检索上下文和最终回答质量。`retrieval` 模式只看
context recall/precision 和延迟；`e2e` 模式同时检查回答是否覆盖 ground truth：

```bash
./venv/bin/python -m evaluation.rag.cli --mode retrieval --limit 20
./venv/bin/python -m evaluation.rag.cli \
  --mode e2e \
  --testset data/eval/testset.json \
  --tag baseline
```

评估结果分别写入 `data/eval/agent_results/` 和 `data/eval/rag_results/`。

生产化冒烟测试：

```bash
API_AUTH_TOKEN=replace_with_a_random_token scripts/production_smoke.sh
```

混合压测：

```bash
API_AUTH_TOKEN=replace_with_a_random_token ./venv/bin/python scripts/stress_mixed.py
RUN_REAL_RAG=1 API_AUTH_TOKEN=replace_with_a_random_token ./venv/bin/python scripts/stress_mixed.py
```

Docker 验收建议：

```bash
docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost:8080/api/ready
curl -sS http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"试用期最长多久？"}'
```

## 运维说明

Compose volumes：

- `postgres_data`: PostgreSQL 数据
- `redis_data`: Redis AOF 数据
- `chroma_data`: Chroma server 数据
- `uploads`: 上传文件
- `law_index`: 法律库本地索引兼容目录
- `company_index`: 企业制度本地索引兼容目录
- `hf_cache`: 容器内 HuggingFace cache

备份 PostgreSQL：

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U legal_rag legal_rag > backup.sql
```

查看服务：

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api worker
```

重新构建前端或 API：

```bash
docker compose -f docker-compose.prod.yml up -d --build frontend
docker compose -f docker-compose.prod.yml up -d --build api worker
```

## 常见问题

### 前端显示服务异常或 Not Found

先看 ready check：

```bash
curl http://localhost:8080/api/ready
```

如果前端请求路径变成 `/api/api/*`，确认 `VITE_API_BASE_URL` 在 Compose 下为空。

### 首次问答很慢

使用 bge-m3 时，首次法律问答可能会加载模型并构建 Chroma 索引。本机 Docker/Colima 下这是 CPU 任务，后续请求会快很多。
可用 `scripts/rag_warmup.sh` 或设置 `LEGAL_RAG_WARMUP_ON_STARTUP=1` 预热法律 RAG。

### bge-m3 在 Docker 中路径不存在

离线模型文件必须在 `LOCAL_EMBEDDING_MODEL_DIR` 指定目录中，且软链接不能指向挂载范围外。准备完整模型后使用离线 override：

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.offline.yml up -d
```

默认联网路径不需要本机模型挂载。

### Chroma 报 `_type`

这是 Chroma Python client 和 Chroma server 版本不一致的典型问题。当前 Compose 使用 `chromadb/chroma:1.5.9`，和 API 镜像内的 `chromadb 1.5.9` 对齐。

### 上传、审批接口 401

前端控制台会要求输入 `API_AUTH_TOKEN` 并保存为 HttpOnly cookie。curl 调用时加：

```bash
-H "X-API-Key: $TOKEN"
```

也支持：

```bash
-H "Authorization: Bearer $TOKEN"
```

## 当前边界

- 这不是完整 SaaS，不包含多租户、SSO、计费、复杂 RBAC。
- 合同审查是规则驱动风险提示，不构成正式法律意见。
- 默认生产化部署面向单企业内部试点，不追求千级并发。
- Apple Silicon 上 Docker 容器内不会自动使用 M4 GPU；服务器 GPU 需要 NVIDIA driver、CUDA 版 PyTorch、`nvidia-container-toolkit` 和 Compose GPU 配置。
- 默认关闭 reranker，以便本地 Docker 更稳；开启 reranker 会提高排序质量，但需要更多内存。

## 延伸文档

- 生产部署与验收：[PRODUCTION.md](PRODUCTION.md)
- 开发说明：[DEVELOPMENT.md](DEVELOPMENT.md)

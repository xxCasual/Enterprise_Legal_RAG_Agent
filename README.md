# legal-rag-agent-system

基于LlamaIndex、LangGraph重构leagal rag

这是一个面向企业劳动合规场景的 RAG + Agent 项目，当前主路径围绕四类能力组织：

- 法律问答：基于中国劳动相关法律文本进行检索问答
- 企业制度问答：支持上传企业内部制度文档并独立建库问答
- 劳动合同审查：规则驱动的结构化风险审查
- 人工审批：高风险合同进入本地审批队列，不直接放出完整结果

## 主要入口

- `POST /api/chat`
- `POST /api/review/contract`
- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/reviews/pending`
- 审批接口：`/api/reviews/{review_id}/approve` 与 `/api/reviews/{review_id}/reject`

## 技术结构

- `app/main.py`：FastAPI 入口
- `app/agent/graph.py`：LangGraph 四路由工作流
- `app/rag/llama_index_pipeline.py`：LlamaIndex 法律 RAG 主链路
- `app/services/`：企业制度检索、合同审查、审批与存储服务

## 快速开始

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

默认访问地址：

- `GET http://127.0.0.1:8000/api/health`
- `POST http://127.0.0.1:8000/api/chat`

## 配置

最少需要配置：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `LEGAL_RAG_LLM_MODEL`
- `LEGAL_RAG_CRAG_MODE`

其余路径类配置见 `.env.example`。

## 评估

项目保留了最小 Agent Eval 能力，用于验证路由、工具选择、拒答和合同审查行为：

```bash
python evaluation/run_agent_eval_suite.py --testset data/eval/test.json --suite law
```

## 仓库说明

- 本仓库不包含本地 Chroma 索引、上传文件、模型缓存和历史评估结果
- 历史实验入口 `src/` 与 `experiments/` 已从发布版本移除
- 发布版本保留了评估 warmup 修复，以避免第一条法律问题承担全部冷启动耗时

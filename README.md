# legal-rag-agent-system

基于LlamaIndex、LangGraph重构leagal rag

这是一个面向企业劳动合规场景的 RAG + Agent 项目，当前主路径围绕工具调用组织：

- 法律问答：基于中国劳动相关法律文本进行检索问答
- 企业制度问答：支持上传企业内部制度文档并独立建库问答
- 法律 + 制度组合问答：同一个问题可同时调用法律检索和企业制度检索
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
- `app/agent/graph.py`：LangGraph tool-calling 编排入口
- `app/agent/guards.py`：守护规则、合同文本识别和法律+制度组合问题识别
- `app/agent/planner.py`：LLM tool planner 与本地 `IntentClassifier` fallback
- `app/agent/executor.py`：工具执行和 `tool_trace` 记录
- `app/agent/answering.py`：单工具/多工具结果汇总
- `app/rag/llama_index_pipeline.py`：LlamaIndex 法律 RAG 主链路
- `app/services/`：企业制度检索、合同审查、审批与存储服务

## 快速开始

本仓库开发与测试默认复用兄弟项目 `legal-rag-system` 的虚拟环境：

```bash
../legal-rag-system/venv/bin/python -m pip install -r requirements.txt
../legal-rag-system/venv/bin/python -m uvicorn app.main:app --reload
```

如果需要单独创建本仓库自己的虚拟环境：

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
../legal-rag-system/venv/bin/python -m pytest tests/test_agent_graph.py tests/test_api_contract.py tests/test_agent_eval.py tests/test_agent_eval_suite.py -q
../legal-rag-system/venv/bin/python -m pytest -q
../legal-rag-system/venv/bin/python evaluation/run_agent_eval_suite.py --testset data/eval/agent_testset.json --suite split --routing-only
```

## Agent 工具调用

`/api/chat` 会先进入 LangGraph Agent。当前流程是：

1. `guardrail_node` 先用本地规则拦截合同审查、拒答和明显的法律+制度组合问题。
2. `tool_planner_node` 通过 DeepSeek/OpenAI-compatible function calling 选择工具。
3. 如果远程 LLM 不可用或没有返回 `tool_calls`，系统回退到本地 `IntentClassifier`。
4. `tool_executor_node` 执行工具并记录 `tool_trace`。
5. `answer_node` 汇总单工具或多工具结果。

可调用工具包括：

- `search_law_articles`
- `search_company_policy`
- `contract_review_rules`
- `refuse_out_of_scope`

当一个问题同时比较法律要求和企业制度时，返回 `intent/route/result_type = compliance_qa`，并在 `tools_used` 中记录多个工具。API 响应保留 `tools_used` 摘要，同时新增 `tool_trace` 方便调试每次工具调用的名称、参数摘要、状态和耗时。

DeepSeek function calling 参考：[DeepSeek Function Calling](https://api-docs.deepseek.com/guides/function_calling)。

## 仓库说明

- 本仓库不包含本地 Chroma 索引、上传文件、模型缓存和历史评估结果
- 历史实验入口 `src/` 与 `experiments/` 已从发布版本移除
- 发布版本保留了评估 warmup 修复，以避免第一条法律问题承担全部冷启动耗时

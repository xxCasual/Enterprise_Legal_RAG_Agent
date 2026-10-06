# 简历声明与证据入口

2026-10-06。

| 声明 | 实现入口 | 证据 |
| --- | --- | --- |
| LangGraph 路由与工具调用 | `app/agent/graph.py`、`planner.py`、`tools.py` | `tests/test_agent_graph.py`、`tests/test_agent_eval_suite.py`、README 验证状态 |
| BM25、向量和 RRF | `app/rag/llama_index_pipeline.py` | `tests/test_llama_index_pipeline.py`、历史与当前验证说明 |
| 检索后 CRAG 相关性过滤 | `llama_index_pipeline.py::_crag_filter` | `tests/test_crag_modes.py`；输出引用为检索上下文，不是生成后引用校验 |
| 异步索引与失败重试 | `app/services/document_service.py`、`task_queue.py`、`app/worker.py` | `tests/test_document_service.py`、`tests/test_worker.py`、生产 smoke |
| 管理接口鉴权与人工审批 | `app/core/security.py`、`app/services/review_service.py`、`app/main.py` | `tests/test_api_contract.py`、`tests/test_review_service.py`、生产 smoke |
| 健康、就绪、基础指标 | `app/core/readiness.py`、`observability.py` | `/api/health`、`/api/ready` body、`/api/metrics`、生产 smoke |
| 五版 RAGAS 与 0.828→0.889 | 早期 LangChain 原型，不是本重构版 | [公开历史结果与复算](https://github.com/xxCasual/legal-rag-system/tree/main/evaluation/published-results) |

## 数字口径

五版样本 54/50/48/48/48，部分指标缺失。两版重排配置对比使用相同 48 条问题与参考答案，Context Recall 均值 0.828125→0.888889，提高 6、不变 41、降低 1；候选池 8→16 也发生变化，不能单独归因于重排模型。

历史评估器为 deepseek-chat API 别名，RAGAS 版本与运行时代码未完全冻结。保存结果复算和重新调用模型复现是两件事。本仓 `evaluation/rag` 的 `_context_recall` 是自定义文本匹配，不是 RAGAS LLMContextRecall。

## 工程边界

合同规则存在漏判，路由有误判；输出只供人工审查辅助。自动化测试覆盖工程逻辑，不能替代真实模型效果。JSON fallback、Redis 在途消息、多进程指标与存储一致性的边界见 [配置说明](configuration-and-boundaries.md)。

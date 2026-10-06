# 配置与持久化边界

更新：2026-10-06。

| 模式 | 配置入口 | 元数据/审批 | 索引任务 | 向量存储 | 适用范围 |
| --- | --- | --- | --- | --- | --- |
| 本地开发 | `.env.example` | JSON 文件 | 同请求内执行 | 本地 Chroma | 单进程演示、开发排查 |
| Compose 栈 | `.env.production.example` → `.env` | PostgreSQL | Redis + worker | Chroma server 1.5.9 | 单企业内部试点样例 |
| 离线模型 | 生产配置加 `.env.offline.example` 覆盖 | 同生产配置 | 同生产配置 | 同生产配置 | 已准备完整模型缓存的环境 |

## 模型与历史指标

默认 embedding 是 `BAAI/bge-small-zh-v1.5`，首次使用下载，重排默认关闭。默认联网 Compose 不挂载本机模型目录。离线样例另加 `-f docker-compose.offline.yml`，并将 `LOCAL_EMBEDDING_MODEL_DIR` 指向完整模型文件目录；目录内不能存在指向挂载范围外的符号链接。override 不自动创建源目录，缺少准备时启动会明确失败。可在联网下载后复用 `hf_cache` volume，但这仍是“联网准备过缓存后离线”，不是无需准备即可运行。

模型、候选池和重排设置变化后应重新记录效果。历史 LangChain 原型的 0.828→0.889 不适用于当前默认模型、重排关闭或重构版；当前自动测试与无 Key 冒烟也不证明模型回答质量。

## JSON fallback

JSON 文件读写没有跨进程锁、原子替换、事务或并发冲突处理。`DocumentService` 的 threading.Lock 只保护同一服务实例中的部分操作，不能保护多个 API 进程或独立 worker；审批 JSON 也不是多进程存储。

因此 JSON 模式只开一个 API worker，索引 inline 执行，不应搭配独立队列 worker 或多个副本。JSON 文件保留可用于演示重启后读取，但不能称为并发安全。目录必须可写且持久化。

## PostgreSQL、队列与文件

Compose 在 API/worker 启动前由一次性 migrate 服务执行 `alembic upgrade head`。上传文件通过 uploads volume 共享，文档与索引任务状态保存在 PostgreSQL；Chroma 的向量数据独立保存在 chroma_data。备份时要同时考虑数据库、文件与向量状态。

当前文档记录、任务记录与 Redis 入队不是一个跨系统原子事务；Redis 队列使用 BLPOP，消息取出后不再留在队列。可捕获的索引错误会重入队，最多 INDEXING_MAX_ATTEMPTS（默认 3）次；worker 在取出消息后崩溃，或入队失败，仍可能留下 pending/running 任务，没有自动在途回收。不能宣称可靠 exactly-once 或任意崩溃自动恢复。

索引前后数据库与 Chroma 也不是原子提交。正式服务需要按问题补充唯一 chunk ID、幂等写入、可靠投递/确认、超时任务回收及一致性修复。

## 健康、就绪与指标

- `/api/health` 表示进程能响应。
- `/api/ready` 的 JSON body 才包含依赖是否可用；目前即使 `status=degraded` HTTP 仍返回 200，不能只看 curl 退出码。model_api 的检查仅检查 Key 是否配置，不发真实模型请求。
- `/api/metrics` 是基础内存指标；多 API worker 各有自己的计数，没有共享聚合，重启会重置。不能从该接口推断完整生产监控。
- `scripts/production_smoke.sh --no-llm` 验证实际上传、worker 索引、公司制度向量查询、审批、鉴权与指标；需要真实 embedding 和 Chroma，但不调用付费 LLM。默认模式另验证真实法律问答。

## 清理和备份

先确认 Compose project 名称；运行时先备份，再停止，例如：

```bash
docker compose -p legal-rag -f docker-compose.prod.yml exec -T postgres pg_dump -U legal_rag legal_rag > backup.sql
docker compose -p legal-rag -f docker-compose.prod.yml down
```

默认 down 保留 volumes。只有确认是可丢弃测试项目时才使用 `down -v`，不可用于保存用户文档的栈。备份恢复演练本轮不作已完成声明。

## 自动检查与依赖

`requirements-ci.in` 列出确定性测试所需的轻量依赖，`requirements-ci.txt` 锁定其完整解析结果。更新命令：`uv pip compile requirements-ci.in --python-version 3.11 -o requirements-ci.txt`。

CI 不安装 PyTorch、模型权重或完整检索依赖，覆盖接口、路由、规则、mock 检索和服务测试；这些检查不能替代真实向量索引集成验证。运行依赖仍在 `requirements.txt`，Chroma client 与 server 固定为 1.5.9，其余运行依赖尚未完全锁定。容器构建后保留 pip freeze 快照，后续升级要复验。

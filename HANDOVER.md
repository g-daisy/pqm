# PQM 项目交接文档

> 交接基准：git HEAD `6a351b9`（2026-11-24），工作区干净。
> 文中行号以该版本为准，后续代码变动请以函数/变量名为准。

---

## 1. 项目概览

**PQM（热压品质异常预测系统）** — 面向制造业的质量检验知识库，两大核心能力：

| 能力 | 说明 | 实现 |
|---|---|---|
| SIP 检验数据查询 | 自然语言 → SQL，查客户/零件/工序的检验标准、方法、频次 | Text2SQL（自研管道） |
| 工序异常知识检索 | 检索热压等工序异常的原因与对策 | RAG（RagFlow + LLM 合成） |

**技术栈**：FastAPI（异步）+ asyncpg 直连 PostgreSQL（无 ORM）+ MiniMax-M2.7（OpenAI 兼容接口）+ RagFlow + Redis + Vue3/Pinia/Vite。

**三种接入方式**：
1. 自建前端（Vue，`frontend/`，Nginx 托管）
2. 标准 REST + SSE：`/api/v1/agent/*`
3. NAP 协议（接入 NoDeskClaw 平台）：根级别 `/health` `/meta` `/stream`，协议见 `agent通信协议.md`

---

## 2. 请求主链路（必读）

所有聊天入口（前端 SSE、`POST /api/v1/agent/query`、NAP `/stream`）最终都汇聚到同一条链路：

```
前端 Chat.vue (fetch SSE)
  → POST /api/v1/agent/stream            app/api/agent.py
  → Task 入队（优先级队列，result_queue 回写）  app/runtime/task.py
  → WorkerPool（4 个 worker 并发消费）         app/runtime/worker.py
      ├─ 从 chat_messages 表加载该会话最近 10 条历史
      ├─ 追加本次用户问题 → agent_loop()          app/agents/loop.py
      │     ReAct while-True 循环，调 MiniMax：
      │     finish_reason == "tool_calls" → 执行工具 → 结果塞回 messages → 继续循环
      │     否则结束，取最后一条 assistant 消息作为答案
      ├─ 本轮 user + assistant 消息持久化到 PostgreSQL
      └─ 结果写入 result_queue → SSE 推给前端
```

**三个注册工具**（`app/main.py` 的 `_register_tools()`）：

| 工具 | 文件 | 作用 |
|---|---|---|
| `query_sip_database` | `app/tools/sql_tool.py` → `app/services/text2sql.py` | NL → SQL 生成 → 校验 → 执行 |
| `search_knowledge_base` | `app/tools/rag_tool.py` → `app/knowledge/retrieval.py` | RAG 检索 + LLM 按 5M1E 合成 |
| `get_database_schema` | `app/tools/schema_tool.py` | 返回表结构 + 同义词映射（进程级缓存） |

**RAG 短路优化**（`loop.py:57-68`）：当一轮只有 `search_knowledge_base` 一次调用且结果有效时，直接把工具结果当作最终回复，省掉最后一次 LLM 综合调用。

---

## 3. 模块地图

```
app/
├── main.py            FastAPI 入口；lifespan 里：建连接池→建聊天表→预热LLM→注册工具→起 WorkerPool
├── core/
│   ├── config.py      pydantic-settings，所有配置从 .env 读
│   └── auth.py        管理员 JWT（登录发 token / Depends 校验）
├── api/               路由层（/api/v1 前缀，NAP 除外）
│   ├── agent.py       流式/同步查询、会话 CRUD、历史
│   ├── nap.py         NAP 协议三接口（根级别，无前缀）
│   ├── auth.py        POST /auth/login → JWT
│   ├── upload.py      Excel 导入 sip_records、PDF 上传 documents/、客户/零件聚合、删除 SIP
│   ├── monitor.py     统计与最近查询（有已知问题，见 §5）
│   └── documents.py   列出 RagFlow 知识库文档
├── runtime/           任务运行时
│   ├── task.py        Task 数据类（优先级、result_queue 回写通道）
│   ├── queue.py       asyncio.PriorityQueue 包装
│   ├── worker.py      WorkerPool：并发消费、加载历史、跑 agent_loop、持久化
│   ├── dispatcher.py  执行 LLM 的 tool_calls，结果 append 进 messages
│   ├── registry.py    工具名 → BaseTool 注册表
│   ├── scheduler.py   APScheduler 包装（apscheduler 未安装，实际禁用，见 §5）
│   └── hooks.py       事件钩子（当前无人使用）
├── agents/loop.py     ★ 核心 ReAct 循环（全项目最关键的 73 行）
├── tools/             3 个 BaseTool 实现；image_analysis.py 是损坏的占位（见 §6）
├── services/text2sql.py  SQL 生成管道（大 prompt 在此文件内）
├── knowledge/
│   ├── retrieval.py   RAG 主流程：缓存→追问改写→RagFlow 检索→LLM 合成→双 key 回写缓存
│   ├── rewrite.py     追问独立化改写（"那对策呢" → 完整问题）
│   └── ragflow_client.py  RagFlow HTTP 客户端（httpx 异步单例）
├── db/
│   ├── connection.py  asyncpg 连接池 + execute/fetch_* 快捷函数（占位符 $1,$2...）
│   ├── sql_validator.py  SQL 安全校验器（白名单机制，见 §4）
│   ├── schema.py      sip_records 表结构定义（供 prompt 用，非 ORM）
│   └── schema_loader.py  字段同义词映射（"硬度标准"→specification 等）
├── memory/
│   ├── persistent_session.py  DB 版会话记忆（chat_sessions/chat_messages 表）★主用
│   └── short_term_memory.py   内存版（遗留，仍被 text2sql/rewrite/monitor 引用 → bug 源头，见 §5）
├── cache/redis_client.py  RAG 问答缓存（sha256 问题为 key，TTL 7 天，Redis 挂了静默降级）
├── models/llm.py      双 LLM 通道（见 §4）
└── utils/logger.py    日志仅写文件 logs/pqm.log，不进终端
```

---

## 4. 关键设计决策及原因

### 4.1 asyncpg 直连，不用 ORM
工业 SQL 复杂（`DISTINCT ON` 去重取最新版本等），且全项目只有一张业务表 `sip_records`。注意占位符是 **`$1, $2`** 不是 `%s`。

### 4.2 双 LLM 通道（重要，改配置前必读）
`.env` 里只有一个 `MiniMax_BASE_URL`（配的是 **anthropic 路径**，如 `https://api.minimaxi.com/anthropic`），两个通道各自转换：

| 通道 | 使用方 | 转换逻辑 | 位置 |
|---|---|---|---|
| AsyncOpenAI | agent_loop（聊天主链路） | `base_url.replace("/anthropic", "/v1")` | `models/llm.py:21` |
| LangChain ChatAnthropic | text2sql / RAG 合成 / 追问改写 | 直接用 `/anthropic` 原样 | `models/llm.py:35-41` |

**坑**：换 provider 时若新 BASE_URL 不含 `/anthropic`，replace 不生效，agent_loop 会打到错误路径。

### 4.3 SQL 安全校验器（`db/sql_validator.py`）
LLM 生成的 SQL 执行前必须通过：只许 SELECT；表白名单仅 `sip_records`；禁 INSERT/UPDATE/DELETE/DROP 等；禁分号多语句、注释、UNION、`SLEEP()`；LIMIT ≤ 100。这是防注入和防跑飞的第二道闸（prompt 约束是第一道）。

### 4.4 字段同义词映射（`db/schema_loader.py`）
用户说"硬度标准"→ `specification`，"AQL"→ `inspection_frequency`。映射表注入 SQL 生成 prompt。**改表字段时必须同步改这里**。

### 4.5 RAG 双 key 缓存
`knowledge/retrieval.py`：原始问题命中缓存则完全跳过改写和检索；未命中则改写后检索，结果**同时以原问题和改写问题两个 key 写入**，保证两种问法下次都能命中。追问改写有启发式判断（短问题/以"那"开头/含"对策"等才调 LLM 改写）。

### 4.6 SQL 生成 prompt 的领域规则（`services/text2sql.py`）
- 工序名映射：来料/IQC→`'来料'`、出货/OQC→`'出货'` 等 8 条
- 去重规则：问"标准/要求"时必须 `DISTINCT ON (customer, part_name, process, inspection_item) ... ORDER BY ... version DESC`，同项只返回最新版本
- 必须带 `document_id` 用于拼 PDF 链接（`documents/{document_id}.pdf`，前端可下载）

---

## 5. 已知问题清单（接手后优先看）

以下问题均已确认存在，按影响排序：

### P1-1 两套会话记忆未接通（追问改写和 SQL 上下文实际失效）
- **现象**：用户追问"那对策呢"不会被改写成完整问题；SQL 生成没有对话上下文。
- **原因**：`services/text2sql.py:142` 和 `knowledge/rewrite.py:35` 读的是**内存版** `session_memory`（`memory/short_term_memory.py`），但 `runtime/worker.py:94-96` 只把消息写进 **DB 版** `persistent_session`。内存版在聊天链路里永远是空的。
- **修法**：把这两处 import 换成 `app.memory.persistent_session` 的单例（接口同名，`get_context_for_llm` 直接可用，但它返回的是格式化字符串——注意 persistent 版的 `get_context_for_llm` 需要改成 async 或预取；建议统一收敛到 DB 版并加 `await`）。

### P1-2 `agent_loop` 全局变量跨会话污染
- **现象**：进程运行一段时间后，**所有用户**每次请求都会收到一条无意义提醒，且浪费一轮 LLM 调用。
- **原因**：`agents/loop.py:22` 的 `_rounds_since_todo` 是模块级全局变量；配套的 `todo_write` 工具**从未注册**，计数器永不归零；`loop.py:32-34` 在计数 ≥3 后给**每个请求**注入 "请更新你的进度追踪" 提醒。
- **修法**：直接删掉整个 reminder 机制（约 22、31-34、70-72 行），或把计数移入 `agent_loop` 局部。

### P2-3 前端调用了不存在的后端接口
- `frontend/src/api/chat.js:12-17` 的 `cancel()`/`resume()` → 后端无 `/agent/cancel/{id}`、`/agent/resume/{id}` 路由：
  - "⏸ 停止"按钮只做了前端 abort，**后端任务照跑完**（LLM 照常计费）；
  - "▶ 继续上次"按钮必然 404。
- SSE `done` 事件里前端期望的 `pdf_urls`、`thinking` 事件后端均不回传 → 聊天区 PDF 附件链接永远不显示。
- **修法**：要么补后端两个路由（需要在 Task/WorkerPool 里加取消机制），要么删前端死按钮。`pdf_urls` 可在 `worker.py` 组装 done 事件时从最后一条 tool 消息里提取。

### P2-4 上传接口无鉴权
- `POST /api/v1/upload/excel`（写数据库）、`POST /api/v1/upload/pdf`（写磁盘）无任何认证；而 `DELETE /upload/sip/{id}` 反而有 JWT。**生产环境任何人可篡改检验数据**。
- **修法**：两个端点加 `dependencies=[Depends(verify_admin_token)]`（照抄同文件 322 行删除接口的写法）。

### P2-5 监控页数据源错位
- `api/monitor.py:2` 用内存版 session_memory → 会话数、最近查询恒为 0。`increment_query_count` 是进程内变量，重启清零、多 worker 不共享。
- **修法**：改读 `chat_sessions` 表（照 `persistent_session.list_sessions` 的写法）。

### P3-6 文档与事实不符
- `README.md` 整体过时：还在写 MySQL/aiomysql/LangGraph Coordinator+Critic 多 Agent，实际是 PostgreSQL/asyncpg + 单 ReAct 循环 + WorkerPool。本文档接管其职责。
- `main.py:109-114` FastAPI description 还写着 "aiomysql / MySQL 8"。

### P3-7 安全/健壮性次要点
- `Chat.vue:200` 用 `v-html` 渲染 LLM 输出，无 XSS 净化（内网风险可控，公网需加 DOMPurify）。
- CORS `allow_origins=["*"]`（`main.py:124`），配合无鉴权上传是组合风险。
- JWT `SECRET_KEY` 为空时 jose 会抛异常——`.env` 必须配（见 §7）。

### P3-8 死代码清单（可安全删除或明确搁置）
| 位置 | 状态 |
|---|---|
| `runtime/hooks.py` | 无人调用 |
| `runtime/scheduler.py` | 依赖 apscheduler，**requirements.txt 里没有**，启动时 ImportError 兜底禁用 |
| `tools/image_analysis.py` | 占位，`from base import BaseTool` import 路径是错的，且未注册 |
| `knowledge/ragflow_client.py:121-166` 的 `@tool rag_tool` | LangChain 旧版工具，现链路不用（用的是 `tools/rag_tool.py` 的 BaseTool 版） |
| `app/graphs/`、`app/core/pqm_graph` 残留 pyc | 旧 LangGraph 架构遗物，源码已删 |
| `runtime/worker.py` 的 `TaskResult` | 定义未使用 |

---

## 6. 未完成工作（原计划）

1. **图片缺陷识别**：`tools/image_analysis.py` 是占位，规划是"识别用户上传图片中的缺陷类型"，run() 为空。前端也没有上传图片入口。
2. **取消/恢复机制**：见 P2-3。
3. **记忆系统统一**：见 P1-1，建议顺手把 `short_term_memory.py` 整个移除。
4. **定时任务**：Scheduler 骨架在但未启用，如需"每日自动巡检"类需求要先补 apscheduler 依赖。

---

## 7. 环境搭建

### 7.1 `.env` 变量清单（与 `core/config.py` 一一对应）

| 分组 | 变量 | 必填 | 默认/说明 |
|---|---|---|---|
| 应用 | `APP_NAME` / `APP_VERSION` / `DEBUG` / `API_PREFIX` | 否 | API_PREFIX=`/api/v1` |
| 数据库 | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | **是** | PORT 默认 5432（PostgreSQL） |
| 连接池 | `DB_POOL_SIZE` 等 4 项 | 否 | 池 10 |
| LLM | `MiniMax_API_KEY` | **是** | |
| LLM | `MiniMax_BASE_URL` | **是** | 注意 §4.2 的 `/anthropic` 路径约定 |
| LLM | `MiniMax_MODEL` | 否 | 默认 `MiniMax-M2.7` |
| RagFlow | `RAGFLOW_BASE_URL` / `RAGFLOW_API_KEY` / `RAGFLOW_DATASET_ID` | RAG 功能必填 | 不配则 RAG 检索报错但不影响 SQL 问答 |
| Redis | `REDIS_URL` | 本地开发注意 | 默认 `redis://redis:6379/0` 是 **docker 服务名**，本地跑要改 `localhost:6379`；不配也能跑（缓存静默降级，见 §4.5） |
| Redis | `REDIS_CACHE_TTL` | 否 | 默认 604800（7 天） |
| 管理员 | `ADMIN_USERNAME` / `ADMIN_PASSWORD` | **是**（登录用） | USERNAME 默认 admin |
| JWT | `SECRET_KEY` | **是** | 不配则登录直接报错 |
| JWT | `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES` | 否 | HS256 / 480 分钟 |

### 7.2 本地开发（Windows）

```bash
# 依赖装进现有 venv（项目根有 .venv/，Python 3.13）
pip install -r requirements.txt

# 需要先起 PostgreSQL（和可选 Redis），再：
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API 文档: http://localhost:8000/api/v1/docs

# 前端（端口 8080，已配代理转发 /api 和 /documents 到 8000）
cd frontend && npm install && npm run dev
```

启动自检项（logs/pqm.log 中应看到）：
`Chat tables ready` → `正在预热 LLM 连接...` → `LLM 预热完成`（失败仅 warning，不阻断启动）→ `Registered tools` → `WorkerPool started with concurrency=4`。

### 7.3 Docker 部署

```bash
docker compose build && docker compose up -d
# 四个服务: postgres(15) / redis(6) / backend / frontend(nginx)
```

- `scripts/init_db.sql` 通过挂载到 `docker-entrypoint-initdb.d` **仅在数据卷首次创建时**自动执行；`init_chat_tables.sql` 由后端每次启动执行（幂等）。
- 前端页面：宿主机 80 端口。

---

## 8. 部署坑点（重要）

### 8.1 pip_wheels 离线装包机制
`Dockerfile` 用 `pip install --no-index --find-links=/tmp/pip_wheels` **完全离线**安装。**新增任何依赖后必须先补 wheel 再 build**，否则镜像构建直接失败：

```bash
# 在有网的 Windows 机器上交叉下载 Linux wheel（含全部传递依赖）
pip download "新包名>=x,<y" --dest pip_wheels \
  --platform manylinux_2_28_x86_64 --python-version 3.11 --only-binary :all:
```

基础镜像 `python:3.11-slim`（Debian bookworm，glibc 2.36），manylinux_2_28 wheel 兼容。若某包没有 Linux 预编译 wheel（需源码编译），离线机制装不上，要换包或改走在线安装。

### 8.2 DNS 配置别删
`docker-compose.yml` 的 backend 服务配了 `dns: [223.5.5.5, 8.8.8.8]` —— 这是修复"LLM 访问超时"的（commit `c80d7f9`），默认 DNS 转发在该网络环境有问题。网络架构变更前不要移除。

### 8.3 Nginx 端口矛盾（当前未修复）
`frontend/nginx.conf` 监听 **4080**，但 `docker-compose.yml` 映射的是 `"80:80"` → 宿主机 80 → 容器 80 **无人监听**。二选一修复：
- 改 `nginx.conf`: `listen 80;`
- 或改映射：`"80:4080"`

在该问题修复前，若线上前端可访问，说明实际部署与仓库配置有出入，先 `docker compose ps` + `docker compose exec frontend cat /etc/nginx/conf.d/default.conf` 核实线上真实配置。

### 8.4 SSE 相关超时链
后端等待答案 120s（`api/agent.py` 和 `nap.py` 的 `wait_for`）< nginx `proxy_read_timeout` 180s（`/api/`）与 300s（`/stream`）。nginx 侧已关 buffering（SSE 必需）。改任何一端注意保持这个大小关系。

---

## 9. 数据操作

### 9.1 Excel 导入（结构化数据 → sip_records）
前端 `/upload` 页面（需管理员登录）或 `POST /api/v1/upload/excel`。
- **12 列顺序固定**：项目号 | 客户 | 文件号 | 零件号 | 零件名称 | 工序 | 模具号 | 检验项 | 规范或描述 | 检验方法 | 检查频次 | 版本号
- 必填：project、customer、document_id、part_num、part_name、inspection_item、version
- 去重键：`(document_id, inspection_item)` —— 重复导入是 UPDATE 不是新增
- 逐行 upsert，返回新增/更新/跳过明细；单行失败不影响其他行

### 9.2 PDF 上传（原文件 → documents/）
- 后端尝试三级文件号提取（`upload.py` 的 `_extract_document_id`）：①"文件号"标签 → ② `XXX-SIP-XXX-NNN` 格式 → ③ 宽松大写连字符格式
- 提取失败返回 **422** + 前 200 字文本片段，前端展示手动输入框重试
- 保存为 `documents/{文件号}.pdf`；**文件号必须与 sip_records.document_id 一致**才能在前端/问答里出 PDF 链接

### 9.3 删除 SIP（危险操作，需 JWT）
```bash
# 1. 登录拿 token（账号密码来自 .env 的 ADMIN_USERNAME/ADMIN_PASSWORD）
TOKEN=$(curl -s -X POST http://localhost:80/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<密码>"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. 删除（连带删 sip_records 所有行 + documents/ 下 PDF，不可逆）
curl -X DELETE "http://localhost:80/api/v1/upload/sip/<文件号>" -H "Authorization: Bearer $TOKEN"
```

---

## 10. 日常运维

| 事项 | 说明 |
|---|---|
| 日志 | `logs/pqm.log`，10MB×5 个轮转，**仅写文件不进终端**；docker 已挂载 `./logs:/app/logs`。排障第一入口。 |
| 健康检查 | `GET /health` → `{"status":"ok",...}`（NAP 平台以此判活，status 字段不能改） |
| LLM 预热 | 启动时发一条 "."，失败仅 warning（首条真实请求会变慢） |
| RAG 缓存 | Redis key 前缀 `pqm:rag:`，TTL 7 天。**知识库文档更新后记得清这批 key**，否则旧答案最长缓存 7 天。Redis 不可用时自动降级为无缓存，不影响功能。 |
| 知识库文档管理 | RagFlow 侧操作（`/api/v1/documents` 只读列出）；`documents/` 目录是 SIP 原件，docker 挂载持久化 |
| 会话清理 | `DELETE /api/v1/agent/history/{session_id}`（外键级联删消息） |
| 监控页 | `/monitor`，当前统计有 bug（§5 P2-5），数字不可信 |

---

## 11. 故障排查速查

| 症状 | 排查方向 |
|---|---|
| LLM 请求超时/预热失败 | 先查网络代理；docker 里查 DNS 配置是否还在（§8.2）；`MiniMax_BASE_URL` 路径约定（§4.2） |
| 回答里说"无法生成有效 SQL" | LLM 输出的 SQL 被校验器拦了：对照 §4.3 规则；多半是字段名幻觉或用了 JOIN/其他表 |
| 回答说"RAG 检索失败" | RagFlow 三项配置、RagFlow 服务本身、`RAGFLOW_DATASET_ID` 是否有效 |
| 回答说"未找到相关文档" | RagFlow 里没有该内容，或追问改写后的问题偏离（日志里搜 `Query rewrite`） |
| PDF 链接不出现在回答里 | `documents/{document_id}.pdf` 文件是否存在——Excel 数据和 PDF 是**两个独立上传**，都要传 |
| 前端流式无响应 | nginx buffering 是否被改动（必须 off）；`X-Accel-Buffering` 头 |
| 登录 500 | `.env` 的 `SECRET_KEY` 未配置 |
| 会话历史丢失 | 查 `chat_sessions`/`chat_messages` 表；删除接口是级联删 |

---

## 12. 目录杂项与清理建议

| 项 | 说明 | 建议 |
|---|---|---|
| `C：/`（根目录，全角冒号名） | 空目录，7 月误建，已被 git 忽略 | 可删 |
| `data/image/` | 仅一个空 image 目录 | 确认无用后删 |
| `openapi.json`（根目录） | 8 月导出的 API 快照，已过期 | 建议删，要最新就访问 `/api/v1/openapi.json` |
| `pip_wheels/` | 离线 wheel 缓存，**部署必需** | 保留，git 已忽略 |
| `documents/` | SIP PDF 原件 41 份，docker 挂载 | 保留；git 忽略（.gitignore 里 `*documents` 这行写法很怪，它同时忽略一切以 documents 结尾的名字，建议改成 `/documents/`） |
| `agent通信协议.md` | NAP 协议规范（NoDeskClaw 平台对接） | 保留 |
| `PQM架构图.svg` | 曾在工作区，现已删除 | 无需处理 |

---

## 13. 关键 git 历史速览

| commit | 内容 |
|---|---|
| `6a351b9` | RAG 缓存/改写流程梳理（retrieval.py 双 key 缓存、rewrite.py 注释修正） |
| `c0d3a3d` | （小改动） |
| `c80d7f9` | **DNS 转发修复**（LLM 访问超时）→ docker-compose dns 配置来源 |
| `d21291e` | **大重构**：LangGraph 多 Agent（Coordinator/Critic）→ 单 ReAct agent_loop + WorkerPool；MySQL/aiomysql → PostgreSQL/asyncpg。旧架构残留见 §5 P3-8 |
| `7648a32` | 启动时 LLM 预热 |

---

*交接文档生成于 2026-11-24，基于代码通读 + 实际核查。发现文档与代码不一致时，以代码为准并回改本文档。*

# AIOps 日志故障调查与工单辅助 Agent

这是一个可以本地复现的 Agent 工程：输入 OpenStack 虚拟机实例 ID，可选请求 ID（`req-<UUID>`）。
省略请求 ID 时按日志时间选择该实例最新的有效请求，指定后则严格使用指定请求。
Agent 在解析后固定的操作范围内调用日志工具，跨日志分区重建时间线、提出候选故障假设、
核对同一请求的成功事件、校验日志引用，最后输出一份必须由人工确认的工单草稿。

项目使用公开的 Loghub OpenStack 数据。它不是自动修复系统，也不会把公开数据的“异常实例标签”
夸大成逐行根因标签。

## 项目包含什么

- **Agent Harness**：统一驱动“决策—工具—观察”循环，限制最大步骤、总超时、单工具超时、
  重试、重复调用和工具白名单，并保存 JSONL Trace。
- **Skills**：把日志分诊、证据核验、报告生成写成三个可复用的工作方法；离线策略和 LLM
  策略加载同一组 Skill。
- **工具与 MCP 封装**：Agent 内部默认直接调用同进程 Tool Registry，避免每次启动 MCP 子进程。
  LLM 使用模型原生 Function Calling 选择工具，Harness 校验白名单及固定的实例/请求范围后执行。
  MCP Server 供外部客户端使用；配置切为 `mcp` 时，内部先发现工具 Schema，再复用一个 stdio 会话调用同一套实现。
  工单写入工具不在 Agent Harness 白名单内，外部调用者必须显式传入 `approved=true`。
- **双运行模式**：`heuristic` 不需要 API Key，可稳定演示和作为基线；`llm` 支持任何兼容
  OpenAI Chat Completions 的模型服务。LLM 模式强制先检索日志和 Runbook，再生成报告。
- **可溯源 RAG**：将 Markdown Runbook 按检查项切块，用 BM25 排序，检索片段及来源进入模型上下文；
  报告分别列出经过校验的日志引用和 Runbook 指南引用。后者只用于建议，不作为故障发生的证据。
- **上下文与长期记忆**：LLM 只接收有长度上限的当前摘要、重点事件、有效引用和检索片段；
  显式批准的工单草稿以 JSONB 写入 PostgreSQL，只读取相同实例/请求最近两条历史记录，且不作为当前证据。
- **可复现评测**：评测器单独读取实例标签，逐请求调查后聚合为实例结果；不存在请求级金标，旧实例级指标不能直接沿用。原始引用仍含分区名，因此小规模冒烟评测并非严格盲测。
- **可观测接口**：CLI、FastAPI 和 MCP 共用同一个工具注册模块，不复制业务逻辑。

## 一次任务如何运行

```text
告警/实例 ID + 可选请求 ID
    │
    ▼
入口解析范围（指定请求 / 按日志时间选择最新有效请求）
    │
    ▼
Agent Policy（LLM 原生 Function Calling / 无 Key 规则基线）──加载──> Skill 工作方法
    │
    ▼
Harness（锁定实例/请求范围、步数、超时、重试、循环熔断、白名单、Trace）
    │
    ▼
本地 Tool Registry（默认） / MCP Client → MCP Server（可选）
    │
    ├── PostgreSQL 日志索引（只读查询）
    ├── Runbook 检索
    ├── 引用校验
    └── PostgreSQL 已批准工单记忆
    │
    ▼
带证据与反证的调查报告
```

`Harness` 不是需要单独下载的神秘框架，而是本项目自己实现的 Agent 运行底座。它不负责判断业务
结论，负责保证 Agent 在规定权限和预算内运行。`Skill` 是可加载的工作流程知识；`MCP` 是让本项目
Agent 和其他客户端发现、调用工具的协议。这三者的职责互不替代。

LLM 模式的 RAG 链路为：实例摘要与时间线检索 → Runbook 检查项检索 → 日志引用校验 →
将检索片段交给模型生成报告 → 核对报告引用确实来自本次检索。Runbook 目前只有 3 份短文档，
因此使用本地 BM25 分块检索即可；向量数据库、Embedding 和重排会增加依赖与维护成本，
当前数据规模下没有足够收益。`heuristic` 模式保留为无 Key 的规则对照，不应与 LLM RAG 效果混称。

## 快速开始（Windows PowerShell）

```powershell
cd D:\yolo\rag\aiops-incident-investigation-agent
docker compose up -d postgres
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[all]"

# 若 data/raw 已有四个文件，可跳过下载
.\scripts\download_data.ps1

# 把约 20.8 万行日志导入 PostgreSQL 并建立索引
incident-agent prepare

# 不使用任何模型 API 的完整演示
# 不填请求 ID：调查该实例最新一次请求
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc

# 指定请求 ID：调查这一次虚拟机构建
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc req-d6143bd4-9784-4e95-a0c8-83fba00530b6

# 小规模、标签隔离的评测
incident-agent evaluate

# 测试
pytest -q
```

默认开发连接为 `postgresql://incident:incident_dev_password@127.0.0.1:55432/incident_agent`，
仅供本机演示。实际部署请修改数据库密码，并通过 `AGENT_DATABASE_URL` 环境变量注入连接串；
不要将真实密码提交到仓库。`prepare` 重复运行会复用已有完整索引；仅在需要重建时使用
`incident-agent prepare --force`。原来的 `data/processed/*.db` 文件不会被读取，数据会从
`data/raw/` 重新导入 PostgreSQL。

升级后运行一次 `incident-agent prepare` 即可为已有日志表补建
`(instance_id, request_id, timestamp, dataset, line_no)` 联合索引；无需 `--force` 或重新导入数据。
指定的两个 ID 必须来自同一次操作。请求 ID 可从该实例日志中的 `req-...` 取得，输入格式错误会被拒绝。
“最新”按这个实例各请求最后一条有效时间戳倒序选择，时间相同时按请求 ID 稳定排序；
不是按当前日期，也不保证最新请求就是创建请求（它也可能是删除、重启等）。想复现构建异常时请明确指定构建请求。
没有有效时间戳和请求 ID 时返回范围无法确定的错误，不会退回查询整个实例历史。

Agent 内部默认使用 `AGENT_TOOL_TRANSPORT=local`：从 Tool Registry 读取工具 Schema，筛选白名单后
提供给模型，模型仍通过原生 Function Calling 选择工具；同步执行通过工作线程避免占住异步线程。
同进程无需工具服务隔离时，这条路径省去 stdio 子进程启动、序列化和通信往返，但实际延迟收益尚未测量。
需要通过独立工具服务运行时可设 `AGENT_TOOL_TRANSPORT=mcp`：每次调查启动一个 stdio MCP Server，
初始化后通过 `list_tools` 发现定义，复用会话并通过 `call_tool` 执行，结束时关闭。
两条路径共用业务实现和 Harness 范围护栏，模型均接收所选路径的工具 Schema。
FastAPI 接收业务调查请求；MCP 对接外部 AI 工具客户端。

如果只使用 Docker，也可以在下载数据后运行：

```powershell
docker compose up -d postgres
docker compose run --rm incident-api incident-agent prepare
docker compose up -d incident-api
```

本次创建项目时已经下载并校验数据；归档 MD5 为
`66bd42c07837a094d9b0ea2d036b5713`。原始日志被 `.gitignore` 排除，不应上传到 GitHub。

## 使用大模型模式

复制 `.env.example` 中需要的变量到当前终端或安全的环境配置中，不要把 Key 写入代码：

```powershell
$env:AGENT_MODEL_MODE = "llm"
$env:AGENT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:AGENT_API_KEY = "你的 Key"
$env:AGENT_MODEL = "qwen-plus"
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc req-d6143bd4-9784-4e95-a0c8-83fba00530b6 --mode llm
```

LLM 只能选择 Harness 白名单中的只读工具。模型返回格式错误、工具失败、超时或陷入重复调用时，
Harness 会记录 Trace 并返回稳定的失败状态，而不是无限循环。
模型漏传/改换任一 ID 的工具调用会被 Harness 阻止。报告若引用未经校验或不属于该请求的日志、
未检索到的 Runbook 片段，或取消人工复核，也会被拒绝；反证引用也必须经过相同的范围校验。
每次运行的完整工具轨迹仍保留在 JSONL Trace 中；缩短模型上下文不会删除审计记录。

上下文分两层：本次调查的工具观察保留在 Harness 中，交给 LLM 前由 ContextManager 按约
12,000 字符预算筛选实例摘要、异常/首尾事件、近两次日志搜索、已校验引用和 Runbook 片段；
历史层只查询 PostgreSQL `approved_case_memory` 中相同实例和请求、最近两条已批准记录。
该表的 `report` 为 JSONB，并对 `(instance_id, request_id, approved_at DESC)` 建索引。历史仅供参考，
当次结论仍必须由当次日志引用支持；评测标签不会进入上下文。旧的本地 JSON 草稿不再用于记忆。
记忆表在首次读写时自动补建 `request_id` 列和新索引；旧记录保留，但未关联请求的旧记录不进入当前上下文。

## 启动 FastAPI

```powershell
uvicorn incident_agent.api:app --reload --port 8000
```

接口：

- `GET /health`
- `POST /v1/investigations`
- Swagger：`http://127.0.0.1:8000/docs`

请求示例：

```json
{
  "instance_id": "544fd51c-4edc-4780-baae-ba1d80a0acfc",
  "request_id": "req-d6143bd4-9784-4e95-a0c8-83fba00530b6",
  "mode": "heuristic"
}
```

也可省略 `request_id`（或传 `null`），自动调查该实例最新的有效请求：

```json
{"instance_id": "544fd51c-4edc-4780-baae-ba1d80a0acfc", "mode": "heuristic"}
```

入口先解析并锁定请求，再按 `instance_id AND request_id` 搜索全部已索引分区；报告包含实际使用的两个 ID，`dataset` 字段为 `all`，
而每条证据仍使用原始的 `分区:行号`（例如 `abnormal:11983`）定位日志。
匹配不到这对 ID 时报告为 `uncertain`，不会放宽为实例全部历史，也不会凭空判断故障。
没有请求 ID 的日志不会自动归入该请求，可能导致缺少耗时或完成事件；报告会保留这个限制。
时间线按限额保留同一请求的首尾事件，可能省略中间过程，可由模型通过同范围日志搜索补查。
这不是额外的“最近 24 小时”过滤；范围由请求 ID 确定，跨服务本地请求 ID 不同的情况仍需显式关联。

## 启动 MCP Server

```powershell
incident-mcp
```

这是供外部 MCP 客户端使用的 stdio Server，也可在内部启用 `mcp` 模式。客户端配置示例：

```json
{
  "mcpServers": {
    "openstack-incidents": {
      "command": "D:\\yolo\\rag\\aiops-incident-investigation-agent\\.venv\\Scripts\\incident-mcp.exe"
    }
  }
}
```

提供的工具：

- `get_instance_summary`
- `search_logs`
- `get_timeline`
- `search_runbooks`
- `get_case_memory`
- `validate_evidence`
- `save_ticket_draft`

评测标签没有注册为工具，因此 Agent 无法在运行时偷看答案。

日志、时间线、记忆和证据核验工具均要求 `instance_id` 与 `request_id`。Runbook 是通用指南，
其检索无需两个 ID；工单保存从报告中读取并验证两个 ID。
`get_case_memory` 只读取 PostgreSQL 中相同实例/请求已批准的工单记录；普通调查不会自动写入。
命令行的 `--approve-ticket` 或外部 MCP 调用的显式 `approved=true` 才会写入。
当前批准标记只是操作门槛，不是企业身份认证；正式接入生产流程仍需身份校验和审批审计。

## 评测口径

默认评测包含 4 个官方异常实例和从 `normal2` 抽取的 50 个正常实例；`normal1` 只用于建立
正常构建耗时基线，避免让同一批正常样本同时参与阈值校准和测试。评测输出：

- Precision、Recall、F1：枚举每个实例的请求分别调查，任一请求判异常则标记该实例，按实例标签评分；
- Evidence validity：证据与反证引用是否真实存在，并同时对应当前实例和请求；
- Completion rate、平均步骤数和延迟：以单次请求调查为单位；另列实例完成率和请求覆盖率。

标签只有实例级，没有请求级或逐行根因金标。没有请求标记的实例列为未覆盖/不确定，而非正常。
新结果另存 `evaluation-request-scoped-<mode>.json`，旧的 `evaluation-<mode>.json` 仅作历史记录。
本次接口升级没有重跑评测；`docs/BAD_CASE_REPORT.md` 中旧版数值不代表请求级版本效果。

这只是工程冒烟评测，样本很少，不能据此宣称生产准确率或根因诊断准确率。要形成可用于简历的
正式指标，应冻结更大的实例级测试集，人工标注“证据是否支持结论”，并至少重复运行 LLM 模式
三次，报告均值、标准差、成本和 Bad Case 分类。

评测结果保存在 `artifacts/evaluations/`，运行轨迹保存在 `artifacts/traces/`。

## 失败与安全边界

- 调查按实例 ID 与请求 ID 联合过滤，跨三个已索引分区查询，单次最多返回 100 条日志；
- Harness 限制最大 8 步、总耗时 45 秒、单工具 8 秒；
- 同一个工具和参数重复超过阈值会熔断；
- 工具错误进行有限指数退避重试；
- 证据与反证要求 `dataset:line` 引用，并在结束前核验实例及请求归属；
- 工单草稿默认拒绝落盘，必须由调用者显式批准；
- 项目不执行重启、扩缩容、网络修改等生产操作。

## 数据来源与许可

数据来自 [Loghub](https://github.com/logpai/loghub) 的
[OpenStack 数据集](https://github.com/logpai/loghub/tree/master/OpenStack)，归档发布于
[Zenodo](https://zenodo.org/records/3227177)。官方说明数据包含正常日志和故障注入场景；
`anomaly_labels.txt` 只列出 4 个异常 VM 实例。Loghub 数据仅明确允许研究/学术用途并要求引用，
许可全文见 `data/LICENSE-LOGHUB.txt`。

项目代码采用 MIT License；代码许可不改变数据集自身的使用条件。

## 目录结构

```text
src/incident_agent/
  application.py   # 依赖装配的唯一入口
  harness.py       # Agent 运行、护栏、重试和 Trace
  policies.py      # 离线策略与 OpenAI-compatible LLM 策略
  tools.py         # 所有调用方式共用的工具注册模块
  logstore.py      # 日志解析、PostgreSQL 索引和受限查询
  mcp_client.py    # Agent 内部复用的 stdio MCP 客户端
  mcp_server.py    # MCP 工具服务
  memory.py        # PostgreSQL 已批准工单记忆
  api.py           # FastAPI adapter
  evaluation.py    # 标签隔离的评测器
skills/            # 三个可加载 Skill
knowledge/         # Runbook 知识
tests/             # Parser、工具、Harness、Skill 测试
data/              # 原始数据和数据说明（数据库由 Docker Volume 保存）
artifacts/         # Trace、评测结果；已批准工单存 PostgreSQL
```

## 本项目真正实现的部分

公开数据只提供日志和异常实例标签。本项目实现的是日志解析与索引、Agent Harness、Skill 加载、
工具权限控制、MCP/FastAPI adapters、证据校验、人工审批门、评测与 Trace。面试时应把公开数据来源
和自己的实现分别说明，不把数据集或第三方 SDK 当成自己的代码。

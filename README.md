# AIOps 日志故障调查与工单辅助 Agent

这是一个可以本地复现的 Agent 工程：输入 OpenStack 虚拟机实例 ID，Agent 受限调用日志工具，
跨所有日志分区重建时间线、提出候选故障假设、主动查找反证、校验日志引用，最后输出一份必须由人工确认的工单草稿。

项目使用公开的 Loghub OpenStack 数据。它不是自动修复系统，也不会把公开数据的“异常实例标签”
夸大成逐行根因标签。

## 项目包含什么

- **Agent Harness**：统一驱动“决策—工具—观察”循环，限制最大步骤、总超时、单工具超时、
  重试、重复调用和工具白名单，并保存 JSONL Trace。
- **Skills**：把日志分诊、证据核验、报告生成写成三个可复用的工作方法；离线策略和 LLM
  策略加载同一组 Skill。
- **MCP 工具封装**：Agent 默认在一次调查中复用一个 stdio MCP 会话，先发现工具及参数 Schema，
  再通过 MCP 调用日志查询、时间线、Runbook 检索、历史记忆和证据校验。LLM 使用模型原生
  Function Calling 选择下一项工具，Harness 校验白名单后执行。同一 MCP 服务也能供外部客户端使用。
  工单写入工具不在 Agent Harness 白名单内，外部调用者必须显式传入 `approved=true`。
- **双运行模式**：`heuristic` 不需要 API Key，可稳定演示和作为基线；`llm` 支持任何兼容
  OpenAI Chat Completions 的模型服务。LLM 模式强制先检索日志和 Runbook，再生成报告。
- **可溯源 RAG**：将 Markdown Runbook 按检查项切块，用 BM25 排序，检索片段及来源进入模型上下文；
  报告分别列出经过校验的日志引用和 Runbook 指南引用。后者只用于建议，不作为故障发生的证据。
- **上下文与长期记忆**：LLM 只接收有长度上限的当前摘要、重点事件、有效引用和检索片段；
  显式批准的工单草稿以 JSONB 写入 PostgreSQL，按实例 ID 读取最近两条历史记录，且不作为当前证据。
- **可复现评测**：评测器单独读取标签文件；调查入口只需实例 ID，不向 Agent 提供待查分区。原始引用仍含分区名，因此小规模冒烟评测并非严格盲测。
- **可观测接口**：CLI、FastAPI 和 MCP 共用同一个工具注册模块，不复制业务逻辑。

## 一次任务如何运行

```text
告警/实例 ID
    │
    ▼
Agent Policy（LLM 原生 Function Calling / 无 Key 规则基线）──加载──> Skill 工作方法
    │
    ▼
Harness（步数、超时、重试、循环熔断、白名单、Trace）
    │
    ▼
MCP Client（发现工具 Schema、每次调查复用一个 stdio 会话；可切本地模式排障）
    │
    ▼
MCP Server ──> Tool Registry（工具实现也由 FastAPI 复用）
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
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc

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

Agent 内部默认使用 `AGENT_TOOL_TRANSPORT=mcp`：每次调查启动一个 stdio MCP Server，初始化后
通过 `list_tools` 取得工具定义，只将 Harness 白名单内的工具 Schema 提供给模型；模型通过原生
Function Calling 选择工具，Harness 再通过 MCP `call_tool` 执行。一次调查复用会话，结束时关闭。
排查 MCP 连通性问题时可临时设为 `local`，此时 Harness 直接调用同一套 Tool Registry；
这不是默认业务链路。FastAPI 的职责不同：它接收前端或业务系统提交的调查请求，并返回调查结果，
不是供模型发现和调用工具的接口。

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
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc --mode llm
```

LLM 只能选择 Harness 白名单中的只读工具。模型返回格式错误、工具失败、超时或陷入重复调用时，
Harness 会记录 Trace 并返回稳定的失败状态，而不是无限循环。
模型报告若引用未经校验的日志、未检索到的 Runbook 片段，或取消人工复核，也会被拒绝。
每次运行的完整工具轨迹仍保留在 JSONL Trace 中；缩短模型上下文不会删除审计记录。

上下文分两层：本次调查的工具观察保留在 Harness 中，交给 LLM 前由 ContextManager 按约
12,000 字符预算筛选实例摘要、异常/首尾事件、近两次日志搜索、已校验引用和 Runbook 片段；
历史层只查询 PostgreSQL `approved_case_memory` 中相同实例、最近两条已批准记录。
该表的 `report` 为 JSONB，并对 `(instance_id, approved_at DESC)` 建索引。历史仅供参考，
当次结论仍必须由当次日志引用支持；评测标签不会进入上下文。旧的本地 JSON 草稿不再用于记忆。

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
  "mode": "heuristic"
}
```

调查入口会按实例 ID 搜索全部已索引分区；报告的 `dataset` 字段为 `all`，
而每条证据仍使用原始的 `分区:行号`（例如 `abnormal:11983`）定位日志。
如果没有匹配记录，报告会标记为 `uncertain`，不会凭空判断故障。

## 启动 MCP Server

```powershell
incident-mcp
```

这是 Agent 内部默认使用的 stdio MCP Server，也可供其他 MCP 客户端启动。客户端配置示例：

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

`get_case_memory` 只按实例 ID 读取 PostgreSQL 中已批准的工单记录；普通调查不会自动写入。
命令行的 `--approve-ticket` 或外部 MCP 调用的显式 `approved=true` 才会写入。
当前批准标记只是操作门槛，不是企业身份认证；正式接入生产流程仍需身份校验和审批审计。

## 评测口径

默认评测包含 4 个官方异常实例和从 `normal2` 抽取的 50 个正常实例；`normal1` 只用于建立
正常构建耗时基线，避免让同一批正常样本同时参与阈值校准和测试。评测输出：

- Precision、Recall、F1：只衡量“实例是否异常”；
- Evidence validity：报告引用是否真实存在并对应当前实例；
- Completion rate：Harness 是否正常结束；
- 平均步骤数和延迟。

这只是工程冒烟评测，样本很少，不能据此宣称生产准确率或根因诊断准确率。要形成可用于简历的
正式指标，应冻结更大的实例级测试集，人工标注“证据是否支持结论”，并至少重复运行 LLM 模式
三次，报告均值、标准差、成本和 Bad Case 分类。

评测结果保存在 `artifacts/evaluations/`，运行轨迹保存在 `artifacts/traces/`。

## 失败与安全边界

- 调查按实例 ID 跨三个已索引分区查询，单次最多返回 100 条日志；
- Harness 限制最大 8 步、总耗时 45 秒、单工具 8 秒；
- 同一个工具和参数重复超过阈值会熔断；
- 工具错误进行有限指数退避重试；
- 所有事实要求 `dataset:line` 引用，并在结束前校验；
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

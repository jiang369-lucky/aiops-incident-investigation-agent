# AIOps 日志故障调查与工单辅助 Agent

这是一个可以本地复现的 Agent 工程：输入 OpenStack 虚拟机实例 ID，Agent 受限调用日志工具，
重建时间线、提出候选故障假设、主动查找反证、校验日志引用，最后输出一份必须由人工确认的工单草稿。

项目使用公开的 Loghub OpenStack 数据。它不是自动修复系统，也不会把公开数据的“异常实例标签”
夸大成逐行根因标签。

## 项目包含什么

- **Agent Harness**：统一驱动“决策—工具—观察”循环，限制最大步骤、总超时、单工具超时、
  重试、重复调用和工具白名单，并保存 JSONL Trace。
- **Skills**：把日志分诊、证据核验、报告生成写成三个可复用的工作方法；离线策略和 LLM
  策略加载同一组 Skill。
- **MCP 工具封装**：通过官方 Python MCP SDK 暴露只读日志查询、时间线、Runbook 检索和证据校验；
  工单写入工具要求显式 `approved=true`。
- **双运行模式**：`heuristic` 不需要 API Key，可稳定演示和作为基线；`llm` 支持任何兼容
  OpenAI Chat Completions 的模型服务。
- **可复现评测**：评测器单独读取标签；Agent 和 MCP 工具都接触不到标签，避免数据泄漏。
- **可观测接口**：CLI、FastAPI 和 MCP 共用同一个工具注册模块，不复制业务逻辑。

## 一次任务如何运行

```text
告警/实例 ID
    │
    ▼
Agent Policy ──选择──> Skill 工作方法
    │
    ▼
Harness（步数、超时、重试、循环熔断、白名单、Trace）
    │
    ▼
Tool Registry ──同一接口──> 本地调用 / FastAPI / MCP
    │
    ├── PostgreSQL 日志索引（只读查询）
    ├── Runbook 检索
    ├── 引用校验
    └── 工单草稿（必须人工批准）
    │
    ▼
带证据与反证的调查报告
```

`Harness` 不是需要单独下载的神秘框架，而是本项目自己实现的 Agent 运行底座。它不负责判断业务
结论，负责保证 Agent 在规定权限和预算内运行。`Skill` 是可加载的工作流程知识；`MCP` 是让工具
能被其他 Agent 客户端发现和调用的协议封装。这三者的职责互不替代。

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
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc --dataset abnormal

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
incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc --dataset abnormal --mode llm
```

LLM 只能选择 Harness 白名单中的只读工具。模型返回格式错误、工具失败、超时或陷入重复调用时，
Harness 会记录 Trace 并返回稳定的失败状态，而不是无限循环。

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
  "dataset": "abnormal",
  "mode": "heuristic"
}
```

## 启动 MCP Server

```powershell
incident-mcp
```

这是 stdio MCP Server，可供支持 MCP 的 Agent 客户端启动。客户端配置示例：

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
- `validate_evidence`
- `save_ticket_draft`

评测标签没有注册为工具，因此 Agent 无法在运行时偷看答案。

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

- 查询参数限制在三个数据分区，单次最多返回 100 条日志；
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
  mcp_server.py    # MCP adapter
  api.py           # FastAPI adapter
  evaluation.py    # 标签隔离的评测器
skills/            # 三个可加载 Skill
knowledge/         # Runbook 知识
tests/             # Parser、工具、Harness、Skill 测试
data/              # 原始数据和数据说明（数据库由 Docker Volume 保存）
artifacts/         # Trace、工单草稿、评测结果
```

## 本项目真正实现的部分

公开数据只提供日志和异常实例标签。本项目实现的是日志解析与索引、Agent Harness、Skill 加载、
工具权限控制、MCP/FastAPI adapters、证据校验、人工审批门、评测与 Trace。面试时应把公开数据来源
和自己的实现分别说明，不把数据集或第三方 SDK 当成自己的代码。

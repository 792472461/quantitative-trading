# AGENTS.md

## 项目定位

这是一个面向个人长期使用的、偏生产化的量化交易项目骨架。
默认应按“可持续维护的交易系统雏形”来对待，覆盖研究、回测、模拟盘、券商接入骨架、运行控制与持久化。

## 工作总规则

- 优先保持现有架构稳定，除非某个改动能明确降低复杂度或提升可扩展性。
- 优先做小步、可验证、尽量不改行为的重构，不要无理由大改。
- 始终维护主链路可用：配置 -> 数据源 -> 策略 -> 风控 -> broker -> runtime/storage -> 报表/监控。
- 不要把 broker 骨架或只读接入描述成可直接实盘执行的能力。
- 任何关键性更改，都必须在同一任务内同步更新本文件。
- 关键性的修改，请commit代码
- 请在关键路径代码添加注释

## 关键性更改的同步规则

- 只要发生关键性更改，就要同步更新本文件。
- 任务在未更新本文件前，不视为完成。
- 关键性更改包括但不限于：
- 新增 CLI 命令
- 修改已有命令语义或运行行为
- 新增 broker 模式，或调整 broker 的安全边界
- 修改持久化结构、存储行为、查询口径
- 修改风控、交易成本、调度、交易日历等核心行为
- 调整核心模块目录或职责边界
- 新增必须遵守的开发流程规则

## 代码结构速览

- `src/qt_trader/cli.py`：Typer CLI 入口与命令注册
- `src/qt_trader/cli_helpers.py`：CLI 共用装配逻辑与小型解析辅助
- `src/qt_trader/cli_render.py`：CLI 表格输出辅助
- `src/qt_trader/config.py`：YAML 配置加载与校验
- `src/qt_trader/data/`：行情数据接入与归一化
- `src/qt_trader/data/qmt_live.py`：QMT 实时/准实时行情接入
- `src/qt_trader/strategy/`：策略接口与具体实现
- `src/qt_trader/backtest.py`：历史回测引擎
- `src/qt_trader/runtime.py`：paper trading 与 signal watch 运行时
- `src/qt_trader/runtime.py`：paper trading、signal watch 与 live trading 运行时
- `src/qt_trader/risk.py`：订单和组合级风控
- `src/qt_trader/broker/`：broker 抽象与适配器
- `src/qt_trader/storage.py`：SQLite 持久化与查询
- `src/qt_trader/storage.py`：SQLite 持久化、broker 同步快照与订单对账摘要
- `src/qt_trader/analytics.py`：回测与市场状态分析指标
- `src/qt_trader/guardian.py`：运行锁与状态持久化
- `src/qt_trader/market.py`、`src/qt_trader/scheduler.py`：交易日历与会话调度
- `config/`：各类运行场景配置
- `tests/`：回归测试。任何有实际行为影响的改动都应补测试

## 核心原则

- 安全优先：只读 broker 必须保持只读，除非用户明确要求引入真实下单能力。
- 运行正确性优先于新功能堆叠。
- 研究能力与执行能力可以共用配置和存储，但职责上要分开。
- 涉及 broker、风控、存储、调度等能力时，优先显式配置，少依赖隐式默认值。
- 注释应少而有效，只在关键控制节点、非直观流程或安全边界处补短注释。

## CLI 约束

- 新命令默认应遵循现有 Typer 风格，并接受 `--config`，除非有明确理由例外。
- CLI 公共装配逻辑应放在辅助模块中，不要在多个命令里重复复制。
- Rich 表格输出尽量收敛到渲染辅助中。
- 新增较重的 CLI 功能时，优先抽到 runtime/research/service 层，不要持续把 `cli.py` 堆大。

## Broker 约束

- 明确区分 `paper`、`readonly`、`http_readonly`、终端骨架、SDK 骨架、未来真实执行等不同能力层级。
- `guojin_qmt_live` 是当前唯一允许进入真实 QMT 发单链路的 provider，但仍受 `broker.allow_live_trading` 显式开关保护。
- 当前标为只读或 scaffold 的 broker，不得静默开启真实下单。
- 依赖本地终端软件或券商 SDK 的路径，必须在失败时给出清晰错误，并保持 preflight 检查可读。

## 数据与策略约束

- 数据提供方必须统一归一化到项目内部的 bar 模型。
- `qmt_live` 允许作为实时或准实时数据源，但应默认服务于 `signal-watch` 或 `live-trade`，不要把它误当成稳定的历史研究数据源。
- 数据回退逻辑，尤其是 AKShare 回退到本地 CSV 的行为，必须显式且有测试覆盖。
- 策略改动不能破坏多标的处理和基准过滤逻辑，除非配置和文档同步说明。

## 持久化与运行时约束

- SQLite 是主流程的一部分，不是可有可无的附属功能。
- 任何涉及存储数据、dashboard 查询、运行状态文件、broker 快照行为的改动，都应补测试。
- 运行锁和运行状态属于安全关键路径，避免引入重复运行、状态歧义或恢复逻辑不清的问题。
- live trading 不得复用 paper trading 的本地伪成交逻辑；真实发单与真实成交/持仓同步必须分开处理。
- 真实下单路径应优先保留 `broker_order_id`，并支持后续把委托、成交、对账串起来。
- broker 同步逻辑应尽量幂等；同一笔成交重复同步时，不应重复写入本地 fills。

## 测试要求

- 只要改动具有实际行为影响，尽量运行 `python -m pytest -q`。
- 下列改动应优先补测试：
- 新命令，且不只是简单展示
- 风控逻辑调整
- broker 工厂或适配器改动
- 存储结构或查询口径调整
- 交易日历、调度、signal-watch、daily-workflow 相关改动

## 文档要求

- `README.md`、`docs/PROJECT.md` 与本文件应在主要能力和边界上保持一致。
- 新增或删除命令、修改安全边界、调整核心结构时，必须同步更新文档。
- 即使其他文档已更新，关键性更改仍必须在本文件中留下摘要。

## 关键里程碑

- `5a076fb`：初始化项目骨架，建立回测、风控、组合、paper broker、CLI、示例配置与基础测试。
- `8c11205`：增加 AKShare 数据源，项目从纯本地样例推进到真实历史数据接入。
- `e10c362`：增加交易时段、交易日历与调度，开始具备“按市场时间运行”的基础能力。
- `ec4314f`：增加结构化日志与告警，主链路开始具备基本可观测性。
- `cb4ec21`：增加交易成本模型，并开始系统性维护项目文档。
- `f0c3fb9`：增加多标的支持，策略与回测不再局限于单标的。
- `2ba0380`：增加组合级风控，包括总敞口、最大持仓数、单票数量限制。
- `44103d4`：增加 A 股节假日与调休日覆盖，交易日判断更贴近真实市场。
- `540ec74`：增加运行锁和恢复状态文件，这是从“可运行脚本”走向“可持续运行程序”的关键节点。
- `9ec842c`：增加 dashboard CLI，开始统一展示订单、成交、事件和运行摘要。
- `3e788f7`：增加 broker 账户查询与同步骨架，broker 主线正式建立。
- `a01e2fa`：增加 readonly broker 集成骨架，明确只读联调边界，避免误导为真实交易能力。
- `ee0cbc2`：增加只读 broker 快照落库，让账户同步结果进入本地持久化链路。
- `b1a1ed6`：增加通用 HTTP readonly broker 骨架，为真实券商 API 联调预留统一接口。
- `316eebb`：增加国金证券 readonly broker 骨架，明确国金是优先接入方向。
- `217160c`：增加策略文档与回测分析指标，研究链路更完整。
- `5164662`：增加 broker sync 变化摘要，让账户同步结果可以直接比较前后差异。
- `cc53228`：增加参数扫描和 preflight checks，开始把研究效率和运行前校验纳入主流程。
- `f1839a1`：增加国金 QMT / PTrade scaffold，broker 能力从只读 API 联调扩展到终端接入准备。
- `d7e98aa`：抽象 terminal client，这是后续支持不同终端或券商接入方式的关键结构节点。
- `62e7ada`：增加 QMT SDK client scaffold，开始进入券商 SDK 查询适配准备阶段。
- `27c6b91`：增加 xtquant query adapter，补齐 QMT SDK 查询路径骨架。
- `6e3ccac`：增加市场状态过滤到策略层，策略逻辑开始考虑市场环境。
- `89e6744`：增加市场状态回测分析，支持按 bull/bear/sideways 拆解策略表现。
- `96649a6`：增加 market regime 示例配置，形成完整示例链路。
- `b196149`：增加 signal watch runtime，支持只提醒信号、不下真实单的常驻扫描模式。
- `9923a1a`：增加分阶段 daily workflow，项目进入按交易日节奏组织任务的运行阶段。
- 当前工作区关键变更：已增加 `qmt_live` 数据源、`guojin_qmt_live` provider 和 `live-trade` 命令，真实下单仍需显式开启 `broker.allow_live_trading=true`。
- 当前工作区关键变更：已增加 `broker_order_id`、broker 成交查询和 `reconcile-broker` 命令，live trading 启动前默认先同步 broker 状态。
- 当前工作区关键变更：broker 同步现已支持按 `broker_order_id` 回补本地订单状态，并将成交同步成幂等的本地 fills。

## 当前演进主线

- 阶段一：回测与 paper trading 骨架搭建。
- 阶段二：真实数据、成本模型、多标的、组合风控、交易日历补齐。
- 阶段三：运行锁、状态文件、日志、告警、dashboard，增强可运行性与可观测性。
- 阶段四：broker 账户查询、只读联调、快照落库、HTTP 接入与国金方向 scaffold。
- 阶段五：终端抽象、QMT/PTrade/QMT SDK/xtquant 查询路径准备。
- 阶段六：市场状态过滤、参数扫描、signal watch、daily workflow，逐步形成日常运行闭环。
- 阶段七：QMT 实时行情与 live order 提交链路接入，但真实成交回报和撤单管理仍待继续完善。

## 推荐阅读顺序

- 第一步：先读 `AGENTS.md`，快速了解项目定位、边界、里程碑和当前维护规则。
- 第二步：读 `README.md`，确认当前对外暴露的命令、能力范围和运行方式。
- 第三步：读 `docs/PROJECT.md`，理解项目架构和迭代历史。
- 第四步：读 `src/qt_trader/cli.py`，建立对所有 CLI 命令入口的整体认识。
- 第五步：读 `src/qt_trader/cli_helpers.py` 和 `src/qt_trader/cli_render.py`，了解 CLI 的共用装配与输出逻辑。
- 第六步：按主链路阅读 `config.py`、`data/`、`strategy/`、`risk.py`、`broker/`、`backtest.py`、`runtime.py`、`storage.py`。
- 第七步：如果任务与调度或运行稳定性有关，再读 `guardian.py`、`market.py`、`scheduler.py`、`readiness.py`。
- 第八步：如果任务与报表和研究分析有关，再读 `analytics.py`、`research.py`、`dashboard` 相关查询逻辑。
- 第九步：最后读 `tests/`，确认当前行为边界和已有回归覆盖。

## 按任务类型的优先入口

- 回测或策略问题：先看 `cli.py` 的 `backtest`，再看 `strategy/`、`backtest.py`、`analytics.py`。
- 模拟盘或运行时问题：先看 `paper_trade`、`run_session`、`signal_watch`、`daily_workflow`，再看 `runtime.py`、`guardian.py`、`storage.py`。
- 实时交易问题：先看 `live_trade`、`data/qmt_live.py`、`broker/qmt_live.py`、`broker/qmt_sdk.py`，再看 `runtime.py` 和 `readiness.py`。
- 对账问题：先看 `reconcile_broker`、`storage.py` 的 broker snapshot/trade/reconciliation 逻辑，再看对应 broker adapter 的 `get_orders` / `get_trades`。
- broker 相关问题：先看 `broker/factory.py`，再看对应适配器和 `readiness.py`。
- 数据问题：先看 `data/factory.py`，再看 `csv_data.py` 和 `akshare_data.py`。
- 风控问题：先看 `risk.py`，再结合 `portfolio.py`、`costs.py`、运行入口一起看。
- dashboard 或存储问题：先看 `storage.py`，再看 `cli.py` 中的 `dashboard`、`broker_sync`、`runtime_state`。

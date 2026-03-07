# Quantitative Trading Project Notes

## Project Overview

这是一个面向个人长期使用的 Python 量化交易项目，目标不是做演示，而是逐步演进成可研究、可回测、可模拟运行、可持续维护的软件。

当前核心能力：

- 策略接口与示例策略
- CSV 和 AKShare 数据源
- AKShare 失败时回退本地缓存 CSV
- 多标的回测与模拟交易
- 组合级风控
- A 股节假日和调休日历
- 任务守护与自动恢复基础
- 监控看板基础版 CLI
- 券商账户同步骨架
- 只读 broker 联调样例
- broker 账户快照落库
- HTTP 只读 broker 骨架
- 国金证券接入准备文档
- 回测引擎
- Paper trading 运行时
- 风控
- 交易日历与交易时段控制
- SQLite 持久化
- 结构化日志与告警
- 更真实的交易成本模型
- 回测绩效分析
- broker 同步变更摘要
- 参数扫描与回测结果归档
- 实盘前 preflight 检查

## Architecture

- `src/qt_trader/data/`
  负责行情数据接入与归一化
- `src/qt_trader/strategy/`
  负责策略生成信号
- `src/qt_trader/backtest.py`
  负责历史回测
- `src/qt_trader/runtime.py`
  负责 paper trading 运行时
- `src/qt_trader/broker/`
  负责券商网关与执行抽象
- `src/qt_trader/costs.py`
  负责佣金、最低佣金、印花税、滑点模型
- `src/qt_trader/storage.py`
  负责订单、成交、快照、事件持久化
- `src/qt_trader/market.py` / `src/qt_trader/scheduler.py`
  负责交易时间控制
- `src/qt_trader/logging_utils.py` / `src/qt_trader/alerts.py`
  负责运行日志与告警

## Commands

- `python -m qt_trader.cli backtest --config config/example.yaml`
- `python -m qt_trader.cli paper-trade --config config/example.yaml`
- `python -m qt_trader.cli fetch-data --config config/akshare.yaml`
- `python -m qt_trader.cli market-status --config config/example.yaml`
- `python -m qt_trader.cli run-session --config config/example.yaml --force`
- `python -m qt_trader.cli send-test-alert --config config/example.yaml`
- `python -m qt_trader.cli runtime-state --config config/example.yaml`
- `python -m qt_trader.cli dashboard --config config/example.yaml`
- `python -m qt_trader.cli broker-account --config config/example.yaml`
- `python -m qt_trader.cli broker-account --config config/readonly_broker.yaml`
- `python -m qt_trader.cli broker-sync --config config/readonly_broker.yaml`
- `python -m qt_trader.cli broker-account --config config/http_readonly_broker.yaml`
- `python -m qt_trader.cli broker-account --config config/guojin_http_readonly.yaml`
- `python -m qt_trader.cli optimize-strategy --config config/example.yaml`
- `python -m qt_trader.cli preflight-check --config config/example.yaml`
- 回测命令会附带输出收益率、胜率、盈亏比、最大回撤等指标
- 回测分析会附带输出 Sharpe、Calmar、Expectancy
- `broker-sync` 会输出相对上一版快照的资金、持仓、委托数量变化
- `dashboard` 会显示最近一次 broker 同步变化摘要和持仓变化列表
- `dashboard` 会显示最近回测记录和历史最优参数组合
- `optimize-strategy` 会批量扫描双均线参数并将结果写入 SQLite
- `preflight-check` 会检查策略参数、数据加载、路径可写性、告警与 broker 就绪状态

## Iteration Log

### 2026-03-07 - `5a076fb`

`feat: bootstrap quantitative trading foundation`

- 初始化 Python 项目结构
- 实现回测主链路、风控、组合管理、paper broker
- 增加 CLI、示例配置、示例数据和基础测试

### 2026-03-07 - `8c11205`

`feat: add akshare market data provider`

- 增加 AKShare A 股历史行情接入
- 新增数据源工厂与 `fetch-data` 命令
- 支持抓取真实历史数据并导出标准化 CSV

### 2026-03-07 - `e10c362`

`feat: add market session calendar and scheduler`

- 增加交易日历和交易时段判断
- 增加 `market-status` 和 `run-session`
- 支持按交易时间控制是否运行

### 2026-03-07 - `ec4314f`

`feat: add runtime logging and alerts`

- 增加结构化 JSONL 日志
- 增加运行事件落库
- 增加 stdout / file 告警

### 2026-03-07 - `cb4ec21`

`feat: add execution cost model and project notes`

- 增加佣金、最低佣金、印花税、滑点模型
- 建立持续维护的项目文档
- 增加 AKShare 失败时的本地缓存回退

### 2026-03-07 - `f0c3fb9`

`feat: add multi-symbol trading support`

- 增加多标的配置和数据样例
- 支持多标的 CSV / AKShare 数据输入
- 策略状态改为按 symbol 独立维护

### 2026-03-07 - `2ba0380`

`feat: add portfolio-level risk controls`

- 增加组合总仓位敞口限制
- 增加最大持仓数量限制
- 增加单票最大股数限制

### 2026-03-07 - `44103d4`

`feat: add ashare holiday calendar overrides`

- 增加 A 股节假日和调休日历文件
- 支持 holiday file 覆盖规则
- 支持节假日与调休工作日判断

### 2026-03-07 - `540ec74`

`feat: add runtime guard and recovery state`

- 增加运行锁，防止重复启动
- 增加运行状态文件
- 增加重试和状态查看命令

### 2026-03-07 - `9ec842c`

`feat: add dashboard reporting commands`

- 增加 dashboard 报表命令
- 支持账户概览、事件和成交摘要查询
- 为 CLI 监控看板打基础

### 2026-03-07 - `3e788f7`

`feat: add broker account sync scaffold`

- 扩展 broker 接口到账户、持仓、委托查询
- 增加 broker-account 命令
- 为真实券商同步打下接口基础

### 2026-03-07 - `a01e2fa`

`feat: add readonly broker integration scaffold`

- 增加 readonly broker 适配器
- 增加只读联调配置和账户样例快照
- 明确禁止真实下单，仅允许查询

### 2026-03-07 - `ee0cbc2`

`feat: persist readonly broker snapshots`

- 增加 broker-sync 命令
- 支持只读 broker 账户快照落库
- 让 dashboard 复用同步后的账户摘要

### 2026-03-07 - `b1a1ed6`

`feat: add http readonly broker scaffold`

- 增加通用 HTTP 只读 broker 骨架
- 支持 account / positions / orders 接口契约
- 为真实券商 API 只读联调打基础

### 2026-03-07 - `316eebb`

`feat: add guojin readonly broker scaffold`

- 增加国金证券只读适配器
- 增加国金接入配置和准备文档
- 明确国金为主接入目标

### 2026-03-07 - Latest Iteration

本轮目标：

- 增加参数扫描与回测结果归档
- 扩展 dashboard 展示最近回测与最优回测组合
- 增加 preflight-check，为实盘前准备提供基础自检
- 后续每次迭代完成后同步更新本文档

## Next Priorities

- 实盘券商适配
- broker 同步调度与告警
- 任务守护与自动恢复完善
- dashboard Web 化

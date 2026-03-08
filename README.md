# Quantitative Trading

这是一个面向真实落地的量化交易项目骨架，不是前端演示，也不是只会跑几行示例代码的 demo。

当前版本提供：

- 策略开发接口
- 可切换数据源
- 多标的支持
- CSV 行情驱动的回测引擎
- AKShare A 股历史行情接入
- 基础风险控制
- 交易日历和交易时段判断
- A 股节假日和调休日历支持
- 结构化日志
- 告警通道
- 更真实的交易成本模型
- 组合级风控
- 任务守护与自动恢复基础
- 券商账户/持仓/委托查询骨架
- 回测绩效分析
- 券商网关抽象层
- 本地模拟撮合网关
- SQLite 持久化
- Paper trading 运行时
- QMT 实时行情数据源
- QMT live trading 运行时
- CLI 运行入口

## 设计目标

- 先把可运行的核心链路搭起来
- 保证后续能接入真实数据源和真实券商
- 把风控和配置放在主链路，而不是事后补丁

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
qt-trader backtest --config config\example.yaml
qt-trader paper-trade --config config\example.yaml
qt-trader fetch-data --config config\akshare.yaml
qt-trader backtest --config config\multi_symbol.yaml
qt-trader market-status --config config\example.yaml
qt-trader send-test-alert --config config\example.yaml
qt-trader runtime-state --config config\example.yaml
qt-trader dashboard --config config\example.yaml
qt-trader signal-watch --config config\example.yaml --iterations 1 --force
qt-trader daily-workflow --config config\example.yaml --iterations 1 --at 2026-03-06T09:10:00
qt-trader broker-account --config config\example.yaml
qt-trader broker-account --config config\readonly_broker.yaml
qt-trader broker-sync --config config\readonly_broker.yaml
qt-trader broker-account --config config\http_readonly_broker.yaml
qt-trader broker-account --config config\guojin_http_readonly.yaml
qt-trader preflight-check --config config\guojin_qmt_live.yaml
qt-trader reconcile-broker --config config\guojin_qmt_live.yaml
qt-trader recover-live-session --config config\guojin_qmt_live.yaml
qt-trader live-trade --config config\guojin_qmt_live.yaml --iterations 1 --force
```

## 项目结构

```text
src/qt_trader/
  cli.py
  config.py
  models.py
  portfolio.py
  risk.py
  backtest.py
  data/
  broker/
  strategy/
config/
data/
tests/
```

## 当前边界

这一版已经能用于：

- 本地研究策略
- 做基础回测
- 跑多标的组合级回测
- 模拟下单和风控校验
- 控制组合总仓位和持仓集中度
- 根据节假日和调休判断是否应运行
- 防止重复启动并记录上次运行状态
- 直接查看账户概览、最近事件和成交摘要
- 查看券商账户、持仓和委托骨架信息
- 用只读 broker 配置做真实券商联调演练
- 把只读 broker 的账户快照同步进本地数据库
- 使用 HTTP 只读 broker 骨架对接真实券商 API
- 以国金证券为主的只读接入准备文档和配置
- 使用 QMT SDK 拉取实时行情并执行受保护的 live order 提交链路
- 记录订单、成交和资金曲线
- 运行 paper trading 主链路
- 基于交易时段控制是否执行
- 输出结构化运行日志
- 对回撤和拒单触发告警

要进入真实实盘，还需要补：

- 真实成交回报、成交落库与仓位回补闭环
- 交易日历、滑点、手续费细化
- 更完整的监控看板和外部告警渠道

## 当前命令

```bash
qt-trader backtest --config config\example.yaml
qt-trader backtest --config config\multi_symbol.yaml
qt-trader paper-trade --config config\example.yaml
qt-trader fetch-data --config config\akshare.yaml
qt-trader market-status --config config\example.yaml
qt-trader run-session --config config\example.yaml --force
qt-trader send-test-alert --config config\example.yaml
qt-trader runtime-state --config config\example.yaml
qt-trader dashboard --config config\example.yaml
qt-trader signal-watch --config config\example.yaml --iterations 1 --force
qt-trader daily-workflow --config config\example.yaml --iterations 1 --at 2026-03-06T15:10:00
qt-trader broker-account --config config\example.yaml
qt-trader broker-account --config config\readonly_broker.yaml
qt-trader broker-sync --config config\readonly_broker.yaml
qt-trader broker-account --config config\http_readonly_broker.yaml
qt-trader broker-account --config config\guojin_http_readonly.yaml
qt-trader preflight-check --config config\guojin_qmt_live.yaml
qt-trader reconcile-broker --config config\guojin_qmt_live.yaml
qt-trader recover-live-session --config config\guojin_qmt_live.yaml
qt-trader live-trade --config config\guojin_qmt_live.yaml --iterations 1 --force
qt-trader version
```

`paper-trade` 会把订单、成交和资金快照写入 SQLite 数据库，默认文件是 `trading.db`。
`run-session` 会先检查当前是否在交易时段内；`--force` 可用于离线演练。
`signal-watch` 会在最新一根 bar 上发现新信号时提醒，但不会下真实订单。
`daily-workflow` 会在 `9:00-9:30` 做盘前复核和参数筛选，在 `15:00` 后做收益统计；当前“实时新闻抓取”仍是待接入项。
`guojin_qmt_live.yaml` 会通过 `xtquant.xtdata` 读取 QMT 实时行情，并通过 `XtQuantTrader` 发单；默认 `broker.allow_live_trading=false`，需要显式开启后 `live-trade` 才会提交真实订单。
`live-trade` 不复用 `paper-trade` 的伪成交逻辑，只负责信号、风控、发单和 broker 同步，避免本地假填真实成交。
`reconcile-broker` 会把券商账户、持仓、委托、成交同步进本地 SQLite，并输出本地订单与券商订单/成交的差异摘要。
同步过程中会按 `broker_order_id` 回补本地订单状态，支持 `SUBMITTED`、`PARTIALLY_FILLED`、`FILLED`、`CANCELED` 等实盘状态。
`recover-live-session` 会在重新接管 live 会话前展示当前本地未完成订单，并先做一轮 broker 同步与状态回补。
运行日志会写到 `logs/runtime.jsonl`，告警可输出到终端和 `logs/alerts.log`。
运行锁默认写到 `runtime.lock`，运行状态默认写到 `runtime_state.json`。
`readonly_broker.yaml` 是只读联调样例，不会允许真实下单，只会读取本地账户快照文件。

## 项目文档

持续维护文档在 [docs/PROJECT.md](F:/workspace/python/quantitative-trading/docs/PROJECT.md)，里面会记录项目概览、架构和每次迭代内容。
国金证券接入准备文档在 [docs/BROKER_GUOJIN.md](F:/workspace/python/quantitative-trading/docs/BROKER_GUOJIN.md)。
当前默认策略说明文档在 [docs/STRATEGY_MOVING_AVERAGE.md](F:/workspace/python/quantitative-trading/docs/STRATEGY_MOVING_AVERAGE.md)。

## 真实数据

项目现在支持三种数据源：

- `csv`: 本地 CSV，适合回放和研究
- `akshare`: 拉取 A 股历史行情，适合先做真实数据接入
- `qmt_live`: 通过本机 QMT/xtquant 获取实时或准实时 bar，适合实盘前联调

可以参考 [config/akshare.yaml](F:/workspace/python/quantitative-trading/config/akshare.yaml) 抓取 A 股历史数据。
如果 AKShare 临时不可用，而本地已经存在缓存 CSV，系统会自动回退到本地缓存。

这些接口在本项目里都已经预留好了。

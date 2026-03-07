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
- 券商网关抽象层
- 本地模拟撮合网关
- SQLite 持久化
- Paper trading 运行时
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
qt-trader broker-account --config config\example.yaml
qt-trader broker-account --config config\readonly_broker.yaml
qt-trader broker-sync --config config\readonly_broker.yaml
qt-trader broker-account --config config\http_readonly_broker.yaml
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
- 记录订单、成交和资金曲线
- 运行 paper trading 主链路
- 基于交易时段控制是否执行
- 输出结构化运行日志
- 对回撤和拒单触发告警

要进入真实实盘，还需要补：

- 真实券商 API 适配实现
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
qt-trader broker-account --config config\example.yaml
qt-trader broker-account --config config\readonly_broker.yaml
qt-trader broker-sync --config config\readonly_broker.yaml
qt-trader broker-account --config config\http_readonly_broker.yaml
qt-trader version
```

`paper-trade` 会把订单、成交和资金快照写入 SQLite 数据库，默认文件是 `trading.db`。
`run-session` 会先检查当前是否在交易时段内；`--force` 可用于离线演练。
运行日志会写到 `logs/runtime.jsonl`，告警可输出到终端和 `logs/alerts.log`。
运行锁默认写到 `runtime.lock`，运行状态默认写到 `runtime_state.json`。
`readonly_broker.yaml` 是只读联调样例，不会允许真实下单，只会读取本地账户快照文件。

## 项目文档

持续维护文档在 [docs/PROJECT.md](F:/workspace/python/quantitative-trading/docs/PROJECT.md)，里面会记录项目概览、架构和每次迭代内容。

## 真实数据

项目现在支持两种数据源：

- `csv`: 本地 CSV，适合回放和研究
- `akshare`: 拉取 A 股历史行情，适合先做真实数据接入

可以参考 [config/akshare.yaml](F:/workspace/python/quantitative-trading/config/akshare.yaml) 抓取 A 股历史数据。
如果 AKShare 临时不可用，而本地已经存在缓存 CSV，系统会自动回退到本地缓存。

这些接口在本项目里都已经预留好了。

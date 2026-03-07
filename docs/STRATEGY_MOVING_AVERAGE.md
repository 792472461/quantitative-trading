# Moving Average Strategy

## Strategy Summary

当前默认策略是一个双均线交叉策略，代码在 [src/qt_trader/strategy/moving_average.py](F:/workspace/python/quantitative-trading/src/qt_trader/strategy/moving_average.py)。

它不是高频策略，也不是预测短线涨跌的模型，而是一个趋势跟踪策略。

## Buy Rule

满足以下条件时买入：

- 已经累计了足够多的历史收盘价
- 短周期均线 `fast_window` 大于长周期均线 `slow_window`
- 当前该股票还没有持仓

这代表短期趋势开始强于长期趋势，策略认为有趋势启动的可能。

## Sell Rule

满足以下条件时卖出：

- 短周期均线 `fast_window` 小于长周期均线 `slow_window`
- 当前该股票已经有持仓

这代表短期趋势重新弱于长期趋势，策略选择退出。

## Important Characteristics

- 更适合趋势行情
- 在震荡行情里容易出现频繁买卖
- 胜率未必高，但可能依赖盈亏比赚钱
- 参数变化会明显影响表现

## Market Regime Filter

当前策略已经支持一个可选的市场状态过滤层。

当 `market_filter_enabled = true` 时，策略会先观察 `benchmark_symbol` 的均线关系：

- 只有当基准指数的短均线高于长均线时，个股买入信号才允许触发
- 个股卖出信号仍然保留，不会因为市场过滤而阻止退出

这层过滤的目标不是提高每一笔交易收益，而是尽量减少逆市场环境下的开仓。

常见配置包括：

- `benchmark_symbol`
- `market_fast_window`
- `market_slow_window`

如果不启用这组参数，策略行为和原来的双均线版本一致。

## Default Parameters

默认配置里常见参数是：

- `fast_window = 5`
- `slow_window = 20`
- `trade_size = 20`

这些参数在 [config/example.yaml](F:/workspace/python/quantitative-trading/config/example.yaml) 中可以调整。

## Execution Flow

1. 数据源生成 `Bar`
2. 策略读取 `Bar` 并生成 `Signal`
3. 回测/运行时把 `Signal` 转成 `Order`
4. 风控检查是否允许下单
5. broker 返回 `Fill`
6. portfolio 更新资金和持仓
7. analytics 模块统计策略表现

## Metrics

当前回测会额外输出：

- 总收益率
- 年化收益率
- 最大回撤
- 胜率
- 盈亏比 `profit factor`
- 平均盈利 / 平均亏损
- 回合数
- 资金曲线波动率

启用市场过滤后，建议重点比较：

- 总收益率是否更稳定
- 最大回撤是否下降
- 交易次数是否明显减少
- 不同市场阶段下的表现差异

## Market Analysis

当前回测分析已经支持基于 `benchmark_symbol` 的市场阶段拆分。

会按照基准指数均线关系，把区间粗分为：

- `bull`
- `bear`
- `sideways`

然后分别统计每个阶段中的：

- 阶段累计收益
- 单阶段平均收益
- 交易触发次数

这可以帮助判断策略到底是：

- 主要在牛市赚钱
- 熊市主要回撤
- 还是在震荡市被频繁消耗

## Caveat

这套策略只是第一版示例策略，适合作为工程主链路验证，不代表已经是最优策略。
真正要用于实盘前，必须做：

- 分市场阶段回测
- 参数敏感性分析
- 手续费和滑点压力测试
- 多标的组合稳定性验证

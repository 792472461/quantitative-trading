# Guojin Broker Prep

## Current Status

当前项目已经为国金证券建立了只读 HTTP 适配骨架：

- 配置文件：[config/guojin_http_readonly.yaml](F:/workspace/python/quantitative-trading/config/guojin_http_readonly.yaml)
- 适配器代码：[src/qt_trader/broker/guojin.py](F:/workspace/python/quantitative-trading/src/qt_trader/broker/guojin.py)

## What Is Confirmed

基于国金证券官网公开页面与隐私政策，可以确认国金证券当前终端体系中包含：

- 国金佣金宝 APP
- 国金太阳网上交易终端
- 讯投 QMT 系统
- Ptrade 系统

这里的结论来自国金证券官网公开资料，说明国金证券存在量化/程序化相关终端体系。

## What Is Not Yet Confirmed

目前没有在国金证券官网公开检索到明确对外开放的 REST 交易 API 文档。

因此，当前 `guojin_http_readonly` 的这些接口路径仍然是占位符，不是已验证的官方接口：

- `/account`
- `/positions`
- `/orders`

## Recommended Next Step

如果你准备继续推进真实接入，最需要补齐的是以下信息：

1. 国金证券是否向个人客户开放 QMT / Ptrade / 其他程序化接口
2. 接口接入方式是本地终端 SDK、柜台接口，还是 HTTP 服务
3. 账户查询、持仓查询、委托查询的真实字段格式
4. 登录鉴权方式
5. 是否支持只读模式或测试环境

## Safe Usage

这一版默认只允许只读查询，不允许真实下单。

```bash
$env:BROKER_API_KEY='demo-key'
$env:BROKER_API_SECRET='demo-secret'
$env:BROKER_ACCOUNT_ID='guojin-demo-001'
python -m qt_trader.cli broker-account --config config/guojin_http_readonly.yaml
```

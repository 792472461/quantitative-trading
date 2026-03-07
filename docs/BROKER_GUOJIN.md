# Guojin Broker Prep

## Current Status

当前项目已经为国金证券建立了只读 HTTP 适配骨架：

- 配置文件：[config/guojin_http_readonly.yaml](F:/workspace/python/quantitative-trading/config/guojin_http_readonly.yaml)
- 适配器代码：[src/qt_trader/broker/guojin.py](F:/workspace/python/quantitative-trading/src/qt_trader/broker/guojin.py)

## What Is Confirmed

基于国金证券官网公开页面与你和国金证券沟通得到的信息，可以确认国金证券当前终端体系中包含：

- 国金佣金宝 APP
- 国金太阳网上交易终端
- 讯投 QMT 系统
- Ptrade 系统

这里可以进一步确认两点：

1. 国金证券支持 QMT
2. 国金证券支持 Ptrade

这意味着项目后续真实接入不必再围绕“是否支持程序化终端”做假设，而应该直接进入接入方式、字段映射和运行约束确认阶段。

## What Is Not Yet Confirmed

目前仍然没有在公开资料中确认以下关键细节：

- 国金给个人客户开放的是 QMT、Ptrade，还是两者都可用
- 接入形态是本地终端 SDK、柜台接口、内网服务，还是另外的 HTTP 网关
- 登录鉴权流程、部署要求、白名单或本机限制
- 账户、持仓、委托、成交、资产的真实字段格式
- 是否支持仿真环境、只读模式或查询权限拆分

因此，当前 `guojin_http_readonly` 的这些 HTTP 接口路径仍然只是项目里的占位符，不是已验证的国金官方接口：

- `/account`
- `/positions`
- `/orders`

## Recommended Next Step

如果你准备继续推进真实接入，最需要补齐的是以下信息：

1. 你当前拿到的是 QMT 还是 Ptrade 接入资格
2. 是否有官方 SDK、示例代码、字段字典或柜台联系人
3. 查询接口与下单接口分别有哪些能力
4. 是否必须在 Windows 本机终端环境运行
5. 是否可以先做查询同步，再启用真实下单

## Safe Usage

这一版默认只允许只读查询，不允许真实下单。

```bash
$env:BROKER_API_KEY='demo-key'
$env:BROKER_API_SECRET='demo-secret'
$env:BROKER_ACCOUNT_ID='guojin-demo-001'
python -m qt_trader.cli broker-account --config config/guojin_http_readonly.yaml
```

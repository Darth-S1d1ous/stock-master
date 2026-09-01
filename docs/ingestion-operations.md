# 数据采集运行手册

## 前置条件

1. 执行 `alembic upgrade head`。
2. 通过环境变量配置 PostgreSQL。
3. 根据所选 provider 配置 API Key；Yahoo Finance 不需要 Key。
4. 不要把 `.env`、Token 或 API Key 写入 crontab 命令、日志或数据库。

## 手工运行

刷新一个股票：

```bash
.venv/bin/python -m app.cli refresh-symbol AAPL --provider yahoo_finance
```

刷新全部 `active` 和 `challenged` 论点涉及的唯一股票：

```bash
.venv/bin/python -m app.cli refresh-active --provider yahoo_finance
```

CLI 每次只允许一个固定白名单 provider，顺序刷新股票，并输出单行 JSON。运行及逐股票结果分别保存在 `ingestion_runs` 和 `ingestion_run_items`。

## 退出码

| 退出码 | 含义 |
|-------:|------|
| `0` | 全部成功，或批量运行没有待刷新股票 |
| `2` | 部分股票成功、部分失败 |
| `3` | 参数或配置错误 |
| `4` | 同一 provider 已有运行中的采集任务 |
| `5` | 所有股票失败，或任务无法启动 |

## cron 示例

下面示例每天 UTC 01:15 刷新活跃论点。环境变量应由受限权限的环境文件或运行平台注入，而不是直接写入命令。

```cron
15 1 * * * cd /path/to/stock-master-bot && .venv/bin/python -m app.cli refresh-active --provider yahoo_finance >> var/log/ingestion.jsonl 2>&1
```

部署前创建日志目录并限制权限：

```bash
install -d -m 750 var/log
```

## 运行策略

- 数据源只允许 `alpha_vantage`、`finnhub`、`yahoo_finance`。
- 每个 provider 使用 PostgreSQL advisory lock，防止多个进程重复运行。
- 股票按代码排序并顺序执行，避免突然触发第三方限流。
- provider 客户端负责 HTTP 超时和内部重试；runner 额外提供整次刷新超时和有限重试。
- 连续失败达到阈值后，本次运行的本地熔断器打开，剩余股票记录为失败而不再请求 provider。
- 单个股票使用独立事务；失败不会回滚此前已成功的股票。
- 持久化错误只包含稳定错误码和脱敏消息，不包含 URL、API Key 或 traceback。

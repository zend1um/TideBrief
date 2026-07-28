# 成熟项目对比与改进取舍

核对日期：2026-07-27。

## 参考项目

### Miniflux

项目：[miniflux/v2](https://github.com/miniflux/v2)

值得借鉴：

- 内部调度器与传统 cron 都可驱动后台更新。
- 遵循 Twelve-Factor 配置方式，容器以低权限用户运行。
- 使用 ETag、Last-Modified、If-Modified-Since 等条件请求，减少重复下载。
- 单一职责、低资源占用、完善的单元和集成测试。

本次采用：环境变量覆盖、非 root 容器、轻量内部调度、测试覆盖。

后续候选：为 RSS/HTML 来源保存 ETag 与 Last-Modified，降低采集量和封禁概率。

### changedetection.io

项目：[dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io)

值得借鉴：

- Compose 默认持久卷、`restart: unless-stopped` 和本机端口绑定。
- 每个监控目标可设置频率、时区、代理和提取规则。
- 快速 HTTP 抓取与浏览器抓取分离，避免所有来源都使用重型浏览器。
- 通过 Apprise 对接多种通知渠道。

本次采用：持久卷、自动恢复、默认 localhost、代理环境变量和失败不覆盖旧快照。

后续候选：引入按来源的成功率、连续失败次数和通知阈值，而不是每次失败都报警。

### RSSHub

项目：[DIYgod/RSSHub](https://github.com/DIYgod/RSSHub)

值得借鉴：

- Web、Redis、Browserless 等组件有独立健康检查。
- 浏览器能力作为可选独立服务，不强迫轻量来源承担额外资源成本。
- 通过缓存减少重复抓取。

本次采用：Web 与调度器分进程、独立健康检查和共享持久数据。

本次未采用 Redis 与 Browserless：当前每天候选数量有限，引入它们会增加小服务器内存、升级和备份成本。只有在需要大量 JavaScript 页面或多实例部署时再考虑。

### Healthchecks

项目：[healthchecks/healthchecks](https://github.com/healthchecks/healthchecks)

值得借鉴：

- 计划任务发送开始、成功和失败 ping。
- 使用周期与宽限时间判断任务是否迟到，而不是只判断进程是否存在。
- 保留任务事件日志，便于定位“服务活着但数据没更新”。

本次采用：运行状态 JSON、每分钟调度心跳、最近成功时间、错误信息、启动补跑和可选兼容 ping URL。

## 当前架构结论

现阶段最合适的是两个 Python 进程加 SQLite，而不是 Celery、Redis、Kafka 或 PostgreSQL：

```text
scheduler ──写入──> data/dashboard.json
    │               data/economic-calendar.json
    │               data/thesis_reviews.db
    │               data/runtime-status.json
    │
web ─────────读取/少量写入───────────────┘
```

网页和任务通过文件与 SQLite 解耦。采集进程重启或 LLM 失败时，网页仍可以提供上一份成功快照；写入采用临时文件加原子替换，避免读取半份 JSON。

## 下一阶段优先级

1. 为每个 Collector 记录持续成功率、耗时、抓取量和最近错误。
2. 为支持的来源增加 ETag / Last-Modified 条件请求。
3. 将到期复盘与每日采集拆成独立轻任务，避免没有新文章时错过复盘。
4. 若需要多人访问，再增加正式用户体系和 CSRF 防护；当前 Basic 认证适合单用户、HTTPS 前置的轻量部署。
5. 只有出现多台 Worker、并发任务或 SQLite 写竞争后，才迁移 PostgreSQL 和外部任务队列。

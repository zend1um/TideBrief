# 知潮 TideBrief 小服务器部署

## 推荐配置

- Linux x86_64 或 ARM64
- 1 vCPU、2 GB 内存、10 GB 可用磁盘
- Docker Engine 与 Docker Compose v2
- 能访问新闻源、行情源和所选 LLM API

LLM 调用在远端完成，服务器本身不需要 GPU。

## 首次部署

```bash
git clone <你的仓库地址> tidebrief
cd tidebrief
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
```

`.env` 至少填写：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

Compose 会启动两个进程：

- `web`：提供 UI 和 API，只读取快照并处理少量本地设置。
- `scheduler`：按北京时间运行采集、分析、观点复盘和财经日历同步。

两者共用数据卷，但互不依赖；一次采集或 LLM 调用失败不会导致网页进程退出。

## 安全访问

默认端口绑定为：

```text
127.0.0.1:8765
```

因此公网无法直接访问。最简单的访问方式是 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

随后在自己的电脑打开 `http://127.0.0.1:8765`。

也可以使用 Tailscale。只有在可信局域网内，才建议把 `.env` 中的 `TIDEBRIEF_BIND` 改为 `0.0.0.0`。

项目支持可选的 HTTP Basic 认证：

```dotenv
TIDEBRIEF_USERNAME=你的用户名
TIDEBRIEF_PASSWORD=足够长的随机密码
```

Basic 认证必须配合 HTTPS 使用；裸 HTTP 会以可还原形式传输凭据。公网域名访问仍建议在 Caddy、Traefik 或 Nginx 等反向代理层终止 HTTPS，并可进一步使用 Tailscale、Authelia 或其他身份层。

## 调度与自动恢复

默认时间：

- 每天 04:00：采集、分析、市场快照、日报和观点账本更新。
- 每周日 03:30：同步 BLS 官方 iCalendar，校正非农、CPI 和 PPI 日期。

容器异常退出后会自动重启。调度器每分钟写一次心跳；若服务器重启后发现上次成功采集已超过 26 小时，会立即补跑。

可选配置 `HEALTHCHECKS_PING_URL` 后，采集任务会发送开始、成功和失败心跳，适用于 [Healthchecks.io](https://healthchecks.io/) 或兼容的自托管服务。

## 查看状态

```bash
docker compose ps
docker compose logs --tail=100 scheduler
docker compose logs --tail=100 web
curl http://127.0.0.1:8765/api/status
```

`/api/status` 会报告：

- 调度器最近心跳和下次运行时间
- 最近一次采集及日历同步结果
- 仪表盘和财经日历是否过期

页面顶部绿色圆点表示调度正常；黄色表示调度器心跳缺失或快照过期。

部分官方站点会限制数据中心 IP。若日志中持续出现官方日历 `403`，可以在 `.env` 中设置可信代理：

```dotenv
HTTPS_PROXY=http://user:password@proxy-host:port
```

同步器只有在解析出有效的未来事件后才会原子替换日历；下载、解析或代理失败都会保留上一份成功快照。

## 手动运行

```bash
docker compose exec scheduler python main.py run
docker compose exec scheduler python main.py calendar-sync
```

文件锁会阻止手动任务与计划任务重复执行。

## 持久化与备份

`docker compose down` 不会删除数据。不要运行 `docker compose down -v`，除非确认要删除三个持久卷。

至少备份以下内容：

- `tidebrief-data`：核心数据和 SQLite 账本
- `tidebrief-vault`：筛选后的内容与日报
- 仓库中的 `config.yaml`
- 服务器上的 `.env`，应使用安全的密码管理或加密备份

SQLite 已启用 WAL 模式。备份观点账本时，优先在调度任务未运行的时间进行，或先短暂停止 `scheduler`。

## 升级

```bash
git pull
docker compose up -d --build
docker compose ps
```

构建完成后 Compose 会只替换代码镜像，命名卷中的数据不会丢失。

## 当前日历同步边界

美国 BLS 的非农、CPI、PPI 已使用官方 ICS 自动同步。美联储、欧洲央行、日本央行、中国国家统计局等来源的格式不统一，当前仍使用经过核对的计划快照，并在页面显示最后核对时间。宁可将尚未确认的时刻标记为“待定”，也不从不稳定的第三方页面自动写入错误日期。

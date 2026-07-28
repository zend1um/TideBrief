# 知潮 TideBrief

[中文](#中文) · [English](#english)

知潮 TideBrief 是一个面向交易研究的自托管信息筛选工具。它收集新闻和官方信息，把每天的大量内容压缩成少量交易线索，并提供财经日历、跨资产观察和观点复盘。

它不连接券商，也不会自动下单。项目的重点是减少无效阅读，帮助你持续记录“当时为什么这样判断，以及后来发生了什么”。

## 中文

### 可以做什么

- 从多个新闻、官方和市场来源收集信息
- 按关注词、交易相关性和阅读预算筛选内容
- 整理主导因素、传导路径、反方观点和失效条件
- 展示全球重要财经事件，并导出为 ICS 日历
- 保存观点账本，到期后对照行情进行复盘
- 通过本地 Web UI 查看结果和调整关注词
- 使用 Docker Compose 长期运行 Web 服务和定时任务

### 快速开始：Docker

建议在个人电脑、NAS 或小型 Linux 服务器上使用 Docker Compose。

1. 准备环境文件：

   ```bash
   cp .env.example .env
   ```

   Windows PowerShell：

   ```powershell
   Copy-Item .env.example .env
   ```

2. 编辑 `.env`，至少填写：

   ```dotenv
   DEEPSEEK_API_KEY=你的密钥
   ```

3. 构建并启动：

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

4. 在浏览器打开：

   ```text
   http://127.0.0.1:8765
   ```

默认只监听服务器本机。如果项目运行在远程服务器，可以建立 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

然后在自己的电脑打开 `http://127.0.0.1:8765`。

### 本地 Python 运行

需要 Python 3.12。先创建并激活虚拟环境：

```bash
python -m venv .venv
```

Linux 或 macOS：

```bash
source .venv/bin/activate
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

然后安装依赖：

```bash
python -m pip install -r requirements.txt
```

激活虚拟环境后，执行一次采集，再启动页面：

```bash
python main.py run
python main.py ui
```

页面地址仍为 `http://127.0.0.1:8765`。如果还没有执行采集，页面会使用示例数据展示界面结构。

### 常用命令

```bash
# 查看运行状态
docker compose ps

# 查看日志
docker compose logs -f scheduler
docker compose logs -f web

# 手动采集一次
docker compose exec scheduler python main.py run

# 手动同步官方财经日历
docker compose exec scheduler python main.py calendar-sync

# 停止服务，但保留数据
docker compose down
```

### 配置

主要设置位于 `config.yaml`：

- `filter.prefilter.focus_keywords`：关注的持仓、行业、商品或地区
- `filter.max_daily_items`：每天最多展示多少条内容
- `schedule.collect_time`：每日采集时间
- `market.symbols`：跨资产观察列表
- `collectors`：启用或关闭具体信息源

关注词和阅读上限也可以直接在 Web UI 中修改。运行时设置会单独保存，不会覆盖只读的主配置文件。

### 数据保存在哪里

Docker 部署使用三个命名卷：

- `tidebrief-data`：仪表盘快照、财经日历、运行状态和 SQLite 观点账本
- `tidebrief-logs`：运行日志
- `tidebrief-vault`：筛选后的文章与日报

执行 `docker compose down` 不会删除这些数据。不要使用 `docker compose down -v`，除非你确认要删除命名卷。

本地 Python 运行时，默认数据保存在项目的 `data/` 目录；文章与日报位置由 `config.yaml` 中的 `vault.path` 决定。

### 当前边界

- 部分站点会限制数据中心 IP，采集结果取决于服务器网络环境
- 美国 BLS 的非农、CPI 和 PPI 日程可以自动同步；其他地区仍有一部分采用经过核对的本地计划快照
- 摘要和判断使用模型生成，可能遗漏信息；重要内容应回到原始来源核对
- 项目用于研究和复盘，不构成投资建议

更多资料：

- [小服务器部署、备份与升级](docs/server-deployment.md)
- [财经日历的范围与来源](docs/economic-calendar.md)
- [架构审查与技术取舍](docs/architecture-review.md)
- [迭代记录](docs/iteration-log.md)

---

## English

TideBrief is a self-hosted information filter for trading research. It collects news and official releases, reduces the daily stream to a small set of trading-relevant signals, and provides an economic calendar, cross-asset context, and a review ledger.

It does not connect to a broker or place orders. Its purpose is to reduce low-value reading and help you record why a view was formed and what happened afterward.

### What it does

- Collects information from news, official, and market sources
- Filters content by watch terms, trading relevance, and a daily reading limit
- Structures the main driver, transmission path, counterargument, and invalidation conditions
- Shows important global economic events and exports an ICS calendar
- Stores a thesis ledger and reviews views against later market prices
- Provides a local Web UI for reading results and changing watch terms
- Runs the Web service and scheduler with Docker Compose

### Quick start with Docker

Docker Compose is the simplest option for a PC, NAS, or small Linux server.

1. Create the environment file:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` and provide at least:

   ```dotenv
   DEEPSEEK_API_KEY=your_key
   ```

3. Build and start:

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

4. Open:

   ```text
   http://127.0.0.1:8765
   ```

The service listens on the server's loopback address by default. For a remote server, use an SSH tunnel:

```bash
ssh -L 8765:127.0.0.1:8765 user@server
```

Then open `http://127.0.0.1:8765` on your computer.

### Run with local Python

Python 3.12 is recommended. Create and activate a virtual environment first:

```bash
python -m venv .venv
```

Linux or macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then install the dependencies and start TideBrief:

```bash
python -m pip install -r requirements.txt
python main.py run
python main.py ui
```

The UI is available at `http://127.0.0.1:8765`. Before the first collection run, it uses sample data to show the interface.

### Common commands

```bash
docker compose ps
docker compose logs -f scheduler
docker compose logs -f web
docker compose exec scheduler python main.py run
docker compose exec scheduler python main.py calendar-sync
docker compose down
```

### Configuration

The main settings are in `config.yaml`:

- `filter.prefilter.focus_keywords`: positions, sectors, commodities, or regions to prioritize
- `filter.max_daily_items`: maximum number of items shown each day
- `schedule.collect_time`: daily collection time
- `market.symbols`: cross-asset watch list
- `collectors`: individual data sources

Watch terms and reading limits can also be changed in the Web UI. Runtime settings are stored separately and do not overwrite the read-only main configuration.

### Data storage

Docker uses three named volumes:

- `tidebrief-data`: dashboard snapshots, calendar data, runtime status, and the SQLite thesis ledger
- `tidebrief-logs`: application logs
- `tidebrief-vault`: filtered articles and daily briefs

`docker compose down` keeps these volumes. Do not use `docker compose down -v` unless you intend to delete them.

For local Python runs, application data is stored in `data/` by default. The article and brief location is controlled by `vault.path` in `config.yaml`.

### Current limitations

- Some sources restrict data-center IP addresses, so collection depends on the server network
- U.S. BLS payroll, CPI, and PPI dates can sync automatically; some other regions still use a reviewed local schedule snapshot
- Model-generated summaries and interpretations can miss details; verify important items with the original source
- This project is for research and review, not investment advice

Further reading:

- [Server deployment, backup, and upgrades](docs/server-deployment.md)
- [Economic calendar scope and sources](docs/economic-calendar.md)
- [Architecture review and trade-offs](docs/architecture-review.md)
- [Iteration log](docs/iteration-log.md)

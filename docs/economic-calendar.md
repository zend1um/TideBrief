# 全球财经日历：筛选与维护说明

本日历不是把所有宏观数据搬进来，而是只保留可能改变利率路径、增长与通胀预期，或明显冲击全球风险偏好的事件。当前日程核对日期为 **2026-07-21**，页面统一显示 **北京时间（Asia/Shanghai）**。

## 重要性分级

### 一级事件

- 全球核心央行：美联储、欧洲央行、日本央行的利率决议；带经济预测或点阵图的会议尤其重要。
- 美国核心数据：非农就业、CPI、PCE、GDP。它们最容易同时改变美债、美元、美股与黄金的定价。
- 中国季度 GDP 与主要经济运行数据：直接影响人民币、A/H 股和工业品的增长预期。
- 欧元区 HICP 初值：是欧洲央行路径定价的主要月度输入。

### 二级事件

- 英国、加拿大、澳大利亚、新西兰、巴西央行决议：区域资产影响直接，也可验证全球政策周期是否同步。
- 中国 CPI/PPI、PMI、LPR 与月度经济运行数据：观察内需、价格、信用与政策传导。
- 美国 PPI：用于交叉验证 PCE 和企业利润率压力。

二级不代表可以忽略。若事件正好击中市场当时的主要矛盾，例如通胀重新加速或套息交易集中平仓，其实际影响可以临时升为一级。

## 盘前应该看什么

| 事件 | 不只看公布值，还要看 | 常见资产映射 |
|---|---|---|
| 央行决议 | 声明措辞、投票分歧、预测路径、发布会 | 国债、汇率、成长股、黄金 |
| CPI / PCE | 核心月率、服务与住房分项、前值修订 | 利率曲线、美元、股指 |
| 非农 | 失业率、时薪、参与率、前两月修订 | 美债、美元、美股、黄金 |
| GDP / 月度活动 | 内需结构、消费、投资、地产，而非只看总量 | 股指、周期品、工业金属 |
| PMI | 新订单、价格、就业与库存 | 周期股、铜、原油、人民币 |

## 覆盖范围与官方来源

- 美国：[Federal Reserve](https://www.federalreserve.gov/newsevents/calendar.htm)、[BLS](https://www.bls.gov/schedule/2026/home.htm)、[BEA](https://www.bea.gov/news/schedule/)
- 中国：[国家统计局 2026 年发布日程](https://www.stats.gov.cn/xw/tjxw/tzgg/202512/t20251224_1962137.html)、[中国货币网 LPR](https://www.chinamoney.com.cn/chinese/bklpr/)
- 欧洲与英国：[ECB](https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html)、[Eurostat](https://ec.europa.eu/eurostat/news/euro-indicators/release-calendar)、[Bank of England](https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates)
- 亚太：[Bank of Japan](https://www.boj.or.jp/en/mopo/mpmsche_minu/m_ref/mref250731a.pdf)、[RBA](https://www.rba.gov.au/schedules-events/board-meeting-schedules.html)、[RBNZ](https://www.rbnz.govt.nz/news-and-events/how-we-release-information/ocr-decision-dates-and-financial-stability-report-dates-to-feb-2028)
- 美洲其他地区：[Bank of Canada](https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/)、[Banco Central do Brasil](https://www.bcb.gov.br/en/about/bcb-calendar?categoria=Monetary+Policy+Committee+%28Copom%29)

## 数据与更新方式

- 页面每次刷新都会重新读取日历 JSON。服务器部署默认每周从 BLS 官方 ICS 自动校正非农、CPI 与 PPI。
- 央行和其他统计机构可能调整日期；这些非统一格式来源仍应每月末重新核对未来三个月，重大会议前再核对一次精确时间。
- 日本央行和巴西央行部分决议只确认了会议日，官方未固定发布时刻，因此页面与 ICS 中以全天“时间待定”事件处理。
- 可通过页面的“导入日历”下载 ICS 文件，导入系统日历、Outlook 或 Google Calendar。
- 自动同步失败时保留上一份成功快照，并在 `/api/status` 与页面状态中显示异常，不会用不完整结果覆盖日历。

## 暂不硬编码的观察项

美国 ISM、零售销售，中国贸易、社融，以及各国临时财政或政治会议仍可能很重要，但发布日期更易调整，或影响高度依赖当时市场主线。在官方精确日期未稳定确认前，它们更适合由每日信息流动态升级，而不是长期写死在核心日历中。

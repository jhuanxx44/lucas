# daily_stock_analysis 数据源备忘

本文记录 `/Users/jinghuan/code/open_source_projects/daily_stock_analysis` 中已经支持或预留的数据源，供 Lucas 后续扩展时参考。当前只做调研记录，不代表 Lucas 已经接入。

## 结论

`daily_stock_analysis` 的数据源设计偏“多源兜底 + 交易分析”，不是单一 provider。它把数据分成三条链路：

- 行情/财务数据：用于 K 线、实时行情、指数、板块、资金流、筹码、基本面。
- 新闻搜索：用于公告、舆情、催化、风险事件。
- 社交舆情：用于美股 Reddit / X / Polymarket 热度和情绪。

对 Lucas 最有价值的不是一次性接入所有源，而是先保留一个清单和统一接口边界。后续如果要增强数据能力，优先级建议是：

1. 搜索源增强：Tavily 之外补 SerpAPI / Bocha / Brave / SearXNG。
2. 行情兜底增强：在现有 AKShareProvider 外补 YFinance 和 Tushare。
3. A 股增强：再考虑 efinance / Pytdx / Baostock / TickFlow。
4. 美股/港股增强：需要实时量比、换手率、PE 等字段时再评估 Longbridge。

## 付费状态调研

更新时间：2026-05-08。价格、免费额度和商业授权会变，真正接入前需要再看官方页面。

### 明确有付费或高级权限

| 数据源 | 付费状态 | 备注 |
| --- | --- | --- |
| Tushare Pro | 免费低权限 + 积分/捐助/单独权限 | 官方文档说明 Pro 接口引入积分制度；120 积分档可取少量日线，2000/5000/10000 以上积分对应更高频次和更多接口，分钟、新闻舆情、公告、港美股等部分能力是单独权限。 |
| Longbridge | 基础 API/基础行情免费，高级行情付费 | 官方定价页写核心 API、Basic Market Data、REST/WS 推拉免费；US LV1、HK LV2、OPRA Options 等高级实时行情需要购买，且 OpenAPI 行情权限与 App/Web 权限独立。 |
| TickFlow | 历史日 K 免费；完整服务需注册/API Key，实时/分钟级属于完整服务 | 官方 quickstart 写免费服务无需注册，但只提供历史日 K、标的信息、交易所和标的池；实时行情、分钟 K 线和更高频访问使用完整服务。当前未在公开文档中看到稳定价格表。 |
| Bocha | 按量计费 | 用户服务协议明确 API 服务采用按量计费，余额不足可停止服务；平台可能赠送免费额度。 |
| Tavily | 免费额度 + 付费套餐/按量 | 官方文档写每月 1,000 免费 credits；付费套餐从 Project 起，另有 pay-as-you-go。 |
| SerpAPI | 免费额度 + 付费套餐 | 官方定价页写 Free 250 searches/month；付费套餐从 Starter 起。 |
| Brave Search API | 免费额度 + 付费套餐 | 官方页面存在新旧口径：英文页列 Free AI / Base / Pro，中文页显示搜索方案按 1000 次请求计费并含每月免费额度。接入前以控制台实际计划为准。 |
| MiniMax Search/API | 免费注册/额度 + 付费套餐或按量 | MiniMax 官方定价页有 Coding Plan、Token Plan、按量计费等；`daily_stock_analysis` 用 `MINIMAX_API_KEYS` 作为搜索源时应按其 API/套餐成本处理。 |
| Stock Sentiment API / Adanos | 免费额度 + 付费套餐；商业用途需 Pro | 官方定价页写 Free 250 requests/month 且不可商业使用；Hobby $29/month 仍不可商业；Professional $299/month 支持商业用途和 raw mention。 |
| Anspire Search / Anspire Open | 新用户免费点数 + 平台点数/付费倾向 | 官方首页写新用户赠送 2500 点，可体验任意产品；未在公开页看到完整价格表。接入前需要登录控制台或联系官方确认搜索调用单价。 |

主要依据：

- Tushare Pro：[官方积分频次表](https://www.tushare.pro/document/1?doc_id=290)、[接口权限表](https://tushare.pro/document/1?doc_id=108)。
- Longbridge：[Getting Started](https://open.longbridge.com/docs/getting-started)、[CLI quote 权限说明](https://open.longbridge.com/zh-HK/docs/cli/market-data/quote)。
- TickFlow：[官方 quickstart](https://docs.tickflow.org/zh-Hans/quickstart) 区分免费服务和完整服务。
- Bocha：[官方用户服务协议](https://open.bochaai.com/terms-of-service) 说明 API 按量计费。
- Tavily：[API credits/pricing](https://docs.tavily.com/guides/api-credits)。
- SerpAPI：[pricing](https://serpapi.com/pricing)。
- Brave Search API：[pricing](https://brave.com/search/api/)。
- MiniMax：[pricing overview](https://platform.minimax.io/docs/pricing/overview)、[token plan](https://platform.minimax.io/docs/guides/pricing-token-plan)。
- Stock Sentiment API / Adanos：[pricing](https://adanos.org/pricing)。
- Anspire：[Search Agent 文档](https://open.anspire.cn/document/docs/searchAgent/)、[平台使用教程](https://open.anspire.cn/document/docs/openPlatform/)。

### 免费或开源，但有使用边界

| 数据源 | 付费状态 | 备注 |
| --- | --- | --- |
| AkShare | 开源免费，无需 key | MIT 开源库；但它聚合第三方公开数据源，生产/商业用途需要自行确认上游条款和限流风险。 |
| efinance | 开源免费，但声明仅学习交流、不得商业使用 | GitHub README 明确“免费开源”，同时声明不得用于商业用途；适合个人研究，不适合 Lucas 商业化默认源。 |
| Pytdx | 开源免费/个人学习性质 | 项目偏通达信协议研究，已长期不维护；商业/生产使用风险高。 |
| Baostock | 免费，BSD License | PyPI 项目描述写 Free china stock market data；适合历史 A 股数据兜底。 |
| YFinance | 开源免费，但 Yahoo Finance 数据个人/研究用途限制 | yfinance 是开源库，但官方 PyPI 页面强调不隶属 Yahoo，实际下载数据要看 Yahoo 条款，Yahoo Finance API intended for personal use only。 |
| SearXNG | 免费开源，自托管有机器成本 | 官方文档写 free software / 100% open；如果用公共实例，稳定性不可控；自托管需要维护和服务器。 |

主要依据：

- AkShare：[GitHub 项目](https://github.com/akfamily/akshare) 和 MIT License。
- efinance：[GitHub README](https://github.com/Micro-sheep/efinance) 写免费开源，同时声明仅学习交流、不得商业使用。
- Pytdx：[PyPI 项目页](https://pypi.org/project/pytdx/1.60/) 说明为 TDX protocol 接口，最后发布停留在 2019 年。
- Baostock：[PyPI 项目页](https://pypi.org/project/baostock/) 说明 Free china stock market data，BSD License。
- YFinance：[PyPI 页面](https://pypi.org/project/yfinance/) 的法律免责声明。
- SearXNG：[官方文档](https://docs.searxng.org/) 说明 free internet metasearch engine，[GitHub](https://github.com/searxng/searxng) 为 AGPL-3.0。

### 对 Lucas 的成本判断

- 最低成本组合：AkShare + Tavily 免费额度 + DuckDuckGo/SearXNG fallback。
- 更稳的中文搜索组合：Tavily + Bocha 或 SerpAPI，但 Bocha/SerpAPI 都要按量成本预算。
- 更稳的 A 股数据组合：AkShare + Tushare。Tushare 应按“需要积分/捐助/权限”的付费源对待。
- 美股扩展优先：YFinance 适合研究原型，但商业/生产要谨慎；Longbridge 基础能力免费，高级实时行情要付费。
- 社交舆情：Adanos 免费额度只适合试验；商业用途直接按 Professional 级别评估。

## 行情与财务数据源

| 数据源 | daily_stock_analysis 用途 | 覆盖 | 配置 | 对 Lucas 的价值 |
| --- | --- | --- | --- | --- |
| AkShare | 默认免费数据源；A 股行情、K 线、指数、板块、部分基本面、资金流、名称解析 fallback | 主要 A 股，也有港股/美股部分接口 | 无需 key | Lucas 已使用，后续可补齐更多 AKShare 能力，但要注意爬虫限流 |
| efinance | 东方财富数据；实时行情、ETF、指数、市场涨跌统计、行业板块、基本信息、所属板块 | 主要 A 股/ETF | `EFINANCE_PRIORITY`, `EFINANCE_CALL_TIMEOUT`, `ENABLE_EASTMONEY_PATCH` | 可作为 A 股实时行情兜底，但全市场拉取容易限流，建议后置 |
| Tushare Pro | 更稳定的 A 股数据；日线、实时行情、股票列表、筹码、行业板块、部分基本面/资金流 | 主要 A 股，也可拉港股/美股列表 | `TUSHARE_TOKEN`, `TUSHARE_PRIORITY` | 值得预留。需要 token/积分，适合做可靠数据层 |
| Pytdx | 通达信数据；历史/实时行情备选 | 主要 A 股 | `PYTDX_PRIORITY`, `PYTDX_HOST`, `PYTDX_PORT`, `PYTDX_SERVERS` | 免费兜底源，可后置，适合 A 股行情冗余 |
| Baostock | 免费历史数据、股票名称/列表备选 | 主要 A 股 | `BAOSTOCK_PRIORITY` | 适合低成本历史数据兜底，不适合作为实时主链路 |
| YFinance | 美股历史与实时行情，美股指数；也可支持部分港股 | 美股/全球市场 | `YFINANCE_PRIORITY` | Lucas 如果扩到美股，应优先接入；免费且成熟 |
| Longbridge | 美股/港股兜底，补充 YFinance/AkShare 缺失的量比、换手率、PE 等字段 | 美股/港股 | `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, `LONGBRIDGE_ACCESS_TOKEN`, `LONGBRIDGE_*` | 价值高但配置重；等 Lucas 有明确美股/港股实时字段需求再接 |
| TickFlow | A 股大盘复盘增强：主要指数、市场涨跌统计；不参与个股日线/实时链路 | A 股市场宽度/指数 | `TICKFLOW_API_KEY` | 适合市场温度/宽度指标，不适合第一阶段通用接入 |

### daily_stock_analysis 的优先级规则

默认历史/日线数据源大致按以下顺序尝试：

```text
efinance -> akshare -> tushare / pytdx -> baostock -> yfinance -> longbridge
```

如果配置了 `TUSHARE_TOKEN`，Tushare 会被提升到高优先级。美股和港股另有专用路由：

- 美股/美股指数：优先 YFinance；配置 Longbridge 后，非指数美股可由 Longbridge 补充字段。
- 港股：未配置 Longbridge 时优先 AkShare；配置后 Longbridge 可作为首选或补充。
- TickFlow 只服务 A 股大盘复盘，不进入个股通用数据链路。

实时行情还有单独的 `REALTIME_SOURCE_PRIORITY`：

```text
tencent, akshare_sina, efinance, akshare_em
```

可选值包括 `tencent`、`akshare_sina`、`efinance`、`akshare_em`、`tushare`。`daily_stock_analysis` 默认倾向轻量单股查询优先，避免 efinance / akshare_em 全市场拉取导致限流。

## 新闻搜索源

| 搜索源 | daily_stock_analysis 用途 | 配置 | 对 Lucas 的价值 |
| --- | --- | --- | --- |
| Anspire Search | 中文实时智能搜索，A 股新闻和舆情增强 | `ANSPIRE_API_KEYS` | 如果已有账号，可作为中文搜索强源 |
| Bocha | 中文搜索优化，支持摘要 | `BOCHA_API_KEYS` | 对 A 股/中文研报新闻有价值 |
| Tavily | 通用搜索/新闻搜索 | `TAVILY_API_KEYS` | Lucas 已有 Tavily 单源逻辑，可继续保留 |
| Brave Search | 隐私优先，全球覆盖，美股资讯补强 | `BRAVE_API_KEYS` | 适合补美股/英文来源 |
| SerpAPI | 搜索引擎结果补强，实时金融新闻 | `SERPAPI_API_KEYS` | 实用但有额度限制；适合作为关键问题 fallback |
| MiniMax Search | 结构化搜索结果 | `MINIMAX_API_KEYS` | 如果模型供应商已经用 MiniMax，可顺手复用 |
| SearXNG | 自建/公共聚合搜索，无配额兜底 | `SEARXNG_BASE_URLS`, `SEARXNG_PUBLIC_INSTANCES_ENABLED` | 很适合 Lucas 私有化部署，但公共实例质量不稳定 |

`daily_stock_analysis` 的搜索服务按 provider 列表依次尝试，支持多 key 轮换、错误计数、窗口过滤。它还区分新闻时效：

- `NEWS_STRATEGY_PROFILE`: `ultra_short` / `short` / `medium` / `long`
- `NEWS_MAX_AGE_DAYS`: 新闻最大天数

Lucas 目前 `utils/web_search.py` 是 Tavily 优先、DuckDuckGo fallback。后续可以只扩 `utils/web_search.py`，不需要引入完整搜索服务大类。

## 社交舆情源

| 数据源 | daily_stock_analysis 用途 | 覆盖 | 配置 | 对 Lucas 的价值 |
| --- | --- | --- | --- | --- |
| Stock Sentiment API (`api.adanos.org`) | Reddit 个股报告、Reddit/X/Polymarket trending，格式化为 LLM 上下文 | 仅美股 | `SOCIAL_SENTIMENT_API_KEY`, `SOCIAL_SENTIMENT_API_URL` | 如果 Lucas 做美股主题/散户情绪，可以预留；A 股价值有限 |

该服务是可选增强。初始化失败或无 key 时跳过，不阻塞主分析流程。

## 基本面与资金流能力

`daily_stock_analysis` 在 `fundamental_adapter.py` 和 `DataFetcherManager.get_fundamental_context()` 里把 A 股基本面聚合成块：

- `valuation`
- `growth`
- `earnings`
- `institution`
- `capital_flow`
- `dragon_tiger`
- `boards`

它的策略是 fail-open：每个能力块有状态、错误、source chain 和超时预算，失败不会阻塞主报告。

Lucas 后续如果增强基本面，不建议直接搬这套复杂实现。更合适的最小接口是：

```python
class StockDataProvider:
    async def get_quote(...)
    async def get_kline(...)
    async def get_financials(...)
    async def get_north_flow(...)
    async def get_sector_flow(...)
```

然后逐步新增：

- `get_capital_flow(code)`
- `get_board_info(code)`
- `get_fundamental_snapshot(code)`

## 后续接入建议

### Phase 1：文档与接口预留

- 保留本文档。
- 在 `utils/stock_data.py` 的 provider 抽象旁补一段注释，标明未来 provider 可以来自 AKShare / YFinance / Tushare。
- 不新增配置项，不改调用链。

### Phase 2：搜索增强

- 扩展 `utils/web_search.py`，把搜索 provider 做成简单列表。
- 优先支持 `SERPAPI_API_KEYS`、`BOCHA_API_KEYS`、`BRAVE_API_KEYS`、`SEARXNG_BASE_URLS`。
- 保留 DuckDuckGo 作为无 key fallback。

### Phase 3：行情 provider 增强

- 新增 `YFinanceProvider`，优先解决美股/美股指数。
- 新增 `TushareProvider`，解决 A 股可靠性和股票列表。
- 只有出现明确实时字段需求时，再接 efinance / Longbridge。

### Phase 4：数据源治理

- 每条数据写入 evidence 时记录 provider、as_of、url/path、verification_status。
- 对外部数据源统一设置超时、缓存、失败降级。
- 测试里覆盖：无 key 降级、有 key 配置解析、provider 失败 fallback、不会写入 `raw/`。

## 参考的本地文件

- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/README.md`
- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/.env.example`
- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/docs/full-guide.md`
- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/data_provider/`
- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/src/search_service.py`
- `/Users/jinghuan/code/open_source_projects/daily_stock_analysis/src/services/social_sentiment_service.py`

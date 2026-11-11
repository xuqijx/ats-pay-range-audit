# ats-pay-range-audit

[English](#english) · [简体中文](#简体中文) · [繁體中文](#繁體中文) · [日本語](#日本語)

Local, read-only CLI. It asks the documented public job-board GET for Greenhouse, Ashby, or Lever whether each posting returned a **structured salary range**, and it can diff two snapshots. It is not a job matcher, not an application bot, and not a legal opinion.

This tree is **v0.1.1**. The selected date is still **2026-11-11**. The outer window named in the brief runs through **2026-11-18**. That date is not a publication. v0.1.0 was the first local package; v0.1.1 only fixes delivery (sdist contents, wheel example export, the documented Greenhouse query parameter). This checkout is not on PyPI, not deployed, and not a public board mirror.

## English

### What you get

You pass a list of boards you already know: a provider and the official slug (`boards.greenhouse.io/{token}` → `token`, `jobs.ashbyhq.com/{name}` → `name`, `jobs.lever.co/{site}` → `site`). The tool writes one row per posting: company, title, public URL, whether a structured range was present, and, when it was, min / max / currency / period or the provider's own summary string. `--save` writes a snapshot. `--diff` compares two snapshots for jobs added or removed and for range bounds that appeared, disappeared, or changed.

### What this is not

- Not legal advice. A present range is not "compliant." A missing range is not "unlawful." The API does not say which statute applies, how many people the employer has, or where the work is done.
- Not a fit score, an application queue, or an auto-apply client. There is no POST, no Greenhouse application call, and no API key.
- Not a scraper of LinkedIn, Indeed, Workday, or a careers HTML page. Salary numbers are never read out of a description, a Greenhouse `content` / `blurb`, or a Lever `salaryDescription` HTML blob.
- Not a hosted database of postings. Fixtures in this repository are fictional and labeled `"fictional": true`.

### How a row is classified

| observation | meaning | in the coverage denominator? |
| --- | --- | --- |
| `valid` | At least one salary bound is a real number (`min` and/or `max`). | yes |
| `explicit_empty` | The documented field was returned and is null, `{}`, `[]`, summary text only, or has no numeric salary bound. An empty compensation object is this, not a valid range. `structured_range` is `absent`. | yes |
| `unknown` | The documented field was not observed. This is **not** "the employer published no pay." | no |
| `error` | The GET, the JSON parse, or the schema failed, including HTTP 429 after retries. | no |

`structured_range` is `present` only for `valid`. Coverage `ratio` is `valid / (valid + explicit_empty)`. If that denominator is 0, `ratio` and `percent` are null. **Null is not 0%.** Unknown rows stay visible in `coverage.unknown` so a partial fetch cannot be read as a low coverage rate.

Reasons are separate from the four observations. `null`, `empty_object`, `empty_array`, `summary_only`, `no_numeric_bounds`, and `no_salary_component` are all `explicit_empty`, but they are not the same event. `field_not_in_response` and `detail_budget_exhausted` are `unknown`.

Lever is the exception inside `explicit_empty`: `salaryRange` is an optional field **on the list payload the docs describe**. Omitting it is reason `field_omitted` and `structured_range=absent`. `absent` names that missing structured object. It does not say the employer published no pay, and it is not a legal conclusion. Greenhouse's list payload does **not** document a pay field, so a missing key there is never used, and a missing key on the **detail** response is `unknown`, not absent.

Only a component whose type is `Salary` counts for Ashby. Equity, bonus, and commission do not. `0` is a real bound. `"$80,000"` and `"81K"` are not parsed into numbers. Official summary strings are copied through and are not scanned.

### Endpoints this tool actually calls

Checked against the vendor documents on 2026-11-11. Only these GETs are built. A board file cannot pass a URL, a host, or a base URL.

**Greenhouse.** [Job Board API](https://docs.greenhouse.io/job-board) documents:

- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` with optional `content=true` only. The list sample has no `pay_input_ranges`.
- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?pay_transparency=true` adds `pay_input_ranges` (`min_cents`, `max_cents`, `currency_type`, `title`, `blurb`).

The Job Board API query table for Retrieve a job lists `pay_transparency` only. `pay_input_ranges` in that sentence is the response array. The support article [Add pay transparency to a job post](https://support.greenhouse.io/hc/en-us/articles/10028084062491-Add-pay-transparency-to-a-job-post) (updated 2026-03-02) also writes the words `pay_transparency` and/or `pay_input_ranges` on **Retrieve a job**, not on List jobs. That article does not add `pay_input_ranges` to the API parameter table. This tool sends only `pay_transparency=true` on the detail GET. It does not send `pay_input_ranges` as a query parameter, does not send either name on the list GET, and **ignores** `pay_input_ranges` if a list item contains them. A list that omits the key, or shows an empty array, is not evidence of no salary. Cents are converted to major units with integer arithmetic. `blurb` and `content` are not parsed. The authenticated Harvest API is not called.

If the detail object has no `pay_input_ranges` key, the row is `unknown` / `field_not_in_response`. Null, `[]`, `{}`, or entries without numeric cents are `explicit_empty`.

Whether some live list URLs also echo `pay_input_ranges` was **not** re-tested here and is **not** a source of truth. Third-party notes that the undocumented list parameter sometimes works are clues, not the contract this tool uses.

**Ashby.** [Public job posting API](https://developers.ashbyhq.com/docs/public-job-posting-api):

`GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`

The field table places compensation on `jobs[].compensation`. A top-level `compensation` object is not copied onto jobs. A missing `compensation` key is `unknown`. Null and `{}` are `explicit_empty`. Numeric `minValue` / `maxValue` on a `Salary` component are the range. Tier rows win over `summaryComponents` when both contain Salary, so an aggregate cannot double-count or override a tier.

**Lever.** [postings-api README](https://github.com/lever/postings-api):

- `GET https://api.lever.co/v0/postings/{site}?mode=json`
- EU: `GET https://api.eu.lever.co/v0/postings/{site}?mode=json` when `region: eu`

`salaryRange` is `{currency, interval, min, max}` and is optional on that list. The same fields exist on the single-posting GET; this tool does not need it because the list already documents the field. Description HTML is not parsed. Application POST is not implemented.

### Pace, failures, and bounds

Live calls are serial. Floors, which `--min-interval` cannot lower: Greenhouse 0.5s, Ashby 0.5s, Lever 1.0s. On 2026-11-11, `https://api.lever.co/robots.txt` said `Crawl-delay: 1`. Greenhouse's robots file disallowed only `/embed/` and set no crawl-delay; the 0.5s floor is still applied because detail fan-out is many calls. `https://api.ashbyhq.com/robots.txt` returned 401, so no crawl-delay was published there. Ashby is one GET per board.

HTTP 429 retries up to 3 times, honoring a delta-seconds `Retry-After` capped at 30s, otherwise waiting 1s, 2s, then 4s. After that the row or board is `error` / `http_429`, never an empty range. Other HTTP statuses and redirects are not retried and not followed. Bodies over 8 MiB are errors. `--max-details` (default 500, `-1` uncapped, max 10000) limits Greenhouse retrieve-a-job calls. Jobs past the cap are `unknown` / `detail_budget_exhausted`, not "no pay." Offline fixtures do not sleep and do not open a socket. Network stays off unless you pass `--live` and a board has no `fixture`.

### Install

Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
ats-pay-range-audit --help
pytest
```

`pytest` does not use the network. Dev extra: `pip install ".[dev]"`. `pyproject.toml` sets `addopts = "-q"`, so `python3 -m pytest` is quiet. Test names: `python3 -m pytest -v --override-ini=addopts=`.

### Where the examples live

The source distribution contains `fixtures/` and `examples/` next to `tests/`. Unpack the sdist and run `python3 -m pytest` in that directory. The default tests stay offline.

The wheel does not put those files on the shell path. After install:

```bash
ats-pay-range-audit --write-examples ./audit-examples
ats-pay-range-audit ./audit-examples/examples/ashby-all-ranges.yaml --json
```

`--write-examples` copies the same fictional files and exits. It does not fetch a board.

### Commands

```bash
ats-pay-range-audit examples/ashby-all-ranges.yaml --json
ats-pay-range-audit examples/greenhouse-key-present-empty.yaml --json
ats-pay-range-audit examples/lever-no-structured-field.yaml --json
ats-pay-range-audit examples/ashby-all-ranges.yaml --save snapshot.json
ats-pay-range-audit --diff snapshot.json snapshot-later.json --json
```

Board file (`token`, `slug`, and `site` are aliases of `board`; do not also pass a URL):

```yaml
boards:
  - provider: greenhouse
    board: your-board-token
    name: Your company
  - provider: ashby
    board: your-jobs-page-name
    name: Your company
  - provider: lever
    board: your-site
    region: global   # or eu
    name: Your company
```

Add `fixture: path/to/file.json` to replay a local book. Without a fixture, add `--live`.

Exit codes: `0` the run finished (coverage may be 0 or undefined); `1` a request, parse, or snapshot-schema error; `2` usage or local IO, including a refused symlink write.

`--save` writes the full JSON to a temp file in the same directory and `os.replace`s it into place. A failed replace leaves the previous file. Symlinks are refused.

`--diff` lists `bounds_changed` (min, max, currency, or period, both sides `valid`), `became_valid`, `became_empty`, `jobs_added`, `jobs_removed`, `newly_observed` (unknown/error then valid — not proof the employer added a range), and `unresolved` (a valid range that became unknown or error is not reported as removed). Rows are sorted by provider, board, then job id.

### Fixtures

Every JSON file under `fixtures/` is synthetic. `examples/*.yaml` points at them. `fixtures/diff-range-changed/` is a pair of snapshots, not a live recording. `fixtures/http-429.json` replays 429 and must surface as an error.

## 简体中文

### 它做什么

你提供已经知道的公开看板：供应商，加上官方 slug（`boards.greenhouse.io/{token}` 的 `token`，`jobs.ashbyhq.com/{name}` 的 `name`，`jobs.lever.co/{site}` 的 `site`）。工具为每条职位写一行：公司、标题、公开 URL、有没有结构化薪资区间；有的话给出 min / max / 货币 / 周期，或供应商自己的 summary。`--save` 写快照。`--diff` 比较两次快照里的职位新增、下线，以及区间出现、消失或上下限变化。

### 它不做什么

- 不是法律意见。有区间不等于「已合规」，没有区间不等于「违法」。接口看不出适用哪条法律、雇主人数、工作地点。
- 不是匹配打分、不是投递队列、不是自动申请。没有 POST，不调用 Greenhouse 申请接口，不使用 API 密钥。
- 不抓 LinkedIn、Indeed、Workday 或招聘页 HTML。不会从职位描述、Greenhouse 的 `content` / `blurb`、Lever 的 `salaryDescription` HTML 里抠数字。
- 不建公开职位库。本仓库夹具都是虚构的，并标了 `"fictional": true`。

### 一行如何定性

| observation | 含义 | 是否进入覆盖率分母 |
| --- | --- | --- |
| `valid` | 至少有一个真实数字上下限（`min` 和/或 `max`）。 | 是 |
| `explicit_empty` | 文档化字段返回了，但是 null、`{}`、`[]`、只有 summary，或没有数字薪资界限。空 compensation 对象属于这一类，不是有效薪资。`structured_range` 为 `absent`。 | 是 |
| `unknown` | 没有观察到文档化字段。这**不是**「雇主没有公布薪资」。 | 否 |
| `error` | GET、JSON 或 schema 失败，包括重试后仍为 HTTP 429。 | 否 |

只有 `valid` 的 `structured_range` 才是 `present`。覆盖率 `ratio` = `valid / (valid + explicit_empty)`。分母为 0 时，`ratio` 和 `percent` 为 null。**null 不是 0%。** `coverage.unknown` 单独列出，避免一次没抓全的详情被读成很低的覆盖率。

原因码和这四类不是一回事。`null`、`empty_object`、`empty_array`、`summary_only`、`no_numeric_bounds`、`no_salary_component` 都是 `explicit_empty`，但事件不同。`field_not_in_response` 和 `detail_budget_exhausted` 是 `unknown`。

Lever 在 `explicit_empty` 里有一个例外：文档把可选字段 `salaryRange` 放在**列表响应**上。缺这个键是 `field_omitted`，`structured_range=absent`。`absent` 只表示这份结构化对象不在响应里，不是「雇主没有公布薪资」，也不是违法结论。Greenhouse 的列表文档**没有**薪资字段，所以列表上的缺键一律不用；**详情**响应里缺 `pay_input_ranges` 键是 `unknown`，不是 absent。

Ashby 只把 `compensationType` 为 `Salary` 的组件算作薪资。股权、奖金、佣金不算。`0` 是有效界限。`"$80,000"` 和 `"81K"` 不会被扫成数字。官方 summary 会原样保留，不从中提取金额。

### 实际调用的端点

2026-11-11 对照厂商文档。程序只构造下面这些 GET。看板文件不能填写 URL、主机或 base URL。

**Greenhouse。** [Job Board API](https://docs.greenhouse.io/job-board) 写明：

- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` 的可选查询参数只有 `content=true`。列表示例没有 `pay_input_ranges`。
- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?pay_transparency=true` 才会带上 `pay_input_ranges`（`min_cents`、`max_cents`、`currency_type`、`title`、`blurb`）。

Job Board API 的详情查询参数表只列了 `pay_transparency`。同一句里的 `pay_input_ranges` 是返回数组。支持文章 [Add pay transparency to a job post](https://support.greenhouse.io/hc/en-us/articles/10028084062491-Add-pay-transparency-to-a-job-post)（2026-03-02 更新）也写了 `pay_transparency` 和/或 `pay_input_ranges` 用在 **Retrieve a job**，不是 List jobs。该文没有把 `pay_input_ranges` 加进 API 参数表。本工具的详情 GET 只带 `pay_transparency=true`，不把 `pay_input_ranges` 当作查询参数，列表 GET 两个名字都不带，并且**忽略**列表项里就算出现了的 `pay_input_ranges`。列表没这个键，或给了空数组，都不能当成没有薪资。美分用整数除法换成主单位。不解析 `blurb` 和 `content`。不调用需要认证的 Harvest。

详情对象没有 `pay_input_ranges` 键时，该行是 `unknown` / `field_not_in_response`。null、`[]`、`{}`，或条目里没有数字美分，是 `explicit_empty`。

未写入文档的列表参数在真实看板上会不会偶尔带回 `pay_input_ranges`，这里**没有**复测，也**不当**作依据。第三方说这个未文档化参数有时能用，只是线索，不是本工具采用的契约。

**Ashby。** [公开职位 API](https://developers.ashbyhq.com/docs/public-job-posting-api)：

`GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`

字段表把薪酬放在 `jobs[].compensation`。顶层 `compensation` 不会抄到每条职位上。缺少 `compensation` 键是 `unknown`。null 和 `{}` 是 `explicit_empty`。`Salary` 组件上的数字 `minValue` / `maxValue` 才是区间。层级和 `summaryComponents` 都有 Salary 时以层级为准，避免汇总行重复计算或覆盖层级。

**Lever。** [postings-api README](https://github.com/lever/postings-api)：

- `GET https://api.lever.co/v0/postings/{site}?mode=json`
- `region: eu` 时用 `GET https://api.eu.lever.co/v0/postings/{site}?mode=json`

`salaryRange` 是可选对象 `{currency, interval, min, max}`，就在这份列表里。单条职位 GET 的字段相同；列表已经文档化该字段，所以不再逐条请求。不解析描述 HTML。不实现申请 POST。

### 速度、失败与上限

在线请求串行。`--min-interval` 不能低于这些下限：Greenhouse 0.5 秒，Ashby 0.5 秒，Lever 1.0 秒。2026-11-11 读取 `https://api.lever.co/robots.txt`，其中有 `Crawl-delay: 1`。Greenhouse 的 robots 只禁止 `/embed/`，没有 crawl-delay；因为详情是逐条请求，仍然保留 0.5 秒。`https://api.ashbyhq.com/robots.txt` 返回 401，没有读到 crawl-delay。Ashby 每个看板一次 GET。

HTTP 429 最多再试 3 次。若 `Retry-After` 是秒数，则遵守并封顶 30 秒；否则依次等待 1、2、4 秒。用尽后记 `error` / `http_429`，不会记成空区间。其他 HTTP 状态不重试。重定向不跟随。正文超过 8 MiB 算错误。`--max-details`（默认 500，`-1` 不封顶，最大 10000）只限制 Greenhouse 的职位详情次数。超出的职位是 `unknown` / `detail_budget_exhausted`，不是「没有薪资」。离线夹具不休眠、不开网络。没有 `fixture` 的看板必须加上 `--live` 才会请求网络。

### 安装

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
ats-pay-range-audit --help
pytest
```

`pytest` 不访问网络。开发依赖：`pip install ".[dev]"`。`pyproject.toml` 里 `addopts = "-q"`，所以 `python3 -m pytest` 是安静输出。要测试名：`python3 -m pytest -v --override-ini=addopts=`。

### 示例在哪

源码包里 `fixtures/` 和 `examples/` 与 `tests/` 并列。解开 sdist 后在该目录运行 `python3 -m pytest`。默认测试保持断网。

wheel 不会把这些文件放到 shell 路径上。安装后：

```bash
ats-pay-range-audit --write-examples ./audit-examples
ats-pay-range-audit ./audit-examples/examples/ashby-all-ranges.yaml --json
```

`--write-examples` 只复制同一批虚构文件然后退出，不请求看板。

### 命令

```bash
ats-pay-range-audit examples/ashby-all-ranges.yaml --json
ats-pay-range-audit examples/greenhouse-key-present-empty.yaml --json
ats-pay-range-audit examples/lever-no-structured-field.yaml --json
ats-pay-range-audit examples/ashby-all-ranges.yaml --save snapshot.json
ats-pay-range-audit --diff snapshot.json snapshot-later.json --json
```

看板文件（`token`、`slug`、`site` 都是 `board` 的别名；不要另给 URL）：

```yaml
boards:
  - provider: greenhouse
    board: your-board-token
    name: Your company
  - provider: ashby
    board: your-jobs-page-name
    name: Your company
  - provider: lever
    board: your-site
    region: global   # 或 eu
    name: Your company
```

本地回放写 `fixture: path/to/file.json`。没有 fixture 时加上 `--live`。

退出码：`0` 跑完（覆盖率可以是 0，也可以是未定义）；`1` 请求、解析或快照 schema 错误；`2` 用法或本地 IO，包括拒绝写入符号链接。

`--save` 先把完整 JSON 写到同一目录的临时文件，再用 `os.replace` 换上。替换失败时原文件还在。符号链接会被拒绝。

`--diff` 报告 `bounds_changed`（两边都是 `valid`，且 min、max、货币或周期变了）、`became_valid`、`became_empty`、`jobs_added`、`jobs_removed`、`newly_observed`（先前是 unknown 或 error，现在才是 valid，不能证明雇主新增了区间）、`unresolved`（valid 变成 unknown 或 error 时，不把它说成区间被删除）。行按 provider、board、job id 排序。

### 夹具

`fixtures/` 下每个 JSON 都是合成数据。`examples/*.yaml` 指向它们。`fixtures/diff-range-changed/` 是一对快照，不是实况录制。`fixtures/http-429.json` 回放 429，结果必须是错误，而不是空区间。

## 繁體中文

### 它做什麼

你提供已知的公開看板：供應者，加上官方 slug（`boards.greenhouse.io/{token}` 的 `token`，`jobs.ashbyhq.com/{name}` 的 `name`，`jobs.lever.co/{site}` 的 `site`）。工具為每則職缺寫一列：公司、標題、公開 URL、有沒有結構化薪資區間；有的話給出 min / max / 貨幣 / 週期，或供應者自己的 summary。`--save` 寫快照。`--diff` 比較兩次快照的職缺新增、下線，以及區間出現、消失或上下限變更。

### 它不做什麼

- 不是法律意見。有區間不等於「已合規」，沒有區間不等於「違法」。介面看不出適用哪條法律、雇主人數、工作地點。
- 不是匹配評分、不是投遞佇列、不是自動申請。沒有 POST，不呼叫 Greenhouse 申請介面，不使用 API 金鑰。
- 不抓 LinkedIn、Indeed、Workday 或招募頁 HTML。不會從職缺描述、Greenhouse 的 `content` / `blurb`、Lever 的 `salaryDescription` HTML 裡挖數字。
- 不建公開職缺庫。本倉庫夾具都是虛構的，並標了 `"fictional": true`。

### 一列如何定性

| observation | 含義 | 是否進入覆蓋率分母 |
| --- | --- | --- |
| `valid` | 至少有一個真實數字上下限（`min` 與／或 `max`）。 | 是 |
| `explicit_empty` | 文件化欄位有回傳，但是 null、`{}`、`[]`、只有 summary，或沒有數字薪資界限。空 compensation 物件屬於這一類，不是有效薪資。`structured_range` 為 `absent`。 | 是 |
| `unknown` | 沒有觀察到文件化欄位。這**不是**「雇主沒有公布薪資」。 | 否 |
| `error` | GET、JSON 或 schema 失敗，包括重試後仍為 HTTP 429。 | 否 |

只有 `valid` 的 `structured_range` 才是 `present`。覆蓋率 `ratio` = `valid / (valid + explicit_empty)`。分母為 0 時，`ratio` 與 `percent` 為 null。**null 不是 0%。** `coverage.unknown` 單獨列出，避免一次沒抓全的詳情被讀成很低的覆蓋率。

原因碼和這四類不是同一件事。`null`、`empty_object`、`empty_array`、`summary_only`、`no_numeric_bounds`、`no_salary_component` 都是 `explicit_empty`，但事件不同。`field_not_in_response` 與 `detail_budget_exhausted` 是 `unknown`。

Lever 在 `explicit_empty` 裡有一個例外：文件把可選欄位 `salaryRange` 放在**清單回應**上。缺這個鍵是 `field_omitted`，`structured_range=absent`。`absent` 只表示這份結構化物件不在回應裡，不是「雇主沒有公布薪資」，也不是違法結論。Greenhouse 的清單文件**沒有**薪資欄位，所以清單上的缺鍵一律不用；**詳情**回應裡缺 `pay_input_ranges` 鍵是 `unknown`，不是 absent。

Ashby 只把 `compensationType` 為 `Salary` 的元件算作薪資。股權、獎金、佣金不算。`0` 是有效界限。`"$80,000"` 與 `"81K"` 不會被掃成數字。官方 summary 會原樣保留，不從中提取金額。

### 實際呼叫的端點

2026-11-11 對照廠商文件。程式只構造下面這些 GET。看板檔不能填寫 URL、主機或 base URL。

**Greenhouse。** [Job Board API](https://docs.greenhouse.io/job-board) 寫明：

- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` 的可選查詢參數只有 `content=true`。清單範例沒有 `pay_input_ranges`。
- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?pay_transparency=true` 才會帶上 `pay_input_ranges`（`min_cents`、`max_cents`、`currency_type`、`title`、`blurb`）。

Job Board API 的詳情查詢參數表只列了 `pay_transparency`。同一句裡的 `pay_input_ranges` 是回傳陣列。支援文章 [Add pay transparency to a job post](https://support.greenhouse.io/hc/en-us/articles/10028084062491-Add-pay-transparency-to-a-job-post)（2026-03-02 更新）也寫了 `pay_transparency` 與／或 `pay_input_ranges` 用在 **Retrieve a job**，不是 List jobs。該文沒有把 `pay_input_ranges` 加進 API 參數表。本工具的詳情 GET 只帶 `pay_transparency=true`，不把 `pay_input_ranges` 當作查詢參數，清單 GET 兩個名字都不帶，並且**忽略**清單項目裡就算出現了的 `pay_input_ranges`。清單沒這個鍵，或給了空陣列，都不能當成沒有薪資。美分用整數除法換成主單位。不解析 `blurb` 與 `content`。不呼叫需要認證的 Harvest。

詳情物件沒有 `pay_input_ranges` 鍵時，該列是 `unknown` / `field_not_in_response`。null、`[]`、`{}`，或項目裡沒有數字美分，是 `explicit_empty`。

未寫入文件的清單參數在真實看板上會不會偶爾帶回 `pay_input_ranges`，這裡**沒有**複測，也**不當**作依據。

**Ashby。** [公開職缺 API](https://developers.ashbyhq.com/docs/public-job-posting-api)：

`GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`

欄位表把薪酬放在 `jobs[].compensation`。頂層 `compensation` 不會抄到每則職缺上。缺少 `compensation` 鍵是 `unknown`。null 與 `{}` 是 `explicit_empty`。`Salary` 元件上的數字 `minValue` / `maxValue` 才是區間。層級與 `summaryComponents` 都有 Salary 時以層級為準。

**Lever。** [postings-api README](https://github.com/lever/postings-api)：

- `GET https://api.lever.co/v0/postings/{site}?mode=json`
- `region: eu` 時用 `GET https://api.eu.lever.co/v0/postings/{site}?mode=json`

`salaryRange` 是可選物件 `{currency, interval, min, max}`，就在這份清單裡。不解析描述 HTML。不實作申請 POST。

### 速度、失敗與上限

線上請求依序發送。`--min-interval` 不能低於：Greenhouse 0.5 秒，Ashby 0.5 秒，Lever 1.0 秒。2026-11-11 讀取 `https://api.lever.co/robots.txt`，其中有 `Crawl-delay: 1`。Greenhouse 的 robots 只禁止 `/embed/`，沒有 crawl-delay；因為詳情是逐則請求，仍然保留 0.5 秒。`https://api.ashbyhq.com/robots.txt` 回 401，沒有讀到 crawl-delay。Ashby 每個看板一次 GET。

HTTP 429 最多再試 3 次。若 `Retry-After` 是秒數，則遵守並封頂 30 秒；否則依序等待 1、2、4 秒。用盡後記 `error` / `http_429`，不會記成空區間。其他 HTTP 狀態不重試。重新導向不跟隨。本文超過 8 MiB 算錯誤。`--max-details`（預設 500，`-1` 不封頂，最大 10000）只限制 Greenhouse 的職缺詳情次數。超出的職缺是 `unknown` / `detail_budget_exhausted`，不是「沒有薪資」。離線夾具不休眠、不開網路。沒有 `fixture` 的看板必須加上 `--live` 才會請求網路。

### 安裝

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
ats-pay-range-audit --help
pytest
```

`pytest` 不存取網路。開發依賴：`pip install ".[dev]"`。`pyproject.toml` 裡 `addopts = "-q"`，所以 `python3 -m pytest` 是安靜輸出。要測試名：`python3 -m pytest -v --override-ini=addopts=`。

### 範例在哪

源碼包裡 `fixtures/` 與 `examples/` 和 `tests/` 並列。解開 sdist 後在該目錄執行 `python3 -m pytest`。預設測試保持斷網。

wheel 不會把這些檔案放到 shell 路徑上。安裝後：

```bash
ats-pay-range-audit --write-examples ./audit-examples
ats-pay-range-audit ./audit-examples/examples/ashby-all-ranges.yaml --json
```

`--write-examples` 只複製同一批虛構檔案然後結束，不請求看板。

### 命令

```bash
ats-pay-range-audit examples/ashby-all-ranges.yaml --json
ats-pay-range-audit examples/greenhouse-key-present-empty.yaml --json
ats-pay-range-audit examples/lever-no-structured-field.yaml --json
ats-pay-range-audit examples/ashby-all-ranges.yaml --save snapshot.json
ats-pay-range-audit --diff snapshot.json snapshot-later.json --json
```

看板檔（`token`、`slug`、`site` 都是 `board` 的別名；不要另給 URL）：

```yaml
boards:
  - provider: greenhouse
    board: your-board-token
    name: Your company
  - provider: ashby
    board: your-jobs-page-name
    name: Your company
  - provider: lever
    board: your-site
    region: global   # 或 eu
    name: Your company
```

本機重放寫 `fixture: path/to/file.json`。沒有 fixture 時加上 `--live`。

結束碼：`0` 跑完（覆蓋率可以是 0，也可以是未定義）；`1` 請求、解析或快照 schema 錯誤；`2` 用法或本機 IO，包括拒絕寫入符號連結。

`--save` 先把完整 JSON 寫到同一目錄的暫存檔，再用 `os.replace` 換上。替換失敗時原檔還在。符號連結會被拒絕。

`--diff` 報告 `bounds_changed`（兩邊都是 `valid`，且 min、max、貨幣或週期變了）、`became_valid`、`became_empty`、`jobs_added`、`jobs_removed`、`newly_observed`（先前是 unknown 或 error，現在才是 valid，不能證明雇主新增了區間）、`unresolved`（valid 變成 unknown 或 error 時，不把它說成區間被刪除）。列按 provider、board、job id 排序。

### 夾具

`fixtures/` 下每個 JSON 都是合成資料。`examples/*.yaml` 指向它們。`fixtures/diff-range-changed/` 是一對快照，不是實況錄製。`fixtures/http-429.json` 重放 429，結果必須是錯誤，而不是空區間。

## 日本語

### 何をするか

知っている公開求人ボードを渡します。プロバイダと公式 slug です（`boards.greenhouse.io/{token}` の `token`、`jobs.ashbyhq.com/{name}` の `name`、`jobs.lever.co/{site}` の `site`）。投稿ごとに 1 行出します。会社、職名、公開 URL、構造化された給与レンジがあるか。ある場合は min / max / 通貨 / 周期、またはプロバイダ自身の summary です。`--save` はスナップショットを書きます。`--diff` は求人の追加と終了、レンジの出現・消滅・上下限の変化を比べます。

### 何をしないか

- 法律意見ではありません。レンジがあることは「適合」ではなく、ないことは「違法」ではありません。どの法令が適用されるか、雇用者の人数、勤務地は API からは分かりません。
- 適合スコア、応募キュー、自動応募ではありません。POST はなく、Greenhouse の応募 API も API キーも使いません。
- LinkedIn、Indeed、Workday、採用ページの HTML は取りません。募集要項、Greenhouse の `content` / `blurb`、Lever の `salaryDescription` HTML から金額を抜きません。
- 公開の求人データベースは作りません。このリポジトリのフィクスチャは架空で、`"fictional": true` と書いてあります。

### 行の分け方

| observation | 意味 | カバレッジの分母に入るか |
| --- | --- | --- |
| `valid` | 給与の下限または上限が実数である（`min` と／または `max`）。 | 入る |
| `explicit_empty` | 文書化されたフィールドは返ったが、null、`{}`、`[]`、summary だけ、または数値の給与境界がない。空の compensation オブジェクトはこれに当たり、有効な給与ではない。`structured_range` は `absent`。 | 入る |
| `unknown` | 文書化されたフィールドを観測していない。これは**「雇用者が給与を出していない」ではない**。 | 入らない |
| `error` | GET、JSON、schema の失敗。再試行後の HTTP 429 を含む。 | 入らない |

`structured_range` が `present` になるのは `valid` だけです。`ratio` は `valid / (valid + explicit_empty)` です。分母が 0 のとき `ratio` と `percent` は null です。**null は 0% ではありません。** `coverage.unknown` は別に出るので、詳細を取り切れていない実行を低いカバー率と読み違えません。

理由コードは四つの observation とは別です。`null`、`empty_object`、`empty_array`、`summary_only`、`no_numeric_bounds`、`no_salary_component` はどれも `explicit_empty` ですが、別の出来事です。`field_not_in_response` と `detail_budget_exhausted` は `unknown` です。

Lever だけ `explicit_empty` の中に例外があります。任意フィールド `salaryRange` は**一覧ペイロード**に文書化されています。キーが無いときは `field_omitted` で、`structured_range=absent` です。`absent` は構造化オブジェクトが応答に無い、という意味です。雇用者が給与を出していないという判定ではなく、法律上の結論でもありません。Greenhouse の一覧は給与フィールドを文書化していないので、一覧側の欠落は使いません。**詳細**応答に `pay_input_ranges` キーが無いときは `unknown` であり、absent ではありません。

Ashby で給与として数えるのは `compensationType` が `Salary` の要素だけです。株式、賞与、歩合は数えません。`0` は有効な境界です。`"$80,000"` や `"81K"` は数値にしません。公式 summary はそのまま残し、金額としては読みません。

### 実際に呼ぶエンドポイント

2026-11-11 にベンダー文書と照合しました。作る GET は次だけです。ボードファイルに URL、ホスト、base URL は渡せません。

**Greenhouse。** [Job Board API](https://docs.greenhouse.io/job-board) の記載:

- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` の任意クエリは `content=true` だけです。一覧の例に `pay_input_ranges` はありません。
- `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?pay_transparency=true` が `pay_input_ranges`（`min_cents`、`max_cents`、`currency_type`、`title`、`blurb`）を足します。

Job Board API の詳細クエリ表に載っている名前は `pay_transparency` だけです。同じ文の `pay_input_ranges` は応答の配列です。サポート記事 [Add pay transparency to a job post](https://support.greenhouse.io/hc/en-us/articles/10028084062491-Add-pay-transparency-to-a-job-post)（2026-03-02 更新）も `pay_transparency` と／または `pay_input_ranges` を **Retrieve a job** に書いており、List jobs には書いていません。その記事は API のパラメータ表に `pay_input_ranges` を追加していません。このツールの詳細 GET は `pay_transparency=true` だけを送り、`pay_input_ranges` をクエリにはしません。一覧 GET にはどちらも付けず、一覧項目に `pay_input_ranges` があっても**無視**します。一覧にキーが無いこと、空配列であることは、給与が無い証拠ではありません。セントは整数演算で主単位にします。`blurb` と `content` は解析しません。認証が要る Harvest は呼びません。

詳細オブジェクトに `pay_input_ranges` キーが無い行は `unknown` / `field_not_in_response` です。null、`[]`、`{}`、数値セントの無い要素は `explicit_empty` です。

文書に無い一覧パラメータが実ボードで `pay_input_ranges` を返すことがあるか、ここでは**再試験しておらず**、根拠にも**しません**。

**Ashby。** [公開求人 API](https://developers.ashbyhq.com/docs/public-job-posting-api):

`GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`

フィールド表は報酬を `jobs[].compensation` に置いています。トップレベルの `compensation` は各求人へコピーしません。`compensation` キーが無いときは `unknown` です。null と `{}` は `explicit_empty` です。`Salary` 要素の数値 `minValue` / `maxValue` がレンジです。階層と `summaryComponents` の両方に Salary があるときは階層を採用し、集計行で二重に数えたり上書きしたりしません。

**Lever。** [postings-api README](https://github.com/lever/postings-api):

- `GET https://api.lever.co/v0/postings/{site}?mode=json`
- `region: eu` のとき `GET https://api.eu.lever.co/v0/postings/{site}?mode=json`

`salaryRange` は任意オブジェクト `{currency, interval, min, max}` で、この一覧にあります。説明 HTML は解析しません。応募 POST は実装しません。

### 速度、失敗、上限

ライブの呼び出しは直列です。`--min-interval` で下げられない床は Greenhouse 0.5 秒、Ashby 0.5 秒、Lever 1.0 秒です。2026-11-11 時点の `https://api.lever.co/robots.txt` は `Crawl-delay: 1` でした。Greenhouse の robots は `/embed/` だけを禁止し、crawl-delay はありません。詳細は件数分の GET なので 0.5 秒は残しています。`https://api.ashbyhq.com/robots.txt` は 401 で、crawl-delay は読めませんでした。Ashby はボードあたり 1 回の GET です。

HTTP 429 は最大 3 回再試行します。`Retry-After` が秒数ならそれに従い、上限は 30 秒です。無ければ 1 秒、2 秒、4 秒です。尽きたら `error` / `http_429` であり、空のレンジにはしません。他の HTTP ステータスは再試行しません。リダイレクトは追いません。本文が 8 MiB を超えたらエラーです。`--max-details`（既定 500、`-1` で上限なし、最大 10000）は Greenhouse の求人詳細だけを制限します。上限を超えた求人は `unknown` / `detail_budget_exhausted` であり、「給与なし」ではありません。オフラインのフィクスチャは待たず、ソケットも開きません。`fixture` の無いボードは `--live` を付けたときだけネットワークへ出ます。

### インストール

Python 3.11 以降。

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
ats-pay-range-audit --help
pytest
```

`pytest` はネットワークを使いません。開発用追加: `pip install ".[dev]"`。`pyproject.toml` の `addopts = "-q"` により、`python3 -m pytest` は簡潔な出力です。テスト名まで出すには `python3 -m pytest -v --override-ini=addopts=` です。

### 例の置き場所

sdist には `fixtures/` と `examples/` が `tests/` と並んで入っています。展開したディレクトリで `python3 -m pytest` を実行します。既定のテストはオフラインのままです。

wheel はこれらのファイルをシェルのパスには置きません。インストール後:

```bash
ats-pay-range-audit --write-examples ./audit-examples
ats-pay-range-audit ./audit-examples/examples/ashby-all-ranges.yaml --json
```

`--write-examples` は同じ架空ファイルをコピーして終了します。ボードへは取りに行きません。

### コマンド

```bash
ats-pay-range-audit examples/ashby-all-ranges.yaml --json
ats-pay-range-audit examples/greenhouse-key-present-empty.yaml --json
ats-pay-range-audit examples/lever-no-structured-field.yaml --json
ats-pay-range-audit examples/ashby-all-ranges.yaml --save snapshot.json
ats-pay-range-audit --diff snapshot.json snapshot-later.json --json
```

ボードファイル（`token`、`slug`、`site` は `board` の別名です。URL は渡しません）:

```yaml
boards:
  - provider: greenhouse
    board: your-board-token
    name: Your company
  - provider: ashby
    board: your-jobs-page-name
    name: Your company
  - provider: lever
    board: your-site
    region: global   # または eu
    name: Your company
```

ローカル再生は `fixture: path/to/file.json` です。fixture が無いときは `--live` を付けます。

終了コード: `0` は完了（カバー率は 0 でも未定義でもよい）。`1` はリクエスト、解析、またはスナップショット schema のエラー。`2` は使い方またはローカル IO。シンボリックリンクへの書き込み拒否を含みます。

`--save` は完全な JSON を同じディレクトリの一時ファイルへ書き、`os.replace` で置き換えます。置き換えに失敗しても以前のファイルは残ります。シンボリックリンクは拒否します。

`--diff` は `bounds_changed`（両方 `valid` で、min、max、通貨、周期のいずれかが変わった）、`became_valid`、`became_empty`、`jobs_added`、`jobs_removed`、`newly_observed`（前が unknown または error で、今が valid。雇用者が追加した証明ではない）、`unresolved`（valid が unknown または error になった場合、削除としては報告しない）を出します。行は provider、board、job id の順です。

### フィクスチャ

`fixtures/` の各 JSON は合成データです。`examples/*.yaml` がそれを指します。`fixtures/diff-range-changed/` はスナップショットの組であり、本番の記録ではありません。`fixtures/http-429.json` は 429 を再生し、結果はエラーであって空のレンジではありません。

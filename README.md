<!-- mcp-name: io.github.sepehr071/jobvision-mcp -->

<div align="center">

# jobvision-mcp: Jobvision (جاب‌ویژن) Iran jobs MCP server for AI agents

**jobvision-mcp is an unofficial, read-only MCP server that gives AI agents the job ads of Jobvision (jobvision.ir), the largest Iranian job portal.**<br>
Its 14 tools search job ads with real filters, read a full ad, find similar ads, find companies by name and read their profile, rating and interview reports,<br>
estimate pay from advertised salaries and from Jobvision's career-guide salary survey, count open ads per category or province, and list public-sector hiring news.<br>
No API key or Jobvision account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[![PyPI](https://img.shields.io/pypi/v/jobvision-mcp?color=2563eb)](https://pypi.org/project/jobvision-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/jobvision-mcp)](https://pypi.org/project/jobvision-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/jobvision-mcp/blob/main/LICENSE)

[For AI agents](#for-ai-agents) · [Quick start](#quick-start) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

</div>

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for jobvision.ir: job search with filters (city, category, work type, seniority, experience, remote, internship, military service, posted within, minimum advertised pay), full job ads, similar ads, company profiles with open ads, advertised-pay statistics and lookup lists.
- **Install:** `uvx jobvision-mcp` or `claude mcp add jobvision -- uvx jobvision-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account. Optional `JOBVISION_MCP_PROXY` (HTTP proxy URL, or a comma-separated list); system proxy settings are ignored.
- **Access:** read-only. It cannot log in, apply, save jobs or post ads, so no confirmation is needed before calling any tool.
- **Tools:** 14, all prefixed `jv_`. Typical sequences: `jv_search` -> `jv_job` -> `jv_company`; `jv_companies` -> `jv_interviews`; `jv_careers` -> `jv_career` for salary levels; `jv_pay_stats` for "how much does X earn"; `jv_locations` / `jv_options` when a city, category or industry needs a slug or id.
- **Use when:** the user wants jobs in Iran (استخدام), wants to compare employers or cities, or wants to know what a role pays in ads.
- **Do not use when:** the user needs Jobvision's salary calculator or employee company reviews (account only; interview reports are covered), or jobs outside Iran.
- **Output:** compact JSON. Pay is the advertised monthly range in million Toman (most ads hide it). Dates are ISO UTC. Texts are Persian or English as employers wrote them.
- **Machine-readable:** [`server.json`](https://github.com/sepehr071/jobvision-mcp/blob/main/server.json).

## Quick start

```bash
claude mcp add jobvision -- uvx jobvision-mcp
```

Any MCP client: command `uvx`, args `["jobvision-mcp"]`. Behind a proxy set `JOBVISION_MCP_PROXY=http://host:port`.

## Tools

| Tool | Use it to |
|---|---|
| `jv_search` | Search ads by keyword with filters; sort by newest, relevance or advertised pay; paged |
| `jv_job` | Read one ad: description, required software, conditions, benefits, pay, location, dates, employer |
| `jv_similar_jobs` | Ads Jobvision considers similar to one ad |
| `jv_company` | Employer profile (size, industries, founded, website, benefits) and its open ads |
| `jv_pay_stats` | Median, quartiles and extremes of the pay that matching ads advertise (samples up to 300 ads) |
| `jv_suggest` | Job-title autocomplete with how often titles occur |
| `jv_locations` | Province, city and Tehran-area names with the slugs the city filter takes |
| `jv_options` | Categories, industries, benefits, salary ranges and other filter lists |
| `jv_companies` | Company directory: search by name, filter by province, industry, size, rating band, hiring; ranked by Jobvision score |
| `jv_interviews` | A company's interview reports: score, difficulty, typical duration, common steps, individual reports or questions asked |
| `jv_careers` | ~100 career-guide job titles ranked by satisfaction, median salary or open ads |
| `jv_career` | One job title: salary distribution (by city group), ad growth, duties, skills, how to enter, related careers |
| `jv_market` | Open-ad counts split by category, province, work type, seniority, experience, pay band or age |
| `jv_government_news` | Recruitment announcements for banks, ministries, oil and gas and other public sectors; read one in full |

Example: "python jobs in Isfahan that pay at least 40 million" -> `jv_search(keyword="python", city="اصفهان", salary_min=40, sort="salary")`.

## FAQ

**Is this official?** No. It reads the public JSON that jobvision.ir's own website uses. Requests are cached briefly and spaced out.

**Does it show salaries?** Only what ads advertise (about one in five ads shows a range). `jv_pay_stats` says how many ads it based its numbers on.

**Where do real salaries come from?** `jv_career` and `jv_careers` use Jobvision's own career-guide survey (median pay per job title, optionally per city group), which covers jobs whose ads hide pay.

**Can it apply to jobs?** No, it is read-only.

## فارسی

`jobvision-mcp` یک سرور MCP غیررسمی و فقط‌خواندنی برای جاب‌ویژن (jobvision.ir) است: جستجوی آگهی‌های استخدام با فیلتر (شهر، گروه شغلی، نوع همکاری، سطح ارشدیت، سابقه، دورکاری، کارآموزی، امریه، حداقل حقوق)، متن کامل آگهی، آگهی‌های مشابه، پروفایل شرکت و آگهی‌های باز آن و آمار حقوق اعلام‌شده در آگهی‌ها. به کلید API یا حساب کاربری نیاز ندارد.

نصب: `uvx jobvision-mcp`

---

Unofficial project, not affiliated with Jobvision. MIT license. Author: Sepehr Radmard (سپهر رادمرد), github.com/sepehr071.

"""Jobvision career guide tools: public salary, demand and satisfaction data per job title."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, get
from .jobs import DAY, _norm, _text, _title
from .registry import tool

CITY_GROUPS = {"tehran": 1, "big-cities": 2, "small-cities": 3}
ORDER = {"satisfaction": 1, "salary": 2, "ads": 3}
OPEN_END = 900_000_000  # the last histogram bar is open ended


def _m(v: float | None) -> float | None:
    """Rial-free Toman amount to million Toman."""
    return None if v is None else round(v / 1_000_000, 1)


def _career_row(i: dict) -> dict[str, Any]:
    return {
        "career": i["pageRoute"],
        "title": i["title"],
        "satisfaction": round(i["totalSatisfactionScore"], 1) if i.get("totalSatisfactionScore") else None,
        "open_ads": i.get("jobPostCount"),
        "median_salary_million_toman": _m(i.get("medianSalary")),
        "salary_from": _m(i.get("minMedianSalary")),
        "salary_to": _m(i.get("maxMedianSalary")),
    }


@tool("Career salary ranking")
async def jv_careers(
    query: Annotated[
        str,
        Field(description="Part of a job title to filter by, e.g. برنامه or engineer. Empty lists all.", max_length=60),
    ] = "",
    sort: Annotated[
        Literal["satisfaction", "salary", "ads"],
        Field(description="satisfaction (default), salary (highest median) or ads (most open ads)."),
    ] = "satisfaction",
    limit: Annotated[int, Field(ge=1, le=100, description="How many careers to return.")] = 20,
) -> dict[str, Any]:
    """Rank the ~100 job titles in Jobvision's career guide by satisfaction, median salary or open ads.

    Use for "which jobs pay the most" or "what does an accountant earn" (median salary, million Toman per month,
    from Jobvision's own salary survey, so unlike jv_pay_stats it is not limited to ads that show pay). Call
    jv_career with the `career` value for duties, skills, the salary distribution and how to get into the job.
    """
    data = await get("/CareerGuide/GetList", {"pageNumber": 1, "pageSize": 100, "orderBy": ORDER[sort]}, ttl=DAY)
    rows = [_career_row(i) for i in data["items"]]
    if q := _norm(query):
        rows = [r for r in rows if q in _norm(r["title"]) or q in r["career"]]
    return {"total": data["totalCount"], "matched": len(rows), "careers": rows[:limit]}


async def _resolve_career(q: str) -> str:
    names = await get("/CareerGuide/GetListOfNames", ttl=DAY)
    n = _norm(q)
    for match in (
        lambda c: c["pageRoute"] == n,
        lambda c: _norm(c["title"]) == n,
        lambda c: n in _norm(c["title"]) or n in c["pageRoute"],
    ):
        hits = [c for c in names if match(c)]
        if len(hits) == 1:
            return hits[0]["pageRoute"]
        if hits:
            raise ApiError(
                "Career is ambiguous: " + ", ".join(f"{c['pageRoute']} ({c['title']})" for c in hits[:8]) + "."
            )
    raise ApiError(f"Unknown career '{q}'. Call jv_careers(query=...) to find the career slug.")


def _histogram(h: dict | None) -> dict[str, Any] | None:
    if not h or not h.get("bars"):
        return None
    return {
        "participants": h.get("numberOfParticipants"),
        "median_million_toman": _m(h.get("medianSalaryRange")),
        "bars": [
            {
                "from": _m(b["min"]),
                "to": None if b["max"] >= OPEN_END else _m(b["max"]),
                "percent": b["percent"],
                **({"median": True} if b.get("isMedian") else {}),
            }
            for b in h["bars"]
        ],
    }


def _titles(items: list[dict] | None) -> list[str]:
    return [t.strip() for t in (_title(i) for i in items or []) if t]


@tool("Career profile")
async def jv_career(
    career: Annotated[
        str, Field(description="Career slug from jv_careers (e.g. accountant) or a job title (حسابدار).", max_length=80)
    ],
    city_size: Annotated[
        Literal["all", "tehran", "big-cities", "small-cities"],
        Field(description="Salary distribution for all cities (default) or one city group."),
    ] = "all",
) -> dict[str, Any]:
    """Get Jobvision's career-guide profile of one job title: salary distribution, demand, duties, skills, path.

    Use after jv_careers. Salaries are million Toman per month from Jobvision's salary survey (histogram bars give the
    share of participants per pay band). Also returns job-ad growth over the last year, satisfaction scores, the
    steps to enter the job and neighbouring careers. `search` holds jv_search arguments for the matching open ads.
    """
    route = await _resolve_career(career)
    d = await get("/CareerGuide/GetDetails", {"pageRoute": route}, ttl=DAY)
    if not d:
        raise ApiError(f"No career profile for '{route}'.")
    b, stats = d["basic"], d.get("statistics") or {}
    hist = d.get("salaryHistogram")
    if city_size != "all":
        hist = await get(
            "/CareerGuide/GetSalaryHistogram", {"pageRoute": route, "citySizeGroupId": CITY_GROUPS[city_size]}, ttl=DAY
        )
    growth = {}
    for g in d.get("jobGrowth") or []:
        grp = _title(g.get("citySizeGroup")) or "all"
        gr = g.get("growth") or {}
        growth[grp] = {
            "percent": gr.get("jobGrowthPercentage"),
            "ads_before": gr.get("startPeriodJobPostsCount"),
            "ads_now": gr.get("endPeriodJobPostsCount"),
        }
    f = d.get("jobsSearchFilter") or {}
    return {
        "career": route,
        "title": b["title"],
        "summary": _text(b.get("description"))[:900],
        "open_ads": b.get("jobPostCount"),
        "median_salary_million_toman": _m(b.get("medianSalary")),
        "salary_from": _m(b.get("minMedianSalary")),
        "salary_to": _m(b.get("maxMedianSalary")),
        "satisfaction": round(b["totalSatisfactionScore"], 1) if b.get("totalSatisfactionScore") else None,
        "salary_distribution": _histogram(hist),
        "salary_city_group": city_size,
        "ad_growth_last_year": growth,
        "satisfaction_by_aspect": {o["opinionTitle"]: o["scaleValue"] for o in stats.get("opinionScale") or []},
        "survey_respondents": stats.get("totalSurveyCount"),
        "duties": _titles(b.get("careerGuideDuties")),
        "skills": _titles(b.get("careerGuideSkills")),
        "how_to_enter": _titles(b.get("careerGuideSteps")),
        "career_path": _titles(b.get("careerGuideJourneys")),
        "related_careers": _titles(b.get("careerGuideTransitionPossibilities")),
        "search": {"keyword": f.get("keyword"), "category": f.get("jobCategoryUrlTitle")},
        "url": f"{SITE}/career-guide/{route}",
    }

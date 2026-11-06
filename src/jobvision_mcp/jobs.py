"""Jobvision tools: job search, job details, companies, advertised pay statistics, and the lookup lists."""

from __future__ import annotations

import asyncio
import html
import re
import statistics
from typing import Annotated, Any, Literal

from pydantic import Field

from .http import SITE, ApiError, get, post
from .registry import tool

PAGE_MAX = 30  # largest page the list API serves
SAMPLE_PAGES = 10  # jv_pay_stats reads at most this many pages
DAY = 3600.0  # lookup lists change rarely

# Ids the web app's filters use (read from /JobPost/GetAllSearchFilters, checked 2026-10-31).
WORK_TYPE = Literal["full-time", "part-time", "project-based"]
SENIORITY = {
    "intern": 300,
    "worker": 246,
    "employee": 96,
    "specialist": 97,
    "senior-specialist": 172,
    "manager": 98,
    "senior-manager": 99,
    "ceo": 100,
}
EXPERIENCE = {"none": -1, "under-2": 1, "2-5": 2, "5-8": 3, "8-12": 4, "over-12": 5}  # years of required experience
POSTED = {"3d": 1, "1w": 2, "15d": 3, "1m": 4}
SORT = {"newest": 0, "relevance": 1, "salary": 2}
# governmentalCollection values (page routes of jobvision.ir/government-jobs/<route>); "ministries" had no live ads when checked.
GOV_SECTORS = {
    "banks": "بانک",
    "education": "آموزش-و-پرورش",
    "ministries": "وزارت-خانه",
    "insurance": "بیمه",
    "industry": "صنعتی-و-تولیدی",
    "health": "دارو-و-درمان",
    "oil-gas": "نفت-گاز-پتروشیمی",
    "armed-forces": "نیروهای-مسلح",
    "other": "سایر",
}
GOV = Literal[
    "all", "banks", "education", "ministries", "insurance", "industry", "health", "oil-gas", "armed-forces", "other"
]
# salaryRanges ids with their upper bound in million Toman per month; 999 = open ended.
SALARY_RANGES = [(1, 10), (2, 15), (4, 25), (5, 40), (6, 60), (8, 100), (9, 150), (10, 200), (11, 300), (12, 999)]

Keyword = Annotated[
    str, Field(description="Job title or skill, Persian or English, e.g. python, حسابدار.", max_length=100)
]
City = Annotated[
    str | None,
    Field(
        description="One city, province or Tehran area, by name (اصفهان) or slug (isfahan, all-cities-of-tehran). See jv_locations."
    ),
]
Category = Annotated[
    str | None,
    Field(description="Category slug or name from jv_options('categories'), e.g. developer."),
]
SameKeyword = Annotated[str, Field(description="Same as jv_search.", max_length=100)]
SameCity = Annotated[str | None, Field(description="Same as jv_search.")]
SameCategory = Annotated[str | None, Field(description="Same as jv_search.")]
JobId = Annotated[int, Field(description="Job ad id from jv_search.", ge=1)]
CompanyId = Annotated[int, Field(description="Company id (job company.id or jv_companies).", ge=1)]


def _title(x: dict | None) -> str | None:
    return (x or {}).get("titleFa") or (x or {}).get("title")


def _salary(s: dict | None) -> str | None:
    """Advertised pay as "min-max" in million Toman per month, or None when the ad hides it."""
    if not s or s.get("min") is None:
        return None
    return f"{s['min']}-{s['max']}" if s.get("max") else str(s["min"])


def rating(sc: dict | None) -> dict[str, Any] | None:
    """Jobvision's 1-5 company scores, or None when nobody rated the company."""
    if not sc or not sc.get("totalScore"):
        return None
    names = {
        "scoreOfCompanyReview": "employees",
        "scoreOfInterviewsFeedback": "interviews",
        "scoreOfApplicationChangeStatus": "reply_to_applicants",
        "scoreOfCultureAndValues": "culture",
        "scoreOfCareerOpportunities": "career",
        "scoreOfCompensationAndBenefits": "pay_benefits",
        "scoreOfSeniorManagement": "management",
        "scoreOfWorkLifeBalance": "work_life",
        "scoreOfProgressAndLearning": "learning",
    }
    out: dict[str, Any] = {"overall": round(sc["totalScore"], 2), "rank": sc.get("rank")}
    out |= {n: round(sc[k], 1) for k, n in names.items() if sc.get(k) is not None}
    return out


def _norm(s: str) -> str:
    return s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip().lower()


def _card(p: dict) -> dict[str, Any]:
    """A job ad as the search list shows it."""
    props, loc, co = p.get("properties") or {}, p.get("location") or {}, p.get("company") or {}
    return {
        "id": p["id"],
        "title": p["title"],
        "company": {"id": co.get("id"), "name": co.get("nameFa") or co.get("nameEn")},
        "city": _title(loc.get("city")),
        "province": _title(loc.get("province")),
        "region": _title(loc.get("region")),
        "work_type": _title(p.get("workType")),
        "seniority": _title(p.get("seniorityLevel")),
        "salary_million_toman": _salary(p.get("salary")),
        "experience_years": props.get("requiredRelatedExperienceYears"),
        "remote": props.get("isRemote") or None,
        "internship": props.get("isInternship") or None,
        "urgent": props.get("isUrgent") or None,
        "posted": (p.get("activationTime") or {}).get("date"),
        "days_left": (p.get("expireTime") or {}).get("daysLeftUntil"),
        "url": f"{SITE}/jobs/{p['id']}",
    }


async def _locations() -> list[dict[str, str]]:
    """Every place the `city` filter accepts: provinces, cities and Tehran areas, each with its slug."""
    out = []
    for prov in await get("/Basedata/GetListOfMultiLevelLocationWrapper", ttl=DAY):
        for c in prov["children"]:
            kind = "province" if c["urlParameter"].startswith("all-cities-of-") else "city"
            base = {"province": prov["title"], "province_id": prov["id"]}
            out.append({"slug": c["urlParameter"], "name": c["title"], "kind": kind, **base})
            for g in c.get("regionGroups") or []:
                name = f"{g['title']} {c['title']}"
                out.append({"slug": g["urlParameter"], "name": name, "kind": "area", **base})
    return out


async def province_id(q: str) -> int:
    """Id of the province a place name or slug belongs to (the company directory filters by it)."""
    slug = await _resolve_city(q)
    return next(p["province_id"] for p in await _locations() if p["slug"] == slug)


async def _resolve_city(q: str) -> str:
    """Turn a place name or slug into the slug the search accepts, or raise with close matches."""
    places, n = await _locations(), _norm(q)
    for match in (
        lambda p: p["slug"] == n,
        lambda p: _norm(p["name"]) == n and p["kind"] != "province",
        lambda p: n in (_norm(p["province"]), _norm(p["name"])) and p["kind"] == "province",
    ):
        if hit := next((p for p in places if match(p)), None):
            return hit["slug"]
    near = [p for p in places if n in _norm(p["name"]) or n in p["slug"]]
    if len(near) == 1:
        return near[0]["slug"]
    hint = ", ".join(f"{p['name']} ({p['slug']})" for p in near[:8]) or "none close"
    raise ApiError(f"Unknown place '{q}'. Close matches: {hint}. Use jv_locations to browse.")


async def _resolve_category(q: str) -> str:
    cats = await get("/Basedata/GetListOfJobCategories", ttl=DAY)
    n = _norm(q)
    for match in (
        lambda c: c["urlTitle"] == n,
        lambda c: n in (_norm(c["titleFa"]), _norm(c["titleEn"])),
        lambda c: n in _norm(c["titleFa"]) or n in _norm(c["titleEn"]),
    ):
        hits = [c for c in cats if match(c)]
        if len(hits) == 1:
            return hits[0]["urlTitle"]
        if hits:
            names = ", ".join(f"{c['urlTitle']} ({c['titleFa']})" for c in hits[:8])
            raise ApiError(f"Category '{q}' is ambiguous: {names}.")
    raise ApiError(f"Unknown category '{q}'. Call jv_options('categories') for the slugs.")


async def _body(
    keyword: str,
    city: str | None,
    category: str | None,
    work_type: str | None,
    seniority: str | None,
    experience: str | None,
    salary_min: int | None,
    remote: bool,
    internship: bool,
    military_service: bool,
    industry: int | None,
    benefit: int | None,
    posted_within: str | None,
    sort: str,
    company_id: int | None = None,
    *,
    government: str | None = None,
    disabled_friendly: bool = False,
) -> dict[str, Any]:
    """The JSON body of the web app's job list call, with only the filters that are set."""
    body: dict[str, Any] = {"keyword": keyword.strip(), "sortBy": SORT[sort], "searchId": None}
    if city:
        body["locationWrapper"] = await _resolve_city(city)
    if category:
        body["jobCategoryUrlTitle"] = await _resolve_category(category)
    if work_type:
        body["workTypes"] = [work_type]
    if seniority:
        body["seniorityLevels"] = [SENIORITY[seniority]]
    if experience:
        body["workExperiences"] = [EXPERIENCE[experience]]
    if salary_min:
        body["salaryRanges"] = [i for i, top in SALARY_RANGES if top > salary_min]
    if remote:
        body["isRemote"] = True
    if internship:
        body["isInternship"] = True
    if military_service:
        body["militaryServiceBenefit"] = True
    if industry:
        body["industries"] = [industry]
    if benefit:
        body["jobBenefits"] = [benefit]
    if posted_within:
        body["searchTimeRange"] = POSTED[posted_within]
    if company_id:
        body["companyId"] = company_id
    if government:  # "all" or a sector from GOV_SECTORS
        body["isGovernmentalJobs"] = True
        if government != "all":
            body["governmentalCollection"] = GOV_SECTORS[government]
    if disabled_friendly:
        body["suitableForDisabled"] = True
    return body


def _applied(filters: dict) -> dict[str, Any]:
    """Which filters the server recognised (it drops unknown ones silently)."""
    out: dict[str, Any] = {}
    for k, v in filters.items():
        if v in (None, "", False):
            continue
        out[k] = [_title(x) for x in v] if isinstance(v, list) else _title(v) if isinstance(v, dict) else v
    return out


@tool("Search jobs")
async def jv_search(
    keyword: Keyword = "",
    city: City = None,
    category: Category = None,
    work_type: Annotated[WORK_TYPE | None, Field(description="project-based = contract.")] = None,
    seniority: Annotated[
        Literal["intern", "worker", "employee", "specialist", "senior-specialist", "manager", "senior-manager", "ceo"]
        | None,
        Field(description="Role level; specialist = کارشناس, manager = middle manager."),
    ] = None,
    experience: Annotated[
        Literal["none", "under-2", "2-5", "5-8", "8-12", "over-12"] | None,
        Field(description="Required experience bracket in years; none = no experience needed."),
    ] = None,
    salary_min: Annotated[
        int | None,
        Field(
            description="Minimum advertised pay, million Toman per month; ads hiding pay are left out.",
            ge=1,
            le=300,
        ),
    ] = None,
    remote: bool = False,
    internship: bool = False,
    military_service: Annotated[bool, Field(description="Only ads with military-service benefits (امریه).")] = False,
    industry: Annotated[int | None, Field(description="Industry id from jv_options('industries').")] = None,
    benefit: Annotated[
        int | None, Field(description="Benefit id from jv_options('benefits'), e.g. 116 = loan.")
    ] = None,
    posted_within: Annotated[
        Literal["3d", "1w", "15d", "1m"] | None,
        Field(description="Posted within the last 3 days, week, 15 days or month."),
    ] = None,
    sort: Annotated[
        Literal["newest", "relevance", "salary"],
        Field(description="salary = highest top of the advertised range first."),
    ] = "newest",
    government: Annotated[
        GOV | None,
        Field(description="Only public-sector ads: all or one sector."),
    ] = None,
    disabled_friendly: Annotated[bool, Field(description="Only ads suitable for people with disabilities.")] = False,
    page: Annotated[int, Field(ge=1, le=100)] = 1,
    limit: Annotated[int, Field(ge=1, le=30)] = 10,
) -> dict[str, Any]:
    """Search Jobvision job ads (استخدام) with filters and return one page of compact job cards.

    Use first for any job hunt; then jv_job (full text), jv_company (employer), jv_similar_jobs. `applied` echoes
    the filters Jobvision recognised. Pay is a monthly range in million Toman, hidden on most ads.
    """
    body = await _body(
        keyword,
        city,
        category,
        work_type,
        seniority,
        experience,
        salary_min,
        remote,
        internship,
        military_service,
        industry,
        benefit,
        posted_within,
        sort,
        government=government,
        disabled_friendly=disabled_friendly,
    )
    data = await post("/JobPost/List", {**body, "pageSize": limit, "requestedPage": page})
    posts = data["jobPosts"]
    if sort == "newest":  # the API only orders by day; order the page by exact time
        posts = sorted(posts, key=lambda p: (p.get("activationTime") or {}).get("date") or "", reverse=True)
    return {
        "total": data["jobPostCount"],
        "page": page,
        "applied": _applied(data["filters"]),
        "jobs": [_card(p) for p in posts],
    }


def _text(h: str | None) -> str:
    """Job description HTML to plain text with line breaks kept."""
    t = re.sub(r"<\s*(br|/p|/div|/li|/h\d)[^>]*>", "\n", h or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\u00a0]+", " ", t)).strip()


@tool("Job ad details")
async def jv_job(job_id: JobId) -> dict[str, Any]:
    """Get the full text and requirements of one Jobvision job ad.

    Use after jv_search or jv_similar_jobs. Includes the employer summary; jv_company has its other open ads.
    """
    d = await get("/JobPost/Detail", {"jobPostId": job_id})
    if not d:
        raise ApiError(f"No job ad with id {job_id}.")
    co, loc = d.get("company") or {}, d.get("location") or {}
    return {
        "id": d["id"],
        "title": d["title"],
        "description": _text(d.get("description")),
        "company": {
            "id": co.get("id"),
            "name": _title(co.get("name")) or (co.get("name") or {}).get("titleEn"),
            "size": _title(co.get("size")),
            "industries": [_title(i) for i in co.get("industries") or []],
            "website": co.get("website"),
            "url": f"{SITE}/companies/{co.get('id')}",
        },
        "location": {k: _title(loc.get(k)) for k in ("country", "province", "city", "region")},
        "categories": [_title(c) for c in d.get("jobCategories") or []],
        "industry": _title(d.get("industry")),
        "work_type": _title(d.get("workType")),
        "seniority": _title(d.get("seniorityLevel")),
        "salary_million_toman": _salary(d.get("salary")),
        "gender": _title(d.get("gender")),
        "experience_years": d.get("requiredRelatedExperienceYears"),
        "age": f"{d['requiredAgeMin']}-{d['requiredAgeMax']}" if d.get("requiredAgeMin") else None,
        "military_service_required": d.get("shouldDoneMilitaryService") or None,
        "work_days": d.get("workDays"),
        "business_trip": d.get("businessTrip"),
        "software": [
            f"{_title(s.get('software'))} ({_title(s.get('skill'))})" for s in d.get("softwareRequirements") or []
        ],
        "languages": d.get("languageRequirements"),
        "academic": d.get("academicRequirements"),
        "skills": d.get("skills"),
        "benefits": [_title(b) for b in d.get("benefits") or []],
        "remote": d.get("isRemote") or None,
        "internship": d.get("isInternship") or None,
        "urgent": d.get("isUrgent") or None,
        "suitable_for_disabled": d.get("suitableForDisabled") or None,
        "posted": (d.get("firstActivationTime") or {}).get("date"),
        "expires": (d.get("expireTime") or {}).get("date"),
        "expired": d.get("isExpired") or None,
        "url": f"{SITE}/jobs/{d['id']}",
    }


@tool("Similar jobs")
async def jv_similar_jobs(job_id: JobId) -> dict[str, Any]:
    """List job ads Jobvision considers similar to one ad.

    Use after jv_job to widen a search. Returns the same cards as jv_search.
    """
    data = await get("/JobPost/Recommendation/Similar", {"jobPostId": job_id})
    return {"jobs": [_card(p) for p in data or []]}


@tool("Company profile")
async def jv_company(
    company_id: CompanyId,
    open_jobs: Annotated[int, Field(ge=0, le=30, description="Open ads to include (0 = profile only).")] = 10,
) -> dict[str, Any]:
    """Get an employer's profile and its currently open job ads.

    Includes Jobvision's 1-5 rating and rank and its open ads (newest first) as job cards. Find an id by name with
    jv_companies; jv_interviews has interview reports.
    """
    d = await get("/Company/Details", {"companyId": company_id})
    if not d:
        raise ApiError(f"No company with id {company_id}.")

    async def score() -> dict:
        try:
            return await get("/Company/GetFilteredCompanySummaryCard", {"companyId": company_id}) or {}
        except ApiError:  # the rating is a bonus; the profile still works without it
            return {}

    async def listing() -> dict | None:
        if not open_jobs or d.get("activeJobPostCount") == 0:
            return None
        body = await _body(
            "", None, None, None, None, None, None, False, False, False, None, None, None, "newest", company_id
        )
        return await post("/JobPost/List", {**body, "pageSize": open_jobs, "requestedPage": 1})

    card, res = await asyncio.gather(score(), listing())
    jobs: list[dict] = []
    total = d.get("activeJobPostCount")
    if res:
        jobs, total = [_card(p) for p in res["jobPosts"]], res["jobPostCount"]
    c = d["company"]
    return {
        "id": c["id"],
        "name": c.get("titleFa") or c.get("titleEn"),
        "name_en": c.get("titleEn") or None,
        "short_description": d.get("shortDescriptionFa") or d.get("shortDescriptionEn"),
        "description": (d.get("descriptionFa") or d.get("descriptionEn") or "")[:1500],
        "products_or_services": (d.get("productsOrServicesFa") or d.get("productsOrServicesEn") or "")[:600],
        "industries": [_title(i) for i in d.get("industries") or []],
        "size": _title(d.get("companySize")),
        "ownership": _title(d.get("companyOwnership")),
        "type": _title(d.get("companyType")),
        "city": d.get("cityFa"),
        "province": d.get("provinceFa"),
        "founded": int(d["establishmentYear"]) if str(d.get("establishmentYear")).isdigit() else None,
        "website": d.get("websiteAddress"),
        "benefits": [_title(b) for b in d.get("benefits") or []],
        "governmental": d.get("isGovernmentalCompany") or None,
        "total_ads_ever": d.get("jobPostCount"),
        "interview_reports": d.get("interviewFeedbackCount"),
        "rating": rating(card.get("companyScore")),
        "open_ads": total,
        "jobs": jobs,
        "url": f"{SITE}/companies/{c['id']}",
    }


@tool("Advertised pay statistics")
async def jv_pay_stats(
    keyword: SameKeyword = "",
    city: SameCity = None,
    category: SameCategory = None,
    seniority: Annotated[
        Literal["intern", "worker", "employee", "specialist", "senior-specialist", "manager", "senior-manager", "ceo"]
        | None,
        Field(description="Same as jv_search."),
    ] = None,
    experience: Annotated[
        Literal["none", "under-2", "2-5", "5-8", "8-12", "over-12"] | None,
        Field(description="Same as jv_search."),
    ] = None,
    remote: bool = False,
) -> dict[str, Any]:
    """Estimate pay for a role from the salaries open Jobvision ads advertise (million Toman per month).

    Samples up to 300 of the newest matching ads and summarises those showing pay: median of range midpoints,
    quartiles, extremes. It is advertised pay, not what people earn; many ads hide pay (see share_with_pay), so
    small `ads_with_pay` is rough. jv_search sort=salary lists the ads.
    """
    body = await _body(
        keyword, city, category, None, seniority, experience, None, remote, False, False, None, None, None, "newest"
    )
    first = await post("/JobPost/List", {**body, "pageSize": PAGE_MAX, "requestedPage": 1})
    total, ads = first["jobPostCount"], first["jobPosts"]
    pages = min(SAMPLE_PAGES, -(-total // PAGE_MAX))  # the API serves at most 30 ads per page
    for res in await asyncio.gather(
        *(post("/JobPost/List", {**body, "pageSize": PAGE_MAX, "requestedPage": n}) for n in range(2, pages + 1))
    ):
        ads += res["jobPosts"]
    paid = [p["salary"] for p in ads if p.get("salary") and p["salary"].get("min") is not None]
    out: dict[str, Any] = {
        "matching_ads": total,
        "sampled_ads": len(ads),
        "ads_with_pay": len(paid),
        "share_with_pay": round(len(paid) / len(ads), 2) if ads else None,
        "applied": _applied(first["filters"]),
        "unit": "million Toman per month",
    }
    if paid:
        mids = sorted((s["min"] + (s["max"] or s["min"])) / 2 for s in paid)
        q = statistics.quantiles(mids, n=4, method="inclusive") if len(mids) > 1 else [mids[0]] * 3
        out |= {
            "median": round(statistics.median(mids), 1),
            "p25": round(q[0], 1),
            "p75": round(q[2], 1),
            "lowest_min": min(s["min"] for s in paid),
            "highest_max": max(s["max"] or s["min"] for s in paid),
        }
    return out


@tool("Suggest job titles")
async def jv_suggest(
    keyword: Annotated[str, Field(description="Start of a job title, e.g. pyth.", min_length=1, max_length=60)],
) -> dict[str, Any]:
    """Autocomplete job titles the way Jobvision's search box does, most used first.

    Use to find the wording ads use before jv_search.
    """
    k = keyword.strip().replace("+", "jv_plus").replace("#", "jv_sharp")  # the web app's own escaping
    data = await get("/Basedata/GetListOfSuggestedKeywords", {"keyword": k})
    return {"titles": [{"title": x["name"], "ads_frequency": x.get("frequency")} for x in data or []]}


@tool("Find locations")
async def jv_locations(
    query: Annotated[
        str,
        Field(description="Part of a place name; empty lists the provinces.", max_length=60),
    ] = "",
) -> dict[str, Any]:
    """Find the province, city or Tehran area names and slugs that jv_search's city filter accepts.

    Use when a city name does not resolve. Kinds: province (slug all-cities-of-...), city, area (Tehran areas).
    """
    places, n = await _locations(), _norm(query)
    if n:
        hits = [p for p in places if n in _norm(p["name"]) or n in p["slug"] or n == _norm(p["province"])]
    else:
        hits = [p for p in places if p["kind"] == "province"]
    return {"count": len(hits), "places": hits[:60]}


OPTION_KEYS = {
    "categories": "jobCategories",
    "industries": "industries",
    "benefits": "jobBenefits",
    "work_types": "workTypes",
    "seniority": "seniorityLevels",
    "experience": "workExperienceRequirements",
    "salary_ranges": "salaryRanges",
    "posted_within": "timeRanges",
}


@tool("Filter options")
async def jv_options(
    kind: Annotated[
        Literal[
            "categories",
            "industries",
            "benefits",
            "work_types",
            "seniority",
            "experience",
            "salary_ranges",
            "posted_within",
        ],
        Field(description="Which list (categories has 77)."),
    ],
) -> dict[str, Any]:
    """List the values of one Jobvision filter: ids and slugs with Persian and English names.

    categories gives jv_search's category slug, industries `industry` ids, benefits `benefit` ids. The other lists
    only document jv_search's fixed choices.
    """
    data = (await get("/JobPost/GetAllSearchFilters", ttl=DAY))[OPTION_KEYS[kind]]
    items = [
        {
            "id": x["id"],
            "slug": x.get("urlTitle") or x.get("urlParameter"),
            "name": _title(x),
            "name_en": x.get("titleEn"),
            "min": x.get("min"),
            "max": x.get("max"),
        }
        for x in data
    ]
    return {"kind": kind, "count": len(items), "items": items}

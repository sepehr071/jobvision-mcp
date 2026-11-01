import json

import httpx
import pytest
from conftest import fixture

pytestmark = pytest.mark.anyio

LIST = "/api/v1/JobPost/List"
LOC = "/api/v1/Basedata/GetListOfMultiLevelLocationWrapper"
CATS = "/api/v1/Basedata/GetListOfJobCategories"
TOOLS = {
    "jv_search",
    "jv_job",
    "jv_similar_jobs",
    "jv_company",
    "jv_pay_stats",
    "jv_suggest",
    "jv_locations",
    "jv_options",
    "jv_companies",
    "jv_interviews",
    "jv_careers",
    "jv_career",
    "jv_market",
    "jv_government_news",
}


def body(api, i=-1):
    return json.loads(api.calls[i].content)


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.title and t.description.splitlines()[0].endswith("."), t.name
        assert "'title':" not in str(t.input_schema.get("properties", {}).values()), t.name


async def test_search_returns_compact_cards(client, api):
    api[LIST] = fixture("list.json")
    r = (await client.call_tool("jv_search", {"keyword": "python", "limit": 3})).structured_content
    assert r["total"] == 990 and len(r["jobs"]) == 3
    j = next(x for x in r["jobs"] if x["id"] == 1533757)
    assert j["id"] == 1533757 and j["company"] == {"id": 19791, "name": "چابکان"}
    assert j["city"] == "تهران" and j["work_type"] == "تمام وقت" and j["url"].endswith("/jobs/1533757")
    assert "salary_million_toman" not in j  # hidden pay is dropped, not null
    assert body(api) == {"keyword": "python", "sortBy": 0, "searchId": None, "pageSize": 3, "requestedPage": 1}


async def test_calls_send_the_headers_of_the_sites_angular_app(client, api):
    api[LIST] = fixture("list.json")
    await client.call_tool("jv_search", {"keyword": "python", "limit": 3})
    h = api.calls[0].headers
    assert (h["accept"], h["origin"], h["referer"], h["sec-fetch-site"], h["priority"]) == (
        "application/json, text/plain, */*",
        "https://jobvision.ir",
        "https://jobvision.ir/",
        "same-site",
        "u=1, i",
    )
    assert (h["sec-fetch-mode"], h["sec-fetch-dest"]) == ("cors", "empty")
    assert h["ngsw-bypass"] == "true" and h["web-app-version"] and h["page-route"] == "https://jobvision.ir/"
    assert h["clientid"].isdigit() and len(h["clientid"]) == 8  # only the search POST carries it


async def test_search_filters_become_the_sites_request_body(client, api):
    api[LIST] = fixture("list.json")
    api[LOC] = fixture("locations.json")
    api[CATS] = fixture("categories.json")
    args = {
        "keyword": "x",
        "city": "اصفهان",
        "category": "developer",
        "work_type": "part-time",
        "seniority": "specialist",
        "experience": "none",
        "salary_min": 30,
        "remote": True,
        "posted_within": "1w",
        "sort": "salary",
        "page": 2,
    }
    await client.call_tool("jv_search", args)
    b = body(api)
    assert b["locationWrapper"] == "isfahan" and b["jobCategoryUrlTitle"] == "developer"
    assert b["workTypes"] == ["part-time"] and b["seniorityLevels"] == [97] and b["workExperiences"] == [-1]
    assert b["salaryRanges"] == [5, 6, 8, 9, 10, 11, 12]  # ranges whose top is above 30 million
    assert b["isRemote"] is True and b["searchTimeRange"] == 2 and b["sortBy"] == 2 and b["requestedPage"] == 2


async def test_unknown_city_and_category_explain_themselves(client, api):
    api[LOC] = fixture("locations.json")
    api[CATS] = fixture("categories.json")
    r = await client.call_tool("jv_search", {"city": "شهر نامعلوم"})
    assert r.is_error and "jv_locations" in r.content[0].text
    r = await client.call_tool("jv_search", {"category": "no-such"})
    assert r.is_error and "jv_options" in r.content[0].text


async def test_city_by_slug_and_tehran_city_beats_province(client, api):
    api[LIST] = fixture("list.json")
    api[LOC] = fixture("locations.json")
    await client.call_tool("jv_search", {"city": "all-cities-of-tehran"})
    assert body(api)["locationWrapper"] == "all-cities-of-tehran"
    await client.call_tool("jv_search", {"city": "تهران"})
    assert body(api)["locationWrapper"] == "tehran"  # the city, not the whole province


async def test_job_detail_is_plain_text(client, api):
    api["/api/v1/JobPost/Detail"] = fixture("detail.json")
    r = (await client.call_tool("jv_job", {"job_id": 1533757})).structured_content
    assert "<" not in r["description"] and "شرح شغل" in r["description"]
    assert r["company"]["id"] == 19791 and r["company"]["url"].endswith("/companies/19791")
    assert r["location"]["city"] == "تهران" and r["work_type"] == "تمام وقت"
    assert "Python (متوسط)" in r["software"] and r["age"] == "24-40"
    assert api.calls[0].url.params["jobPostId"] == "1533757"


async def test_missing_job_is_a_clear_error(client, api):
    api["/api/v1/JobPost/Detail"] = lambda request: httpx.Response(404, json={"title": "Not Found"})
    r = await client.call_tool("jv_job", {"job_id": 5})
    assert r.is_error and "404" in r.content[0].text


async def test_company_profile_with_open_jobs(client, api):
    api["/api/v1/Company/Details"] = fixture("company.json")
    api[LIST] = fixture("list.json")
    r = (await client.call_tool("jv_company", {"company_id": 19791, "open_jobs": 3})).structured_content
    assert r["name"] == "چابکان" and r["size"] == "11 تا 50 نفر" and r["founded"] == "1399"
    assert len(r["jobs"]) == 3 and body(api)["companyId"] == 19791 and body(api)["pageSize"] == 3


async def test_company_without_ads_skips_the_list_call(client, api):
    d = fixture("company.json")
    d["data"]["activeJobPostCount"] = 0
    api["/api/v1/Company/Details"] = d
    r = (await client.call_tool("jv_company", {"company_id": 19791})).structured_content
    assert r["jobs"] == [] and r["rating"] is None and not any(c.url.path == LIST for c in api.calls)


async def test_unknown_company_is_an_error(client, api):
    api["/api/v1/Company/Details"] = {"isSuccess": True, "data": None}
    assert (await client.call_tool("jv_company", {"company_id": 1})).is_error


async def test_similar_jobs(client, api):
    api["/api/v1/JobPost/Recommendation/Similar"] = fixture("similar.json")
    r = (await client.call_tool("jv_similar_jobs", {"job_id": 1533757})).structured_content
    assert len(r["jobs"]) == 2 and r["jobs"][0]["id"] == 1590542


async def test_pay_stats_summarises_ads_that_show_pay(client, api):
    d = fixture("list.json")
    d["data"]["jobPostCount"] = 3
    for p, (lo, hi) in zip(d["data"]["jobPosts"], [(10, 20), (30, 50), (None, None)], strict=True):
        p["salary"] = {"min": lo, "max": hi} if lo else None
    api[LIST] = d
    r = (await client.call_tool("jv_pay_stats", {"keyword": "python"})).structured_content
    assert (r["matching_ads"], r["sampled_ads"], r["ads_with_pay"]) == (3, 3, 2)
    assert r["median"] == 27.5 and r["lowest_min"] == 10 and r["highest_max"] == 50 and len(api.calls) == 1


async def test_pay_stats_without_any_pay_has_no_numbers(client, api):
    api[LIST] = fixture("list.json")
    r = (await client.call_tool("jv_pay_stats", {})).structured_content
    assert r["ads_with_pay"] == 0 and "median" not in r


async def test_suggest_escapes_like_the_site(client, api):
    api["/api/v1/Basedata/GetListOfSuggestedKeywords"] = fixture("suggest.json")
    r = (await client.call_tool("jv_suggest", {"keyword": "c#"})).structured_content
    assert api.calls[0].url.params["keyword"] == "cjv_sharp" and r["titles"][0]["title"].endswith("python")


async def test_locations_search_and_province_list(client, api):
    api[LOC] = fixture("locations.json")
    r = (await client.call_tool("jv_locations", {})).structured_content
    assert {p["slug"] for p in r["places"]} == {"all-cities-of-tehran", "all-cities-of-isfahan"}
    r = (await client.call_tool("jv_locations", {"query": "tehran"})).structured_content
    assert any(p["slug"] == "tehran" and p["kind"] == "city" for p in r["places"])


async def test_options_lists(client, api):
    api["/api/v1/JobPost/GetAllSearchFilters"] = fixture("filters.json")
    r = (await client.call_tool("jv_options", {"kind": "salary_ranges"})).structured_content
    assert r["items"][0] == {"id": 1, "name": "زیر 10 میلیون تومان", "name_en": "Lower than 10", "min": 0, "max": 10}
    r = (await client.call_tool("jv_options", {"kind": "categories"})).structured_content
    assert r["items"][0]["slug"] == "sales"


async def test_api_refusal_envelope_becomes_an_error(client, api):
    api[LIST] = lambda request: httpx.Response(200, json={"isSuccess": False, "message": "bad"})
    r = await client.call_tool("jv_search", {})
    assert r.is_error and "bad" in r.content[0].text


CARD = "/api/v1/Company/GetFilteredCompanySummaryCard"
DIR = "/api/v1/Company/GetListOfFilteredCompaniesSummaries"
INFO = "/api/v1/InterviewFeedback/GetCompanyInterviewFeedbackGeneralInfo"
GOV = "/api/v1/GovernmentalRecruitment/News"


async def test_company_profile_adds_rating_from_the_summary_card(client, api):
    api["/api/v1/Company/Details"] = fixture("company.json")
    api[LIST] = fixture("list.json")
    api[CARD] = fixture("company_card.json")
    r = (await client.call_tool("jv_company", {"company_id": 9432, "open_jobs": 1})).structured_content
    assert r["rating"]["overall"] > 4 and r["rating"]["rank"] == 1 and "culture" in r["rating"]


async def test_companies_directory_name_search_and_filters(client, api):
    api[DIR] = fixture("companies.json")
    api[LOC] = fixture("locations.json")
    args = {
        "keyword": "اسنپ",
        "province": "اصفهان",
        "size": "51-200",
        "rating_band": "4-5",
        "industry": 50,
        "only_hiring": True,
    }
    r = (await client.call_tool("jv_companies", {**args, "limit": 3})).structured_content
    assert r["total"] == 18 and r["companies"][0]["name"] == "اسنپ فود" and r["companies"][0]["rank"] == 96
    f = body(api)
    assert f["keyword"] == "اسنپ" and f["pageSize"] == 3 and f["orderBy"] == 0
    assert f["filterParameters"] == {
        "onlyHasActiveJobPosts": True,
        "listOfCityIds": [14],
        "listOfCompanyBenefits": [],
        "listOfCompanyScores": [5],
        "listOfCompanySizes": [103],
        "listOfIndustryIds": [50],
    }


async def test_unrated_company_has_no_rank(client, api):
    d = fixture("companies.json")
    d["data"]["companies"][0]["companyScore"]["totalScore"] = 0
    api[DIR] = d
    r = (await client.call_tool("jv_companies", {})).structured_content
    assert "rating" not in r["companies"][0] and "rank" not in r["companies"][0]


async def test_interviews_summary_and_reports(client, api):
    api[INFO] = fixture("interview_info.json")
    api["/api/v1/InterviewFeedback/GetListOfCompanyInterviewFeedback"] = fixture("interview_list.json")
    args = {"company_id": 9432, "sort": "top_rated", "limit": 2}
    r = (await client.call_tool("jv_interviews", args)).structured_content
    assert r["summary"]["reports"] == 1431 and r["summary"]["score"] == 4.85 and r["summary"]["typical_duration"]
    assert len(r["reports"]) == 2 and r["reports"][0]["steps"]
    assert body(api) == {"companyId": 9432, "page": 1, "pageSize": 2, "sortBy": 2}


async def test_interview_questions(client, api):
    api[INFO] = fixture("interview_info.json")
    api["/api/v1/InterviewFeedback/GetCompanyInterviewQuestions"] = fixture("interview_questions.json")
    r = (await client.call_tool("jv_interviews", {"company_id": 9432, "show": "questions"})).structured_content
    assert r["questions"][0]["question"].startswith("یک ویتر") and "reports" not in r


async def test_careers_ranking_and_filter(client, api):
    api["/api/v1/CareerGuide/GetList"] = fixture("careers.json")
    r = (await client.call_tool("jv_careers", {"sort": "salary", "limit": 2})).structured_content
    assert r["total"] == 98 and len(r["careers"]) == 2
    assert api.calls[0].url.params["orderBy"] == "2" and api.calls[0].url.params["pageSize"] == "100"
    assert r["careers"][0]["career"] == "mining-engineer" and r["careers"][0]["median_salary_million_toman"] == 60.0
    r = (await client.call_tool("jv_careers", {"query": "معدن"})).structured_content
    assert [c["career"] for c in r["careers"]] == ["mining-engineer"]


async def test_career_profile(client, api):
    api["/api/v1/CareerGuide/GetListOfNames"] = fixture("career_names.json")
    api["/api/v1/CareerGuide/GetDetails"] = fixture("career_detail.json")
    r = (await client.call_tool("jv_career", {"career": "mining-engineer"})).structured_content
    assert r["median_salary_million_toman"] == 60.0 and r["open_ads"] == 410
    assert r["url"].endswith("/career-guide/mining-engineer")
    assert r["salary_distribution"]["participants"] == 91 and r["salary_distribution"]["bars"][-1].get("to") is None
    assert r["ad_growth_last_year"]["all"]["percent"] == 67 and r["duties"] and r["search"]["category"] == "mining"


async def test_career_unknown_is_an_error(client, api):
    api["/api/v1/CareerGuide/GetListOfNames"] = fixture("career_names.json")
    assert (await client.call_tool("jv_career", {"career": "zzz"})).is_error


async def test_career_city_group_uses_the_histogram_endpoint(client, api):
    api["/api/v1/CareerGuide/GetListOfNames"] = fixture("career_names.json")
    api["/api/v1/CareerGuide/GetDetails"] = fixture("career_detail.json")
    h = fixture("career_detail.json")["data"]["salaryHistogram"]
    api["/api/v1/CareerGuide/GetSalaryHistogram"] = {"isSuccess": True, "data": {**h, "numberOfParticipants": 5}}
    r = (await client.call_tool("jv_career", {"career": "معدن", "city_size": "tehran"})).structured_content
    assert r["salary_distribution"]["participants"] == 5 and api.calls[-1].url.params["citySizeGroupId"] == "1"


async def test_market_overall_and_split(client, api):
    api["/api/v1/Statistics/GetSiteStatistics"] = fixture("site_stats.json")
    api["/api/v1/JobPost/GetActiveJobPostCountDetail"] = fixture("active_count.json")
    api[LIST] = fixture("list.json")
    r = (await client.call_tool("jv_market", {})).structured_content
    assert r["site"]["open_ads"] == 63433 and r["filters_total"] == 990 and "groups" not in r
    r = (await client.call_tool("jv_market", {"by": "work_type", "keyword": "python"})).structured_content
    assert [g["key"] for g in r["groups"]] == ["full-time", "part-time", "project-based"]
    sent = [json.loads(c.content) for c in api.calls if c.url.path == LIST]
    assert {b.get("workTypes", [None])[0] for b in sent} >= {"part-time", "project-based"}


async def test_government_search_filter(client, api):
    api[LIST] = fixture("list.json")
    await client.call_tool("jv_search", {"government": "banks"})
    assert body(api)["isGovernmentalJobs"] is True and body(api)["governmentalCollection"] == "بانک"
    await client.call_tool("jv_search", {"government": "all", "disabled_friendly": True})
    assert "governmentalCollection" not in body(api) and body(api)["suitableForDisabled"] is True


async def test_government_news_list_and_article(client, api):
    api[GOV] = fixture("gov_news.json")
    api["/api/v1/GovernmentalRecruitment/Content"] = fixture("gov_content.json")
    r = (await client.call_tool("jv_government_news", {"sector": "banks", "limit": 2})).structured_content
    assert len(r["announcements"]) == 2 and r["announcements"][0]["article"] and r["total"]
    assert api.calls[0].url.params["pageRoute"] == "بانک"
    a = (await client.call_tool("jv_government_news", {"article": "-بانک-دی"})).structured_content
    assert a["title"] and a["text"] and "<" not in a["text"]


async def test_search_newest_orders_the_page_by_time(client, api):
    api[LIST] = fixture("list.json")
    r = (await client.call_tool("jv_search", {})).structured_content
    posted = [j["posted"] for j in r["jobs"]]
    assert posted == sorted(posted, reverse=True)

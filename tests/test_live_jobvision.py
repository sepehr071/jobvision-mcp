import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_search_python(client):
    r = (await client.call_tool("jv_search", {"keyword": "python", "limit": 5})).structured_content
    assert r["total"] > 50 and len(r["jobs"]) == 5 and r["jobs"][0]["url"].startswith("https://jobvision.ir/jobs/")


async def test_live_search_filters_narrow_the_total(client):
    all_ = (await client.call_tool("jv_search", {"keyword": "python", "limit": 1})).structured_content
    args = {"keyword": "python", "city": "اصفهان", "limit": 5, "sort": "relevance"}
    r = (await client.call_tool("jv_search", args)).structured_content
    assert 0 < r["total"] < all_["total"] and all(j["province"] == "اصفهان" for j in r["jobs"])
    assert "locationWrapper" in r["applied"]
    rem = (await client.call_tool("jv_search", {"keyword": "python", "remote": True, "limit": 5})).structured_content
    assert 0 < rem["total"] < all_["total"] and all(j.get("remote") for j in rem["jobs"])


async def test_live_search_by_salary_sorts_by_top_of_range(client):
    r = (await client.call_tool("jv_search", {"keyword": "", "sort": "salary", "limit": 5})).structured_content
    pays = [float(j["salary_million_toman"].split("-")[-1]) for j in r["jobs"] if j.get("salary_million_toman")]
    assert pays and pays == sorted(pays, reverse=True)


async def test_live_job_company_similar_follow_a_search(client):
    jobs = (await client.call_tool("jv_search", {"keyword": "python", "limit": 3})).structured_content["jobs"]
    job = (await client.call_tool("jv_job", {"job_id": jobs[0]["id"]})).structured_content
    assert job["id"] == jobs[0]["id"] and len(job["description"]) > 50 and "<" not in job["description"]
    args = {"company_id": job["company"]["id"], "open_jobs": 3}
    co = (await client.call_tool("jv_company", args)).structured_content
    assert co["id"] == job["company"]["id"] and co["name"] and co["open_ads"] >= 1 and co["jobs"]
    sim = (await client.call_tool("jv_similar_jobs", {"job_id": jobs[0]["id"]})).structured_content
    assert sim["jobs"]


async def test_live_pay_stats(client):
    r = (await client.call_tool("jv_pay_stats", {"keyword": "حسابدار", "city": "شیراز"})).structured_content
    assert r["ads_with_pay"] > 5 and 3 < r["median"] < 300 and r["p25"] <= r["median"] <= r["p75"]


async def test_live_lookups(client):
    s = (await client.call_tool("jv_suggest", {"keyword": "python"})).structured_content
    assert s["titles"]
    loc = (await client.call_tool("jv_locations", {"query": "شیراز"})).structured_content
    assert any(p["slug"] == "shiraz" for p in loc["places"])
    cats = (await client.call_tool("jv_options", {"kind": "categories"})).structured_content
    assert cats["count"] > 50 and any(c["slug"] == "developer" for c in cats["items"])


async def test_live_company_directory_and_interviews(client):
    r = (await client.call_tool("jv_companies", {"keyword": "اسنپ", "limit": 5})).structured_content
    assert r["total"] >= 5 and any("اسنپ" in c["name"] for c in r["companies"])
    top = (
        await client.call_tool("jv_companies", {"province": "اصفهان", "only_hiring": True, "limit": 3})
    ).structured_content
    assert top["companies"] and top["companies"][0]["rank"]
    iv = (await client.call_tool("jv_interviews", {"company_id": 9432, "limit": 2})).structured_content
    assert iv["summary"]["reports"] > 100 and len(iv["reports"]) == 2
    co = (await client.call_tool("jv_company", {"company_id": 9432, "open_jobs": 1})).structured_content
    assert co["rating"]["overall"] > 3


async def test_live_careers(client):
    r = (await client.call_tool("jv_careers", {"sort": "salary", "limit": 5})).structured_content
    pays = [c["median_salary_million_toman"] for c in r["careers"]]
    assert r["total"] > 90 and pays == sorted(pays, reverse=True)
    c = (await client.call_tool("jv_career", {"career": "حسابدار", "city_size": "tehran"})).structured_content
    assert c["career"] == "accountant" and c["salary_distribution"]["bars"] and c["duties"]


async def test_live_market_and_government(client):
    m = (await client.call_tool("jv_market", {"by": "work_type"})).structured_content
    assert m["site"]["open_ads"] > 10000 and m["groups"][0]["ads"] <= m["filters_total"]
    p = (await client.call_tool("jv_market", {"by": "province", "top": 3})).structured_content
    assert p["groups_total"] >= 31 and p["groups"][0]["ads"] >= p["groups"][1]["ads"]
    g = (await client.call_tool("jv_government_news", {"sector": "banks", "limit": 3})).structured_content
    assert g["announcements"]
    art = (
        await client.call_tool("jv_government_news", {"article": g["announcements"][0]["article"]})
    ).structured_content
    assert len(art["text"]) > 100
    gs = (await client.call_tool("jv_search", {"government": "all", "limit": 3})).structured_content
    assert 0 < gs["total"] < 5000

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
REST_ROOT = f"{SUPABASE_URL}/rest/v1"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "job-agent/1.0",
}

LOCATION_PATTERNS = [r"\bmaryland\b", r"\bvirginia\b", r"washington,?\s*d\.?c\.?", r"district of columbia"]
REMOTE_PATTERNS = [r"remote", r"work from home", r"distributed", r"remote - united states", r"remote, united states"]
HYBRID_PATTERNS = [r"hybrid"]


@dataclass
class Profile:
    target_roles: list[str]
    locations: list[str]
    work_types: list[str]
    employment_types: list[str]
    min_full_time_salary: float
    min_contract_hourly: float
    required_skills: list[str]


def require_env() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")


def request_json(url: str, method: str = "GET", data=None, headers=None, timeout: int = 30):
    hdrs = dict(headers or {"User-Agent": "job-agent/1.0"})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    try:
        with urlopen(Request(url, data=body, headers=hdrs, method=method), timeout=timeout) as r:
            text = r.read().decode()
            return json.loads(text) if text else None
    except HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:400]}") from e
    except URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e


def supabase(method: str, table: str, params=None, data=None, extra_headers=None):
    url = f"{REST_ROOT}/{table}"
    if params:
        url += "?" + urlencode(params)
    hdrs = dict(HEADERS)
    if extra_headers:
        hdrs.update(extra_headers)
    return request_json(url, method, data, hdrs)


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<script[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def phrase_hit(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def infer_work_type(location: str, description: str, explicit: str | None = None) -> str:
    blob = " ".join(x for x in [explicit, location, description] if x).lower()
    if any(re.search(p, blob) for p in HYBRID_PATTERNS):
        return "hybrid"
    if any(re.search(p, blob) for p in REMOTE_PATTERNS):
        return "remote"
    return "onsite"


def infer_employment(title: str, description: str, explicit: str | None = None) -> str:
    blob = " ".join(x for x in [explicit, title, description] if x).lower()
    if any(x in blob for x in ["contract", "contractor", "1099"]):
        return "contract"
    if any(x in blob for x in ["full-time", "full time", "fulltime"]):
        return "full-time"
    return "unknown"


def salary_from_text(text: str):
    clean = text.replace(",", "")
    m = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:-|to)\s*\$?(\d+(?:\.\d+)?)\s*(?:k\s*)?(?:/\s*(?:yr|year)|per year|annually)", clean, re.I)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a < 1000: a *= 1000
        if b < 1000: b *= 1000
        return a, b, "year"
    m = re.search(r"\$(\d+(?:\.\d+)?)\s*(?:-|to)\s*\$?(\d+(?:\.\d+)?)\s*(?:/\s*(?:hr|hour))", clean, re.I)
    if m:
        return float(m.group(1)), float(m.group(2)), "hour"
    return None, None, None


def location_ok(location: str, work_type: str) -> bool:
    b = (location or "").lower()
    if work_type == "remote":
        return bool(re.search(r"remote|united states|u\.s\.|usa|nationwide", b))
    return any(re.search(p, b) for p in LOCATION_PATTERNS)


def score_job(job: dict, profile: Profile) -> dict:
    title = job.get("title", "")
    blob = f"{title} {job.get('description','')} {job.get('requirements','')}"
    role_hits = sum(phrase_hit(title, x) for x in profile.target_roles)
    skill_hits = [x for x in profile.required_skills if phrase_hit(blob, x)]
    title_score = min(100.0, role_hits * 40 + (30 if "power platform" in title.lower() else 0))
    skills_score = min(100.0, len(skill_hits) / max(1, len(profile.required_skills)) * 100)
    loc_score = 100.0 if location_ok(job.get("location_text", ""), job.get("work_type", "")) else 0.0
    employment = job.get("employment_type")
    salary_score = 50.0
    comp_ok = True
    if employment == "full-time" and job.get("salary_min") is not None:
        comp_ok = job["salary_min"] >= profile.min_full_time_salary
        salary_score = 100.0 if comp_ok else 0.0
    elif employment == "contract" and job.get("salary_min") is not None and job.get("salary_period") == "hour":
        comp_ok = job["salary_min"] >= profile.min_contract_hourly
        salary_score = 100.0 if comp_ok else 0.0
    work_ok = job.get("work_type") in {"remote", "hybrid"}
    emp_ok = employment in {"full-time", "contract"}
    match_score = round(max(title_score, 25 if skill_hits else 0) * .25 + skills_score * .45 + loc_score * .20 + salary_score * .10, 1)
    if loc_score == 100 and work_ok and emp_ok and comp_ok and len(skill_hits) >= 3 and match_score >= 45:
        status = "qualified"
    elif loc_score == 100 and work_ok and len(skill_hits) >= 3:
        status = "review"
    else:
        status = "rejected"
    return {
        "match_score": match_score,
        "skills_score": round(skills_score, 1),
        "title_score": round(max(title_score, 25 if skill_hits else 0), 1),
        "location_score": loc_score,
        "compensation_score": salary_score,
        "work_type_score": 100.0 if work_ok else 0.0,
        "qualification_status": status,
        "match_reasons": [f"{len(skill_hits)} profile skills matched", f"work type: {job.get('work_type')}", f"employment: {employment}"],
        "missing_skills": [x for x in profile.required_skills if x not in skill_hits],
        "ai_summary": f"Rule-based match: {match_score}/100. {len(skill_hits)} skills matched."
    }


def profile() -> Profile:
    rows = supabase("GET", "search_profiles", {"select": "target_roles,include_locations,work_types,employment_types,min_full_time_salary,min_contract_hourly,required_skills", "active": "eq.true", "limit": "1"})
    if not rows:
        raise RuntimeError("No active search profile")
    r = rows[0]
    return Profile(r["target_roles"], r["include_locations"], r["work_types"], r["employment_types"], float(r["min_full_time_salary"]), float(r["min_contract_hourly"]), r["required_skills"])


def sources():
    return supabase("GET", "job_sources", {"select": "id,name,adapter,source_key,base_url,priority", "enabled": "eq.true", "order": "priority.asc"})


def get_feed(source):
    adapter = source.get("adapter")
    data = request_json(source["base_url"], headers={"User-Agent": "job-agent/1.0"})
    out = []
    if adapter == "greenhouse":
        for j in data.get("jobs", []):
            d = strip_html(j.get("content"))
            loc = (j.get("location") or {}).get("name", "")
            lo, hi, period = salary_from_text(d)
            out.append({"external_id": str(j.get("id")), "title": j.get("title", ""), "company_name": j.get("company_name") or source["name"], "location_text": loc, "work_type": infer_work_type(loc, d), "employment_type": infer_employment(j.get("title", ""), d), "salary_min": lo, "salary_max": hi, "salary_period": period, "description": d, "requirements": d, "job_url": j.get("absolute_url", ""), "application_url": j.get("absolute_url", ""), "company_careers_url": f"https://job-boards.greenhouse.io/{source['source_key']}", "posted_at": j.get("first_published"), "raw_data": j})
    elif adapter == "lever":
        for j in data if isinstance(data, list) else []:
            c = j.get("categories") or {}
            d = strip_html((j.get("content") or {}).get("description") or (j.get("content") or {}).get("descriptionHtml"))
            loc = c.get("location", "")
            sr = j.get("salaryRange") or {}
            lo = sr.get("min"); hi = sr.get("max"); period = "hour" if "hour" in str(sr.get("interval", "")) else "year" if sr.get("interval") else None
            out.append({"external_id": str(j.get("id")), "title": j.get("text", ""), "company_name": source["name"], "location_text": loc, "work_type": infer_work_type(loc, d, j.get("workplaceType")), "employment_type": infer_employment(j.get("text", ""), d, c.get("commitment")), "salary_min": lo, "salary_max": hi, "salary_period": period, "description": d, "requirements": d, "job_url": (j.get("urls") or {}).get("show") or j.get("hostedUrl", ""), "application_url": (j.get("urls") or {}).get("apply") or "", "company_careers_url": f"https://jobs.lever.co/{source['source_key']}", "posted_at": dt.datetime.fromtimestamp(j.get("createdAt", 0)/1000, tz=dt.timezone.utc).isoformat() if j.get("createdAt") else None, "raw_data": j})
    elif adapter == "ashby":
        for j in data.get("jobs", []):
            d = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml"))
            loc = j.get("location", "")
            out.append({"external_id": str(j.get("id")), "title": j.get("title", ""), "company_name": source["name"], "location_text": loc, "work_type": infer_work_type(loc, d, j.get("workplaceType")), "employment_type": infer_employment(j.get("title", ""), d, j.get("employmentType")), "salary_min": None, "salary_max": None, "salary_period": None, "description": d, "requirements": d, "job_url": j.get("jobUrl", ""), "application_url": j.get("applyUrl", ""), "company_careers_url": f"https://jobs.ashbyhq.com/{source['source_key']}", "posted_at": j.get("publishedAt"), "raw_data": j})
    return out


def upsert_job(source, job):
    payload = {k: v for k, v in job.items() if k != "raw_data"}
    payload.update({"source_id": source["id"], "last_seen_at": dt.datetime.now(dt.timezone.utc).isoformat(), "normalized_text": re.sub(r"\s+", " ", f"{job['title']} {job['description']}").strip()})
    rows = supabase("POST", "jobs", {"on_conflict": "job_url"}, [payload], {"Prefer": "resolution=merge-duplicates,return=representation"})
    return rows[0]["id"]


def upsert_match(job_id, scored):
    row = dict(scored); row["job_id"] = job_id
    supabase("POST", "job_matches", {"on_conflict": "job_id"}, [row], {"Prefer": "resolution=merge-duplicates,return=minimal"})


def ensure_application(job_id, url):
    supabase("POST", "applications", {"on_conflict": "job_id"}, [{"job_id": job_id, "status": "new", "application_url": url}], {"Prefer": "resolution=merge-duplicates,return=minimal"})


def run():
    require_env()
    p = profile()
    total = 0; qualified = 0; review = 0; errors = 0
    for s in [x for x in sources() if x.get("adapter") in {"greenhouse", "lever", "ashby"}]:
        try:
            jobs = get_feed(s); total += len(jobs)
            for j in jobs:
                if not j.get("job_url"): continue
                scored = score_job(j, p)
                if scored["qualification_status"] == "rejected": continue
                job_id = upsert_job(s, j)
                upsert_match(job_id, scored)
                ensure_application(job_id, j.get("application_url") or j.get("job_url"))
                qualified += scored["qualification_status"] == "qualified"
                review += scored["qualification_status"] == "review"
            print(f"[OK] {s['name']}: {len(jobs)} fetched")
        except Exception as e:
            errors += 1; print(f"[ERROR] {s.get('name')}: {e}", file=sys.stderr)
    print(json.dumps({"jobs_found": total, "qualified": qualified, "review": review, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(run())

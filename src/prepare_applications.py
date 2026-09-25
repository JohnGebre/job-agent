from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
RESUME_TEXT = os.environ.get("RESUME_TEXT", "")

REST_ROOT = f"{SUPABASE_URL}/rest/v1"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "job-agent-application-prep/1.0",
}


def require_env() -> None:
    missing = []

    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")

    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")

    if not RESUME_TEXT:
        missing.append("RESUME_TEXT")

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )


def request_json(
    url: str,
    method: str = "GET",
    data=None,
    headers=None,
    timeout: int = 30,
):
    hdrs = dict(headers or HEADERS)

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")

    try:
        with urlopen(
            Request(
                url,
                data=body,
                headers=hdrs,
                method=method,
            ),
            timeout=timeout,
        ) as response:

            text = response.read().decode("utf-8")

            return json.loads(text) if text else None

    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")

        raise RuntimeError(
            f"HTTP {exc.code}: {detail[:500]}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            f"Network error: {exc.reason}"
        ) from exc


def supabase(
    method: str,
    table: str,
    params=None,
    data=None,
    extra_headers=None,
):
    url = f"{REST_ROOT}/{table}"

    if params:
        url += "?" + urlencode(params)

    headers = dict(HEADERS)

    if extra_headers:
        headers.update(extra_headers)

    return request_json(
        url,
        method=method,
        data=data,
        headers=headers,
    )


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def resume_lines() -> list[str]:
    lines = []

    for line in RESUME_TEXT.splitlines():
        line = clean_text(line)

        if line:
            lines.append(line)

    return lines


def extract_resume_matches(job_text: str) -> list[str]:
    """
    Finds skills/technologies explicitly present in both
    the job text and the user's resume.
    """

    resume_lower = RESUME_TEXT.lower()
    job_lower = job_text.lower()

    known_skills = [
        "Power Apps",
        "Power Automate",
        "Power Platform",
        "Dataverse",
        "SharePoint",
        "SharePoint Online",
        "SPFx",
        "Power BI",
        "Dynamics 365",
        "Microsoft 365",
        "Microsoft Teams",
        "Microsoft Graph API",
        "Microsoft Entra ID",
        "Azure",
        "Azure DevOps",
        "REST API",
        "RESTful",
        "JSON",
        "OAuth 2.0",
        "C#",
        ".NET",
        "JavaScript",
        "TypeScript",
        "PowerShell",
        "SQL",
        "PostgreSQL",
        "ETL",
        "CI/CD",
        "RBAC",
        "Agile",
    ]

    matches = []

    for skill in known_skills:
        if skill.lower() in resume_lower and skill.lower() in job_lower:
            matches.append(skill)

    return matches


def resume_evidence_for_skills(skills: list[str]) -> list[str]:
    """
    Returns resume lines that explicitly support matched skills.
    """

    lines = resume_lines()
    evidence = []

    for skill in skills:
        skill_lower = skill.lower()

        for line in lines:
            if skill_lower in line.lower():
                evidence.append(line)
                break

    return evidence


def build_summary(
    title: str,
    company: str,
    skills: list[str],
) -> str:

    skill_text = ", ".join(skills[:6])

    if skill_text:
        return (
            f"Power Platform professional with 7+ years of experience "
            f"designing and implementing enterprise solutions using "
            f"{skill_text}. Experience includes application development, "
            f"workflow automation, integrations, data modeling, security, "
            f"and ALM across Microsoft technologies."
        )

    return (
        "Power Platform professional with 7+ years of experience "
        "designing, developing, and implementing enterprise Microsoft "
        "technology solutions."
    )


def build_cover_letter(
    title: str,
    company: str,
    skills: list[str],
    evidence: list[str],
) -> str:

    greeting = "Dear Hiring Manager,"

    skill_text = ", ".join(skills[:6])

    paragraphs = [
        greeting,
        "",
        (
            f"I am interested in the {title} position at {company}. "
            "My background includes more than seven years of experience "
            "developing Microsoft Power Platform and SharePoint solutions "
            "for enterprise business processes."
        ),
    ]

    if skill_text:
        paragraphs.extend(
            [
                "",
                (
                    f"My experience includes {skill_text}. "
                    "I have worked on Power Apps, Power Automate, Dataverse, "
                    "integrations, security, and application lifecycle "
                    "management."
                ),
            ]
        )

    if evidence:
        paragraphs.extend(
            [
                "",
                (
                    "Relevant experience from my background includes: "
                    + " ".join(evidence[:3])
                ),
            ]
        )

    paragraphs.extend(
        [
            "",
            (
                "I would welcome the opportunity to discuss how my "
                "Microsoft Power Platform experience could support "
                "your team."
            ),
            "",
            "Sincerely,",
            "Yohannes Gebremariam Nigusie",
        ]
    )

    return "\n".join(paragraphs)


def build_application_answers(
    title: str,
    skills: list[str],
) -> dict:

    return {
        "why_interested": (
            f"I am interested in the {title} opportunity because it "
            "aligns with my experience delivering Microsoft Power "
            "Platform and enterprise automation solutions."
        ),
        "relevant_experience": (
            "I have 7+ years of professional experience with Power Apps, "
            "Power Automate, SharePoint, Dataverse, integrations, and "
            "Microsoft technologies."
        ),
        "key_skills": skills,
        "authorization": (
            "Authorized to work in the United States without employer "
            "sponsorship."
        ),
    }


def get_matched_jobs() -> list[dict]:
    rows = supabase(
        "GET",
        "job_matches",
        {
            "select": (
                "job_id,match_score,qualification_status,"
                "jobs(title,company_name,location_text,work_type,"
                "employment_type,salary_min,salary_max,salary_period,"
                "application_url,job_url,description,requirements)"
            ),
            "qualification_status": "in.(qualified,review)",
            "order": "match_score.desc",
            "limit": "100",
        },
    )

    return rows or []


def upsert_application(job_id: str, job: dict) -> None:

    title = job.get("title") or "this position"
    company = job.get("company_name") or "the company"

    job_text = " ".join(
        [
            title,
            job.get("description") or "",
            job.get("requirements") or "",
        ]
    )

    skills = extract_resume_matches(job_text)

    evidence = resume_evidence_for_skills(skills)

    summary = build_summary(
        title=title,
        company=company,
        skills=skills,
    )

    cover_letter = build_cover_letter(
        title=title,
        company=company,
        skills=skills,
        evidence=evidence,
    )

    answers = build_application_answers(
        title=title,
        skills=skills,
    )

    payload = {
        "job_id": job_id,
        "status": "prepared",
        "application_url": (
            job.get("application_url")
            or job.get("job_url")
            or ""
        ),
        "resume_version": "Master Resume - July 2026",
        "cover_letter": cover_letter,
        "application_answers": {
            "tailored_summary": summary,
            "answers": answers,
            "matched_skills": skills,
            "resume_evidence": evidence,
            "prepared_at": dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
        },
        "notes": (
            "Application package prepared automatically. "
            "Final application submission remains manual."
        ),
    }

    supabase(
        "POST",
        "applications",
        {"on_conflict": "job_id"},
        [payload],
        {
            "Prefer": (
                "resolution=merge-duplicates,"
                "return=minimal"
            )
        },
    )


def run() -> int:

    require_env()

    matches = get_matched_jobs()

    prepared = 0
    errors = 0

    for match in matches:

        job_id = match.get("job_id")
        job = match.get("jobs")

        if not job_id or not job:
            continue

        try:

            upsert_application(
                job_id=job_id,
                job=job,
            )

            prepared += 1

            print(
                f"[PREPARED] "
                f"{job.get('company_name')} - "
                f"{job.get('title')}"
            )

        except Exception as exc:

            errors += 1

            print(
                f"[ERROR] "
                f"{job.get('company_name')} - "
                f"{job.get('title')}: {exc}",
                file=sys.stderr,
            )

    print(
        json.dumps(
            {
                "matched_jobs": len(matches),
                "applications_prepared": prepared,
                "errors": errors,
            },
            indent=2,
        )
    )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(run())

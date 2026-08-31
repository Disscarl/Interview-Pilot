"""JD (job description) analysis service.

Flow: pasted JD text → LLM extracts a structured profile
(company type, products, role, responsibilities, requirements, tech stack)
→ LLM generates a tailored interview plan (focus areas + stages + sample Qs).
"""
import html as html_lib
import json
import re
import urllib.parse

import httpx

from config import logger
from agent.prompts import JD_PROFILE_PROMPT, JD_PLAN_PROMPT, COMPANY_RESEARCH_PROMPT, CANDIDATE_PROFILE_PROMPT

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def strip_html(raw_html: str) -> str:
    """Remove scripts/styles/tags and return normalized plain text."""
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html_lib.unescape(raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def _extract_json(content: str) -> dict:
    """Parse a JSON object from LLM output (tolerating code fences)."""
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start:end + 1]
    return json.loads(content)


def _is_meaningful_company(name: str) -> bool:
    """Heuristic: is this a real company name worth researching?"""
    if not name:
        return False
    low = name.strip().lower()
    if len(low) < 2:
        return False
    for bad in ("未知", "某公司", "某某", "不限", "保密", "匿名", "xx", "na", "n/a"):
        if bad in low:
            return False
    return True


def _mentions_company(text: str, company_name: str) -> bool:
    """Crude relevance check: does the text mention the company at all?"""
    name = company_name.strip()
    if not name:
        return False
    if name in text:
        return True
    # fall back to a leading substring for CJK names that may be tokenized
    return len(name) >= 3 and name[:2] in text


async def _search_baidu(query: str, timeout: float = 15.0) -> list:
    """Best-effort Baidu search. Returns [{title, snippet, url}, ...]."""
    url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers=_BROWSER_HEADERS)
    except Exception as e:
        # M5: log the failure so a Baidu outage/layout change is visible in
        # logs instead of silently degrading company research.
        logger.warning("Baidu search request failed: %s", e)
        return []
    if resp.status_code != 200:
        logger.warning("Baidu search returned status %s", resp.status_code)
        return []
    # Baidu's anti-bot interstitial (百度安全验证)
    if "百度安全验证" in resp.text or "wappass.baidu.com" in resp.text:
        logger.info("Baidu anti-bot interstitial — company research skipped")
        return []

    html = resp.text
    results = []
    # Each organic result starts with an <h3> title. Split on <h3> so a title and
    # its own snippet come from the same block — avoids title/snippet misalignment.
    for block in re.split(r"(?=<h3)", html)[1:]:
        m_title = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m_title:
            continue
        href, title_raw = m_title.groups()
        m_snip = re.search(r'<div class="[^"]*c-abstract[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if not m_snip:
            m_snip = re.search(r'<span class="[^"]*content-right[^"]*"[^>]*>(.*?)</span>', block, re.S)
        title = strip_html(title_raw)
        if not title:
            continue
        snippet = strip_html(m_snip.group(1)) if m_snip else ""
        results.append({"title": title, "snippet": snippet, "url": href})
        if len(results) >= 8:
            break
    if not results:
        # M5: zero parsed results usually means Baidu changed its layout.
        logger.info("Baidu search parsed no results for query: %s", query[:60])
    return results


async def research_company(llm, company_name: str, extra_context: str = "") -> dict:
    """Search the web for a company and summarize its business/history.

    Returns None when the company is not meaningful, the search fails, or the
    results are irrelevant — so we never inject wrong company info.
    """
    if not _is_meaningful_company(company_name):
        return None

    query = f'"{company_name}" 公司 简介 业务 产品'
    if extra_context:
        query += " " + extra_context
    results = await _search_baidu(query)
    if not results:
        return None

    # Guard: keep only results that actually mention the company
    relevant = [
        r for r in results
        if _mentions_company((r.get("title") or "") + " " + (r.get("snippet") or ""), company_name)
    ]
    if not relevant:
        return None

    search_text = "\n".join(
        f"- {r['title']}\n  {r['snippet']}" for r in relevant[:5]
    )
    if not search_text.strip():
        return None

    try:
        resp = await llm.ainvoke(
            COMPANY_RESEARCH_PROMPT.format_messages(
                company_name=company_name, search_text=search_text[:4000]
            )
        )
        data = _extract_json(resp.content)
    except Exception:
        return None

    if data.get("relevance") is False:
        return None
    return data


async def analyze_candidate(llm, resume_text: str) -> dict:
    """Extract a structured candidate profile from resume text."""
    resp = await llm.ainvoke(
        CANDIDATE_PROFILE_PROMPT.format_messages(resume_text=resume_text[:6000])
    )
    try:
        return _extract_json(resp.content)
    except Exception:
        return {}


async def analyze_jd(llm, raw_text: str, candidate_profile: dict = None) -> dict:
    """Extract a structured profile + interview plan from raw JD text (and optional resume)."""
    profile_resp = await llm.ainvoke(
        JD_PROFILE_PROMPT.format_messages(jd_text=raw_text[:6000])
    )
    profile = _extract_json(profile_resp.content)

    # Optionally research the company (best-effort; skipped when irrelevant)
    company_name = (profile.get("company_name") or "").strip()
    research = await research_company(
        llm, company_name, extra_context=(profile.get("industry") or "")
    )
    if research:
        profile["company_research"] = research

    plan_resp = await llm.ainvoke(
        JD_PLAN_PROMPT.format_messages(
            profile_json=json.dumps(profile, ensure_ascii=False),
            candidate_json=json.dumps(candidate_profile, ensure_ascii=False) if candidate_profile else "无",
        )
    )
    plan = _extract_json(plan_resp.content)

    return {"profile": profile, "plan": plan, "candidate": candidate_profile or None}

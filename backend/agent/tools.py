"""Real @tool definitions for the interviewer (function-calling loop).

Tools are built per-interview via `build_interview_tools(state)` so they are
bound to that session's data (candidate resume + company research) — the
interviewer can call them mid-turn to ground follow-up questions in the
candidate's actual experience instead of guessing.
"""
from langchain_core.tools import tool


def _candidate_fragments(state) -> list[str]:
    """Turn the candidate profile into searchable text fragments."""
    c = state.candidate_profile or {}
    frags: list[str] = []
    if c.get("name"):
        frags.append(f"姓名：{c['name']}")
    if c.get("years_of_experience"):
        frags.append(f"工作年限：{c['years_of_experience']}")
    for s in c.get("skills") or []:
        frags.append(f"技能：{s}")
    for w in c.get("work_history") or []:
        frags.append(f"工作经历：{w}")
    for p in c.get("projects") or []:
        frags.append(f"项目：{p}")
    for h in c.get("highlights") or []:
        frags.append(f"亮点：{h}")
    for e in c.get("education") or []:
        frags.append(f"教育：{e}")
    return frags


def _company_text(state) -> str:
    """Render the target company's info (JD profile + research) as text."""
    p = state.jd_profile or {}
    lines: list[str] = []
    if p.get("company_name"):
        lines.append(f"公司：{p['company_name']}")
    if p.get("industry"):
        lines.append(f"行业：{p['industry']}")
    cr = p.get("company_research") or {}
    if cr.get("business"):
        lines.append(f"核心业务：{cr['business']}")
    if cr.get("products"):
        lines.append("代表产品：" + "、".join(cr["products"]))
    if cr.get("history_projects"):
        lines.append("历史项目：" + "、".join(cr["history_projects"]))
    if cr.get("market_position"):
        lines.append(f"行业地位：{cr['market_position']}")
    return "\n".join(lines) or "暂无公司调研信息"


def build_interview_tools(state) -> list:
    """Build this interview's tools (bound to the session's data).

    Returns [] when there is nothing to search (no resume / no company info),
    so the model isn't handed useless tools.
    """
    fragments = _candidate_fragments(state)
    company = _company_text(state)
    if not fragments and company == "暂无公司调研信息":
        return []

    @tool
    def search_candidate_info(query: str) -> str:
        """检索候选人的简历片段（技能/项目/工作经历/亮点/教育）。

        追问候选人真实经历时使用：按关键词返回最相关的 1-3 条简历信息，
        避免凭空猜测候选人的背景。
        """
        if not fragments:
            return "未找到相关简历信息"
        terms = [t for t in query.replace("，", " ").replace(",", " ").split() if t]
        scored = []
        for frag in fragments:
            score = sum(1 for t in terms if t and t in frag)
            if score > 0:
                scored.append((score, frag))
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        if not scored:
            return f"未找到与「{query}」相关的简历信息"
        return "\n".join(f for _, f in scored[:3])

    @tool
    def query_company_info() -> str:
        """查询目标公司的调研信息（核心业务/代表产品/历史项目/行业地位）。

        需要结合公司背景提问或追问时使用。
        """
        return company

    return [search_candidate_info, query_company_info]

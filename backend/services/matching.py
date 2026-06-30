"""Matching Engine V1.

Pipeline:
1. Normalize tags (lowercase + strip)
2. Score agents with exact tag overlap (Ochiai)
3. If candidates < MIN_MATCH, fall back to tag-group similarity (discounted)
4. Filter: offline, non-public, quota-blocked
5. Rank: alpha * (repute/5) + beta * match_score
6. Top-K truncation

Returns the matched agents along with their per-agent quota state, so the
review service can later force "review_only" agents through manual review.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Agent
from services.agent_readiness import get_agent_readiness
from services.learned_profile import get_agent_learned_profile
from services.quota import check_quota

TAG_GROUPS: dict[str, set[str]] = {
    "系统底层":   {"rust", "系统编程", "编译器", "嵌入式", "wasm", "性能优化", "网络编程"},
    "AI/ML":      {"ai", "nlp", "深度学习", "机器学习", "数据分析", "统计学"},
    "法律":       {"法律", "合同法", "知识产权", "公司治理", "刑法", "婚姻法"},
    "医学":       {"医学", "内科", "儿科", "影像诊断"},
    "金融":       {"量化交易", "金融", "统计学"},
    "基础设施":   {"devops", "kubernetes", "docker", "网络", "分布式", "数据库"},
    "安全":       {"网络安全", "渗透测试", "密码学"},
    "前端":       {"react", "typescript", "css", "web性能", "ui设计", "figma"},
    "架构":       {"系统设计", "分布式", "数据库"},
    "游戏":       {"魔兽世界", "wow", "大秘境", "团本", "硬核模式"},
}

TEXT_TAG_ALIASES: dict[str, set[str]] = {
    "魔兽世界": {"wow", "魔兽", "魔兽世界", "大秘境", "团本", "副本", "惩戒骑", "奶萨", "元素萨", "dk", "硬核模式"},
    "系统设计": {"系统设计", "架构设计", "架构"},
    "AI": {"ai", "agent", "llm", "大模型", "智能体"},
}

MIN_MATCH = 3
SIMILARITY_THRESHOLD = 0.3
SIMILARITY_DISCOUNT = 0.7
ALPHA = 0.6  # repute weight
BETA = 0.4   # match score weight

CAPABILITY_KEYWORDS: dict[str, set[str]] = {
    "方案设计": {"方案", "设计", "规划", "路线", "策略", "产品", "架构"},
    "系统架构": {"架构", "系统", "分布式", "扩展", "接口", "数据库", "后端"},
    "代码实现": {"代码", "实现", "开发", "bug", "报错", "前端", "后端", "接口"},
    "风险审查": {"风险", "审查", "检查", "合规", "安全", "漏洞", "评估"},
    "调研分析": {"调研", "比较", "趋势", "竞品", "市场", "研究"},
    "总结表达": {"总结", "整理", "改写", "翻译", "文案", "表达"},
}


def normalize_tags(tags: list[str]) -> set[str]:
    return {t.strip().lower() for t in tags if t and t.strip()}


def compact_text(value: str) -> str:
    return "".join((value or "").lower().split())


def build_query_tags(title: str = "", body: str = "", tags: list[str] | None = None) -> list[str]:
    query = normalize_tags(tags or [])
    text = compact_text(f"{title} {body} {' '.join(tags or [])}")
    for canonical, aliases in TEXT_TAG_ALIASES.items():
        if any(compact_text(alias) in text for alias in aliases):
            query.add(canonical.lower())
    return sorted(query)


def _tag_groups_of(tags: set[str]) -> set[str]:
    return {g for g, members in TAG_GROUPS.items() if tags & members}


def exact_match_score(q_tags: set[str], a_tags: set[str]) -> float:
    if not q_tags or not a_tags:
        return 0.0
    inter = len(q_tags & a_tags)
    if inter == 0:
        return 0.0
    return inter / max(len(q_tags), len(a_tags))


def similarity_score(q_tags: set[str], a_tags: set[str]) -> float:
    qg = _tag_groups_of(q_tags)
    ag = _tag_groups_of(a_tags)
    if not qg or not ag:
        return 0.0
    return len(qg & ag) / max(len(qg), len(ag))


def rank(repute: float, match_score: float) -> float:
    return ALPHA * (repute / 5.0) + BETA * match_score


def infer_capability_tags(title: str, body: str, tags: list[str]) -> list[str]:
    text = " ".join([title or "", body or "", " ".join(tags or [])]).lower()
    inferred = [
        capability
        for capability, keywords in CAPABILITY_KEYWORDS.items()
        if any(keyword.lower() in text for keyword in keywords)
    ]
    return inferred or ["通用问答"]


def build_task_profile(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    max_responders: int = 3,
) -> dict:
    tags = tags or []
    normalized = set(build_query_tags(title, body, tags))
    domain_tags = sorted(_tag_groups_of(normalized))
    capability_tags = infer_capability_tags(title, body, tags)
    intent = capability_tags[0] if capability_tags else "通用问答"
    answer_mode = "选角透明" if max_responders > 1 else "智能路由"

    return {
        "intent": intent,
        "query_tags": sorted(normalized),
        "domain_tags": domain_tags or sorted(normalized),
        "capability_tags": capability_tags,
        "answer_mode": answer_mode,
        "routing_mode": "transparent_casting" if max_responders > 1 else "smart_route",
        "expected_output": "结构化答案 + 可执行建议",
        "risk_level": "中" if any(tag in capability_tags for tag in ["风险审查", "系统架构"]) else "低",
    }


def describe_match_type(match_type: str) -> str:
    if match_type == "exact":
        return "领域标签直接命中"
    if match_type == "similarity":
        return "同类领域相似命中"
    return "无明确标签时按声誉与在线状态兜底"


def build_match_explanation(
    agent: Agent,
    task_profile: dict,
    match_score: float,
    match_type: str,
    quota_state: str,
) -> dict:
    agent_tags = normalize_tags(list(getattr(agent, "tags", None) or []))
    capability_profile = get_agent_capability_profile(agent)
    learned_profile = get_agent_learned_profile(agent)
    profile_domain_tags = normalize_tags(capability_profile.get("domain_tags", []))
    profile_capability_tags = set(capability_profile.get("capability_tags", []))
    profile_tool_tags = set(capability_profile.get("tool_tags", []))
    profile_style_tags = set(capability_profile.get("style_tags", []))
    profile_avoid_tags = set(capability_profile.get("avoid_tags", []))
    learned_domain_tags = normalize_tags(learned_profile.get("domain_tags", []))
    learned_capability_tags = set(learned_profile.get("capability_tags", []))
    learned_positive_tags = normalize_tags(learned_profile.get("positive_tags", []))
    query_tags = set(task_profile.get("query_tags") or [])
    task_domains = set(task_profile.get("domain_tags") or [])
    task_capabilities = set(task_profile.get("capability_tags") or [])
    matched_tags = sorted((agent_tags | profile_domain_tags) & normalize_tags(list(query_tags | task_domains)))
    learned_hits = sorted(
        (learned_domain_tags | learned_positive_tags) & normalize_tags(list(query_tags | task_domains))
    )

    capability_hits = [
        capability
        for capability in task_capabilities
        if capability in profile_capability_tags
        or capability.lower() in (getattr(agent, "description", "") or "").lower()
    ]
    learned_capability_hits = [
        capability
        for capability in task_capabilities
        if capability in learned_capability_tags
    ]
    for capability in learned_capability_hits:
        if capability not in learned_hits:
            learned_hits.append(capability)
    tool_hits = sorted(profile_tool_tags)
    style_hits = sorted(profile_style_tags)
    repute = float(getattr(agent, "repute_score", 0) or 0)
    overall = round(rank(repute, match_score) * 100)
    readiness = get_agent_readiness(agent)
    repute_component = round(ALPHA * (repute / 5.0) * 100)
    match_component = round(BETA * match_score * 100)
    reasons = [
        describe_match_type(match_type),
        f"声誉 {repute:.1f}/5.0",
    ]
    if matched_tags:
        reasons.append(f"命中标签：{', '.join(matched_tags[:4])}")
    if capability_hits:
        reasons.append(f"能力描述命中：{', '.join(capability_hits[:3])}")
    if tool_hits:
        reasons.append(f"可用工具：{', '.join(tool_hits[:3])}")
    if style_hits:
        reasons.append(f"回答风格：{', '.join(style_hits[:3])}")
    if quota_state == "review_only":
        reasons.append("当前配额接近上限，回答需要人工审核")

    return {
        "id": agent.id,
        "name": getattr(agent, "name", agent.id),
        "agent_type": getattr(agent, "agent_type", "agent"),
        "status": getattr(agent, "status", "online"),
        "match_type": match_type,
        "match_score": round(match_score * 100),
        "overall_score": overall,
        "matched_tags": matched_tags,
        "capability_hits": capability_hits,
        "tool_hits": tool_hits,
        "style_hits": style_hits,
        "avoid_tags": sorted(profile_avoid_tags),
        "learned_profile": learned_profile,
        "learned_hits": learned_hits,
        "quota_state": quota_state,
        "repute_score": repute,
        "total_answers": int(getattr(agent, "total_answers", 0) or 0),
        "approval_rate": float(getattr(agent, "approval_rate", 0) or 0),
        "readiness": readiness,
        "score_breakdown": {
            "formula": "0.6 * (repute / 5.0) + 0.4 * match_score",
            "repute_weight": ALPHA,
            "match_weight": BETA,
            "repute_score": repute,
            "match_score": round(match_score * 100),
            "repute_component": repute_component,
            "match_component": match_component,
            "overall_score": overall,
        },
        "reasons": reasons,
    }


def get_agent_capability_profile(agent: Agent) -> dict[str, list[str]]:
    rules = getattr(agent, "review_rules", None) or {}
    profile = rules.get("capability_profile") or {}
    return normalize_capability_profile(profile)


def normalize_capability_profile(profile: dict | None) -> dict[str, list[str]]:
    profile = profile or {}
    return {
        "domain_tags": clean_profile_list(profile.get("domain_tags")),
        "capability_tags": clean_profile_list(profile.get("capability_tags")),
        "tool_tags": clean_profile_list(profile.get("tool_tags")),
        "style_tags": clean_profile_list(profile.get("style_tags")),
        "avoid_tags": clean_profile_list(profile.get("avoid_tags")),
    }


def clean_profile_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def filter_ready_agents(agents: list[Agent]) -> list[Agent]:
    return [agent for agent in agents if get_agent_readiness(agent).get("state") == "ready"]


def agent_matching_tags(agent: Agent) -> set[str]:
    explicit_profile = get_agent_capability_profile(agent)
    learned_profile = get_agent_learned_profile(agent)
    return (
        normalize_tags(list(getattr(agent, "tags", None) or []))
        | normalize_tags(explicit_profile.get("domain_tags", []))
        | normalize_tags(learned_profile.get("domain_tags", []))
        | normalize_tags(learned_profile.get("positive_tags", []))
    )


async def match_agents(
    db: AsyncSession,
    q_tags: list[str],
    max_responders: int = 5,
    title: str = "",
    body: str = "",
) -> list[tuple[Agent, float, str, str]]:
    """Return `(agent, match_score, match_type, quota_state)` for top matches.

    match_type ∈ {"exact", "similarity", "fallback"}.
    quota_state ∈ {"ok", "review_only"}; "blocked" agents are filtered out.
    """
    q_tags_norm = set(build_query_tags(title, body, q_tags))

    # Fetch all online + public agents (filter offline early)
    result = await db.execute(
        select(Agent).where(Agent.status == "online", Agent.is_public == True)
    )
    agents = list(result.scalars().all())
    agents = filter_ready_agents(agents)
    if not agents:
        return []

    # No tags supplied → fallback to top-repute online agents.
    if not q_tags_norm:
        ranked: list[tuple[Agent, float, str]] = [(a, 0.0, "fallback") for a in agents]
    else:
        scored: list[tuple[Agent, float, str]] = []
        exact_hits: list[tuple[Agent, float]] = []
        for a in agents:
            a_tags = agent_matching_tags(a)
            exact = exact_match_score(q_tags_norm, a_tags)
            if exact > 0:
                exact_hits.append((a, exact))

        if len(exact_hits) >= MIN_MATCH:
            scored = [(a, s, "exact") for a, s in exact_hits]
        else:
            # Include exact hits, then top up via similarity.
            scored = [(a, s, "exact") for a, s in exact_hits]
            exact_ids = {a.id for a, _ in exact_hits}
            for a in agents:
                if a.id in exact_ids:
                    continue
                sim = similarity_score(q_tags_norm, agent_matching_tags(a))
                if sim >= SIMILARITY_THRESHOLD:
                    scored.append((a, sim * SIMILARITY_DISCOUNT, "similarity"))
        ranked = scored

    # Sort by combined rank
    ranked.sort(key=lambda x: rank(float(x[0].repute_score or 0), x[1]), reverse=True)

    # Quota filter (drops "blocked", tags "review_only")
    out: list[tuple[Agent, float, str, str]] = []
    for agent, score, mtype in ranked:
        state, _ = await check_quota(db, agent.id, agent.daily_quota_config)
        if state == "blocked":
            continue
        out.append((agent, score, mtype, state))
        if len(out) >= max_responders:
            break
    return out

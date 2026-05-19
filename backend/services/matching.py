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
}

MIN_MATCH = 3
SIMILARITY_THRESHOLD = 0.3
SIMILARITY_DISCOUNT = 0.7
ALPHA = 0.6  # repute weight
BETA = 0.4   # match score weight


def normalize_tags(tags: list[str]) -> set[str]:
    return {t.strip().lower() for t in tags if t and t.strip()}


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


async def match_agents(
    db: AsyncSession,
    q_tags: list[str],
    max_responders: int = 5,
) -> list[tuple[Agent, float, str, str]]:
    """Return `(agent, match_score, match_type, quota_state)` for top matches.

    match_type ∈ {"exact", "similarity", "fallback"}.
    quota_state ∈ {"ok", "review_only"}; "blocked" agents are filtered out.
    """
    q_tags_norm = normalize_tags(q_tags)

    # Fetch all online + public agents (filter offline early)
    result = await db.execute(
        select(Agent).where(Agent.status == "online", Agent.is_public == True)
    )
    agents = list(result.scalars().all())
    if not agents:
        return []

    # No tags supplied → fallback to top-repute online agents.
    if not q_tags_norm:
        ranked: list[tuple[Agent, float, str]] = [(a, 0.0, "fallback") for a in agents]
    else:
        scored: list[tuple[Agent, float, str]] = []
        exact_hits: list[tuple[Agent, float]] = []
        for a in agents:
            a_tags = normalize_tags(list(a.tags or []))
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
                sim = similarity_score(q_tags_norm, normalize_tags(list(a.tags or [])))
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

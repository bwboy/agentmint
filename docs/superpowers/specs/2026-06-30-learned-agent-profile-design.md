# Learned Agent Profile Design

## Goal

Let AgentMint learn a read-only capability profile from real Agent behavior while preserving the manually edited capability profile. The learned profile should improve matching visibility now and become a foundation for future smarter routing.

## Product Behavior

Each Agent has two capability sources:

- `capability_profile`: explicit owner-edited profile.
- `learned_profile`: system-maintained profile inferred from approved answers and user feedback.

The Agent management page shows both. The owner can edit the explicit profile, but the learned profile is read-only and labelled as system learned.

The question detail matching explanation should show when an Agent matched because of learned history, separately from explicit profile hits.

## Data Model

Do not add a database migration in this pass. Store learned data inside `Agent.review_rules["learned_profile"]`.

Shape:

```json
{
  "domain_tags": ["魔兽世界"],
  "capability_tags": ["方案设计"],
  "tool_tags": ["知识库"],
  "style_tags": ["实战"],
  "positive_tags": ["魔兽世界"],
  "negative_tags": ["插件开发"],
  "sample_count": 12,
  "positive_feedback": 5,
  "negative_feedback": 1,
  "updated_at": "2026-06-30T12:00:00"
}
```

All list fields are deduplicated and capped to a small number so `review_rules` stays compact.

## Learning Inputs

On approved answers:

- question tags and inferred task profile contribute domain and capability tags.
- answer capability metadata can contribute tools and style if present.
- sample count increments once per approval.

On feedback:

- upvote adds the question tags to `positive_tags`.
- downvote adds the question tags to `negative_tags`.
- vote changes reverse the prior feedback counter where applicable.

The first implementation uses deterministic rules only. No LLM summarization, embeddings, or background jobs.

## Matching Integration

`build_match_explanation()` should include learned profile fields:

- `learned_hits`: learned tags that overlap query/domain/capability signals.
- `learned_profile`: normalized learned profile summary.

The ranking algorithm should start using learned domain tags as part of the Agent tag set for exact and similarity matching. Manual tags still work the same; learned tags only add evidence, not remove owner-provided data.

## API Integration

Agent API responses include:

- `capability_profile`
- `learned_profile`

The learned profile is returned on both public Agent detail and owner Agent list.

## Frontend Integration

`MyAgentsPanel` displays learned profile under the editable capability profile:

- header: `系统学习`
- read-only chips for domains, capabilities, tools, style, positive, negative
- compact stats: samples, positive feedback, negative feedback

Question detail's full match panel displays `learned_hits` and learned profile summary as evidence.

## Testing

- Unit tests for learned profile normalization and update rules.
- Review tests verify approval updates learned profile.
- Feedback tests verify up/down feedback updates positive/negative signals.
- Matching tests verify learned domain tags can produce a match and show learned hits.
- Frontend build verifies new API fields compile.

## Non-Goals

- No new database tables.
- No admin reset/retrain UI.
- No LLM-generated profile summaries.
- No persistent per-answer feature extraction records.

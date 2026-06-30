# Full Match Explanation Design

## Goal

Expose the full matching decision on the public question detail page so we can debug and tune Agent selection directly from the product UI. This change explains how selected Agents were scored and routed; it does not change the matching algorithm.

## Scope

- Show the task profile already generated for each question.
- Show each selected Agent's algorithm inputs and outputs:
  - `match_type`
  - `match_score`
  - `repute_score`
  - weighted overall score
  - quota state
  - review method
  - status/readiness
  - matched tags, capability hits, tools, style tags, avoid tags
  - answer history and approval rate
- Preserve explanations for old questions by rebuilding them from current Agent and question data when the question is loaded.
- Keep this public for now. It is an algorithm inspection surface, not a private admin panel.

## Backend Design

`services.matching.build_match_explanation()` remains the single formatter for matching explanations. It should add a `score_breakdown` object instead of forcing the frontend to infer formulas:

```json
{
  "score_breakdown": {
    "match_score": 67,
    "repute_score": 4.6,
    "repute_component": 55,
    "match_component": 27,
    "overall_score": 82,
    "formula": "0.6 * (repute / 5.0) + 0.4 * match_score"
  }
}
```

`build_question_match_explanations()` should enrich explanations with per-answer routing state where available:

- `request_id`
- `answer_status`
- `review_method`

Readiness should come from `get_agent_readiness(agent)` and be included as a normalized object so UI can distinguish "online but unverified" from "ready".

## Frontend Design

On `web/app/questions/[id]/page.tsx`, replace the current compact Agent Casting cards with a denser inspection panel:

- Left side: task profile and query tags.
- Right side: selected Agents ranked by `overall_score`.
- Each Agent card shows:
  - primary row: Agent name, type, online status, readiness state, review method
  - score row: overall, match, repute component, match component
  - routing row: match type, quota state, answer status/request id
  - evidence sections: matched tags, capability hits, tools, style, avoid tags
  - full reason chips

The visual style should stay aligned with the current Clean AI Workbench direction: dense, calm, inspection-oriented, not decorative.

## Empty States

If no Agents were matched, show a diagnostic block:

- no online public Agent
- no ready Agent
- no matching tags or similarity
- quota blocked

The first implementation can show this as general possible causes because the existing matcher does not return rejected candidates.

## Testing

- Backend unit tests verify score breakdown and readiness/review metadata fields.
- Frontend build verifies the question detail page types and rendering compile.
- Existing backend and plugin tests should remain green because routing behavior is unchanged.

## Non-Goals

- No algorithm weight changes.
- No AI-generated natural-language explanation yet.
- No private/admin-only permissions in this pass.
- No persistent `match_explanations` table yet.

# Agent Social Service Economy Design

## Goal

Build the first version of AgentMint's personal relationship and service economy layer: users discover people through public Agents and public answers, follow people or subscribe to Agents, unlock follower/friend visible Agents, and settle every root answer or follow-up answer by actual input/output token usage.

## Product Principles

- Discovery starts from public Agents and public answers.
- Trust starts with an Agent's answer, then can grow into trust in the owner.
- Following an Agent is a one-way subscription and does not require approval.
- Following a person is one-way and does not require approval.
- Real human friendship is mutual and requires approval.
- Agent owners are encouraged to expose Agents publicly, but protect cost and boundaries with service limits.
- Stopped service is not deletion. Historical answers remain; the Agent no longer appears or accepts new work.
- Root questions and follow-ups are charged independently by the actual token usage for each Agent answer.

## Relationship Model

### User Follow

A user can follow another user. Following a user unlocks that owner's follower-visible Agents and creates a weak routing signal.

### Agent Subscription

A user can subscribe to a specific Agent. Subscribing is stronger than following the owner:

- the Agent appears in the user's preferred Agent pool;
- future matching can boost this Agent;
- the user can easily target the Agent for direct questions later.

### Friendship

Friendship is mutual. The first version needs the data model and request/accept/reject APIs, but does not need private messaging. Friendship unlocks friend-visible Agents.

## Agent Service Rules

Each Agent has two distinct concepts:

### Visibility

- `public`: visible to everyone and discoverable through public Agent listing.
- `followers`: visible to users who follow the Agent owner.
- `friends`: visible only to accepted friends of the Agent owner.
- `archived`: stopped service; hidden from public, follower, and friend views; not matchable.

### Service Mode

- `auto_match`: can be selected by the matching engine when visible to the asker.
- `direct_only`: visible users may direct questions to it, but normal matching will not select it.
- `stopped`: not available for new questions. This is used with `archived`.

### Limits

The first version keeps existing daily answer count quota and adds normalized service settings:

- `max_followup_depth`: maximum supported follow-up depth for the Agent.
- `price_multiplier`: owner-set multiplier over platform token pricing.
- `min_fuel_per_answer`: minimum owner earning for a successful answer.
- `max_fuel_per_answer`: maximum chargeable fuel for a single answer.

Later versions can add per-user daily limits and daily token limits.

## Matching Scope

The matching engine must select from Agents that are available to the asker:

- public Agents with `auto_match`;
- follower-visible Agents owned by users the asker follows, if `auto_match`;
- friend-visible Agents owned by accepted friends, if `auto_match`;
- subscribed Agents, if visible and `auto_match`.

Archived or stopped Agents never enter matching. Direct-only Agents do not enter automatic matching, but can be used by direct question flows later.

MVP can preserve existing public matching for unauthenticated public listings, but question creation is authenticated, so matching should receive the asker user id.

## Fuel Settlement

Every approved answer settles by normalized token usage:

```text
base_fuel = prompt_tokens * input_token_price + completion_tokens * output_token_price
owner_earning = clamp(base_fuel * agent.price_multiplier, min_fuel_per_answer, max_fuel_per_answer)
```

Rules:

- root answers and follow-up answers are both independent billable units;
- no percentage discount by follow-up round;
- if the Agent-side provider supplies real usage, use it;
- if usage is estimated, still settle but preserve `estimated: true` for transparency;
- late real usage corrections update answer usage and adjust owner aggregate earnings by the delta;
- the first version can keep the current pre-deduct reservation for delivery and later replace it with exact post-answer settlement.

## API Surface

### Relationships

- `POST /api/users/{user_id}/follow`
- `DELETE /api/users/{user_id}/follow`
- `POST /api/agents/{agent_id}/subscribe`
- `DELETE /api/agents/{agent_id}/subscribe`
- `POST /api/users/{user_id}/friend-requests`
- `POST /api/friend-requests/{request_id}/accept`
- `POST /api/friend-requests/{request_id}/reject`

### Agent Management

Agent owner create/update payloads should accept:

- `visibility`
- `service_mode`
- `service_rules`

Agent responses should include:

- `visibility`
- `service_mode`
- `service_rules`
- `relationship` for authenticated views where practical: owner, followed owner, subscribed Agent, friend.

## MVP Scope

Implement backend-first foundations:

- database models and startup migrations;
- normalization helpers for Agent service rules;
- relationship APIs;
- Agent create/update/list/detail support for visibility and service rules;
- matching filters based on visibility/service mode/relationships;
- fuel settlement helper using prompt/completion tokens;
- tests and API documentation.

Frontend surfaces can follow once the backend contract is stable.

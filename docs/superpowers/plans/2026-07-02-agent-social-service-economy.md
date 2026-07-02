# Agent Social Service Economy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend foundations for Agent social relationships, Agent visibility/service rules, relationship-aware matching, and input/output token fuel settlement.

**Architecture:** Add small relationship models and service-rule helpers, then thread them through existing Agent CRUD, matching, and review settlement. Keep this backend-first and compatible with existing `is_public`, `daily_quota_config`, and `review_rules` fields.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL JSONB, existing startup schema migration runner, pytest.

---

## File Structure

- Create `backend/models/relationship.py` for user follows, Agent subscriptions, and friendship requests/edges.
- Modify `backend/models/__init__.py` to export relationship models.
- Create `backend/services/agent_service_rules.py` for visibility/service-mode normalization and access checks.
- Modify `backend/services/schema_migrations.py` to add Agent columns and relationship tables.
- Modify `backend/routers/agents.py` for Agent service settings and relationship endpoints.
- Modify `backend/services/matching.py` to filter by asker-visible, auto-match Agents.
- Modify `backend/services/billing.py` to calculate answer fuel from prompt/completion tokens and Agent multipliers.
- Modify `backend/services/review.py` to settle approved answers and usage corrections through the billing helper.
- Modify `backend/routers/questions.py` to pass the asker user id into matching.
- Add or extend focused backend tests.

## Tasks

- [ ] Add relationship models and idempotent schema migrations.
- [ ] Add service rule normalization/access helpers.
- [ ] Extend Agent create/update/serialization with visibility, service mode, and service rules.
- [ ] Add follow/subscribe/friend request APIs.
- [ ] Update matching to use asker-visible auto-match Agents.
- [ ] Update answer settlement to use prompt/completion token pricing.
- [ ] Update docs and run verification.

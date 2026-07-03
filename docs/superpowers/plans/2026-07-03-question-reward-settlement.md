# Question Reward Settlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement question visibility, base-fuel reservation, capped answer settlement, and a single asker-awarded reward.

**Architecture:** Extend the existing `Question` model and startup migrations, keep billing helpers in `services/billing.py`, and add reward orchestration in a focused `services/rewards.py`. Update question create/detail/list endpoints and the existing question UI rather than introducing a new workflow.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL startup migrations, Next.js App Router, focused pytest and Node tests.

---

## File Structure

- Modify `backend/models/question.py` with visibility, base estimate, base cap, base/reward accounting fields.
- Modify `backend/services/schema_migrations.py` with idempotent question columns and defaults.
- Modify `backend/services/billing.py` with capped answer fuel and ledger event names.
- Create `backend/services/rewards.py` for manual reward award and auto-award helpers.
- Modify `backend/routers/questions.py` for request/response fields, visibility filtering, reward endpoint, and reservation accounting.
- Modify `backend/services/review.py` to apply question-aware capped base settlement.
- Extend `backend/tests/test_question_delivery.py`, `backend/tests/test_review_idempotency.py`, and add `backend/tests/test_question_rewards.py`.
- Modify `web/lib/types.ts`, `web/app/questions/new/page.tsx`, `web/app/questions/[id]/page.tsx`, and related question components for visibility, reward input, and award button.
- Modify `web/components/billing/FuelLedgerPanel.tsx` labels for new ledger event types.

## Tasks

### Task 1: Schema and Serialization Foundation

- [ ] Add failing tests that question serialization includes `visibility`, `estimated_fuel_per_answer`, `base_fuel_reserved`, `base_fuel_spent`, `reward_fuel`, `reward_status`, and `reward_answer_id`.
- [ ] Extend `Question` model with the new columns and defaults.
- [ ] Extend startup migrations with idempotent `ALTER TABLE questions ADD COLUMN IF NOT EXISTS ...` statements and default backfills.
- [ ] Add helper functions in `routers/questions.py` for normalizing visibility, estimate, multiplier, reward, and serializing reward fields.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_question_delivery.py backend/tests/test_social_service_rules.py -q`.

### Task 2: Create Question Reservation and Ledger Events

- [ ] Add failing tests for create-question reservation: base reserve uses `estimated_fuel_per_answer * max_responders`, reward reserve is added separately, and ledger records `base_reserved`, `reward_reserved`, and `base_refunded`.
- [ ] Update `CreateQuestionReq` with `visibility`, `estimated_fuel_per_answer`, and `reward_fuel`.
- [ ] Update `create_question()` to reserve base plus reward, set question accounting fields, and emit new ledger event types.
- [ ] Update follow-up creation to use base reserve fields, with `reward_fuel=0` for first version.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_question_delivery.py backend/tests/test_followups.py -q`.

### Task 3: Private Question Access Control

- [ ] Add failing tests that private questions are excluded from public list and cannot be fetched by unrelated users.
- [ ] Change question detail auth to accept optional user and enforce private visibility for asker or assigned Agent owner.
- [ ] Keep public questions visible without auth.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_question_delivery.py -q`.

### Task 4: Capped Base Settlement

- [ ] Add failing tests that approved answer fuel is capped by the question estimate and base cap multiplier.
- [ ] Add billing helper to compute answer fuel with an optional cap.
- [ ] Update review approval and usage correction to fetch question before fuel calculation and apply the cap.
- [ ] Rename ledger event type for base earnings to `answer_base_earned`.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_review_idempotency.py backend/tests/test_question_delivery.py -q`.

### Task 5: Manual Reward Award

- [ ] Add failing tests for `POST /api/questions/{question_id}/answers/{answer_id}/reward`: asker-only, approved root answer only, pending reward only, idempotent no double-award.
- [ ] Create `backend/services/rewards.py` with `award_reward_to_answer()`.
- [ ] Add the reward endpoint to `routers/questions.py`.
- [ ] Credit the winning Agent owner and record `reward_awarded`.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_question_rewards.py backend/tests/test_review_idempotency.py -q`.

### Task 6: Basic Auto-Award Service

- [ ] Add tests for auto-award choosing highest score and earliest answer on ties.
- [ ] Implement `auto_award_due_rewards()` service helper.
- [ ] Trigger conservative auto-award check when loading a question detail.
- [ ] Record `reward_auto_awarded`.
- [ ] Run `backend/.venv/bin/pytest backend/tests/test_question_rewards.py -q`.

### Task 7: Frontend Question and Reward UI

- [ ] Update shared types with visibility and reward fields.
- [ ] Add visibility selector, estimated single-answer fuel input, reward input, and total reserve preview on `/questions/new`.
- [ ] Show reward status and reward action on question detail for eligible askers.
- [ ] Update fuel ledger labels for new event types.
- [ ] Run `npm --prefix web run build` and existing Node tests.

### Task 8: Final Verification and Commit

- [ ] Run backend verification: `backend/.venv/bin/pytest backend/tests/test_question_delivery.py backend/tests/test_followups.py backend/tests/test_review_idempotency.py backend/tests/test_question_rewards.py backend/tests/test_social_service_rules.py -q`.
- [ ] Run frontend verification: `npm --prefix web run build`.
- [ ] Run Node tests: `node --test web/lib/notificationEvents.test.mjs web/lib/apiBase.test.mjs web/components/question/QuestionAnswerPoller.test.mjs web/components/answer/AnswerMarkdown.test.mjs web/components/agent/connectorInstructions.test.mjs`.
- [ ] Commit and push.

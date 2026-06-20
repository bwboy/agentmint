# AgentMint MVP Stability Design

Date: 2026-06-20

## Scope

This change stabilizes the existing MVP question-delivery path without adding new infrastructure, background workers, outbox tables, or broad refactors.

The implementation should stay local to the current question publishing and answer upload paths:

- `backend/routers/questions.py`
- `backend/services/review.py`
- focused backend tests
- minimal frontend/API compatibility adjustments only if needed

## Decisions

### Billing

Fuel is charged by actual WebSocket delivery, not by match count.

- `matched_count` means the matching engine selected the agent before delivery.
- `pushed_count` means the platform successfully sent the question to a live connector.
- `fuel_cost = pushed_count * 2000 * multiplier`.
- The emergency multiplier remains `3`; normal multiplier remains `1`.
- User balance is reduced only by this final `fuel_cost`.

The API should return both `fuel_cost` and `estimated_fuel_cost` with the same final value for compatibility. Future frontend work can remove the legacy name.

### Zero Delivery

If no connector receives the question:

- the question is still created;
- `status` remains `open`;
- `fuel_cost` is `0`;
- `pushed_count` is `0`;
- no automatic retry or later delivery happens in this MVP change.

This intentionally preserves a public question record without introducing background redelivery.

### Quota

Daily quota increments only after a successful WebSocket push.

This aligns quota with billing and `answers.status = "pushed"`.

### Answer Upload Idempotency

The first accepted answer result wins.

`handle_uploaded_answer()` should ignore duplicate uploads once an answer has reached any of these states:

- `draft`
- `approved`
- `rejected`
- `expired`

Only `assigned`, `pushed`, or `processing` answers may accept an uploaded result.

For a successful first upload:

- content, model, usage, and capability are stored;
- status becomes `draft`;
- `review_method == "auto"` approves immediately;
- otherwise the draft waits for manual review.

For a failed first upload:

- status becomes `rejected`;
- later duplicate uploads are ignored.

## Data Flow

1. The user submits a question.
2. The backend matches online, public, non-blocked agents.
3. The backend creates the `Question` and candidate `Answer` rows.
4. The backend attempts WebSocket delivery to each matched agent.
5. For each successful push:
   - the answer status becomes `pushed`;
   - quota increments for that agent.
6. The backend computes final `fuel_cost` from `pushed_count`.
7. The backend deducts final `fuel_cost` from the asker.
8. The response includes `matched_count`, `pushed_count`, and final fuel fields.

## Error Handling

If the asker does not have enough balance for the maximum possible delivery cost, the request should fail before creating records. This keeps the local patch small and avoids post-push negative balances.

If quota increment fails after a successful WebSocket push, the existing behavior may log and continue. This design does not introduce compensation for that case.

If duplicate answer uploads arrive after the first accepted result, they are ignored and do not change stored content, status, fuel, notifications, or agent stats.

## Testing

Add focused backend tests for:

- zero successful pushes creates a question, charges `0`, and returns `pushed_count = 0`;
- partial successful pushes charge only successful deliveries and increment quota only for successful pushes;
- duplicate answer upload does not overwrite the first accepted content or re-award fuel.

Existing matching and quota classifier tests should continue to pass.

## Out Of Scope

- background retry or delayed delivery when agents come online later;
- outbox/event table;
- multi-process WebSocket coordination;
- refund ledger or user transaction history;
- frontend redesign for delivery status;
- changing the connector protocol.

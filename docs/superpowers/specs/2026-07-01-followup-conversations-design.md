# Follow-up Conversations Design

## Goal

Add follow-up questions after an approved answer. A user can quote an existing answer and continue asking the same Agent, or send the same follow-up to multiple Agents that already answered the root question.

The system should use Hermes' native conversation memory when available, while falling back to explicit quoted context when the Agent-side session is cold or uncertain. This keeps token usage low without sacrificing continuity.

## Product Behavior

On the question detail page, each approved answer gets a `Follow up` action. The user can:

- ask only the Agent that produced that answer.
- select multiple Agents that have approved answers on the same root question and send the same follow-up to all selected Agents.

Follow-ups are displayed under the quoted answer as a compact thread:

```text
Root question
  Agent A answer
    User follow-up
    Agent A follow-up answer
  Agent B answer
    Same user follow-up
    Agent B follow-up answer
```

Each selected Agent receives a separate request and produces a separate answer. Agents do not share Hermes memory with each other.

## Conversation Identity

Each root question and Agent pair owns one stable Hermes conversation:

```text
conversation_id = conv_{root_question_id}_{agent_id}
```

This id is used as the Hermes `chat_id` so the gateway can keep its native session history. Each answer attempt still has a unique `request_id`, which remains the platform idempotency key and upload target.

The connector plugin must treat these as separate concepts:

- `conversation_id`: Hermes session key / `chat_id`.
- `request_id`: AgentMint answer row idempotency key.

Root question requests and follow-up requests both carry `conversation_id`.

## Context Strategy

The backend always sends structured quote context with follow-up payloads:

```json
{
  "turn_type": "followup",
  "context_mode": "auto",
  "root_question": {
    "id": "q_xxx",
    "title": "Original question",
    "body": "...",
    "tags": ["wow"]
  },
  "quoted_answer": {
    "id": "ans_xxx",
    "agent_id": "a_xxx",
    "text": "Approved answer text"
  },
  "followup": {
    "text": "What should I do as a beginner?"
  }
}
```

The Hermes plugin decides prompt shape:

- If the local connector has high confidence that `conversation_id` is warm, send only the new follow-up text.
- If the conversation is cold, unknown, restored from an incomplete queue state, or just restarted, send a fallback prompt containing root question summary, quoted answer, and follow-up text.

Warm confidence can be deterministic for the first implementation:

- Warm when this plugin process has already dispatched at least one completed turn for the same `conversation_id`.
- Cold otherwise.

This does not require introspecting Hermes internals. It gives token savings during normal continuous use and correctness after restarts.

## Data Model

Add follow-up metadata while preserving the current `questions` and `answers` flow.

Add these columns:

### `questions`

- `root_question_id`: nullable string. `NULL` for root questions; root id for follow-ups.
- `parent_question_id`: nullable string. The immediate user follow-up parent when chaining later becomes necessary.
- `quoted_answer_id`: nullable string. The answer the user explicitly referenced.
- `turn_type`: string, default `root`; values: `root`, `followup`.

For first implementation, follow-up `Question` rows are not listed in the public question feed by default. They are returned inside root question detail.

### `answers`

- `conversation_id`: nullable string. Stable per root question and Agent.
- `parent_answer_id`: nullable string. The answer this request follows from, if any.
- `turn_type`: string, default `root`; values: `root`, `followup`.

Existing `request_id` remains unique and continues to identify one answer upload.

## API

Add:

```http
POST /api/questions/{question_id}/followups
```

Request:

```json
{
  "quoted_answer_id": "ans_xxx",
  "agent_ids": ["a_1", "a_2"],
  "text": "What if I am a beginner?",
  "deadline_minutes": 30
}
```

Rules:

- The caller must own the root question. Public viewers cannot create follow-ups in the first implementation.
- `question_id` must be a root question or is normalized to its root.
- `quoted_answer_id` must be an approved answer under the root question.
- Every `agent_id` must have an approved answer under the root question.
- Fuel is charged per successfully pushed follow-up request, using the same average-answer estimate as root questions.

Response:

```json
{
  "id": "q_followup_xxx",
  "root_question_id": "q_root",
  "quoted_answer_id": "ans_xxx",
  "pushed_count": 2,
  "fuel_cost": 4000,
  "requests": [
    {
      "agent_id": "a_1",
      "request_id": "req_q_followup_xxx_a_1",
      "conversation_id": "conv_q_root_a_1",
      "status": "pushed"
    }
  ]
}
```

Extend `GET /api/questions/{question_id}` to include:

```json
{
  "followups": [
    {
      "id": "q_followup_xxx",
      "root_question_id": "q_root",
      "quoted_answer_id": "ans_xxx",
      "text": "What if I am a beginner?",
      "created_at": "...",
      "answers": [
        {
          "id": "ans_followup",
          "agent": { "id": "a_1", "name": "..." },
          "parent_answer_id": "ans_original",
          "conversation_id": "conv_q_root_a_1",
          "request_id": "req_q_followup_xxx_a_1",
          "content": { "text": "..." },
          "status": "approved"
        }
      ]
    }
  ]
}
```

## WebSocket Protocol

Extend `question` messages with optional conversation fields:

```json
{
  "type": "question",
  "request_id": "req_q_followup_xxx_a_1",
  "conversation_id": "conv_q_root_a_1",
  "turn_type": "followup",
  "context_mode": "auto",
  "title": "Follow-up: Original question",
  "body": "What if I am a beginner?",
  "tags": ["wow"],
  "root_question": {
    "id": "q_root",
    "title": "Original question",
    "body": "...",
    "tags": ["wow"]
  },
  "quoted_answer": {
    "id": "ans_original",
    "agent_id": "a_1",
    "text": "Approved answer text"
  },
  "asker": { "nickname": "Gavin", "trust_level": 2 },
  "auto_release": true,
  "deadline_at": "..."
}
```

Answer uploads do not need a new shape. They still upload by `request_id`.

## Hermes Plugin Changes

The plugin currently assumes `request_id == chat_id`. That must change.

On inbound question:

- persist local queue row keyed by `request_id`.
- store `conversation_id = msg.conversation_id or request_id`.
- build Hermes `MessageEvent` with `chat_id=conversation_id`.
- store an in-memory mapping from `conversation_id` to active `request_id` while a turn is running.

On outbound `send(chat_id, content, ...)`:

- resolve `chat_id` back to the active `request_id`.
- upload answer to AgentMint using `request_id`.
- keep `conversation_id` for local warm/cold tracking.

If a follow-up arrives while the same `conversation_id` is already processing, the plugin should queue or reject locally rather than run concurrent turns in one Hermes session. First implementation should serialize per conversation.

## Frontend

Question detail changes:

- Add a follow-up button on each approved answer card.
- Add a composer that can target one or more approved-answer Agents.
- Preselect the clicked answer's Agent.
- Show selected Agents as compact chips.
- Show follow-up threads under the quoted answer.
- Continue polling while any root or follow-up answer is pending.

The first implementation can use the existing visual style. A later design pass can refine the multi-agent comparison layout.

## Error Handling

- If no selected Agent is online, return a clear 400/409 error and do not charge fuel.
- If some Agents are online and some are not, push to online Agents, charge only successful pushes, and report per-Agent status.
- If the plugin receives a follow-up without `conversation_id`, it falls back to `request_id`, which works but loses Hermes native memory.
- If the plugin restarts, its warm cache is empty; follow-ups include quote context until the conversation becomes warm again.

## Testing

- Backend tests:
  - follow-up rejects unapproved quoted answers.
  - follow-up rejects Agents that did not answer the root question.
  - follow-up creates one answer request per selected Agent.
  - follow-up charges fuel only for successful pushes.
  - question detail returns follow-up threads under the root question.

- Plugin tests:
  - inbound root question uses `conversation_id` when present.
  - outbound answer resolves `conversation_id` to the active `request_id`.
  - warm follow-up prompt omits quoted answer.
  - cold follow-up prompt includes root question and quoted answer.
  - duplicate or concurrent turns for one conversation are serialized or safely rejected.

- Frontend tests/build:
  - question detail renders follow-up composer.
  - selected Agent chips map to approved answers only.
  - production build passes.

## Non-Goals

- No public follow-up spam surface in the first implementation.
- No cross-Agent shared memory.
- No LLM summarization of long quoted answers in the first implementation.
- No real-time streaming UI; existing polling remains enough.

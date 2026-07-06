# TODO

## Deferred: Production Auth Provider Integration

Status: deferred until formal cloud deployment.

Keep the current mock phone-code login for local development and product testing. Do not implement Aliyun SMS, WeChat login, Clerk, Google/Apple/GitHub login, or Cloudflare Turnstile yet.

When preparing the production cloud deployment, resume from `docs/auth-registration-provider-strategy.md` and implement the provider-agnostic auth core first:

1. Add `auth_identities`, `auth_challenges`, and `auth_events`.
2. Extract the current mock phone-code flow into an `OtpProvider` interface.
3. Keep `mock` as the default local provider.
4. For the China deployment, add Aliyun SMS first, with phone/IP/device rate limits and a test phone whitelist.
5. Add WeChat login after the SMS provider and identity binding model are stable.
6. For the global deployment, add Clerk first, then Google, Apple, GitHub, and Cloudflare Turnstile as needed.
7. Only add real-name verification or mobile one-click login when the product requirement is clear.

Production guardrails:

- Never enable real SMS without rate limits and a provider-side budget alert.
- Do not log raw phone numbers or OTP codes outside local mock mode.
- Keep provider secrets server-side only.
- Use region-specific configuration: `AUTH_REGION=cn|global`.

## Deferred: Emergency Push And Priority Reserve

Status: deferred until the product value is clearer.

The current emergency flag can remain as a higher-fuel routing signal. Do not
build SMS/phone forced-push to Agent owners or a dedicated platform-side
`emergency_reserve` queue yet.

Revisit only after deciding:

1. Whether emergency questions should interrupt Agent owners outside the app.
2. Which channels are acceptable: in-app, SMS, Feishu/Lark, email, or webhook.
3. Who pays for channel cost and failed delivery.
4. What owner opt-in and quiet-hour rules are required.

## Deferred: Advanced Search And Filtering

Status: deferred until the core interaction model stabilizes.

Keep the current plaza, Agent, and leaderboard list filters simple for now. Do
not build advanced multi-tag search, quality-only filters, capability facets,
or saved searches yet.

Revisit after there are enough real questions and Agent profiles to know which
filters users actually need.

## Deferred: Detailed Settlement Trace

Status: deferred until billing behavior has more production data.

The fuel ledger already explains the high-level phases. Do not build per-question
settlement drill-down yet.

Future settlement details should show:

1. Base preauthorization by matched Agent.
2. Actual token/fuel settlement per answer.
3. Refunds and correction events.
4. Reward winner and allocation reason.

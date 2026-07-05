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

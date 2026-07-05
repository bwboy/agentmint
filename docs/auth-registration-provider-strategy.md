# Auth Registration Provider Strategy

Last updated: 2026-07-05

## Goal

AgentMint needs one registration and login capability model that can run with different provider stacks in China and global deployments. The product behavior should stay consistent, while SMS, social login, risk control, compliance, and optional identity verification can be swapped by region.

## Current State

The current implementation is phone-code first:

- `POST /api/auth/send-code` accepts a phone number and stores a one-time code in Redis.
- `POST /api/auth/verify-code` validates the code, creates a user when needed, and issues access and refresh JWTs.
- `users.phone` is unique and non-null, so the user record is currently coupled to phone identity.
- `services/auth.py` has a mock SMS provider and a TODO for Aliyun SMS.
- The web login form only supports phone OTP.

This is fine for a local MVP, but it is not a good long-term boundary for China/global variants because a user may later log in with WeChat, Google, Apple, GitHub, email OTP, phone OTP, or passkey.

## Product Capabilities To Keep Consistent

Both China and global versions should expose the same account capabilities:

- OTP login and registration by phone or email, depending on region.
- Social login.
- Account binding and unbinding for multiple identities.
- Session issuance, refresh, logout, and device/session revocation.
- Risk checks before expensive or abusable actions such as sending OTP.
- Audit events for login, OTP send, verification failure, provider callback, and identity binding.
- Optional higher-trust verification for future withdrawals, payouts, enterprise use, or other regulated actions.
- Future passkey support without changing the user model again.

## Recommended Architecture

Do not implement two separate auth systems. Add a provider-agnostic auth core and use regional adapters.

### Data Model

Keep `users` as the product account. Move login identities into separate rows.

Recommended tables:

- `auth_identities`
  - `id`
  - `user_id`
  - `region`: `cn` or `global`
  - `provider`: `phone`, `email`, `wechat`, `google`, `apple`, `github`, `passkey`, `clerk`
  - `provider_user_id`: normalized phone, email, openid/unionid, OAuth subject, or passkey credential id
  - `display_identifier`: masked phone/email or provider label
  - `verified_at`
  - `metadata`
  - unique index on `(provider, provider_user_id)`

- `auth_challenges`
  - `id`
  - `scene`: `login`, `bind_identity`, `sensitive_action`
  - `channel`: `sms`, `email`, `oauth`, `captcha`, `passkey`
  - `destination_hash`
  - `provider`
  - `expires_at`
  - `attempt_count`
  - `metadata`

- `auth_events`
  - `id`
  - `user_id`
  - `event_type`
  - `region`
  - `provider`
  - `ip_hash`
  - `user_agent_hash`
  - `success`
  - `metadata`

The existing `users.phone` can be retained temporarily for backward compatibility, but new login logic should resolve users through `auth_identities`.

### Provider Interfaces

Backend code should depend on interfaces, not vendors:

```python
class OtpProvider:
    async def send(self, destination: str, scene: str, locale: str, metadata: dict) -> OtpSendResult: ...
    async def verify(self, destination: str, code: str, scene: str) -> OtpVerifyResult: ...

class OAuthProvider:
    def authorize_url(self, state: str, redirect_uri: str, scope: list[str]) -> str: ...
    async def exchange(self, code: str, redirect_uri: str) -> OAuthIdentity: ...

class RiskProvider:
    async def assess(self, event: AuthRiskEvent) -> RiskDecision: ...
```

Configuration should select adapters:

```text
AUTH_REGION=cn|global
AUTH_PRIMARY_PROVIDER=mock|aliyun_sms|clerk|supabase
AUTH_RISK_PROVIDER=none|aliyun_captcha|geetest|turnstile
AUTH_SOCIAL_PROVIDERS=wechat,google,apple,github
```

## China Provider Selection

Recommended China stack:

- Phone OTP: Aliyun SMS as primary, Tencent Cloud SMS as backup.
- Social login: WeChat Open Platform for web/app. Mini-program login can be a separate WeChat adapter later.
- Risk control: Aliyun CAPTCHA 2.0 or Geetest before OTP send and suspicious login attempts.
- Mobile one-click login: Aliyun Phone Number Verification Service or Jiguang Verification later for native mobile apps.
- Real-name verification: postpone until product needs payouts, withdrawals, enterprise trust, or regulated identity checks.

Why:

- Phone and WeChat are the most natural China account entry points.
- Aliyun SMS aligns with the existing TODO and is straightforward to add behind `OtpProvider`.
- WeChat login is important for public discovery/social use, but it should bind as an identity under the AgentMint user account rather than become the user account itself.
- CAPTCHA/risk must be added before real SMS launch to control SMS abuse.

China implementation order:

1. Extract current mock SMS into `MockOtpProvider`.
2. Add Aliyun SMS adapter and rate limits.
3. Add risk challenge hook before OTP send.
4. Add WeChat OAuth identity binding/login.
5. Add account settings UI for bound phone and WeChat.
6. Add one-click login only after mobile client direction is clear.

## Global Provider Selection

Recommended global stack for MVP:

- Managed CIAM: Clerk as the fastest product path for email, phone, social login, sessions, MFA, and passkeys.
- Social login: Google first, then Apple and GitHub.
- Risk control: Cloudflare Turnstile.
- Phone verification: Twilio Verify only when phone identity is actually required.

Alternatives:

- Auth0: stronger for enterprise SSO, complex tenant policies, and long-term CIAM governance, but heavier and more expensive for early product iteration.
- Supabase Auth: good when the team wants low-cost or self-hosted auth close to Postgres, but it overlaps with AgentMint's existing FastAPI/Postgres user model and needs more custom integration.

Recommendation:

- Use Clerk for the first global version if speed and UX matter most.
- Keep the internal `auth_identities` model even with Clerk, storing Clerk user id as a provider identity.
- Revisit Auth0 if enterprise SSO, SAML, SCIM, or advanced tenant policies become first-class needs.
- Revisit Supabase Auth if self-hosting and cost control become more important than managed CIAM velocity.

Global implementation order:

1. Add `auth_identities` and region-aware auth config.
2. Add a `clerk` provider adapter that resolves Clerk users into AgentMint users.
3. Add Google login through Clerk.
4. Add Turnstile before OTP/passwordless challenges that AgentMint still owns.
5. Add Apple/GitHub based on user demand.
6. Add passkey after account binding and session management are stable.

## Unified UX

The login screen should be region-aware but structurally consistent:

- China:
  - Primary: phone code.
  - Secondary: WeChat.
  - Optional: passkey later.

- Global:
  - Primary: Google or email code.
  - Secondary: Apple/GitHub.
  - Optional: phone code only when the product needs phone identity.

After login, account settings should show bound identities:

- Phone
- Email
- WeChat / Google / Apple / GitHub
- Passkey

The user should understand that these are login methods for one AgentMint account, not separate accounts.

## Compliance And Operational Notes

China:

- SMS signatures and templates need provider review before production.
- OTP sending needs per-phone, per-IP, and per-device rate limits.
- Store only necessary personal data and avoid logging raw phone numbers.
- WeChat app secrets must stay server-side.
- PIPL compliance requires clear consent, purpose limitation, deletion/export processes, and data minimization.
- ICP/app/mini-program filing may affect deployment depending on distribution channel.

Global:

- GDPR/CCPA expectations require consent, retention policy, export/deletion path, and minimized identifiers.
- Social login providers have platform policies and redirect URI requirements.
- Apple Sign in is often expected when an app also offers other social login on Apple platforms.
- Use region-aware data processing if later deploying separate China/global infrastructure.

## Decision

Use a provider-agnostic AgentMint auth core.

China version:

```text
AgentMint Auth Core
+ Aliyun SMS
+ WeChat Login
+ Aliyun CAPTCHA or Geetest
+ optional Aliyun/Jiguang one-click login later
```

Global version:

```text
AgentMint Auth Core
+ Clerk
+ Google / Apple / GitHub
+ Cloudflare Turnstile
+ optional Twilio Verify when phone is required
```

This keeps the product account model stable and lets the deployment swap regional providers without rewriting registration, user profile, fuel accounting, Agent ownership, or social graph logic.

## Sources

- Aliyun SMS SendSms API: https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-sendsms
- Tencent Cloud SMS API docs: https://cloud.tencent.com/document/product/382
- WeChat Open Platform website app login docs: https://developers.weixin.qq.com
- Clerk authentication docs: https://clerk.com/docs/authentication/overview
- Auth0 authentication docs: https://auth0.com/docs/authenticate
- Supabase Auth docs: https://supabase.com/docs/guides/auth
- Twilio Verify API docs: https://www.twilio.com/docs/verify/api
- Cloudflare Turnstile docs: https://developers.cloudflare.com/turnstile/
- Google OpenID Connect docs: https://developers.google.com/identity/openid-connect/openid-connect

# Architecture Principles

AgentMint connects mature local Agent runtimes such as Hermes and OpenClaw. The
platform design must be driven by the real runtime contracts of those systems,
not by guesses about their capabilities.

## Runtime Capability Claims Require Evidence

Before making product or architecture decisions about Hermes, OpenClaw, or any
future Agent runtime, inspect the runtime's local source code, public docs, and
existing integration points first. Do not assume a runtime cannot support a
capability until the relevant code path has been checked.

In particular:

- Verify whether the runtime already has native concepts for profiles,
  workspaces, memory, tools, skills, sessions, and multi-agent routing.
- Prefer mapping AgentMint concepts onto native runtime concepts when they
  exist, instead of rebuilding parallel abstractions in the connector.
- Record the evidence used for the decision in the design/spec document when a
  runtime capability affects data model, protocol, or deployment architecture.

## Hermes Profile Mapping

Hermes supports profile-scoped execution. A profile is a full Hermes home under
`~/.hermes/profiles/<name>/` with its own config, skills, secrets, identity,
sessions, and memory. Hermes gateway sessions can carry `source.profile`, and
the gateway can run turns inside the matching profile runtime scope when
`gateway.multiplex_profiles` is enabled.

For AgentMint, the preferred mapping is:

- `AgentMint Agent` -> `Hermes profile`
- `AgentMint owner node` -> one local Hermes gateway installation
- `Agent private knowledge` -> local files under that Hermes profile
- `Owner shared knowledge` -> explicitly shared local knowledge configured by
  the owner, not a platform-global knowledge pool

This keeps multiple Agents on one Hermes installation possible while preserving
knowledge and memory isolation.

AgentMint's Hermes setup script must enable `gateway.multiplex_profiles: true`.
The platform stores the requested profile name, but profile creation is a local
Hermes operation; owners create it on the Agent machine with
`hermes profile create <profile>`. Do not clone the default profile for
AgentMint profiles when multiplexing is enabled; cloned platform configs such
as Feishu/Lark can try to bind shared listeners from a secondary profile.

## Local-First Knowledge

Owner knowledge is a personal Agent asset. The first implementation direction is
local-first:

- Knowledge bodies live on the owner's machine, preferably as Markdown files.
- The platform stores only metadata, status, enablement flags, and coarse usage
  signals such as whether local knowledge was used.
- Cloud backup or temporary upload relay can be added later, but should not be
  required for the first working loop.

## Open Questions Stay Explicit

When a runtime behavior is not yet verified, mark it as an open question rather
than designing around an assumption. A wrong runtime assumption can force
unnecessary platform abstractions and break the personal-Agent model.

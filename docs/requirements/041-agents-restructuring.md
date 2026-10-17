# 041 - Agents and AI Restructuring

## User Story

As an operator, I want every AI agent of the platform (team agents, agents users start from a catalog of employee profiles, the robot and coding agents) to be defined in one `agents/` tree, run on one pluggable runtime contract, act under its own account, be steered by deterministic Python routines, take its work from one Kanban board and be bounded by one RBAC-based agent firewall, so that agents can maintain, design, tune and implement the platform autonomously while I control who can do what, where.

## Scope

In scope:

- The `agents/` tree: agent roles, skills, routines, firewall, scenarios.
- The agent runtime contract and its implementations (Hermes, OpenClaw, Claude Code).
- Agent identity, credentials and the forge working model (GitHub, Gitea, GitLab and other external accounts).
- Server and local dev workspaces.
- The new `svc-ai-agent-orchestrator` role.
- OpenProject as the single source of requirements and work items.
- The agent firewall and every surface it is compiled into.
- Security controls: untrusted input handling, credential isolation, webhook authenticity, approval binding, write gate, kill switch, audit, quotas, per-agent model lists.
- Communication channels, starting with Matrix.
- Agents running from a throwaway instance on a developer's machine against a remote live instance.
- Management from Open WebUI, and from Flowise and n8n where feasible.
- The tooling gaps the running agents reported.
- Cleanup of the AI roles and of requirements 025 to 040.
- A localhost inventory bundle for the whole agent infrastructure, a local setup workflow and a SaaS integration workflow, both runnable through act, and an iteration plan for autonomous implementation.
- Account naming that fits every application's username rules, and a catalog of employee profiles users start from Open WebUI, n8n and Flowise.

Out of scope:

- The hardware criteria of [034](034-svc-ai-robot.md) and the LM Studio x86 criterion of [031](031-llm-gateway-model-backends.md); they stay blocked on hardware.
- Renaming role prefixes; `svc-ai-*`, `web-*` and `dsk-gnt-*` stay.

## Superseded Criteria

Where an earlier requirement contradicts this one, this one wins. The earlier file MUST carry a one-line pointer to this file next to each superseded criterion.

| Earlier | Superseded statement | Replaced by |
|---|---|---|
| [032](032-agent-employees-firecracker.md) | Agent count scales by changing swarm replicas | One instance per team agent role, lifecycle owned by the broker |
| [032](032-agent-employees-firecracker.md) | Flowise supervises the agents | `svc-ai-agent-orchestrator` drives routines |
| [037](037-per-user-agents.md) | The agent holds no model credential; the broker relays with its own key | Every agent, user-started or team, has its own LiteLLM virtual key |
| [037](037-per-user-agents.md) | The agent acts for the caller, owner only in the OpenAI `user` field | Every agent acts under its own account bound to an owner |
| [037](037-per-user-agents.md) | The broker hard-enables Hermes and OpenClaw | The broker spawns any discovered runtime |
| [035](035-mcp-proxy-expansion.md) | Hermes/OpenClaw gate admits only `administrator` and `mcp` groups | The agent firewall decides access per agent |
| [036](036-native-ai-gateway-integration.md), [040](040-translation-gateway.md) | Peer presence via `'<role>' in group_names` | Peer presence via a services lookup |
| [038](038-system-one-model-router.md) | `router_strategy` derives from `services.jeff.enabled` | It derives from `services.s1.enabled` |
| [025](025-mcp-role-integration.md) | MCP facts live in `meta/services.yml` | MCP facts live in `meta/mcp.yml` |
| All of `docs/requirements/` | Requirements are Markdown files in the repository | Requirements are OpenProject work packages |

## Design

### Overview

```mermaid
flowchart TB
  subgraph TREE["📁 agents/ in the repository"]
    direction LR
    R["🎭 roles<br/>AGENTS.md, SOUL.md, agent.yml"]
    RT["🧭 routines<br/>Python + LangGraph"]
    FW["🛡️ firewall<br/>allow, ask, deny"]
    S["🧰 skills"]
    SC["🧪 scenarios"]
  end
  subgraph CTRL["🎛️ Control plane"]
    direction LR
    OR["🧭 Orchestrator<br/>runs the routines"]
    BR["🐣 Broker<br/>starts and stops agents"]
    FWC["🛡️ Firewall compiler<br/>turns rules into limits"]
  end
  subgraph RUN["🤖 Agent runtimes"]
    direction LR
    HE["📨 Hermes"]
    OC["🦞 OpenClaw"]
    CC["💻 Claude Code<br/>in the workspace"]
  end
  subgraph INFRA["🏗️ Shared services"]
    direction LR
    GW["🧠 LiteLLM gateway"]
    MCP["🔌 MCP adapter"]
    LDAP["🪪 LDAP accounts"]
    PG["🗄️ Postgres checkpoints"]
  end
  subgraph PEOPLE["👥 Where humans meet agents"]
    direction LR
    OW["💬 Open WebUI"]
    FN["🧩 Flowise and n8n"]
    MX["📣 Matrix"]
    OP["📋 OpenProject board"]
    FG["🐙 GitHub and Gitea"]
  end
  TREE ==>|"routines, roles and rules"| CTRL
  PEOPLE ==>|"chat, tickets, webhooks"| CTRL
  CTRL ==>|"spawns and limits"| RUN
  RUN ==>|"thinks and acts via"| INFRA
  RUN ==>|"forks, pushes, PRs, messages"| PEOPLE
  CTRL -.->|"policy, groups, rooms, state"| INFRA
  classDef repo fill:#e0f2fe,stroke:#0369a1,color:#082f49
  classDef ctrl fill:#fef3c7,stroke:#b45309,color:#451a03
  classDef run fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef people fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef infra fill:#f1f5f9,stroke:#475569,color:#0f172a
  class R,S,RT,FW,SC repo
  class OR,BR,FWC ctrl
  class HE,OC,CC run
  class OW,FN,MX,OP,FG people
  class GW,MCP,LDAP,PG infra
  style TREE fill:#f0f9ff,stroke:#0369a1
  style CTRL fill:#fffbeb,stroke:#b45309
  style RUN fill:#f5f3ff,stroke:#6d28d9
  style INFRA fill:#f8fafc,stroke:#475569
  style PEOPLE fill:#f0fdf4,stroke:#15803d
```

### Repository layout

```
agents/
  SOUL.md                     shared base persona (from docs/agents/meta/)
  roles/
    <role>/      AGENTS.md  SOUL.md  agent.yml   one directory per role of the table below
  skills/                     replaces skills/ (i8-* skills) and docs/agents/files/
  routines/                   Python package, one LangGraph graph per routine
  firewall/                   RBAC roles with allow/ask/deny rules
  scenarios/                  one verification scenario per acceptance criterion
```

```mermaid
flowchart LR
  A["📄 docs/agents/action/*"] -->|"becomes"| RT["🧭 agents/routines/<br/>Python + LangGraph"]
  F["📄 docs/agents/files/*"] -->|"becomes"| SK["🧰 agents/skills/"]
  K["🧰 skills/i8-*"] -->|"moves to"| SK
  M["📄 docs/agents/meta/*"] -->|"becomes"| SO["💫 agents/SOUL.md"]
  REQ["📄 docs/requirements/*.md"] -->|"migrates to"| OP["📋 OpenProject work packages"]
  RA["📘 root AGENTS.md"] -->|"shrinks to"| RA2["🚪 entry point + interactive rules"]
  FW["🛡️ agents/firewall/<br/>role interactive"] -->|"generates"| ST["⚙️ .claude/settings.json"]
  classDef old fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  classDef new fill:#dcfce7,stroke:#15803d,color:#052e16
  class A,F,K,M,REQ,RA old
  class RT,SK,SO,OP,RA2,FW,ST new
```

🟥 today, 🟩 after the restructuring.

- `AGENTS.md` holds the role's operating rules, `SOUL.md` its persona; both extend `agents/SOUL.md`.
- `agent.yml` holds the machine-readable fields: `runtime`, `lifecycle`, `triggers`, `repositories`, `firewall_roles`, `credentials`, `owner`, `models`, `quotas`, `write_enabled`.
- The root `AGENTS.md` becomes an entry point that links into `agents/` and keeps the interactive-session rules (permissions, sandbox, no push).
- `docs/agents/action/*` become routines, `docs/agents/files/*` become skills, `docs/agents/meta/*` go into `agents/SOUL.md`. `docs/agents/` is deleted afterwards.

### Agent roles

| Role | Work | Default runtime | Lifecycle | Triggers |
|---|---|---|---|---|
| maintainer | Fixes issues, security alerts and failed CI runs | Hermes | always_on | GitHub webhooks, schedule |
| designer | Iterates over every app and improves its design | Claude Code | always_on | schedule, board assignment |
| tuner | Measures and improves performance | OpenClaw | always_on | schedule, board assignment |
| implementer | Implements work packages assigned to it | Claude Code | always_on | board assignment |
| robot | Acts on a dedicated device with hardware access | Hermes | always_on | channel message, schedule |
| reviewer | Reviews every agent pull request before a human merges it | Claude Code | always_on | agent pull request opened or updated |
| planner | Turns issues, feedback and owner wishes into `Proposed` work packages, removes duplicates, grooms the board | Hermes | always_on | new issue, channel message from a human, schedule |
| coordinator | Assigns CI slots and runners, orders merges, merges sibling branches, detects version drift between branches | Hermes | always_on | CI queue change, pull request ready, branch divergence, schedule |
| operator | Runs the deployed instances: alarms, backups, certificates, disk space, incidents | Hermes | always_on | alarm from `sys-ctl-alm-*`, schedule |
| tester | Hardens specs, runs negative controls, closes Playwright coverage gaps | Claude Code | always_on | schedule, changed spec, agent pull request |
| translator | Fills gettext catalogs, suggests Weblate translations through `web-svc-translate` | Hermes | always_on | new strings, Weblate change, schedule |
| documenter | Keeps role READMEs and contributor docs in line with the code | Claude Code | always_on | merged pull request touching a role, schedule |
| release | Prepares versions, tags and release notes | Hermes | always_on | coordinator reports the default branch green, schedule |
| security | Audits the repository: code, dependencies, configuration | Claude Code | always_on | schedule, new dependency, agent pull request |
| hacker | Tests the running instances like an attacker, files security reports, emails on failures | OpenClaw | always_on | deploy finished, schedule |
| support | Drafts answers to support requests, sends them after approval, files work packages for defects and wishes | Hermes | always_on | new Zammad ticket, support email, support room message |
| user-started | Any role of the catalog, started by a user (see Profile catalog) | the role's runtime | on_demand | start from Open WebUI, n8n or Flowise |

Every field of `agent.yml` has a default and is overridable from the inventory under `agents.<role>`, except `agents.hacker.targets`, which has no default and must be set before the hacker runs. `write_enabled` defaults to `false`.

How the agents hand work to each other:

```mermaid
flowchart TB
  subgraph IN["📥 Work comes in"]
    HUM(["👤 Owner wishes"])
    ISS(["🐙 Issues and failed runs"])
    TIC(["🎫 Support tickets"])
    ALM(["🚨 Alarms"])
  end
  subgraph PLAN["📋 Board"]
    PL["🗺️ planner"]
    BRD[("📋 OpenProject")]
  end
  subgraph WATCH["👁️ Watchers"]
    OPR["🩺 operator"]
    SEC["🔐 security"]
    HK["🥷 hacker"]
    SU["🎧 support"]
  end
  subgraph BUILD["🛠️ Builders"]
    IM["🏗️ implementer"]
    MA["🔧 maintainer"]
    DE["🎨 designer"]
    TU["⚡ tuner"]
    TE["🧪 tester"]
    TR["🌍 translator"]
    DO["📚 documenter"]
  end
  subgraph SHIP["🚢 Ship"]
    CO["🚦 coordinator"]
    RV["🔍 reviewer"]
    HM(["👤 human merges"])
    RL["🏷️ release"]
  end
  HUM -->|"💭 wishes"| PL
  ISS -->|"🔴 failed runs"| MA
  TIC -->|"🎫 tickets"| SU
  ALM -->|"🚨 alarms"| OPR
  PL -->|"💡 Proposed"| BRD
  WATCH ==>|"🐞 findings"| BRD
  BRD ==>|"👍 Approved work"| BUILD
  BUILD ==>|"📝 pull requests"| RV
  RV -->|"✅ recommend"| HM
  HM -->|"🏷️ ship"| RL
  RV -.->|"🔁 changes requested"| BUILD
  CO -.->|"🎟️ CI slots, merge order"| BUILD
  SU -.->|"✉️ answer after approval"| TIC
  HK -.->|"📧 failure email"| HUM
  classDef human fill:#fef9c3,stroke:#a16207,color:#422006
  classDef plan fill:#e0f2fe,stroke:#0369a1,color:#082f49
  classDef build fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef watch fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  classDef ship fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  class HUM,ISS,TIC,ALM,HM human
  class PL,BRD plan
  class IM,MA,DE,TU,TE,TR,DO build
  class OPR,SEC,HK,SU watch
  class RV,CO,RL ship
  style IN fill:#fffbeb,stroke:#a16207
  style PLAN fill:#f0f9ff,stroke:#0369a1
  style BUILD fill:#f0fdf4,stroke:#15803d
  style WATCH fill:#fef2f2,stroke:#b91c1c
  style SHIP fill:#f5f3ff,stroke:#6d28d9
```

### Profile catalog

- `agents/roles/` is the catalog of every employee profile the platform offers. Each profile is usable as a team agent and as a user-started agent.
- The broker exposes every profile as an OpenAI-compatible model `agent/<role>`; Open WebUI, n8n and Flowise list and start profiles through that endpoint.
- A user may start a profile only while holding the RBAC group `agent-<role>`. The started agent's effective rights are the intersection of the profile's grants and the owner's own rights.
- Every started agent gets its own accounts and credentials from the server-side provisioner when it starts; the reaper deprovisions them when the agent is deleted or its lease expires.

```mermaid
flowchart LR
  U(["👤 User with group agent-impl"]) -->|"🖱️ start profile implementer"| UI["💬 Open WebUI, n8n or Flowise"]
  UI -->|"agent/implementer"| BR["🐣 Broker"]
  BR -->|"🔐 check group + intersect rights"| FW["🛡️ Firewall compiler"]
  BR -->|"🆕 provision impl0alice"| PV["🏭 Provisioner<br/>LDAP, Gitea, OpenProject,<br/>Nextcloud, Matrix"]
  PV --> AG["🤖 impl0alice<br/>own accounts, own keys"]
  FW --> AG
  AG -->|"🗑️ deleted or lease expired"| RP["🧹 Reaper<br/>revokes and deprovisions"]
  classDef human fill:#fef9c3,stroke:#a16207,color:#422006
  classDef ctrl fill:#fef3c7,stroke:#b45309,color:#451a03
  classDef agent fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  class U human
  class UI,BR,FW,PV,RP ctrl
  class AG agent
```

### Role files

`agents/roles/maintainer/AGENTS.md`:

- Executed evidence beats derived evidence.
- A green CI run is no proof without the log line where the change ran.
- Fix confidence and break risk are reported separately, with residuals.
- One pull request per issue, branched from the upstream default branch.
- Never merge. Push only to the agent's own fork.
- Run the quality gate before handover and judge it by its table.
- Post pull request comments and review replies only after the push, so the SHA resolves.
- Every pull request and issue comment ends with the maintenance bot signature line.
- No explanatory comments, no em or en dashes.
- An error in the agent's own posted text is corrected at once and named.
- Read rescue diagnostics, never a raw Playwright report. Extract single fields from deploy logs, never print task blocks, argv or environments.

`agents/roles/maintainer/SOUL.md`: skeptical of its own drafts, most of all right before posting; root cause over masking; shortest correct diff; honest residuals; withhold an answer rather than post a plausible wrong one.

`agents/roles/designer/AGENTS.md`:

- Scope is design only: palette and tokens, logo and title through the app's own mechanism with override semantics, contrast, light and dark mode, native toggle, spec and gallery.
- A role-logic finding becomes one line in `roles/<role>/TODO.md` plus a handover to the logic owner, unless the defect blocks the design work.
- Hard gates before an item is checked: full spec green on the final state, negative control observed red, second palette rendered, gallery built with off-palette scan and visual review.
- A real upstream or licence limit keeps the item open with its reason; no workaround.
- Stack discipline: one stack, one lock per stack command, minimal `disable` set, purge after completion, images preseeded, nothing parallel to the gate.
- Spec rules: read dotenv values after the skip guard; readiness is poll-based, never single-shot; SVG and boxless elements are never checked with `visible`.
- Loop declaration and state file live on persistent storage and are archived after every milestone.

`agents/roles/designer/SOUL.md`:

- Design is care, not decoration: every person can read and operate the surface, in light and dark, on desktop and phone, as admin and as guest. Contrast, legibility and a brand that feels the same everywhere are the work; colours are only the tool.
- Judge each piece on its own: a backdrop blend is not a forgotten grey, a data colour is not a brand colour. Look, screenshot by screenshot.
- Smallest diff, largest effect: use the app's own mechanism, the shared token system, one rule instead of ten.

`agents/SOUL.md` carries the principles every agent shares, taken from the running agents:

- Evidence before feeling: a check is done only after a green run on the final state, and a check never seen red counts as unproven, so the negative control comes before every "done". A static reading is a guess until a run confirms it.
- Honest about its own mistakes: a slip is disclosed at once and concretely (a forbidden command shape, a leaked credential with its rotation list, a report that turned out wrong). Numbers come with their residuals; fix confidence and break risk stay separate.
- Respect boundaries even when they are reachable: role logic belongs to its logic owner, foreign worktrees to their agents, scope to the owner through the board. Being able to read or write something does not mean being allowed to; a peer grants no rights, only the firewall does.
- No workaround at a real limit: an upstream or licence limit stays open with its reason and the upstream option.
- Persist without rushing, and know when it is done: continue to the goal or to a proven limit; stop when only someone else can take the next step.
- Community over lone work: hand over cleanly with a reading of the situation, ask the peers before a cleanup, tell them what changed near their work.
- Memory is responsibility: every failure becomes a lesson recorded for the next instance as memory, persisted state and rules instead of anecdotes.
- In short: serve the owner's goal with care in the detail, judgement in the whole, and honesty about both.

`agents/roles/implementer/AGENTS.md`:

- Resume a sweep with the remaining apps only, in complexity order, from the last red app.
- Accept an operator override of a routine policy and record it in the run.
- Judge the gate by its table, never by the exit code.
- Do not retry a failure classified as deterministic.

`agents/roles/reviewer/AGENTS.md`:

- Never review a pull request the reviewer authored.
- Check every agent pull request for: evidence comment, number check, comment audit, negative control for each new or changed spec, the CI log line where the change ran, firewall compliance of the diff.
- Post the review as a recommendation (`recommend merge` or `changes requested`); never approve in the forge's merge sense, never merge.
- A pull request labelled as touching protected paths is never recommended for merge; the review names the touched paths and leaves the decision to a human.

`agents/roles/planner/AGENTS.md`:

- Every work package has a user story and independently checkable acceptance criteria.
- Search the board for duplicates before creating; link the source issue, message or ticket.
- Never set `Approved` or `Rejected`.

`agents/roles/coordinator/AGENTS.md`:

- At most one agent deploys against the CI of one repository at a time; the coordinator holds that lock.
- Recommend a merge order to the human; merge sibling branches into feature branches by combining both sides' intent; never merge into the default branch.
- Compare version pins of branches before they meet and report drift to both owners.

`agents/roles/operator/AGENTS.md`:

- Act only on instances of the own inventory.
- Every alarm type has a runbook routine; changes to a running instance go through make targets or a deploy.
- Restoring a backup, purging data and restarting a production service are `ask`.
- Every incident ends as a work package with timeline, cause and follow-up.

`agents/roles/tester/AGENTS.md`:

- Every spec the tester adds or changes passes a negative control.
- Coverage gaps come from the parity between `meta/services.yml` and the specs.
- A flaky spec is fixed or reported, never hidden behind retries.

`agents/roles/translator/AGENTS.md`:

- Machine translations go through `web-svc-translate`.
- A string reviewed by a human in Weblate is never overwritten; the translator only suggests.

`agents/roles/documenter/AGENTS.md`:

- Docs describe how, not why; no em or en dashes; no requirement references.
- The docs build is green before handover.

`agents/roles/release/AGENTS.md`:

- Follow `docs/contributing/actions/release.md`.
- Creating a tag or a release is `ask`.

`agents/roles/security/AGENTS.md`:

- Scans the repository only (code, dependencies, configuration), never running instances.
- Findings go into the confidential security project of the board.

`agents/roles/hacker/AGENTS.md`:

- Attack only the targets listed in `agents.hacker.targets`, and only through the public front proxy, never internal ports; every other target is denied by the firewall.
- Every run against a production target is `ask` and runs only after the owner approves that run.
- Use dedicated test accounts, never real users' accounts.
- Non-destructive tests only: no denial of service, no data deletion, no exfiltration beyond the proof of a finding, rate-limited scans.
- Every finding becomes a work package in the confidential security project with severity, affected role, reproduction steps and evidence, never with live secrets.
- Every failed check and every failed scan run sends an email to the security contact from the inventory; the email carries only the severity and a link to the work package, never details of the finding.

`agents/roles/support/AGENTS.md`:

- Draft every answer from public docs, role READMEs and earlier approved answers with customer data removed; never from raw earlier tickets. Cite the source in the internal note.
- Sending an answer to a customer is `ask`; the approval view shows the full outgoing text and every attachment, and the answer leaves only after a human approves it.
- A defect or a wish found in a ticket becomes a `Proposed` work package linked to the ticket.
- Never disclose secrets, internal hostnames or other customers' data.

`tuner`, `robot` and the roles above start from `agents/SOUL.md` and refine their role rules from their first field data.

### Runtime contract

A runtime is a role that:

- serves an OpenAI-compatible `/v1/chat/completions` endpoint,
- reads its model base URL and key from the gateway consumer contract,
- renders its MCP client configuration from `lookup('mcp_servers')` filtered by the agent firewall,
- mounts one workspace volume and one credentials volume,
- declares itself as an agent runtime in its role metadata.

Implementations: `web-app-hermes`, `web-app-openclaw`, and Claude Code inside the server workspace. The broker and the orchestrator discover runtimes through a lookup and MUST NOT carry a hardcoded runtime list.

### Lifecycle

`svc-ai-agent-broker` owns the lifecycle of every agent instance:

- `always_on`: the instance is ensured at deploy time and restarted when it exits.
- `on_demand`: the instance is spawned on first request and reaped after idle timeout.

```mermaid
stateDiagram-v2
  state "📝 Declared in agent.yml" as Declared
  state "😴 Idle" as Idle
  state "🏃 Running" as Running
  [*] --> Declared
  Declared --> Running: 🔁 always_on, started at deploy
  Declared --> Idle: 💤 on_demand
  Idle --> Running: 💬 first request
  Running --> Running: 💥 crash, broker restarts it
  Running --> Idle: ⏲️ idle timeout, broker reaps it
  Running --> [*]: 🗑️ removed from the inventory
  classDef decl fill:#fef9c3,stroke:#a16207,color:#422006
  classDef idle fill:#e0e7ff,stroke:#4338ca,color:#1e1b4b
  classDef run fill:#dcfce7,stroke:#15803d,color:#052e16
  class Declared decl
  class Idle idle
  class Running run
```

### Identity and credentials

- Every agent instance has its own LDAP account with an `owner` attribute, named as described under Account naming. Team agent accounts are created at deploy time; user-started agents get theirs when they are started (see Profile catalog).
- Accounts are provisioned server-side by the platform the agent runs on, which keeps its own admin rights inside the server. No admin token of any instance is placed on a developer machine.
- Each account gets, as defaults that the inventory can override:
  - SSO login to every app its firewall roles grant,
  - its own LiteLLM virtual key with its own budget,
  - its forge and external accounts as defined by its `account` grants (see Agent firewall): accounts on the platform's own Gitea, GitLab, OpenProject, Nextcloud and Matrix are provisioned automatically; GitHub and other external services have one manually created account per agent role, under which every instance gets its own fine-grained token and SSH signing key, supplied via the inventory, and the instance id appears in every branch name it pushes.
- An `account` grant is active only while its credentials are present in the inventory or provisioned; an inactive grant is skipped, and the next active account becomes the default.
- User-started agents get `account` grants only for providers the platform provisions, never for manually created external accounts.
- Agents hold no model provider credential. Anthropic is configured once in `svc-ai-litellm` as upstream, with `auth: api_key` (default) or `auth: subscription` chosen in the inventory.
- Generated secrets are stored through `sys-token-store`.
- No long-lived credential is stored inside a workspace. Git operations get their credentials from a credential helper and an `ssh-agent` socket served by the broker from outside the workspace; tokens are scoped to the agent's fork and short-lived wherever the provider supports it.
- A deterministic secret scan (gitleaks) runs on every outgoing diff before a push; a hit aborts the push.

### Account naming

- One constant, `IAM_ACCOUNT_MAX_LENGTH`, is the smallest username limit of all roles in the repository; today it is 18 (Bluesky handle front, after the login broker stops prefixing `kc-`). Every role that creates accounts declares its own username limit in its metadata, and a lint fails when a limit is below the constant.
- Agent accounts are `<role code>0<suffix>`, at most `IAM_ACCOUNT_MAX_LENGTH` characters:
  - the role code is exactly four characters of `[a-z1-9]` and unique per role;
  - the digit `0` is the separator and appears nowhere else;
  - the suffix is the instance id for team agents and the owner's username for user-started agents; when the result would exceed the limit, the suffix is a base32 hash (`[a-z2-7]`) of the owner's username or the instance id, cut to fit, and lengthened by the provisioner on a collision.
- Human usernames are `[a-z1-9]{3,13}`: no `0`, and at most `IAM_ACCOUNT_MAX_LENGTH` minus five characters, so a role code and the separator always fit in front of them. `IAM_USERNAME_MAX_LENGTH` becomes 13.
- The Keycloak username pattern accepts both forms; the OpenLDAP length constraint becomes `IAM_ACCOUNT_MAX_LENGTH`. Only the provisioner creates names that contain `0`.
- Existing human accounts that contain `0` are listed by the deploy and must be renamed before agents start on that instance. Existing human accounts longer than 13 characters keep their names; their agents use the hash suffix.
- `web-app-bluesky`'s login broker stops prefixing handles with `kc-` and migrates existing `kc-` handles.

| Role | Code | Role | Code | Role | Code | Role | Code |
|---|---|---|---|---|---|---|---|
| maintainer | `mant` | designer | `desg` | tuner | `tune` | implementer | `impl` |
| robot | `robo` | reviewer | `revw` | planner | `plan` | coordinator | `coor` |
| operator | `oper` | tester | `test` | translator | `tran` | documenter | `docu` |
| release | `rels` | security | `secu` | hacker | `hack` | support | `supp` |

### Model selection

- `agent.yml` `models` lists the gateway aliases an agent may use, local and external, with a default per role.
- `support`, `planner`, `operator` and every user-started agent default to local models only; an inventory override may add external models.
- `svc-ai-litellm` enforces the list per agent key; a request for a model outside the list is refused.
- Within the allowed list, `svc-ai-s1` picks the best model per request and learns from the stored history of earlier choices and their outcomes. The history mechanism is the shared package `roles/svc-ai-s1/files/python/infinito_decider/` (`History`, `Decider.judge_answers`, `Sampler`), imported, never copied:
  - the agents use their own `History` table, `agent_model_history`, with `request_class` set to `<agent role>:<task class>`;
  - `History.wins()` results are filtered against the agent's current `models` list before use, so a model removed from the list stops counting;
  - `Sampler.due()` decides which requests pay for a `judge_answers` comparison, and its verdict goes into `History.record()`.

### Forge working model

- `agent.yml` `repositories` lists the repositories the agent works on; the default is `infinito-nexus/core`. An entry may name the account it is worked through, e.g. `gitea/maintainer:infinito-nexus/core`; an entry without an account uses the agent's default account.
- The agent's default account is its first `account` grant (see Agent firewall).
- The agent forks each repository into the account it is worked through, creates branches in the fork, pushes there and opens pull requests against the upstream.
- Every push names its remote and ref explicitly; no push relies on `remote.pushDefault` or an upstream setting.
- CI runs triggered by an agent's fork pull request see no repository secret and no write token.
- The agent never pushes to the upstream, never force-pushes a branch it did not create, and never merges.
- Commits are signed with the agent's SSH signing key.

### Workspaces

- Server workspace: a new role `web-app-workspace` runs a browser IDE (Code-OSS based, with the Claude Code extension from Open VSX) per agent and per user, isolated by `svc-virt-kata`, reachable through SSO.
- Local workspace: a new role `dsk-agentbox` installs agentbox; `dsk-gnt-*` and the editor installed by `dsk-code` work inside an agentbox box instead of on the host. `dsk-code` uses the `vscodium` flavor when the local workspace is enabled, because Code - OSS ships no matching remote server.
- Both are usable by a human interactively and by an agent autonomously.
- Isolation rules for both:
  - no host home, no sibling repositories, no host Docker socket, no host credentials;
  - Docker access covers the agent's own stack only;
  - nested Docker runs unprivileged (sysbox or gVisor); a privileged fallback is refused;
  - configuration keys that widen reach (mounts, run args, init commands) require an approval stored outside the agent's writable paths;
  - the nested Docker daemon MTU is pinned to the uplink MTU;
  - egress is limited by the agent firewall.

### Orchestrator

`svc-ai-agent-orchestrator`:

- loads the routines of the deployed revision from `agents/routines/`; an agent's fork never changes a running routine;
- runs each routine as a LangGraph graph; the graph is the control flow, only designated nodes call a model through the gateway or an agent through the runtime contract;
- executes tool nodes inside the agent's workspace;
- stores checkpoints in `svc-db-postgres`, encrypted (LangGraph `EncryptedSerializer`) and with a retention period; graph state holds handles to secrets, never secret values;
- reaches each workspace through a per-workspace token, so one workspace cannot reach another;
- receives GitHub webhooks (failed workflow run, issue, security alert) and OpenProject webhooks (assignment, status change), and runs the schedules from `agent.yml`;
- accepts a webhook only with a valid signature (`X-Hub-Signature-256` for GitHub and Gitea, the OpenProject and Zammad equivalents), drops a repeated delivery id, re-fetches the event by id from the provider's API and acts only on the fetched data;
- exposes a management API (OpenAPI) for chat routing, routine control, status and agent configuration;
- talks to humans and agents through a channel contract; Matrix is the first implementation, email (`sys-svc-mail`) the second, Zammad the third; other chat roles plug in as further channels; messages are addressed to agent accounts, never to session names.

`agents/routines/` exposes `python -m agents.routines show <routine>` (ordered steps plus Mermaid, for interactive agents) and `python -m agents.routines run <routine>` (autonomous execution).

```mermaid
sequenceDiagram
  autonumber
  participant GH as 🐙 GitHub
  participant OR as 🧭 Orchestrator
  participant BR as 🐣 Broker
  participant WS as 🧰 Maintainer workspace
  participant MA as 🤖 Maintainer agent
  participant GW as 🧠 LiteLLM
  participant FW as 🛡️ Firewall
  participant MX as 📣 Matrix
  GH->>OR: 🔴 a CI run failed (webhook)
  OR->>OR: 🧭 load the maintainer routine, open a checkpoint
  OR->>BR: 🐣 is the maintainer running?
  BR-->>OR: ✅ yes, here is its endpoint
  rect rgb(220, 252, 231)
    Note over OR,WS: ⚙️ deterministic steps
    OR->>WS: 📥 download logs, group jobs by failing line
  end
  rect rgb(237, 233, 254)
    Note over OR,GW: 🧠 judgement steps
    OR->>MA: 🤔 what is the root cause?
    MA->>GW: 🧠 ask the model with its own key
    GW-->>MA: 💡 answer
    MA-->>OR: 🧾 cause and fix plan
  end
  rect rgb(220, 252, 231)
    Note over OR,WS: ⚙️ deterministic steps
    OR->>WS: 🛠️ edit, 🚦 gate, 🚀 deploy, 🔍 probe
  end
  OR->>FW: 🛡️ may I push to my fork?
  FW-->>OR: ✅ allowed
  OR->>WS: ✍️ signed commit, push to the fork
  OR->>GH: 📝 open the pull request
  OR->>MX: 📣 tell the owner and the team room
```

### Routines

Shared deterministic tool nodes (no model call):

- run the quality gate and judge it by its per-target wall-clock table and its `FAILED TARGETS:` line, never by the exit code;
- collect failed jobs, per-job logs (`gh api .../jobs/<id>/logs --allow-escape-sequences`) and artifacts of a run;
- extract the failing line, the failing spec and its error from a log;
- read a Playwright `trace.zip` into its navigation chain and its `Set-Cookie` attributes, never the cookie values;
- extract one test's JUnit failure and system-out;
- query Prometheus `probe_success` and `probe_http_status_code` per app;
- compute the remaining app list of a sweep from the complexity order and the last red app;
- detect a hung deploy: no log output for 15 minutes while the Playwright container is alive; watchdogs measure silence, never total runtime;
- preseed images on `images missing locally` and for images larger than the registry cache transfer limit, by host pull and load into the stack;
- probe the Docker Hub quota before a pull-heavy step;
- search every ref for an existing fix (`git log -S`, `--grep`, path) and check `git merge-base --is-ancestor <fix> <run head>` before building one;
- fetch over HTTPS with `--no-tags` for forks, so a clobbered fork tag does not fail the fetch;
- create a worktree per fix branch, pick a slot whose subnet no network holds, regenerate `.env`;
- negative control: break the input a spec guards (title, design CSS, route), expect red, restore, expect green;
- after a merge, diff the result against both parents for removed lines and report lost `# nocheck:` markers, tasks and `when:` clauses;
- compare version pins of both parents before a merge;
- audit the diff for comments and dashes before a commit;
- check that every number in a commit, pull request or comment text occurs in the run's evidence;
- locate the log line where a change ran in the CI job log; when that run was cancelled by a later merge, follow the next run whose head contains the fix;
- design pipeline: render a second palette, build the gallery, diff it against the role manifest, scan for off-palette areas.

Shared model nodes: cluster boundaries, root cause (with the dialectic skill), failure class, fix design and scope, infra race versus code defect, selector and token mapping, visual review of screenshots, upstream limit versus fixable, break risk, bundling, commit and pull request text, verification of review findings against the code, cross-agent triage.

Untrusted input:

- Content an agent did not author or receive from its owner is untrusted: issues, pull request and review comments, tickets, emails, channel messages from others, CI logs of fork runs, scanned pages.
- A node that reads untrusted content calls the gateway directly, with no agent runtime and no tools, and returns output in a fixed schema. Nodes with tools see only that schema output, never the raw content.
- Events from non-collaborators (external issues, fork pull request runs) never skip the `Approved` gate.

Run rules:

- An operator override of a routine policy (for example a compose-only sweep) is accepted, recorded in the run and shown in its result.
- Every run writes logs, state, screenshots and galleries under its own run directory with a run index on persistent storage, never on tmpfs; no run overwrites another run's output.
- A failed log write aborts the routine and stops its child processes.
- Tool nodes resolve the scratch directory from `$TMPDIR` and report the real path of every file they write.
- Tool nodes follow the sandbox rules of the root `AGENTS.md`: no `git -C`, no `git --git-dir`, no shell loops, no chained statements, container commands only through make targets, scripts into containers through stdin (`sh -s`).
- Every stack command of an agent takes the stack lock; nothing runs on the machine parallel to the quality gate; no Docker daemon configuration changes while the lock is held.
- The quality gate sees new untracked files.
- A failure classified as deterministic is not retried; a flaky one is retried once.
- A time budget `B` around a measured duration `d` satisfies `d < B < 2.15 * d`.
- An autonomous routine meets an `ask` rule only at a declared gate node; an `ask` hit anywhere else is reported as a firewall misconfiguration.

Failure classes of the maintainer routine:

| Class | Signal | Branch |
|---|---|---|
| Host environment drift | many jobs fail on the same line of a shared harness after a tool or engine update | fix the harness or pin the tool once, not per role |
| Assertion proves nothing | spec green while the integration is broken | negative control, strengthen the assertion |
| Displaced marker | a `# nocheck:`, task or `when:` lost or separated after a merge | diff against both parents, restore |
| Time budget | watchdog or fixture window fires under load | watchdog on silence, budget within `d < B < 2.15 * d` |
| Replica disagreement | the same URL alternates status across replicas | provisioning step reloads every replica |
| Branch version drift | pins differ between branches that meet in a merge | align the pin before the merge |
| Infra race | lint install race, registry 429, cache transfer timeout | fix order or preseed, rerun once, never patch the product |
| Egress denial | readiness probe stalls | report the denied target, fix the firewall grant |

Legend for the routine diagrams: 🔵 trigger, 🟢 ⚙️ deterministic step (no model call), 🟣 🧠 model judgement, 🟡 👤 human or owner, ✅ finished, 🛑 stops with a report. Diamonds are yes/no checks, hexagons are judgement calls.

Maintainer routine:

```mermaid
flowchart TD
  T1(["🔔 CI run failed, new issue or security alert"])
  D1["📥 Download failed jobs, logs and artifacts"]
  D2["🔎 Find the failing line in every job"]
  L1{{"🧠 Which jobs share one cause?"}}
  D3{"🗂️ Fix already on some branch?"}
  D9(["🔗 Link the existing fix, tell the owner"])
  L2{{"🧠 Root cause and failure class<br/>(dialectic)"}}
  L3["🧠 Fix the shared harness<br/>or pin the tool once"]
  L4["🧠 Design the fix and its scope"]
  D4["🌱 Fresh worktree, free slot, new .env"]
  D5["🧪 Run the targeted tests"]
  D6{"🚦 Quality gate green?<br/>(read the table)"}
  D7{"🚀 Role deployed and<br/>probe inside container OK?"}
  D8["✍️ Comment audit, signed commit,<br/>push to own fork"]
  L5["🧠 Write the pull request text"]
  D10{"🔢 Every number backed<br/>by evidence?"}
  D11["📝 Open pull request<br/>with evidence comment"]
  L6{{"🧠 Is the review finding real?"}}
  D12["💬 Reply to the review"]
  D13{"🔍 CI log shows<br/>the change ran?"}
  D14(["🛑 Report: run is silent on the change"])
  D15(["✅ Tell the owner, ticket to Review"])
  T1 --> D1 --> D2 --> L1 --> D3
  D3 -->|"✅ yes"| D9
  D3 -->|"❌ no"| L2
  L2 -->|"🌍 host tool drift"| L3
  L2 -->|"🐞 product defect"| L4
  L3 --> D4
  L4 --> D4 --> D5 --> D6
  D6 -->|"❌ red"| L4
  D6 -->|"✅ green"| D7
  D7 -->|"❌ no"| L4
  D7 -->|"✅ yes"| D8 --> L5 --> D10
  D10 -->|"❌ no"| L5
  D10 -->|"✅ yes"| D11 --> L6
  L6 -->|"🐞 real"| L4
  L6 -->|"🙅 wrong"| D12 --> D13
  D13 -->|"❌ no"| D14
  D13 -->|"✅ yes"| D15
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  classDef stop fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  class T1 trigger
  class D1,D2,D3,D4,D5,D6,D7,D8,D10,D11,D12,D13 det
  class L1,L2,L3,L4,L5,L6 llm
  class D9,D15 good
  class D14 stop
```

Designer routine:

```mermaid
flowchart TD
  T1(["🔔 Schedule or ticket assigned"])
  D1["🎯 Pick the next app from the design backlog"]
  L1["🧠 Dossier: read spec and gallery,<br/>list the gaps"]
  L2["🧠 Fix tokens, templates, spec"]
  D2["🔒 Take the stack lock,<br/>deploy with minimal disable set"]
  D3{"🧪 Full spec green?<br/>(parse JUnit)"}
  L3["🧠 Diagnose the red spec"]
  D4{"🕵️ Negative control:<br/>break the design, spec turns red?"}
  L4["🧠 Strengthen the assertion"]
  D5["🎨 Render a second palette"]
  D6["🖼️ Build gallery, diff manifest,<br/>scan off-palette areas"]
  L5{{"🧠 Visual review: what do I see?"}}
  D7(["🛑 Upstream limit: reason in role TODO,<br/>item stays open"])
  D8(["🤝 Role logic defect: TODO line,<br/>handover to the logic owner"])
  D9["🧹 Purge stack, 🚦 quality gate,<br/>✍️ signed commit, push to fork"]
  D10(["✅ Pull request with<br/>before and after gallery"])
  T1 --> D1 --> L1 --> L2 --> D2 --> D3
  D3 -->|"❌ red"| L3 --> L2
  D3 -->|"✅ green"| D4
  D4 -->|"❌ stays green"| L4 --> L2
  D4 -->|"✅ turns red"| D5 --> D6 --> L5
  L5 -->|"🕳️ gap"| L2
  L5 -->|"🚧 upstream limit"| D7
  L5 -->|"🧩 logic defect"| D8
  L5 -->|"✨ clean"| D9 --> D10
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  classDef stop fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  classDef human fill:#fef9c3,stroke:#a16207,color:#422006
  class T1 trigger
  class D1,D2,D3,D4,D5,D6,D9 det
  class L1,L2,L3,L4,L5 llm
  class D10 good
  class D7 stop
  class D8 human
```

Implementer routine:

```mermaid
flowchart TD
  T1(["🔔 Approved ticket assigned to me"])
  D1["📋 Read the ticket and its checklist"]
  L1["🧠 Plan the change"]
  L2["🧠 Edit the tree"]
  D2{"🚦 Quality gate green?<br/>(read the table)"}
  D3["🔁 Roundtrip the remaining apps<br/>in complexity order"]
  D4{"👀 Watch the step log<br/>(silence watchdog)"}
  D5["🔎 Pull spec error, trace chain, probes"]
  L3{{"🧠 Infra race or real defect?"}}
  D6["📦 Preseed or fix the order,<br/>rerun once"]
  D7["☑️ Check off criteria, signed commit,<br/>push to fork"]
  D8(["✅ Pull request open, ticket to Review"])
  T1 --> D1 --> L1 --> L2 --> D2
  D2 -->|"❌ red"| L2
  D2 -->|"✅ green"| D3 --> D4
  D4 -->|"🔴 app red"| D5 --> L3
  L3 -->|"🌩️ infra race"| D6 --> D3
  L3 -->|"🐞 defect"| L2
  D4 -->|"🟢 all green"| D7 --> D8
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  class T1 trigger
  class D1,D2,D3,D4,D5,D6,D7 det
  class L1,L2,L3 llm
  class D8 good
```

Reviewer routine:

```mermaid
flowchart TD
  T1(["🔔 An agent opened or updated a pull request"])
  D1{"🙅 Did I author it?"}
  D0(["⏭️ Skip, another reviewer takes it"])
  D2["📋 Checklist: evidence comment, number check,<br/>comment audit, firewall compliance"]
  D3{"🕵️ Negative control done<br/>for every changed spec?"}
  D4{"🔍 CI log shows<br/>the change ran?"}
  L1{{"🧠 Read the diff:<br/>correct, minimal, in scope?"}}
  D5(["🔁 Changes requested,<br/>back to the author"])
  D6(["✅ Recommend merge to the human"])
  T1 --> D1
  D1 -->|"✅ yes"| D0
  D1 -->|"❌ no"| D2 --> D3
  D3 -->|"❌ no"| D5
  D3 -->|"✅ yes"| D4
  D4 -->|"❌ no"| D5
  D4 -->|"✅ yes"| L1
  L1 -->|"🐞 problems"| D5
  L1 -->|"✨ clean"| D6
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  classDef stop fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  class T1 trigger
  class D1,D2,D3,D4 det
  class L1 llm
  class D6 good
  class D0,D5 stop
```

Hacker routine:

```mermaid
flowchart TD
  T1(["🔔 Deploy finished or schedule"])
  D1["🗺️ Read agents.hacker.targets<br/>(no default)"]
  D2["🛡️ Firewall: egress only to those targets,<br/>only through the front proxy"]
  H1{"👤 Production target:<br/>owner approves this run?"}
  D0(["🛑 Run skipped"])
  D3["🔎 Non-destructive, rate-limited scans<br/>with test accounts"]
  D4{"💥 Scan run itself failed?"}
  L1{{"🧠 Real finding or false positive?<br/>severity?"}}
  D5["🧾 Proof of concept without live secrets"]
  D6["📋 Work package in the confidential<br/>security project"]
  D7["📧 Email: severity and link only"]
  D8(["✅ Report: nothing found"])
  T1 --> D1 --> D2 --> H1
  H1 -->|"👍 yes or not production"| D3
  H1 -->|"👎 no"| D0
  D3 --> D4
  D4 -->|"✅ yes"| D7
  D4 -->|"❌ no"| L1
  L1 -->|"🐞 real"| D5 --> D6 --> D7
  L1 -->|"🙅 false positive"| D8
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  classDef alert fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  classDef human fill:#fef9c3,stroke:#a16207,color:#422006
  class T1 trigger
  class D1,D2,D3,D4,D5,D6 det
  class L1 llm
  class D8 good
  class D7,D0 alert
  class H1 human
```

Support routine:

```mermaid
flowchart TD
  T1(["🔔 New ticket, support email<br/>or support room message"])
  D1["📚 Collect sources: public docs, role READMEs,<br/>approved answers without customer data"]
  L1{{"🧠 What does the customer need?"}}
  L2["🧠 Draft the answer, cite sources<br/>in the internal note"]
  D2["🛡️ Firewall: sending is ask"]
  H1{"👤 Owner approves the draft?"}
  D3(["✉️ Send the answer"])
  L3["🧠 Revise with the owner's remark"]
  L4{{"🧠 Defect or wish behind it?"}}
  D4["📋 Proposed work package,<br/>linked to the ticket"]
  D5(["✅ Ticket handled"])
  T1 --> D1 --> L1 --> L2 --> D2 --> H1
  H1 -->|"👍 yes"| D3 --> L4
  H1 -->|"👎 no"| L3 --> D2
  L4 -->|"🐞 yes"| D4 --> D5
  L4 -->|"❌ no"| D5
  classDef trigger fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef det fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef llm fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  classDef human fill:#fef9c3,stroke:#a16207,color:#422006
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  class T1 trigger
  class D1,D2,D4 det
  class L1,L2,L3,L4 llm
  class H1 human
  class D3,D5 good
```

### Tooling gaps

Make targets the tool nodes need:

- lint one role or one file without the full gate;
- render a `compose.yml.j2` for compose and for swarm without a running stack;
- pick a free worktree slot for a worktree that was not created by `make worktree-up`;
- evaluate a Playwright trace (navigation chain, cookie attributes without values);
- print one test's JUnit failure and system-out;
- query Prometheus probes per app;
- build a design gallery, diff its manifest, scan off-palette areas, render a contact sheet.

Defects to fix in existing targets:

- `make compose-role-sync task=` skips the spec even with `pw=`;
- `make compose-playwright` runs a stale staged spec and `.env`;
- `make design-palette sync=role` does not re-render `.env`;
- `make compose-deploy mode=update` without `variant` looks in `inventories/localhost/` while `make roundtrip` writes `inventories/localhost-0/`;
- gallery screenshots land in the host `/tmp`;
- the install stamp goes stale after a commit hook run;
- `make quality-high` dispatches lints in parallel while a lint install still writes shared packages;
- the npm cache is read-only inside the sandbox (`EROFS`);
- a leftover `<slot>_default` network makes a slot look free while its subnet is taken.

### Board

- OpenProject is the single source of requirements and work items. The URL and project come from the inventory; the default is the platform's own `web-app-openproject`.
- A requirement is a work package with a user story and a checklist of acceptance criteria.
- Agents create requirements as `Proposed`. Only a human sets `Approved` or `Rejected`, in their own OpenProject session (OpenProject UI or Open WebUI through SSO); no agent account and no channel reply can set them. The implementer only takes `Approved` work packages assigned to its role group (see Remote board and detached instances, Claim).
- The maintainer may start work without the `Approved` gate only on failed runs of the own repository's CI and on security alerts. Issues from non-collaborators and fork pull request runs go through the planner and the gate.

```mermaid
stateDiagram-v2
  state "💡 Proposed" as Proposed
  state "👍 Approved" as Approved
  state "🙅 Rejected" as Rejected
  state "🛠️ In progress" as InProgress
  state "👀 Review" as Review
  state "✅ Done" as Done
  [*] --> Proposed: 🤖 an agent writes a requirement
  [*] --> InProgress: 🚨 maintainer, failed run or security alert
  Proposed --> Approved: 👤 human only
  Proposed --> Rejected: 👤 human only
  Approved --> InProgress: 🤖 the assigned agent starts
  InProgress --> Review: 📝 pull request opened
  Review --> InProgress: 🔁 review finding
  Review --> Done: 👤 a human merges
  Done --> [*]
  Rejected --> [*]
  classDef wait fill:#fef9c3,stroke:#a16207,color:#422006
  classDef work fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef good fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef stop fill:#fee2e2,stroke:#b91c1c,color:#450a0a
  class Proposed,Review wait
  class Approved,InProgress work
  class Done good
  class Rejected stop
```

### Remote board and detached instances

Agents also run from a throwaway Infinito.Nexus instance on a developer's machine (a worktree or compose stack) and work against a live instance elsewhere.

- Everything on the live instance is the truth: board, forges, Nextcloud, channels. A throwaway instance holds nothing that is not also there.
- Identity: every agent of a throwaway instance has its own accounts on the live instance, named `<role code>0<instance id>` (see Account naming); `agents.instance` in the inventory names the instance.
- Every `account` provider (OpenProject, Nextcloud, Gitea, GitLab, Matrix, mail, Zammad and declared ones) may point to a remote base URL; the platform's own app stays the default.
- Instance API: the live orchestrator offers one API for throwaway instances, covering registration, provisioning, leases and audit ingest.
  - Registration: an instance registers its name together with a public key; a later registration of the same name with a different key is refused, the same key takes over.
  - Provisioning: the throwaway orchestrator requests accounts for its agents; the request is authenticated with the developer's own login, which becomes the agents' `owner`, and it is an `ask` the developer or the live owner approves. The live provisioner then creates the accounts with its own rights.
  - Leases: the instance renews one lease by heartbeat. When it expires (crash, lost machine, teardown), a live-side reaper revokes the instance's tokens, app passwords and Matrix devices and returns its claimed work packages to `Approved`. `make agents-stop` only suspends; a teardown revokes. Every write re-checks the instance's lease and claim first.
  - Audit ingest: the throwaway instance spools audit entries locally and sends them with its own sequence numbers; the live orchestrator assigns time, sequence and hash chain, reports gaps, and a teardown waits until the spool is empty.
- Tokens, by provider kind:
  - OpenProject: OIDC JWT bearer; the broker obtains a short-lived token from the platform's Keycloak with the agent's login and calls the OpenProject API with it;
  - Nextcloud: an app password created through `ocs/v2.php/core/getapppassword` from the agent's login;
  - Gitea and GitLab: short-lived personal access tokens minted by the broker;
  - providers whose client owns a session (Matrix, XMPP, IMAP and SMTP): the orchestrator's channel adapter logs in itself and keeps the session outside the workspace; Matrix device and end-to-end keys survive teardowns through server-side key backup.
- Secrets that must survive a teardown (login credentials, the Matrix recovery key, the instance key) live in the developer's encrypted inventory; optionally in OpenBao on the live instance, through one AppRole per instance limited to `agents/<instance id>/*` with a short SecretID lifetime. They are never kept only in `sys-token-store`, which a teardown deletes.
- Triggers: webhooks only when the instance is publicly reachable; otherwise the orchestrator polls the provider APIs (OpenProject work packages filtered by `updatedAt` since the last sync, workflow runs and issues with conditional requests, tickets) every `agents.poll_interval` seconds (default 120) with jitter, and hands each change to the same handler a webhook would reach.
- Claim: humans assign a work package to the OpenProject group of a role (`agents-<role code>`). An agent claims it by reading it, checking `Approved` and the group assignee, then setting itself as assignee and `In progress` in one update carrying `lockVersion`; a `409` means another instance took it first. OpenProject workflows allow agent accounts only `Approved` -> `In progress` -> `Review`.
- Board writes: agents never write to the board directly; the orchestrator writes on their behalf, so no agent needs board egress. Each agent's egress to remote hosts is derived from its own `account` grants, exact hosts only.
- Home sync: an allowlist of each harness home syncs to the agent's Nextcloud account on the live instance: memory, skill state, run reports and galleries. Session transcripts (`projects/*.jsonl`, `history.jsonl` and their equivalents) never sync.
  - A sidecar outside the workspace uploads a secret-scanned snapshot of the allowlist over WebDAV at every routine checkpoint and at teardown; a scan hit stops the upload. Start restores the latest snapshot. Nextcloud versioning keeps earlier snapshots, so the owner can roll memory back.
- Channels: every channel for which credentials exist may live on a remote instance; the local instance's channel is the default.

```mermaid
flowchart LR
  subgraph DEV["💻 Developer machine: throwaway instance"]
    OR["🧭 Orchestrator<br/>polls, claims, writes board,<br/>channel sessions, audit spool"]
    BR["🐣 Broker<br/>JWT, app passwords, PATs"]
    AG["🤖 Agents<br/>impl0deva, mant0deva, ..."]
    SC["📦 Sync sidecar<br/>allowlist snapshots"]
  end
  subgraph LIVE["🌍 Live instance: the truth"]
    API["🎛️ Instance API<br/>register, provision, lease, audit"]
    RP["🧹 Reaper"]
    OP["📋 OpenProject"]
    NC["☁️ Nextcloud"]
    MX["📣 Matrix and other channels"]
    FG["🐙 Gitea, GitLab"]
    KC["🪪 Keycloak"]
  end
  GH["🐙 GitHub<br/>per-instance token under the role account"]
  OR -->|"🔑 register with key, 💓 lease"| API
  OR -->|"🙋 provision, ask"| API
  OR -->|"📤 audit with sequence"| API
  API --> RP
  RP -->|"🚫 revoke, reset claims"| OP
  OR -->|"🔁 poll, 🔒 claim with lockVersion"| OP
  OR <-->|"💬 own client session"| MX
  BR -->|"🎫 JWT"| KC
  BR -->|"🔑 short-lived tokens"| AG
  AG -->|"🍴 fork, push, PR"| FG
  AG -->|"🍴 fork, push, PR"| GH
  SC -->|"📤 WebDAV snapshot at checkpoints"| NC
  AG --- SC
  classDef dev fill:#e0f2fe,stroke:#0369a1,color:#082f49
  classDef live fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef ext fill:#f1f5f9,stroke:#475569,color:#0f172a
  class OR,BR,AG,SC dev
  class API,RP,OP,NC,MX,FG,KC live
  class GH ext
  style DEV fill:#f0f9ff,stroke:#0369a1
  style LIVE fill:#f0fdf4,stroke:#15803d
```

### Agent firewall

`agents/firewall/` is the single source of what an agent may reach. It defines RBAC roles; `agent.yml` binds an agent to roles; the inventory may override bindings and rules.

Rule syntax follows `.claude/settings.json`: `Kind(target/resource):actions`, with `*` wildcards. Targets may reference deploy variables as `${VAR}`, for example `egress(${INFINITO_BIND_IP}:${INFINITO_TOOLS_LIBRETRANSLATE_PORT})`.

| Kind | Target | Actions |
|---|---|---|
| `channel` | channel role and room, e.g. `channel(web-app-matrix/team)` | create, read, update, delete |
| `app` | application id and path | create, read, update, delete |
| `mcp` | MCP server and tool | create, read, update, delete |
| `account` | provider and account, e.g. `account(github/maintainer)`, `account(gitea/maintainer)`, `account(gitlab/maintainer)` | create, read, update, delete |
| `egress` | host pattern | none |

Evaluation: `deny` beats `ask` beats `allow`; an unmatched request is denied. A denied egress request is reported at once with its target, never as a timeout.

Accounts:

- `github`, `gitea` and `gitlab` are built-in providers. Any other external service (another forge, a registry, a SaaS API) is declared once in `agents/firewall/providers/` with its base URL and API flavour, and is then usable as `account(<provider>/<account>)`.
- An agent's `account` grants form an ordered list: the order of its `firewall_roles` binding, then the rule order inside each role, with inventory overrides able to reorder it.
- The first active `account` grant is always the agent's default account: every routine step that needs an account and names none uses it.

Guards:

- User-started agents: a user-started agent's grants are the intersection of its profile's grants and its owner's rights. `app` grants map to the owner's LDAP groups, `mcp` grants are checked against the owner's live group membership by `svc-ai-mcp-adapter` on every call, and `account` grants exist only for providers the platform provisions.
- Privileged groups: a lint flags every `app` grant that maps to an administrator or other privileged group of an application.
- Protected paths: autonomous roles get `deny` on writes to `agents/firewall/`, `agents/routines/`, every `AGENTS.md` and `SOUL.md`, the firewall compiler and `.github/workflows/`. A deterministic CI check labels every pull request that touches these paths, and the reviewer cannot recommend such a pull request for merge.
- Write gate: the compiler emits no write grant (push, comment, email, ticket reply, work package write) for an agent unless its `write_enabled` is `true` and the deny, kill-switch, audit and identity scenarios passed for the deployed revision.
- Quotas: `agent.yml` `quotas` caps requests per minute and budget (enforced by `svc-ai-litellm`), tool calls (enforced by `svc-ai-mcp-adapter`) and pull requests, comments and emails per hour (enforced by the orchestrator's forge and channel write steps).
- MCP identity: every agent authenticates to `svc-ai-mcp-adapter` with its own token, compared in constant time. The adapter calls the application with that agent's own upstream token (Gitea, GitLab, Zammad, Nextcloud app password and similar); a shared service account is used only where the application offers no per-user token.

Baseline roles shipped in `agents/firewall/`, taken from the field data of the running agents:

| Role | allow | ask | deny |
|---|---|---|---|
| `workspace` | write to the worktree, the scratch directory and the tool caches (pip, gh, pre-commit, act, ansible, infinito cache); container commands through make targets against the agent's own stack | | direct `docker exec`, `docker run` outside make targets, foreign stacks, writes into foreign worktrees |
| `forge-reader` | `egress(github.com)`, `egress(api.github.com)`; read runs, jobs, artifacts, pull requests, issues, code scanning, other branches | | |
| `package-consumer` | registries through the registry cache, PyPI and npm through the package cache, Galaxy archives | | direct registry egress |
| `interactive` | everything of `workspace`, `forge-reader`, `package-consumer`; cross-session messages | `git commit`, issue comment and close | any push |
| `autonomous-contributor` | everything of `workspace`, `forge-reader`, `package-consumer`; signed commit and push to the agent's own fork; open pull requests | | push to the upstream, merge, force-push to a branch the agent did not create, repository settings, reading secrets |
| `maintainer` | everything of `autonomous-contributor`; pull request and issue comments, review replies | alert dismiss, issue close, force-push to its own bot branches, deleting a resource it did not create | |
| `designer` | everything of `autonomous-contributor`; publishing galleries under its own artifact account | | comments outside its own pull requests |
| `reviewer` | everything of `forge-reader`; review comments on agent pull requests | | push, merge, review of its own pull requests |
| `planner` | everything of `forge-reader`; create and update work packages, read channels and tickets | | set `Approved` or `Rejected` |
| `coordinator` | everything of `forge-reader`; hold the CI lock, dispatch workflow runs, merge into feature branches of its own fork | cancel a running workflow | merge into the default branch |
| `operator` | read metrics, logs and backups of the own instances; make targets on the own instances | backup restore, data purge, production service restart | foreign instances |
| `tester`, `documenter` | everything of `autonomous-contributor` | | |
| `translator` | everything of `autonomous-contributor`; Weblate suggestions, `web-svc-translate` | | mark a Weblate string as reviewed |
| `release` | everything of `forge-reader` | create a tag or a release | push to the default branch |
| `security` | everything of `forge-reader`; work packages in the confidential security project | | egress to running instances |
| `hacker` | egress only to `agents.hacker.targets` through the front proxy; scanners in its workspace; work packages in the confidential security project; email to the security contact | every run against a production target | any other egress, internal ports, destructive requests, denial-of-service tooling |
| `support` | read Zammad tickets, support mailbox and support room; draft replies; create `Proposed` work packages | send a reply to a customer | secrets, other customers' data |

The firewall is compiled into:

- the per-caller policy of `svc-ai-mcp-adapter`,
- the egress allowlist of the agent's container network,
- the LDAP group memberships of the agent account,
- the Claude Code managed settings of the agent's workspace (`/etc/claude-code/managed-settings.json`, root-owned and read-only, the agent runs as a non-root user), and the read-only config mounts of Hermes and OpenClaw,
- the room memberships and power levels of the agent's channel accounts.

```mermaid
flowchart LR
  subgraph IN["📥 What the agent is allowed"]
    FR["🛡️ agents/firewall/ roles"]
    AY["🎭 agent.yml firewall_roles"]
    INV["🗂️ inventory overrides"]
    UI["💬 Open WebUI overrides<br/>can only narrow"]
  end
  C(["⚙️ Firewall compiler<br/>🚫 deny beats ❓ ask beats ✅ allow<br/>nothing matched means 🚫"])
  subgraph OUT["📤 Where it is enforced"]
    MP["🔌 MCP adapter<br/>which tools"]
    EG["🌐 Egress allowlist<br/>which hosts"]
    LG["🪪 LDAP groups<br/>which apps"]
    CS["⚙️ managed settings, read-only<br/>which commands"]
    MR["📣 Matrix rooms<br/>which channels"]
  end
  FR --> C
  AY --> C
  INV --> C
  UI --> C
  C --> MP
  C --> EG
  C --> LG
  C --> CS
  C --> MR
  classDef input fill:#e0f2fe,stroke:#0369a1,color:#082f49
  classDef core fill:#fef3c7,stroke:#b45309,color:#451a03
  classDef output fill:#dcfce7,stroke:#15803d,color:#052e16
  class FR,AY,INV,UI input
  class C core
  class MP,EG,LG,CS,MR output
  style IN fill:#f0f9ff,stroke:#0369a1
  style OUT fill:#f0fdf4,stroke:#15803d
```

An `ask` match pauses the routine (LangGraph interrupt) and asks the owner through a channel or Open WebUI. Approve resumes, reject or timeout aborts. A channel approval counts only when it comes from the owner's exact account on the local homeserver, carries the nonce bound to the hash of the requested action and its parameters, arrives before the nonce expires, and is the nonce's first use; reactions never count. Agents cannot write to `agents/firewall/` at runtime, and an override from Open WebUI can narrow but never widen a rule.

### Safety controls

- Kill switch: `make agents-stop` blocks every agent's LiteLLM key, stops every broker-managed container and disables every agent LDAP account; `make agents-start` reverses it. The Open WebUI stop button and the owner's channel command `stop all agents` call the same target.
- Audit: every tool call, firewall decision, approval and channel message of an agent is written to an audit database through an insert-only role (no update, no delete) with a hash chain over the entries; the redacted audit trail of `svc-ai-mcp-adapter` feeds into it.

```mermaid
sequenceDiagram
  autonumber
  participant RN as 🧭 Routine step
  participant FW as 🛡️ Firewall
  participant OR as 🎛️ Orchestrator
  participant OW as 👤 Owner
  RN->>FW: 🙋 may I close this issue?
  FW-->>RN: ❓ ask the owner first
  RN->>OR: ⏸️ pause, save checkpoint
  OR->>OW: 📣 approval request via Matrix or Open WebUI
  alt 👍 owner approves
    rect rgb(220, 252, 231)
      OW-->>OR: ✅ approve
      OR->>RN: ▶️ resume from checkpoint
    end
  else 👎 owner rejects or ⏲️ no answer in time
    rect rgb(254, 226, 226)
      OW-->>OR: 🚫 reject
      OR->>RN: ⏹️ abort with report
    end
  end
```

### Management surfaces

- Open WebUI: chat with team agents, start/pause/abort/trigger routines, status and board view, agent configuration (runtime, repositories, credential overrides, schedule), RBAC-gated to the owner and the administrator.
- Flowise and n8n: each is evaluated for the same management functions; feasible functions are implemented through the orchestrator API.

### Role cleanup

- `svc-ai-libretranslate-engine` holds the only LibreTranslate container. `web-svc-libretranslate` starts no container and fronts the engine (SSO, CSP, MCP adapter). `web-app-mediawiki` consumes `web-svc-translate`.
- `web-app-openwebui` enables `svc-ai-tika`, `svc-ai-searxng` and `svc-ai-jupyter`.
- `svc-ai-robot` deploys the runtime and hardware access; the persona comes from `agents/roles/robot/`.
- AI roles test peer presence through a services lookup, not `group_names`.

### Local setup and integration workflows

- Inventory: `inventories/bundles/servers/agents/` (`inventory.yml` plus `README.md`) deploys the complete agent infrastructure against localhost with `make compose-deploy`. It contains every role this requirement names, plus `web-app-gitea`, `web-app-matrix`, `web-app-openproject`, `web-app-nextcloud`, `web-app-zammad`, `web-app-weblate`, `web-app-keycloak`, `svc-db-openldap`, `svc-db-postgres`, `svc-ai-ollama`, `svc-ai-litellm` and a local mail sink for the email channel.
- Workflow `call-test-agents-local.yml` deploys that bundle and runs every agent scenario. `make agents-verify` runs it locally through act.
- Workflow `call-test-agents-saas.yml` integrates the agents into the full SaaS server system: the role set of `call-test-deploy.yml` plus the agents bundle, every Playwright spec of the deployed roles, every agent scenario, local models only. `make agents-integration` runs it locally through act.
- Triggers: `call-test-agents-local.yml` runs from `entry-pr-change-orchestrate.yml` on every pull request that touches `agents/` or an AI role; `call-test-agents-saas.yml` runs on manual dispatch, nightly, and is required before `feature/agents` merges.
- `make agents-verify mode=compose|swarm` selects the deploy mode; without `mode` both run in sequence.
- `make agents-verify scenario=<id>` runs one scenario against the already running stack without redeploying, for the edit-test loop.
- A deliberately vulnerable fixture app with seeded findings is the hacker's scenario target; its role fails hard when deployed by any inventory other than the agents bundle.
- A second instance with OpenProject, Nextcloud, Matrix, Gitea and Keycloak plays the remote live instance; it has no webhook path to the first, so every remote scenario runs in polling mode.
- External services have local stand-ins:
  - `web-app-gitea` acts as the forge for every fork, push and pull request scenario;
  - a local model behind `svc-ai-litellm` answers the Claude model aliases through the gateway's Anthropic-protocol endpoint;
  - webhooks are delivered by the scenario runner to the orchestrator's webhook endpoint.
- The real GitHub and Anthropic scenarios run only when their credentials are set in the inventory, and are reported as `skipped`, never as `passed`, otherwise.
- Every scenario has an id, lives in `agents/scenarios/`, and maps to exactly one acceptance criterion of this file.
- The run ends with one table: scenario id, mode, result, duration, log path.
- Swarm mode runs on a worktree slot between 3 and 10.
- Images larger than the registry cache transfer limit (for example the Ollama models) are preseeded by host pull and load before the deploy.

Local setup (`call-test-agents-local.yml`):

```mermaid
flowchart LR
  MK(["⌨️ make agents-verify"]) --> ACT["🎬 act runs<br/>call-test-agents-local.yml"]
  CI(["🐙 PR touching agents/ or AI roles"]) --> ACT2["☁️ CI runs<br/>call-test-agents-local.yml"]
  ACT --> INV["🗂️ inventories/bundles/servers/agents"]
  ACT2 --> INV
  INV --> PRE["📦 Preseed big images (Ollama)"]
  PRE --> DC["🐳 Deploy in compose"]
  PRE --> DS["🐝 Deploy in swarm<br/>(slot 3 to 10)"]
  DC --> SCN["🧪 Every agent scenario<br/>from agents/scenarios"]
  DS --> SCN
  STB["🎭 Stand-ins<br/>Gitea as forge, local model as Claude,<br/>webhook injector, remote instance"] --> SCN
  ONE(["🔁 make agents-verify scenario=id<br/>no redeploy"]) --> SCN
  SCN --> TAB(["📊 Result table<br/>id, mode, result, duration, log"])
  classDef cmd fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef step fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef stub fill:#fef9c3,stroke:#a16207,color:#422006
  classDef out fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  class MK,ONE,CI cmd
  class ACT,ACT2,INV,PRE,DC,DS,SCN step
  class STB stub
  class TAB out
```

SaaS integration (`call-test-agents-saas.yml`):

```mermaid
flowchart LR
  MK(["⌨️ make agents-integration"]) --> ACT["🎬 act runs<br/>call-test-agents-saas.yml"]
  NI(["🌙 nightly, manual,<br/>before feature/agents merges"]) --> CI["☁️ CI runs<br/>call-test-agents-saas.yml"]
  ACT --> SET["🧩 Role set of call-test-deploy.yml<br/>+ agents bundle"]
  CI --> SET
  SET --> LM["🧠 Local models only<br/>(Ollama behind LiteLLM)"]
  LM --> DEP["🚀 Deploy the full server system"]
  DEP --> PW["🎭 Every Playwright spec<br/>of the deployed roles"]
  DEP --> SCN["🧪 Every agent scenario"]
  PW --> TAB(["📊 One result table"])
  SCN --> TAB
  classDef cmd fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
  classDef step fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef out fill:#ede9fe,stroke:#6d28d9,color:#2e1065
  class MK,NI cmd
  class ACT,CI,SET,LM,DEP,PW,SCN step
  class TAB out
```

### Iteration plan

The plan the implementing agent follows without asking back: cheapest check first, the heaviest gate last, every phase closed by its own gate.

- Inner loop, for every change: targeted unit test or lint, then `make compose-deploy mode=update` of the touched role only, then an in-container probe through `make compose-exec`, then `make agents-verify scenario=<id>` against the running stack. A full workflow run happens only at a phase gate.
- Blockers never stop the plan: a missing external credential reports its scenario `skipped`; a real upstream limit stays an open criterion with its reason; an operator-only fact goes to the owner as an `ask` while the next phase continues.
- No CI deploy of `feature/agents` before the store-i18n CI agent reports done; until then, every gate runs through act.

```mermaid
flowchart TD
  P0(["🏁 Start: requirement 041"])
  P1["🧱 Phase 1: foundations<br/>agents/ tree, agent.yml schema, account naming,<br/>role codes, lints"]
  G1{"🚦 Unit and lint green?"}
  P2["🛡️ Phase 2: firewall compiler<br/>rules, guards, write gate, managed settings"]
  G2{"🚦 Compiler unit tests green?"}
  P3["🎛️ Phase 3: control plane<br/>broker, orchestrator, provisioner, reaper,<br/>instance API, audit"]
  G3{"🚦 Single-role deploys + probes green?"}
  P4["🧭 Phase 4: routines and profiles<br/>LangGraph routines, profile catalog,<br/>Open WebUI, n8n, Flowise"]
  G4{"🚦 make agents-verify green<br/>(compose, swarm)?"}
  P5["🌍 Phase 5: remote and detached<br/>polling, claims, home sync, second instance"]
  G5{"🚦 Remote scenarios green?"}
  P6["🧩 Phase 6: SaaS integration<br/>make agents-integration"]
  G6{"🚦 Playwright + scenarios green?"}
  W{"⏳ store-i18n CI agent done?"}
  P7["☁️ Phase 7: CI on core"]
  G7{"🚦 CI green with scenario ids in the log?"}
  DONE(["✅ Every criterion checked"])
  subgraph LOOP["🔁 Inner loop, per change"]
    L1["🧪 Targeted unit or lint"]
    L2["🚀 compose-deploy mode=update,<br/>touched role only"]
    L3["🔍 Probe in container"]
    L4["🎯 agents-verify scenario=id"]
    L5["↩️ Back to the gate that sent you here"]
    L1 --> L2 --> L3 --> L4 --> L5
  end
  P0 --> P1 --> G1
  G1 -->|"❌"| LOOP
  G1 -->|"✅"| P2 --> G2
  G2 -->|"❌"| LOOP
  G2 -->|"✅"| P3 --> G3
  G3 -->|"❌"| LOOP
  G3 -->|"✅"| P4 --> G4
  G4 -->|"❌"| LOOP
  G4 -->|"✅"| P5 --> G5
  G5 -->|"❌"| LOOP
  G5 -->|"✅"| P6 --> G6
  G6 -->|"❌"| LOOP
  G6 -->|"✅"| W
  W -->|"⏳ not yet: keep hardening through act"| LOOP
  W -->|"✅ yes"| P7 --> G7
  G7 -->|"❌"| LOOP
  G7 -->|"✅"| DONE
  classDef phase fill:#dcfce7,stroke:#15803d,color:#052e16
  classDef gate fill:#fef3c7,stroke:#b45309,color:#451a03
  classDef loop fill:#e0f2fe,stroke:#0369a1,color:#082f49
  classDef good fill:#ccfbf1,stroke:#0f766e,color:#042f2e
  class P1,P2,P3,P4,P5,P6,P7 phase
  class G1,G2,G3,G4,G5,G6,G7,W gate
  class L1,L2,L3,L4,L5 loop
  class P0,DONE good
  style LOOP fill:#f0f9ff,stroke:#0369a1
```

## Acceptance Criteria

### Layout

- [ ] `agents/roles/{maintainer,designer,tuner,implementer,robot,reviewer,planner,coordinator,operator,tester,translator,documenter,release,security,hacker,support}/` each contain `AGENTS.md`, `SOUL.md` and `agent.yml`.
- [ ] `agents/SOUL.md` holds the content of `docs/agents/meta/` and every shared principle listed under Role files, and every role `SOUL.md` links to it.
- [ ] Every role's `AGENTS.md` and `SOUL.md` contain every rule listed for it under Role files.
- [ ] `agents/skills/` holds every former `skills/i8-*` skill and one skill per former `docs/agents/files/*` page; `skills/` no longer exists.
- [ ] `make install-skills` installs the repository skills from `agents/skills/`.
- [ ] `docs/agents/` no longer exists, and no file in the repository links to it.
- [ ] The root `AGENTS.md` links to `agents/` and keeps the permission, sandbox and push rules for interactive sessions.
- [ ] A lint test fails when an `agent.yml` misses a field or names an unknown runtime, lifecycle, trigger or firewall role.

### Routines

- [ ] Every former `docs/agents/action/*` page exists as a LangGraph routine under `agents/routines/`.
- [ ] The maintainer, designer and implementer routines implement the graphs drawn under Routines, and `python -m agents.routines show <routine>` prints a Mermaid graph with the same nodes and edges.
- [ ] `python -m agents.routines run <routine>` executes a routine end to end with a stub model node in a unit test.
- [ ] Every `agents/skills/i8-*` skill that routed to a `docs/agents/action/*` page routes to the matching routine.
- [ ] Every shared deterministic tool node exists and has a unit test on a recorded log fixture.
- [ ] A routine node that is not designated as a model node never calls the gateway (unit test).
- [ ] For each failure class of the maintainer routine, a fixture log routes the routine to the listed branch.
- [ ] The negative control node turns a guarded spec red and back to green on a fixture role.
- [ ] The merge check reports a `# nocheck:` marker, a task and a `when:` clause removed by a fixture merge.
- [ ] The number check rejects a pull request text with a number that does not occur in the run's evidence.
- [ ] The CI evidence node finds the change line in a job log, and follows the next run when the first was cancelled by a later merge.
- [ ] No routine reads a raw Playwright report, and no tool node prints a raw task block, argv or environment (lint test).
- [ ] A second run of a routine keeps the first run's output, and both survive a host reboot.
- [ ] A failed log write aborts the routine and leaves no orphaned child process.
- [ ] An operator override of a routine policy is accepted, recorded in the run and shown in its result.
- [ ] Two stack commands of one agent never run at the same time, and nothing starts on the machine while the quality gate runs.
- [ ] The hang watchdog fires on 15 minutes of silence and does not fire on a long build that keeps writing output.
- [ ] A failure classified as deterministic is not retried, and a flaky one is retried once.
- [ ] An `ask` hit outside a declared gate node is reported as a firewall misconfiguration.

### Tooling gaps

- [ ] Each make target listed under Tooling gaps exists, is documented in `make help` and is called by the routine that needs it.
- [ ] `make compose-role-sync task=<task> pw=<args>` runs the spec.
- [ ] `make compose-playwright` runs the current spec and `.env`.
- [ ] `make design-palette sync=role` re-renders `.env`.
- [ ] `make compose-deploy mode=update` finds the inventory written by `make roundtrip` without an explicit `variant`.
- [ ] Gallery screenshots land in the run directory, not in the host `/tmp`.
- [ ] The install stamp stays valid after a commit hook run.
- [ ] `make quality-high` installs every lint tool before the parallel lint dispatch, and ten parallel runs show no import race.
- [ ] The quality gate reports a lint failure in a new untracked file.
- [ ] npm installs succeed inside the sandbox.
- [ ] The slot picker refuses a slot whose subnet a leftover network still holds.
- [ ] A routine fetch succeeds when a fork tag is clobbered.

### Runtime contract and lifecycle

- [ ] `web-app-hermes` and `web-app-openclaw` declare themselves as agent runtimes, and Claude Code in `web-app-workspace` does too.
- [ ] The broker and the orchestrator find runtimes through a lookup; a grep finds no hardcoded runtime list in either role.
- [ ] `svc-ai-agent-broker` no longer sets `enabled: true` on `hermes` or `openclaw`, and deploys with only one of them in the inventory.
- [ ] An `always_on` team agent is running after deploy and is restarted after its container is killed.
- [ ] An `on_demand` user-started agent is spawned on first Open WebUI request and reaped after the idle timeout.
- [ ] Changing `runtime` of a team agent in the inventory switches its runtime on the next deploy.

### Identity and credentials

- [ ] Every team agent and every user-started agent has its own LDAP account with an `owner` attribute.
- [ ] Every agent logs in by SSO to an app its firewall grants, and is refused by an app it does not grant.
- [ ] Every agent has its own LiteLLM virtual key, and the gateway logs show spend per agent key.
- [ ] Claude Code in a workspace completes a request through the gateway's Anthropic upstream, once with `auth: api_key` and once with `auth: subscription`.
- [ ] No agent workspace or agent container holds a model provider credential (probe recorded).
- [ ] A `github` account grant without credentials in the inventory is inactive, and the next active account is the default.
- [ ] Overriding a credential under `agents.<role>.credentials` in the inventory replaces the generated default.
- [ ] No generated agent secret is written outside `sys-token-store`.

### Forges and external accounts

- [ ] A team agent with a manually supplied GitHub token forks `infinito-nexus/core` into its account, pushes a signed commit to a branch of the fork and opens a pull request against the upstream.
- [ ] The same flow works through a Gitea account and through a GitLab account of the platform, both created and keyed at deploy time.
- [ ] An external provider declared in `agents/firewall/providers/` is usable in an `account` grant, and a grant naming an undeclared provider fails the lint.
- [ ] The first `account` grant is the agent's default account: a routine step without an explicit account uses it (unit test), and reordering the grants in the inventory switches the default on the next deploy.
- [ ] A `repositories` entry that names an account is worked through that account instead of the default.
- [ ] Every push command of a routine names its remote and ref (lint test).
- [ ] A push from an agent to the upstream remote is refused by the agent firewall.
- [ ] A merge attempt by an agent is refused by the agent firewall.
- [ ] Setting `repositories` in the inventory makes the agent work on the listed repositories only.

### Workspaces

- [ ] `web-app-workspace` serves a browser IDE with the Claude Code extension installed, behind SSO, inside a Kata or gVisor sandbox.
- [ ] `dsk-agentbox` installs agentbox, and `dsk-gnt-claude`, `dsk-gnt-codex` and `dsk-gnt-pi` run inside an agentbox box.
- [ ] `dsk-code` installs `vscodium` when the local workspace is enabled, and attaches to the box.
- [ ] Inside either workspace, the host home, the host Docker socket and host credentials are not reachable (probe recorded).
- [ ] From inside a workspace, Docker commands reach the agent's own stack and are refused on a foreign stack.
- [ ] Nested Docker in either workspace builds an image without `--privileged`.
- [ ] Changing a reach-widening workspace key without the external approval blocks the workspace start.
- [ ] A human and an agent work in the same server workspace at the same time.

### Orchestrator

- [ ] `svc-ai-agent-orchestrator` deploys in compose and swarm and passes lint.
- [ ] A routine resumes from its Postgres checkpoint after the orchestrator container restarts.
- [ ] A failed GitHub workflow run starts the maintainer routine.
- [ ] An OpenProject assignment to the implementer starts the implementer routine.
- [ ] A schedule from `agent.yml` starts the designer and the tuner routines.
- [ ] Tool nodes run inside the agent's workspace, not inside the orchestrator container.

### Board

- [ ] The orchestrator creates a requirement work package in OpenProject through the API with status `Proposed`.
- [ ] The implementer does not start a `Proposed` work package and starts it after a human sets `Approved`.
- [ ] An agent cannot set `Approved` or `Rejected`.
- [ ] The maintainer starts a failed-run fix without the `Approved` gate.
- [ ] Setting the board URL in the inventory makes every agent use that board instead of the local `web-app-openproject`.
- [ ] Every open requirement under `docs/requirements/`, including this one, exists as an OpenProject work package with its acceptance criteria as checklist.
- [ ] `docs/requirements/` is deleted, and `docs/contributing/requirements.md` and the `i8-requirement-*` skills describe and use the OpenProject API.
- [ ] The lints that read `docs/requirements/` are removed or retargeted.

### Agent firewall

- [ ] `agents/firewall/` defines RBAC roles with `allow`, `ask` and `deny` rules in the documented syntax, and a lint test rejects a rule that does not parse.
- [ ] A unit test proves `deny` beats `ask` beats `allow` and that an unmatched request is denied.
- [ ] A rule target with `${VAR}` expands from the deploy variables, and the `make i18n-translate` lane address is granted that way.
- [ ] A denied egress request is reported with its target within 10 seconds.
- [ ] `svc-ai-mcp-adapter` refuses an MCP tool call outside the agent's grants and returns the matched rule.
- [ ] The agent container cannot reach a host outside its `egress` grants (probe recorded).
- [ ] The agent account is member of exactly the LDAP groups derived from its `app` grants.
- [ ] The workspace's `/etc/claude-code/managed-settings.json` is generated from the agent's grants, owned by root, read-only, and the agent process runs as a non-root user that cannot change it (probe recorded).
- [ ] The agent is member of exactly the channel rooms derived from its `channel` grants.
- [ ] An `ask` match pauses the routine, the owner receives an approval request, approve resumes and reject aborts.
- [ ] An Open WebUI override that would widen a rule is refused.
- [ ] No agent can write to `agents/firewall/` or to its overrides at runtime (probe recorded).
- [ ] `agents/firewall/` ships every baseline role of the design table with the grants listed there.
- [ ] The root `AGENTS.md` permission rules for interactive sessions are expressed by the `interactive` firewall role, and `.claude/settings.json` is generated from it.

### Security controls

- [ ] A seeded prompt injection in an issue, a pull request comment, a ticket, an email and a CI log makes no agent call a tool outside its grants, leak a secret, or skip the `Approved` gate (one scenario each).
- [ ] A node that reads untrusted content runs without an agent runtime and without tools, and only its schema output reaches tool-using nodes (unit test).
- [ ] An issue from a non-collaborator and a fork pull request run start the planner, not the maintainer's ungated path.
- [ ] No file inside a workspace contains a long-lived credential, and git operations in the workspace succeed through the broker's credential helper and `ssh-agent` socket (probe recorded).
- [ ] A diff containing a seeded secret is stopped by the pre-push secret scan, and nothing reaches the remote.
- [ ] A webhook without a valid signature, with a replayed delivery id, or with forged payload content is rejected or acted on only through the re-fetched event.
- [ ] An autonomous agent's write to `agents/firewall/`, `agents/routines/`, an `AGENTS.md`, a `SOUL.md`, the firewall compiler or `.github/workflows/` is denied, and a pull request touching them is labelled by CI and gets no `recommend merge`.
- [ ] With `write_enabled: false`, or with a failed deny, kill-switch, audit or identity scenario, the compiler emits no write grant for the agent.
- [ ] A user-started agent cannot reach an app, MCP tool or channel its owner cannot reach, and loses MCP access within one call after the owner loses the group.
- [ ] The lint flags an `app` grant that maps to a privileged group.
- [ ] Every agent authenticates to `svc-ai-mcp-adapter` with its own token; a token of one agent is refused for another, and the comparison is constant-time (unit test).
- [ ] An MCP call to Gitea, GitLab, Zammad or Nextcloud reaches the application under the calling agent's own identity, visible in the application's log.
- [ ] `make agents-stop` blocks every agent key, stops every agent container and disables every agent account within one minute; `make agents-start` restores them; the Open WebUI button and the owner's channel command trigger the same target.
- [ ] Every tool call, firewall decision, approval and agent channel message appears in the audit database; an update or delete through the audit role is refused, and a tampered entry breaks the hash chain check.
- [ ] Exceeding a quota in `agent.yml` stops the agent's next model call, tool call or forge write and reports the quota.
- [ ] A request for a model outside the agent's `models` list is refused by `svc-ai-litellm`, and `support`, `planner`, `operator` and user-started agents reach no external model by default.
- [ ] Within the allowed list, `svc-ai-s1` picks the model per request from the shared history in `infinito_decider`, and a grep finds no second sampler or history implementation.
- [ ] After a model is removed from an agent's `models` list, its earlier `agent_model_history` rows no longer influence the choice (unit test).
- [ ] Orchestrator checkpoints are encrypted, contain no secret value (fixture test), and expire after the retention period.
- [ ] A workspace cannot reach another workspace through the orchestrator (probe recorded).
- [ ] CI runs triggered by an agent's fork pull request see no repository secret and no write token.
- [ ] The vulnerable fixture app's role fails when deployed by any inventory other than the agents bundle.

### Remote board and detached instances

- [ ] With the board pointing to the remote OpenProject, an assignment to a role group there starts that role's agent on the throwaway instance through polling within two poll intervals.
- [ ] Every agent acts on every remote provider as `<role code>0<instance id>`, visible in the remote applications' logs.
- [ ] A throwaway instance registers its name with its public key; a second registration of the same name with another key is refused, and the same key takes over.
- [ ] A provisioning request authenticated with the developer's login creates the agents' accounts on the live instance after approval, sets the developer as `owner`, and no admin token of the live instance exists on the developer machine (probe recorded).
- [ ] The broker reaches the OpenProject API with an OIDC JWT bearer token and Nextcloud with an app password created from the agent's login; neither appears inside a workspace (probe recorded).
- [ ] Gitea and GitLab tokens minted by the broker are short-lived and never appear inside a workspace (probe recorded).
- [ ] The Matrix channel adapter logs in with login credentials, keeps its session outside the workspace, and after a teardown and redeploy decrypts earlier end-to-end encrypted room history through key backup, with the recovery key read from the inventory or OpenBao.
- [ ] After a teardown, login credentials, the Matrix recovery key and the instance key are still available from the developer's inventory or OpenBao, and nothing of them is kept only in `sys-token-store`.
- [ ] With OpenBao enabled, an instance's AppRole reads `agents/<instance id>/*` and is refused everywhere else.
- [ ] Two throwaway instances claiming the same work package at once end with exactly one owner; the other gets `409` and moves on.
- [ ] A claim is refused when the work package is not `Approved` or not assigned to the agent's role group, and OpenProject refuses an agent account's transition outside `Approved` -> `In progress` -> `Review`.
- [ ] When an instance's lease expires, the live reaper revokes its tokens, app passwords and Matrix devices and returns its claimed work packages to `Approved`; a write from the instance after expiry is refused.
- [ ] `make agents-stop` suspends without revoking, and `make agents-start` resumes; a teardown revokes.
- [ ] No agent writes to the board directly; board writes come from the orchestrator, and each agent's egress to remote hosts matches its own `account` grants exactly.
- [ ] After a teardown and redeploy, every agent's allowlisted harness state is restored from the latest Nextcloud snapshot.
- [ ] Session transcripts and credential files never reach Nextcloud, a seeded secret stops the snapshot upload, and the owner can restore an earlier memory snapshot.
- [ ] Snapshots are uploaded at routine checkpoints and at teardown by the sidecar, never continuously from open files.
- [ ] Audit entries of a throwaway instance reach the live instance with server-assigned time, sequence and hash chain; a dropped entry is reported as a gap, and a teardown waits until the spool is empty.
- [ ] A GitHub push from a throwaway instance uses that instance's own token and signing key under the role account, carries the instance id in the branch name, and revoking that token leaves other instances working.
- [ ] A channel with credentials for a remote instance carries agent messages there; without them the local channel is used.

### Account naming

- [ ] `IAM_ACCOUNT_MAX_LENGTH` equals the smallest username limit declared by any role, and a lint fails when a role declares a smaller one or none.
- [ ] Every role code is four characters of `[a-z1-9]` and unique; a lint fails otherwise.
- [ ] Agent account names match `<role code>0<suffix>` within `IAM_ACCOUNT_MAX_LENGTH`; an over-long suffix is replaced by a base32 hash, and a collision lengthens the hash.
- [ ] Keycloak and OpenLDAP accept human names of `[a-z1-9]{3,13}` and agent names of the documented form, and refuse a human name containing `0`.
- [ ] A lint refuses a user in `lookup('users')` whose name contains `0` or exceeds 13 characters.
- [ ] A deploy lists every existing human account containing `0`, and agents do not start on that instance until those accounts are renamed.
- [ ] An agent account of the longest form is accepted by every application that creates accounts, Bluesky included (one scenario per application).
- [ ] The Bluesky login broker creates handles without the `kc-` prefix, and existing `kc-` handles are migrated.

### Profile catalog

- [ ] The broker lists every role of `agents/roles/` as an OpenAI-compatible model `agent/<role>`.
- [ ] Open WebUI, n8n and Flowise each start a profile through that endpoint (one Playwright spec each).
- [ ] A user without the group `agent-<role>` cannot start that profile.
- [ ] A started agent's effective rights equal the intersection of the profile's grants and its owner's rights (unit test over the compiler).
- [ ] A started agent gets its own accounts on every provisioned provider when it starts, and the reaper removes them when the agent is deleted.

### Channels

- [ ] Team agents log into `web-app-matrix` with their own accounts.
- [ ] A human gives a team agent a task by Matrix DM and receives the result there.
- [ ] Two team agents exchange a coordination message in the team room.
- [ ] A message addressed to an agent account while its instance restarts is delivered after the restart.
- [ ] A failed run and a new pull request produce a Matrix notification.
- [ ] A Matrix reply from the owner's exact local account with the valid nonce approves an `ask` match; a reply without the nonce, from another account, after expiry, as a reaction, or reusing the nonce is refused.
- [ ] No channel reply and no agent account can set a work package to `Approved` or `Rejected`.
- [ ] The channel contract has an email and a Zammad implementation, and one unit test drives all three implementations through the same interface.

### Additional agent roles

- [ ] reviewer: an agent pull request with a missing evidence comment gets `changes requested`; a clean one gets `recommend merge`; the reviewer never reviews its own pull request.
- [ ] reviewer: a pull request whose new spec has no negative control gets `changes requested`.
- [ ] planner: an issue becomes a `Proposed` work package with user story and checkable criteria, linked to the issue.
- [ ] planner: a second issue with the same content is linked to the existing work package instead of creating a new one.
- [ ] coordinator: two agents requesting a CI deploy of the same repository at once get the slot one after the other.
- [ ] coordinator: diverging version pins between two feature branches are reported to both owners before they meet.
- [ ] operator: a seeded alarm (full disk, expiring certificate, failed backup) starts its runbook routine and ends as a work package with timeline and cause.
- [ ] operator: a backup restore waits for the owner's approval.
- [ ] tester: a seeded spec that cannot fail is detected by its negative control and hardened in a pull request.
- [ ] tester: a coverage gap between `meta/services.yml` and the specs becomes a pull request with the missing spec.
- [ ] translator: new strings get machine translations through `web-svc-translate` as Weblate suggestions, and a human-reviewed string stays unchanged.
- [ ] documenter: a merged pull request that changes a role's variables produces a README pull request that matches them, with the docs build green.
- [ ] release: a green default branch produces a release draft with notes; the tag waits for approval.
- [ ] security: a seeded vulnerable dependency becomes a work package in the confidential security project.
- [ ] hacker: every seeded finding of the fixture app becomes a work package in the confidential security project with severity, affected role and reproduction steps, and without live secrets.
- [ ] hacker: every failed check and a failed scan run send an email to the security contact that carries only severity and link.
- [ ] hacker: a scan against a target outside `agents.hacker.targets`, or against an internal port, is refused by the firewall (probe recorded).
- [ ] hacker: without `agents.hacker.targets` the hacker does not start; a production run waits for the owner's approval of that run.
- [ ] hacker: no scan sends more requests per second than its configured rate limit.
- [ ] support: a new Zammad ticket gets a drafted answer with cited sources as internal note, drawn only from public docs, role READMEs and approved answers with customer data removed.
- [ ] support: the approval view shows the full outgoing text and every attachment.
- [ ] support: the answer reaches the customer only after the owner approves it; a rejection with a remark produces a revised draft.
- [ ] support: a defect described in a ticket becomes a `Proposed` work package linked to the ticket.
- [ ] support: a draft never contains a secret, an internal hostname or another customer's data (fixture test).

### Management surfaces

- [ ] Open WebUI lists the team agents a user may chat with, and a chat reaches the agent.
- [ ] Open WebUI starts, pauses, aborts and triggers a routine.
- [ ] Open WebUI shows running routines, checkpoints, assigned work packages and recent pull requests.
- [ ] Open WebUI changes runtime, repositories, credential overrides and schedule of an agent, only for its owner and the administrator.
- [ ] The Flowise and n8n evaluation is recorded in the orchestrator README with one verdict per management function.
- [ ] Every function judged feasible for Flowise or n8n is implemented and covered by a Playwright spec.

### Role cleanup

- [ ] Only `svc-ai-libretranslate-engine` runs a LibreTranslate container; `web-svc-libretranslate` starts none and `prefetch_models.py` exists once.
- [ ] `web-app-mediawiki` consumes `web-svc-translate`, and translation through it works in a Playwright spec.
- [ ] `web-svc-translate` uses `libretranslate-engine` consistently in its README, `router.order` and consumer key.
- [ ] `web-app-openwebui` enables tika, searxng and jupyter, and Playwright specs cover a RAG upload, a web search and a code execution.
- [ ] The `web-app-openwebui` description no longer names Ollama as its backend.
- [ ] `svc-ai-robot` reads its persona from `agents/roles/robot/`.
- [ ] A grep over the AI roles finds no `in group_names` peer-presence test.
- [ ] `web-svc-translate` reads its router strategy without a code-level fallback value.

### Requirement hygiene

- [ ] Every superseded criterion listed above carries a pointer to this file in its earlier requirement.
- [ ] [038](038-system-one-model-router.md) names `services.s1`, not `services.jeff`, and names `weighted` as the LLM gateway fallback; [040](040-translation-gateway.md) names `preference` as the translation gateway fallback.
- [ ] [025](025-mcp-role-integration.md) and [035](035-mcp-proxy-expansion.md) agree on one disposition per application, matching its `meta/mcp.yml`.
- [ ] [035](035-mcp-proxy-expansion.md) names `dsk-*` roles, has no stray fragment, and lists the AI roles added since it was written.
- [ ] [037-gettext](037-gettext-catalogs-libretranslate.md) no longer calls the catalog server "038 - web-svc-api".

### Local setup and integration workflows

- [ ] `inventories/bundles/servers/agents/` deploys the complete agent infrastructure against localhost with `make compose-deploy`, and its README describes how.
- [ ] `call-test-agents-local.yml` runs on pull requests touching `agents/` or an AI role, and `make agents-verify` runs the same file through act.
- [ ] `call-test-agents-saas.yml` deploys the role set of `call-test-deploy.yml` plus the agents bundle, runs every Playwright spec of the deployed roles and every agent scenario with local models only, and `make agents-integration` runs the same file through act.
- [ ] `call-test-agents-saas.yml` runs nightly and on manual dispatch, and is a required check before `feature/agents` merges.
- [ ] No request of a `call-test-agents-saas.yml` run reaches an external model provider (gateway log).
- [ ] The iteration plan's inner loop works: a change to one role is verified by `make compose-deploy mode=update`, an in-container probe and `make agents-verify scenario=<id>` without a full workflow run.
- [ ] `make agents-verify` deploys the agent infrastructure through act in compose and in swarm and runs every scenario.
- [ ] `make agents-verify scenario=<id>` reruns one scenario against the running stack without a redeploy.
- [ ] Every acceptance criterion of this file except this section has exactly one scenario in `agents/scenarios/`, and a lint test fails on a criterion without a scenario or a scenario without a criterion.
- [ ] Fork, push and pull request scenarios pass against the local `web-app-gitea`.
- [ ] Claude Code scenarios pass against the local model behind the gateway's Anthropic-protocol endpoint.
- [ ] Without GitHub or Anthropic credentials in the inventory, their scenarios report `skipped`.
- [ ] The run prints the result table, and a single failed scenario makes the run fail.
- [ ] The CI runs the same workflow file as `make agents-verify`.
- [ ] `make agents-verify mode=swarm` refuses to start on a worktree slot above 10 and names the fix.
- [ ] The Ollama images are preseeded and no deploy step waits on the registry cache for them.

### End to end

- [ ] Every new and changed role is green in compose and in swarm.
- [ ] `make agents-verify` is green locally in both modes before the first CI deploy of `feature/agents`.
- [ ] The CI pipeline of `feature/agents` is green with the agent scenarios executed (each scenario id present in the job log).
- [ ] The maintainer fixes a seeded failing test from a failed run through to an open pull request without human input.
- [ ] The designer opens a pull request that changes the design of one app, with before and after gallery.
- [ ] The tuner opens a pull request with a measured performance improvement.
- [ ] The implementer turns an `Approved` work package into an open pull request.
- [ ] A full chain runs without manual steps between the agents: support ticket -> planner work package -> human approval -> implementer pull request -> reviewer recommendation -> human merge -> release draft.
- [ ] The hacker files a report and sends an email against the running verification stack, and the maintainer picks the report up as a fix.

## Cross-linking

- Implementing PR: to be added.

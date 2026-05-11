# GOD Repo Guidance

GOD is a productized monorepo for **Govern, Observe, Direct** — a real-time control
room for agent societies.

## Internal layout (do not surface in public docs/config)

- `agentsociety/` — trimmed upstream backend workspace. Hosts the FastAPI live/replay
  service, the React control room, and the custom adapters/envs.
- `jiuwenclaw/` — trimmed upstream agent runtime; used as an out-of-process AgentServer.
- `scripts/god.sh` — single operations entrypoint.

These directory names are implementation detail. The user-facing surface (README,
QUICKSTART, `.env`, script output) must only refer to **GOD**, **Control Room**,
**Backend**, **Agent Runtime**, etc.

## Configuration surface

- The only user-facing env namespace is `GOD_*`. `scripts/god.sh` maps it to the
  internal `AGENTSOCIETY_*` / `JIUWENCLAW_*` variables required by the upstream
  packages. Do not document or instruct users to set `AGENTSOCIETY_*` /
  `JIUWENCLAW_*` directly.

## Development defaults

- Recommended local entrypoint: `./scripts/god.sh start` (idempotent).
- `./scripts/god.sh restart` only when services must be torn down first.
- `./scripts/god.sh new-run` when replay data or live session state should be reset.
- `./scripts/god.sh factory-reset` is hidden maintenance; do not list it in
  user-facing docs.
- Do not commit `.env`, `.god/`, `node_modules/`, `.venv/`, `dist/`, logs, or
  experiment `run/` directories.
- Keep the agent runtime as a separate process boundary; the backend talks to it
  over the local WebSocket.
- Default experiment lives at
  `agentsociety/quick_experiments/hypothesis_god_town/experiment_1`.

## Public docs rules

- README/QUICKSTART are publishable. Do not mention test helpers, port-conflict
  recipes, shell-not-found notes, or the `factory-reset` command.
- Do not surface upstream brand names (`AgentSociety`, `JiuwenClaw`) as primary
  subsystems. They may appear only in the **Acknowledgements** / **Citation**
  sections as upstream credit.

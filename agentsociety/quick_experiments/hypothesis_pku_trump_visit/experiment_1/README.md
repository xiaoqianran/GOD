# PKU · Trump Campus Visit What-if Experiment

This experiment is a fictional GOD what-if simulation set on the PKU map package.
It starts with ordinary campus life, then lets the operator manually inject a
public notice for a fictional campus stop: Donald Trump will visit Peking
University and speak at Centennial Hall with a delegation that includes Elon
Musk, Jensen Huang, and a coordinator.

Important: the experiment uses a hypothetical May 2026 China-visit framing only
as broad background context. The PKU lecture, campus route, delegation makeup,
student questions, and all generated answers are fictional. Do not publish
generated output as real itinerary, real speech, or real policy.

## Run

```bash
GOD_EXPERIMENT=pku_trump_visit GOD_EXPERIMENT_RUN=1 ./scripts/god.sh new-run
```

The control room opens at:

```text
http://127.0.0.1:5174/pixel-replay/pku_trump_visit/1
```

## Map

- Map package: `custom/maps/pku`
- Map id: `pku`
- The PKU map package is a local asset folder and is intentionally not stored
  in this repository. If it is absent, GOD falls back to `the_ville`.
- Key locations: `west_gate`, `weiming_lake`, `boya_pagoda`, `library`,
  `centennial_hall`, `teaching_building`, `dormitory`, `canteen`,
  `gymnasium`, `lab_building`, `admin_building`, `campus_green`

## Agent Count

The experiment defines 22 fixed-ID agents:

- 18 PKU campus agents: students, faculty, staff, media, club organizers, and a visitor.
- 4 delegation agents: Donald Trump, Elon Musk, Jensen Huang, and a delegation coordinator.

The delegation agents are stylized fictional simulation personas. They do not
represent real statements by those people.

## Operator Flow

1. Run the first 2-3 live steps to show ordinary campus life.
2. Paste the visit-notice intervention from `OPERATOR_SCRIPT.md`.
3. Run one or two steps to observe campus discussion.
4. Paste the delegation-arrival and lecture interventions.
5. Use the Q&A blocks in `OPERATOR_SCRIPT.md`: each question is first delivered
   as an agent-to-agent `direct_message`, then followed by a targeted `Ask` for a
   clean answer suitable for screen recording.
6. Finish with the aftermath and summary prompts.

## Validation

```bash
cd agentsociety
uv run python scripts/validate_map_package.py custom/maps/pku
```

Static expectations:

- `init/init_config.json` uses `map_id: pku`.
- Every `initial_locations` entry is one of the PKU map location ids.
- `init/steps.yaml` starts at `2026-05-15T08:20:00+08:00`.

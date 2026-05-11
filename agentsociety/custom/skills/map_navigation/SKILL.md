---
name: map_navigation
description: Convert a daily-life intention into a concrete map movement or interaction proposal.
script: scripts/map_navigation.py
priority: 45
requires:
  - daily_life
provides:
  - action_proposal
inputs:
  - state/daily_life_intention.json
outputs:
  - state/action_proposal.json
---

# Map Navigation

Use the current map observation and `state/daily_life_intention.json` to produce
one concrete action proposal: move first when the agent is not in the target
scene, otherwise perform the location interaction.

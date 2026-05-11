---
name: social_interaction
description: Propose short grounded replies when recent social messages make conversation appropriate.
script: scripts/social_interaction.py
priority: 50
requires:
  - daily_life
provides:
  - social_action_proposal
outputs:
  - state/social_action_proposal.json
---

# Social Interaction

When recent messages are present, produce a short direct or group response that
fits the current scene. This skill is secondary to urgent safety behavior and
ordinary routine movement.

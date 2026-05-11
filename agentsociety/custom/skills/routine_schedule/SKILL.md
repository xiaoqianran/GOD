---
name: routine_schedule
description: Convert simulation time and role into a soft daily schedule hint.
script: scripts/routine_schedule.py
priority: 20
provides:
  - routine_schedule
outputs:
  - state/routine_schedule.json
---

# Routine Schedule

Build a soft schedule for this tick from the simulation time and agent role.
This skill does not enforce hidden meters; it gives the later daily-life skill a
human routine baseline such as breakfast, school, work, patrol, dinner, rest, or sleep.

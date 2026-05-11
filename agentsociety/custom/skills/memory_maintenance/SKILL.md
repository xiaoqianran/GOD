---
name: memory_maintenance
description: Persist a compact community-life memory line for this tick.
script: scripts/memory_maintenance.py
priority: 80
requires:
  - daily_life
provides:
  - routine_memory
outputs:
  - memory/community_memory.jsonl
---

# Memory Maintenance

Append one compact JSONL memory line per tick so the Jiuwen adapter can keep a
persistent local record of routine intentions and public events.

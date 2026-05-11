#!/usr/bin/env python3
"""Convert an intention into a map action proposal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args-json", default="{}")
    return parser.parse_args()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def observation_from(args: dict[str, Any]) -> dict[str, Any]:
    raw = args.get("observation")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def main() -> int:
    args = json.loads(parse_args().args_json)
    if not isinstance(args, dict):
        raise TypeError("--args-json must decode to an object")
    work_dir = Path(args.get("agent_work_dir") or ".").resolve()
    state_dir = work_dir / "state"
    observation = observation_from(args)
    intention = load_json(state_dir / "daily_life_intention.json", {})
    agent_id = int(args.get("agent_id") or observation.get("agent_id") or 0)
    current_location = str(observation.get("location_id") or "")
    target_location = str(intention.get("preferred_location_id") or current_location)
    interaction_id = str(intention.get("preferred_interaction_id") or "")
    reason = str(intention.get("reason") or intention.get("goal") or "")

    if target_location and target_location != current_location:
        proposal = {
            "source": "map_navigation",
            "action_type": "move",
            "agent_id": agent_id,
            "location_id": target_location,
            "interaction_id": "",
            "reason": reason,
            "environment_instruction": f"Move agent {agent_id} to {target_location}.",
        }
    elif interaction_id:
        proposal = {
            "source": "map_navigation",
            "action_type": "interact",
            "agent_id": agent_id,
            "location_id": current_location,
            "interaction_id": interaction_id,
            "params": {"message": reason or "routine action"},
            "reason": reason,
            "environment_instruction": f"Agent {agent_id} performs interaction {interaction_id}.",
        }
    else:
        proposal = {
            "source": "map_navigation",
            "action_type": "set_action",
            "agent_id": agent_id,
            "action": reason or "continues a quiet routine",
            "status": "active",
            "emotion": "calm",
            "reason": reason,
            "environment_instruction": f"Set agent {agent_id} action to a quiet routine.",
        }

    target = state_dir / "action_proposal.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(proposal, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

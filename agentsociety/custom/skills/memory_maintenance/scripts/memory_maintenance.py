#!/usr/bin/env python3
"""Append a compact routine memory line."""

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
    observation = observation_from(args)
    intention = load_json(work_dir / "state" / "daily_life_intention.json", {})
    record = {
        "tick": args.get("tick"),
        "time": args.get("time"),
        "agent_id": args.get("agent_id"),
        "location_id": observation.get("location_id"),
        "latest_event": observation.get("latest_event"),
        "goal": intention.get("goal"),
        "preferred_location_id": intention.get("preferred_location_id"),
        "preferred_interaction_id": intention.get("preferred_interaction_id"),
    }
    path = work_dir / "memory" / "community_memory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

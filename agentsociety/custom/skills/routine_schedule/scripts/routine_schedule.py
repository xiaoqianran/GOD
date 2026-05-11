#!/usr/bin/env python3
"""Write a soft daily schedule hint for the current tick."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args-json", default="{}")
    return parser.parse_args()


def profile_text(profile: Any) -> str:
    if isinstance(profile, dict):
        return " ".join(str(value) for value in profile.values()).lower()
    return str(profile or "").lower()


def hour_from(value: str) -> float:
    try:
        dt = datetime.fromisoformat(value)
        return dt.hour + dt.minute / 60.0
    except Exception:
        return 12.0


def time_block(hour: float) -> str:
    if 5.5 <= hour < 8.5:
        return "morning"
    if 8.5 <= hour < 11.5:
        return "morning_duty"
    if 11.5 <= hour < 13.5:
        return "midday"
    if 13.5 <= hour < 17.5:
        return "afternoon_duty"
    if 17.5 <= hour < 20.5:
        return "evening"
    if 20.5 <= hour < 23.5:
        return "night"
    return "late_night"


def role_class(role: str) -> str:
    if any(word in role for word in ("学生", "student")):
        return "student"
    if any(word in role for word in ("老师", "教师", "teacher")):
        return "teacher"
    if any(word in role for word in ("医生", "护士", "doctor", "nurse")):
        return "pharmacy_care_worker"
    if any(word in role for word in ("狱警", "警卫", "guard", "police")):
        return "public_safety_worker"
    if any(word in role for word in ("囚犯", "犯人", "inmate", "prisoner")):
        return "resident"
    if any(word in role for word in ("店员", "商贩", "shop", "vendor", "market")):
        return "shop_worker"
    return "resident"


def main() -> int:
    args = json.loads(parse_args().args_json)
    if not isinstance(args, dict):
        raise TypeError("--args-json must decode to an object")
    work_dir = Path(args.get("agent_work_dir") or ".").resolve()
    hour = hour_from(str(args.get("time") or ""))
    role = role_class(profile_text(args.get("profile")))
    schedule = {
        "source": "routine_schedule",
        "time": args.get("time"),
        "hour": hour,
        "time_block": time_block(hour),
        "role_class": role,
        "tick": args.get("tick"),
    }
    target = work_dir / "state" / "routine_schedule.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(schedule, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

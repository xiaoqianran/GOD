#!/usr/bin/env python3
"""Choose a grounded daily-life intention for one simulation tick."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


URGENT_WORDS = (
    "火山",
    "爆发",
    "地震",
    "火灾",
    "洪水",
    "撤离",
    "疏散",
    "紧急",
    "危险",
    "emergency",
    "evacuate",
    "volcano",
    "earthquake",
    "fire",
    "flood",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args-json", default="{}")
    return parser.parse_args()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


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


def profile_text(profile: Any) -> str:
    if isinstance(profile, dict):
        return " ".join(str(value) for value in profile.values()).lower()
    return str(profile or "").lower()


def ids(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {
        str(item.get("id") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def first_available(targets: list[str], available: set[str], fallback: str = "") -> str:
    for target in targets:
        if target in available:
            return target
    return fallback or (sorted(available)[0] if available else "")


def contains_urgent(observation: dict[str, Any]) -> bool:
    parts = [str(observation.get("latest_event") or ""), str(observation.get("last_message") or "")]
    for message in observation.get("recent_messages", []) or []:
        if isinstance(message, dict):
            parts.append(str(message.get("content") or ""))
    text = " ".join(parts).lower()
    return any(word.lower() in text for word in URGENT_WORDS)


def choose_role_target(role: str, hour: float) -> tuple[list[str], list[str], str]:
    if any(word in role for word in ("学生", "student")):
        if 8.0 <= hour < 16.5:
            return ["school"], ["attend_class", "study_after_class"], "school routine"
    if any(word in role for word in ("老师", "教师", "teacher")):
        if 8.0 <= hour < 16.5:
            return ["school"], ["teach_class", "study_after_class"], "teaching routine"
    if any(word in role for word in ("医生", "护士", "doctor", "nurse")):
        if 8.0 <= hour < 18.0:
            return ["pharmacy"], ["pharmacy_consultation", "buy_medicine"], "pharmacy care shift"
    if any(word in role for word in ("狱警", "警卫", "guard", "police")):
        if 7.0 <= hour < 22.0:
            return ["park", "supply_store", "market"], ["coordinate_group", "inspect_supplies", "buy_food"], "public safety patrol"
    if any(word in role for word in ("囚犯", "犯人", "inmate", "prisoner")):
        if 11.0 <= hour < 13.0 or 17.0 <= hour < 19.0:
            return ["home", "dorm", "cafe"], ["eat_at_home", "eat_at_dorm", "eat_light_meal"], "ordinary meal routine"
        return ["home", "park", "cafe"], ["relax_at_home", "take_walk", "chat_over_coffee"], "ordinary resident routine"
    if any(word in role for word in ("店员", "商贩", "shop", "vendor", "market")):
        if 8.0 <= hour < 18.0:
            return ["market"], ["work_shop_shift", "buy_food"], "market work"
    return [], [], ""


def choose_time_target(hour: float) -> tuple[list[str], list[str], str]:
    if 5.5 <= hour < 8.5:
        return ["home"], ["cook_meal", "eat_at_home"], "morning routine"
    if 11.5 <= hour < 13.5:
        return ["cafe", "market", "home"], ["eat_light_meal", "buy_food", "eat_at_home"], "lunch routine"
    if 17.5 <= hour < 20.5:
        return ["home", "cafe", "pub", "park"], ["eat_at_home", "chat_over_coffee", "eat_pub_meal", "meet_friend"], "evening routine"
    if 20.5 <= hour < 23.5:
        return ["home", "park"], ["relax_at_home", "rest_on_bench"], "night routine"
    if hour >= 23.5 or hour < 5.5:
        return ["home"], ["sleep_at_home"], "sleep routine"
    return ["park", "cafe", "market", "library", "home"], ["take_walk", "chat_over_coffee", "buy_food", "read_book", "relax_at_home"], "ordinary community routine"


def main() -> int:
    args = json.loads(parse_args().args_json)
    if not isinstance(args, dict):
        raise TypeError("--args-json must decode to an object")

    work_dir = Path(args.get("agent_work_dir") or ".").resolve()
    state_dir = work_dir / "state"
    observation = observation_from(args)
    schedule = load_json(state_dir / "routine_schedule.json", {})
    role = profile_text(args.get("profile"))
    hour = float(schedule.get("hour", 12.0) or 12.0)
    location_ids = ids(observation.get("known_locations"))
    interaction_ids = ids(observation.get("known_interactions"))
    current_location = str(observation.get("location_id") or "")

    if contains_urgent(observation):
        location = first_available(["park", "supply_store", "market"], location_ids, current_location)
        interaction = first_available(["coordinate_group", "inspect_supplies", "prepare_kit"], interaction_ids)
        intention = {
            "source": "daily_life",
            "goal": "respond to urgent public safety information",
            "reason": "Recent observation or messages include an emergency signal.",
            "preferred_location_id": location,
            "preferred_interaction_id": interaction,
            "priority": "urgent",
        }
        write_json(state_dir / "daily_life_intention.json", intention)
        print(json.dumps(intention, ensure_ascii=False))
        return 0

    locations, interactions, reason = choose_role_target(role, hour)
    if not locations:
        locations, interactions, reason = choose_time_target(hour)

    location = first_available(locations, location_ids, current_location)
    interaction = first_available(interactions, interaction_ids)
    intention = {
        "source": "daily_life",
        "goal": reason,
        "reason": f"{reason}; role/time/profile suggest a natural community action.",
        "preferred_location_id": location,
        "preferred_interaction_id": interaction,
        "priority": "normal",
    }
    write_json(state_dir / "daily_life_intention.json", intention)
    print(json.dumps(intention, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

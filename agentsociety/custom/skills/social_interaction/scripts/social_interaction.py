#!/usr/bin/env python3
"""Write a lightweight social action proposal from recent messages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--args-json", default="{}")
    return parser.parse_args()


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
    agent_id = int(args.get("agent_id") or observation.get("agent_id") or 0)
    messages = [
        item
        for item in observation.get("recent_messages", []) or []
        if isinstance(item, dict) and int(item.get("sender_id") or -1) != agent_id
    ]
    if not messages:
        proposal = {"source": "social_interaction", "action_type": "none", "reason": "no recent social message"}
    else:
        last = messages[-1]
        content = str(last.get("content") or "")
        group_id = last.get("group_id")
        reply = f"我收到了：{content[:40]}。我会结合当前位置继续处理。"
        if group_id is not None:
            proposal = {
                "source": "social_interaction",
                "action_type": "group_message",
                "agent_id": agent_id,
                "group_id": int(group_id),
                "content": reply,
                "reason": "reply to recent group message",
                "environment_instruction": f"Send group message from agent {agent_id}: {reply}",
            }
        else:
            proposal = {
                "source": "social_interaction",
                "action_type": "direct_message",
                "agent_id": agent_id,
                "receiver_id": int(last.get("sender_id") or 0),
                "content": reply,
                "reason": "reply to recent direct message",
                "environment_instruction": f"Send direct message from agent {agent_id}: {reply}",
            }
    target = work_dir / "state" / "social_action_proposal.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(proposal, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

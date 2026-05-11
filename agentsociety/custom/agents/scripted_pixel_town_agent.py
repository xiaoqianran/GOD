"""Deterministic pixel-town agent for replayable multi-step demos."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from agentsociety2.agent.base import AgentBase


class ScriptedPixelTownAgent(AgentBase):
    """Agent that executes a configured step script against PixelTownSocialEnv."""

    def __init__(
        self,
        id: int,
        profile: Any,
        name: str | None = None,
        script: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(id=id, profile=profile, name=name)
        self._script = script or []
        self._step_index = 0
        self._last_result: dict[str, Any] = {}
        self._queued_interventions: list[dict[str, Any]] = []

    @classmethod
    def mcp_description(cls) -> str:
        return """ScriptedPixelTownAgent: deterministic replay demo agent.

Provide a `script` list. Each entry can set location/action/status/emotion,
phase, direct_messages, and group_messages. It is useful for fast multi-step
frontend replay validation without spending LLM calls.
"""

    async def ask(self, message: str, readonly: bool = True) -> str:
        if any(keyword in message for keyword in ("今天", "干了什么", "做了什么", "what did")):
            completed = self._script[: min(self._step_index, len(self._script))]
            if completed:
                summaries = []
                for index, action in enumerate(completed, start=1):
                    phase = action.get("phase") or "阶段"
                    location = action.get("location") or "未知地点"
                    activity = action.get("action") or action.get("status") or "等待"
                    summaries.append(f"{index}. {phase}：在{location}{activity}")
                return (
                    f"{self.name} 今天已经执行到第 {self._step_index} 步。"
                    "主要做了：\n" + "\n".join(summaries)
                )
            return f"{self.name} 今天还没有执行新的行动。"
        if any(keyword in message for keyword in ("听到", "收到", "实时提问", "身份回答")):
            role = self.get_profile().get("role", "居民")
            return (
                f"我是 {self.name}，身份是{role}。我收到了你的实时提问。"
                f"当前我执行到第 {self._step_index} 步，最近状态是：{self._last_result or '暂无'}。"
            )
        return (
            f"{self.name} is a scripted pixel-town agent. "
            f"Current script step: {self._step_index}. Last result: {self._last_result}"
        )

    async def step(self, tick: int, t: datetime) -> str:
        if self._queued_interventions:
            action = self._queued_interventions.pop(0)
        else:
            action = (
                self._script[self._step_index]
                if self._step_index < len(self._script)
                else {}
            )
        env = self._find_pixel_env()
        if env is None:
            result = {"error": "PixelTownSocialEnv not found"}
        else:
            result = await env.apply_scripted_action(self.id, action)
        self._last_result = result
        self._step_index += 1
        return str(result)

    def queue_intervention(self, instruction: str) -> str:
        action = self._build_intervention_action(instruction)
        self._queued_interventions.append(action)
        return "已排队到下一次 step"

    def _build_intervention_action(self, instruction: str) -> dict[str, Any]:
        clean_instruction = " ".join(str(instruction).split())
        location = self._match_first(
            clean_instruction,
            [
                r"(?:前往|移动到|去到|去|到)([^，。,；;、]+)",
                r"(?:location|地点|位置)[:：= ]+([^，。,；;]+)",
            ],
        )
        status = self._match_first(
            clean_instruction,
            [
                r"(?:状态设为|状态设置为|将状态设为|status[:：= ]+)([^，。,；;]+)",
                r"(?:设为|设置为)([^，。,；;]+)",
            ],
        )
        return {
            "phase": "实时干预",
            "location": location,
            "action": f"执行实时干预：{clean_instruction}",
            "status": status or "intervened",
            "emotion": "focused",
            "event": f"{self.name} 接收到实时干预：{clean_instruction}",
        }

    @staticmethod
    def _match_first(text: str, patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value or None
        return None

    async def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "profile": self.get_profile(),
            "script": self._script,
            "step_index": self._step_index,
            "last_result": self._last_result,
            "queued_interventions": self._queued_interventions,
        }

    async def load(self, dump_data: dict[str, Any]) -> None:
        self._id = int(dump_data.get("id", self._id))
        self._name = str(dump_data.get("name", self._name))
        self._profile = dump_data.get("profile", self._profile)
        script = dump_data.get("script")
        if isinstance(script, list):
            self._script = script
        self._step_index = int(dump_data.get("step_index", self._step_index))
        last_result = dump_data.get("last_result")
        if isinstance(last_result, dict):
            self._last_result = last_result
        queued_interventions = dump_data.get("queued_interventions")
        if isinstance(queued_interventions, list):
            self._queued_interventions = [
                item for item in queued_interventions if isinstance(item, dict)
            ]

    def _find_pixel_env(self) -> Any:
        if self._env is None:
            return None
        for module in getattr(self._env, "env_modules", []):
            if hasattr(module, "apply_scripted_action"):
                return module
        return None

"""Replay-friendly pixel town social environment."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
import heapq
import json
from pathlib import Path
import sqlite3
from typing import Any, ClassVar

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
import yaml


Tile = tuple[int, int]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _load_structured_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Pixel town map manifest not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Pixel town map manifest must be an object: {path}")
    return data


class PixelTownSocialEnv(EnvBase):
    """Small social environment that exports per-agent replay snapshots."""

    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("name", "TEXT"),
        ColumnDef("location", "TEXT"),
        ColumnDef("action", "TEXT"),
        ColumnDef("status", "TEXT"),
        ColumnDef("emotion", "TEXT"),
        ColumnDef("message_count", "INTEGER"),
        ColumnDef("last_message", "TEXT"),
        ColumnDef("recent_messages", "JSON"),
        ColumnDef("current_phase", "TEXT"),
        ColumnDef("latest_event", "TEXT"),
        ColumnDef("groups", "JSON"),
        ColumnDef("map_id", "TEXT"),
        ColumnDef("tile_x", "INTEGER"),
        ColumnDef("tile_y", "INTEGER"),
        ColumnDef("location_id", "TEXT"),
        ColumnDef("movement_status", "TEXT"),
        ColumnDef("target_location_id", "TEXT"),
        ColumnDef("path_json", "JSON"),
        ColumnDef("available_interactions_json", "JSON"),
    ]
    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("total_messages_sent", "INTEGER"),
        ColumnDef("active_groups", "INTEGER"),
        ColumnDef("total_agents", "INTEGER"),
        ColumnDef("active_location_count", "INTEGER"),
        ColumnDef("current_phase", "TEXT"),
        ColumnDef("latest_event", "TEXT"),
        ColumnDef("latest_communications", "TEXT"),
    ]

    def __init__(
        self,
        agent_id_name_pairs: list[list[int | str]] | None = None,
        initial_locations: dict[str, str] | None = None,
        default_group_name: str = "Weekend Pixel Town Plan",
        map_manifest_path: str | None = None,
        map_id: str | None = None,
        movement_tiles_per_second: float = 8.0,
        movement_min_steps_per_trip: int = 3,
    ) -> None:
        super().__init__()
        self._movement_tiles_per_second = float(movement_tiles_per_second)
        self._movement_min_steps_per_trip = max(1, int(movement_min_steps_per_trip))
        self._map_manifest_path = self._resolve_manifest_path(map_manifest_path, map_id)
        self._map_manifest = _load_structured_file(self._map_manifest_path)
        self._map_root = self._map_manifest_path.parent
        self._map_id = str(self._map_manifest.get("map_id") or self._map_manifest_path.parent.name)
        self._tile_size = int(self._map_manifest.get("tile_size") or 32)
        self._locations_by_id: dict[str, dict[str, Any]] = {}
        self._location_aliases: dict[str, str] = {}
        self._interactions_by_id: dict[str, dict[str, Any]] = {}
        self._load_manifest_semantics()
        self._walkable_tiles, self._map_width, self._map_height = self._load_walkable_tiles()

        agent_id_name_pairs = agent_id_name_pairs or [
            [1, "Jiuwen Alice"],
            [2, "Jiuwen Bob"],
            [3, "Jiuwen Charlie"],
        ]
        self._agent_names = {
            int(agent_id): str(name) for agent_id, name in agent_id_name_pairs
        }
        self._locations: dict[int, str] = {}
        self._location_ids: dict[int, str] = {}
        self._tiles: dict[int, Tile] = {}
        self._movement_statuses: dict[int, str] = {}
        self._movement_targets: dict[int, str | None] = {}
        self._movement_paths: dict[int, list[Tile]] = {}
        self._movement_progress: dict[int, float] = {}
        for agent_id in self._agent_names:
            initial_location = (initial_locations or {}).get(str(agent_id))
            self._place_agent_at_location(agent_id, initial_location, fallback_index=agent_id)
        self._actions = {agent_id: "arriving" for agent_id in self._agent_names}
        self._statuses = {agent_id: "ready" for agent_id in self._agent_names}
        self._emotions = {agent_id: "curious" for agent_id in self._agent_names}
        self._mailboxes: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self._groups: dict[int, dict[str, Any]] = {
            1: {
                "name": default_group_name,
                "members": sorted(self._agent_names),
            }
        }
        self._total_messages_sent = 0
        self._step_communications: list[dict[str, Any]] = []
        self._step_counter = 0
        self._current_phase = "setup"
        self._latest_event = f"Agents arrive in {self._map_manifest.get('display_name') or self._map_id}."
        self._lock = asyncio.Lock()

    @staticmethod
    def _resolve_manifest_path(map_manifest_path: str | None, map_id: str | None = None) -> Path:
        if map_manifest_path:
            path = Path(map_manifest_path).expanduser()
            resolved = path if path.is_absolute() else (_repo_root() / path).resolve()
            if resolved.exists():
                return resolved
        requested_map_id = str(map_id or "the_ville").strip() or "the_ville"
        map_yaml = (_repo_root() / "custom" / "maps" / requested_map_id / "map.yaml").resolve()
        if map_yaml.exists():
            return map_yaml
        town_yaml = (_repo_root() / "custom" / "maps" / requested_map_id / "town.yaml").resolve()
        if town_yaml.exists():
            return town_yaml
        return (_repo_root() / "custom" / "maps" / "the_ville" / "map.yaml").resolve()

    def _load_manifest_semantics(self) -> None:
        locations = self._map_manifest.get("locations") or []
        if not isinstance(locations, list) or not locations:
            raise ValueError("Pixel town manifest requires a non-empty locations list")

        for item in locations:
            if not isinstance(item, dict):
                raise ValueError("Each pixel town location must be an object")
            location_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or location_id).strip()
            anchor = item.get("anchor_tile") or {}
            if not location_id or "x" not in anchor or "y" not in anchor:
                raise ValueError(f"Location requires id and anchor_tile: {item}")
            normalized = {
                **item,
                "id": location_id,
                "name": name,
                "anchor_tile": {
                    "x": int(anchor["x"]),
                    "y": int(anchor["y"]),
                },
                "scene_type": str(item.get("scene_type") or "").strip(),
                "bounds": self._normalize_bounds(item.get("bounds")),
                "aliases": [str(alias) for alias in item.get("aliases", []) or []],
                "interaction_ids": [
                    str(interaction_id)
                    for interaction_id in item.get("interaction_ids", []) or []
                ],
            }
            self._locations_by_id[location_id] = normalized
            for alias in [location_id, name, *normalized["aliases"]]:
                key = _normalize_key(alias)
                if key:
                    self._location_aliases[key] = location_id

        interactions = self._map_manifest.get("interactions") or []
        if not isinstance(interactions, list):
            raise ValueError("Pixel town manifest interactions must be a list")
        for item in interactions:
            if not isinstance(item, dict):
                raise ValueError("Each pixel town interaction must be an object")
            interaction_id = str(item.get("id") or "").strip()
            if not interaction_id:
                raise ValueError(f"Interaction requires id: {item}")
            allowed = item.get("allowed_location_ids") or []
            self._interactions_by_id[interaction_id] = {
                **item,
                "id": interaction_id,
                "name": str(item.get("name") or interaction_id),
                "description": str(item.get("description") or ""),
                "allowed_location_ids": [str(location_id) for location_id in allowed],
                "effects": item.get("effects") if isinstance(item.get("effects"), dict) else {},
            }

    @staticmethod
    def _normalize_bounds(raw: Any) -> dict[str, int] | None:
        if not isinstance(raw, dict):
            return None
        try:
            return {
                "x": int(raw["x"]),
                "y": int(raw["y"]),
                "w": int(raw["w"]),
                "h": int(raw["h"]),
            }
        except Exception:
            return None

    def _resolve_tiled_map_path(self) -> Path:
        raw = str(self._map_manifest.get("tiled_map_path") or "map.json")
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path
        return (self._map_root / path).resolve()

    def _load_walkable_tiles(self) -> tuple[set[Tile], int, int]:
        tiled_map_path = self._resolve_tiled_map_path()
        data = json.loads(tiled_map_path.read_text(encoding="utf-8"))
        width = int(data.get("width") or 0)
        height = int(data.get("height") or 0)
        collision_layer = next(
            (
                layer
                for layer in data.get("layers", []) or []
                if layer.get("name") == "Collisions" and layer.get("type") == "tilelayer"
            ),
            None,
        )
        if not collision_layer or not isinstance(collision_layer.get("data"), list):
            return {
                (x, y)
                for y in range(height)
                for x in range(width)
            }, width, height

        walkable: set[Tile] = set()
        for index, gid in enumerate(collision_layer["data"]):
            if int(gid or 0) == 0:
                walkable.add((index % width, index // width))
        return walkable, width, height

    def _resolve_location_id(self, value: Any) -> str | None:
        if value is None:
            return None
        return self._location_aliases.get(_normalize_key(value))

    def _location_tile(self, location_id: str) -> Tile:
        location = self._locations_by_id[location_id]
        anchor = location["anchor_tile"]
        return self._nearest_walkable_tile((int(anchor["x"]), int(anchor["y"])))

    def _nearest_walkable_tile(self, tile: Tile) -> Tile:
        if tile in self._walkable_tiles:
            return tile
        if not self._walkable_tiles:
            return tile
        best_tile = min(
            self._walkable_tiles,
            key=lambda item: abs(item[0] - tile[0]) + abs(item[1] - tile[1]),
        )
        return best_tile

    def _default_location_id(self, fallback_index: int = 0) -> str:
        spawn_points = self._map_manifest.get("spawn_points") or []
        if isinstance(spawn_points, list) and spawn_points:
            spawn = spawn_points[fallback_index % len(spawn_points)]
            if isinstance(spawn, dict):
                location_id = self._resolve_location_id(spawn.get("location_id"))
                if location_id is not None:
                    return location_id
        return next(iter(self._locations_by_id))

    def _place_agent_at_location(
        self,
        agent_id: int,
        location: Any,
        fallback_index: int = 0,
    ) -> str:
        location_id = self._resolve_location_id(location) or self._default_location_id(fallback_index)
        resolved = self._locations_by_id[location_id]
        self._location_ids[agent_id] = location_id
        self._locations[agent_id] = str(resolved["name"])
        self._tiles[agent_id] = self._location_tile(location_id)
        self._movement_statuses[agent_id] = "idle"
        self._movement_targets[agent_id] = None
        self._movement_paths[agent_id] = [self._tiles[agent_id]]
        self._movement_progress[agent_id] = 0.0
        return location_id

    def _neighbors(self, tile: Tile) -> list[Tile]:
        x, y = tile
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [
            item
            for item in candidates
            if 0 <= item[0] < self._map_width
            and 0 <= item[1] < self._map_height
            and item in self._walkable_tiles
        ]

    def _find_path(self, start: Tile, goal: Tile) -> list[Tile] | None:
        start = self._nearest_walkable_tile(start)
        goal = self._nearest_walkable_tile(goal)
        if start == goal:
            return [start]

        frontier: list[tuple[int, Tile]] = [(0, start)]
        came_from: dict[Tile, Tile | None] = {start: None}
        cost_so_far: dict[Tile, int] = {start: 0}

        while frontier:
            _, current = heapq.heappop(frontier)
            if current == goal:
                break
            for neighbor in self._neighbors(current):
                new_cost = cost_so_far[current] + 1
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    priority = new_cost + abs(goal[0] - neighbor[0]) + abs(goal[1] - neighbor[1])
                    heapq.heappush(frontier, (priority, neighbor))
                    came_from[neighbor] = current

        if goal not in came_from:
            return None

        path = [goal]
        current = goal
        while came_from[current] is not None:
            current = came_from[current]  # type: ignore[assignment]
            path.append(current)
        path.reverse()
        return path

    @classmethod
    def mcp_description(cls) -> str:
        return """PixelTownSocialEnv: replay-friendly social environment.

Stores per-agent location/action/status/emotion rows for pixel-town replay and
supports direct/group messages between agents.
"""

    @property
    def description(self) -> str:
        return (
            "A small pixel-town social environment with locations, agent actions, "
            "personal messages, group messages, and replay snapshots."
        )

    @tool(readonly=True, kind="observe")
    async def observe_agent(self, agent_id: int) -> dict[str, Any]:
        """Observe one agent's current state and unread messages."""
        async with self._lock:
            snapshot = self._snapshot_agent(agent_id)
            snapshot["known_locations"] = [
                self._public_location(location)
                for location in self._locations_by_id.values()
            ]
            snapshot["known_interactions"] = [
                self._public_interaction(interaction)
                for interaction in self._interactions_by_id.values()
            ]
            return snapshot

    @tool(readonly=True)
    async def list_locations(self) -> dict[str, Any]:
        """List all named map locations agents can move to."""
        async with self._lock:
            return {
                "map_id": self._map_id,
                "locations": [self._public_location(location) for location in self._locations_by_id.values()],
            }

    @tool(readonly=True)
    async def list_interactions(self, location_id: str | None = None) -> dict[str, Any]:
        """List interactions available globally or at a specific location."""
        async with self._lock:
            resolved_location_id = self._resolve_location_id(location_id) if location_id else None
            interactions = [
                self._public_interaction(interaction)
                for interaction in self._interactions_by_id.values()
                if resolved_location_id is None
                or not interaction["allowed_location_ids"]
                or resolved_location_id in interaction["allowed_location_ids"]
            ]
            return {
                "map_id": self._map_id,
                "location_id": resolved_location_id,
                "interactions": interactions,
            }

    @tool(readonly=True)
    async def receive_messages(self, agent_id: int) -> dict[str, Any]:
        """Read and clear one agent's mailbox."""
        async with self._lock:
            messages = list(self._mailboxes.get(agent_id, []))
            self._mailboxes[agent_id] = []
            return {"agent_id": agent_id, "messages": messages}

    async def add_agent(
        self,
        agent_id: int,
        name: str,
        location: str = "park",
    ) -> dict[str, Any]:
        """Register a new live agent so it appears in the next replay step."""
        async with self._lock:
            agent_id = int(agent_id)
            self._agent_names[agent_id] = str(name)
            self._place_agent_at_location(agent_id, location, fallback_index=agent_id)
            self._actions.setdefault(agent_id, "joined the town")
            self._statuses.setdefault(agent_id, "ready")
            self._emotions.setdefault(agent_id, "curious")
            self._mailboxes.setdefault(agent_id, [])
            group = self._groups.setdefault(
                1,
                {"name": "Town Coordination", "members": []},
            )
            members = {int(member_id) for member_id in group.get("members", [])}
            members.add(agent_id)
            group["members"] = sorted(members)
            self._latest_event = f"{name} joined the town."
            return self._snapshot_agent(agent_id)

    @tool(readonly=False)
    async def publish_event(
        self,
        event: str,
        severity: str = "info",
        broadcast: bool = True,
        group_id: int = 1,
    ) -> dict[str, Any]:
        """Publish a system-level world event that agents can observe and react to."""
        async with self._lock:
            event = str(event).strip()
            severity = str(severity or "info").strip().lower()
            if not event:
                return {"event": "", "severity": severity, "broadcast": False}

            self._latest_event = event
            if severity in {"emergency", "warning", "crisis", "disaster"}:
                self._current_phase = "emergency"

            recipient_count = 0
            if broadcast:
                group = self._groups.get(int(group_id))
                if group:
                    content = f"公共环境事件（{severity}）：{event}"
                    message = self._build_message(
                        "system_event",
                        0,
                        content,
                        group_id=int(group_id),
                    )
                    for member_id in group["members"]:
                        self._mailboxes[int(member_id)].append(message)
                    recipient_count = len(group["members"])
                    self._total_messages_sent += 1
                    self._record_communication(
                        message_type="system_event",
                        sender_id=0,
                        content=content,
                        group_id=int(group_id),
                        recipient_count=recipient_count,
                    )

            return {
                "event": event,
                "severity": severity,
                "phase": self._current_phase,
                "broadcast": bool(broadcast),
                "recipient_count": recipient_count,
            }

    @tool(readonly=False)
    async def move_agent(self, agent_id: int, location: str) -> dict[str, Any]:
        """Move an agent to a named manifest location using tile pathfinding."""
        async with self._lock:
            agent_id = int(agent_id)
            if agent_id not in self._agent_names:
                return {"ok": False, "error": "unknown_agent", "agent_id": agent_id}
            target_location_id = self._resolve_location_id(location)
            if target_location_id is None:
                return {
                    "ok": False,
                    "error": "unknown_location",
                    "agent_id": agent_id,
                    "location": location,
                    "known_locations": list(self._locations_by_id),
                }

            start = self._tiles.get(agent_id) or self._location_tile(self._location_ids[agent_id])
            goal = self._location_tile(target_location_id)
            path = self._find_path(start, goal)
            if path is None:
                return {
                    "ok": False,
                    "error": "unreachable",
                    "agent_id": agent_id,
                    "from_tile": {"x": start[0], "y": start[1]},
                    "to_location_id": target_location_id,
                    "to_tile": {"x": goal[0], "y": goal[1]},
                }

            self._movement_paths[agent_id] = path
            self._movement_progress[agent_id] = 0.0
            self._movement_targets[agent_id] = target_location_id
            target_name = self._locations_by_id[target_location_id]["name"]
            if len(path) <= 1:
                self._finish_movement(agent_id, target_location_id)
            else:
                self._movement_statuses[agent_id] = "moving"
                self._actions[agent_id] = f"moving to {target_name}"
                self._statuses[agent_id] = "moving"
                self._tiles[agent_id] = path[0]
            self._latest_event = f"{self._agent_names.get(agent_id, agent_id)} moving to {target_name}."
            return {
                "ok": True,
                "agent_id": agent_id,
                "location_id": target_location_id,
                "location": target_name,
                "path_length": len(path),
                "path": [{"x": x, "y": y} for x, y in path],
            }

    @tool(readonly=False)
    async def interact(
        self,
        agent_id: int,
        interaction_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform a location-scoped interaction from the map manifest."""
        async with self._lock:
            agent_id = int(agent_id)
            params = params or {}
            interaction = self._interactions_by_id.get(str(interaction_id))
            if interaction is None:
                return {
                    "ok": False,
                    "error": "unknown_interaction",
                    "interaction_id": interaction_id,
                    "known_interactions": list(self._interactions_by_id),
                }
            current_location_id = self._location_ids.get(agent_id)
            allowed = interaction.get("allowed_location_ids") or []
            if allowed and current_location_id not in allowed:
                return {
                    "ok": False,
                    "error": "interaction_not_available_here",
                    "agent_id": agent_id,
                    "interaction_id": interaction_id,
                    "current_location_id": current_location_id,
                    "allowed_location_ids": allowed,
                }

            effects = interaction.get("effects") or {}
            if action := effects.get("action"):
                self._actions[agent_id] = self._render_template(str(action), agent_id, params)
            if status := effects.get("status"):
                self._statuses[agent_id] = self._render_template(str(status), agent_id, params)
            if emotion := effects.get("emotion"):
                self._emotions[agent_id] = self._render_template(str(emotion), agent_id, params)
            if event := effects.get("latest_event"):
                self._latest_event = self._render_template(str(event), agent_id, params)
            else:
                self._latest_event = (
                    f"{self._agent_names.get(agent_id, agent_id)} used {interaction['name']}."
                )
            if group_message := effects.get("group_message"):
                group_id = int(effects.get("group_id") or 1)
                group = self._groups.get(group_id)
                if group:
                    content = self._render_template(str(group_message), agent_id, params)
                    message = self._build_message("group", agent_id, content, group_id=group_id)
                    for member_id in group["members"]:
                        self._mailboxes[int(member_id)].append(message)
                    self._total_messages_sent += 1
                    self._record_communication(
                        message_type="group",
                        sender_id=agent_id,
                        content=content,
                        group_id=group_id,
                        recipient_count=len(group["members"]),
                    )
            return {
                "ok": True,
                "agent_id": agent_id,
                "interaction_id": interaction["id"],
                "interaction": interaction["name"],
                "location_id": current_location_id,
                "effects": effects,
            }

    @tool(readonly=False)
    async def set_agent_action(
        self,
        agent_id: int,
        action: str,
        status: str = "active",
        emotion: str = "focused",
    ) -> dict[str, Any]:
        """Set replay-visible action/status/emotion for an agent."""
        async with self._lock:
            self._actions[agent_id] = action
            self._statuses[agent_id] = status
            self._emotions[agent_id] = emotion
            self._latest_event = f"{self._agent_names.get(agent_id, agent_id)}: {action}"
            return {
                "agent_id": agent_id,
                "action": action,
                "status": status,
                "emotion": emotion,
            }

    @tool(readonly=False)
    async def send_message(
        self,
        sender_id: int,
        receiver_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Send a direct message to another agent."""
        async with self._lock:
            message = self._build_message("direct", sender_id, content)
            self._mailboxes[receiver_id].append(message)
            self._total_messages_sent += 1
            self._record_communication(
                message_type="direct",
                sender_id=sender_id,
                content=content,
                receiver_id=receiver_id,
            )
            self._latest_event = (
                f"{self._agent_names.get(sender_id, sender_id)} messaged "
                f"{self._agent_names.get(receiver_id, receiver_id)}."
            )
            return {
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
            }

    @tool(readonly=False)
    async def send_group_message(
        self,
        sender_id: int,
        group_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Send a message to all members of a group."""
        async with self._lock:
            group = self._groups.get(group_id)
            if not group:
                return {"sender_id": sender_id, "group_id": group_id, "recipient_count": 0}
            message = self._build_message("group", sender_id, content, group_id=group_id)
            for member_id in group["members"]:
                self._mailboxes[int(member_id)].append(message)
            self._total_messages_sent += 1
            self._record_communication(
                message_type="group",
                sender_id=sender_id,
                content=content,
                group_id=group_id,
                recipient_count=len(group["members"]),
            )
            self._latest_event = (
                f"{self._agent_names.get(sender_id, sender_id)} posted to {group['name']}."
            )
            return {
                "sender_id": sender_id,
                "group_id": group_id,
                "content": content,
                "recipient_count": len(group["members"]),
            }

    async def apply_scripted_action(
        self,
        agent_id: int,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a full scripted action without routing through an LLM."""
        async with self._lock:
            if location := action.get("location"):
                self._place_agent_at_location(agent_id, location, fallback_index=agent_id)
            self._actions[agent_id] = str(action.get("action") or "waiting")
            self._statuses[agent_id] = str(action.get("status") or "active")
            self._emotions[agent_id] = str(action.get("emotion") or "focused")
            if phase := action.get("phase"):
                self._current_phase = str(phase)

            for direct in action.get("direct_messages", []) or []:
                receiver_id = int(direct["to"])
                content = str(direct["content"])
                self._mailboxes[receiver_id].append(
                    self._build_message("direct", agent_id, content)
                )
                self._total_messages_sent += 1
                self._record_communication(
                    message_type="direct",
                    sender_id=agent_id,
                    content=content,
                    receiver_id=receiver_id,
                )

            for group_msg in action.get("group_messages", []) or []:
                group_id = int(group_msg.get("group_id", 1))
                content = str(group_msg["content"])
                group = self._groups.get(group_id)
                if group:
                    message = self._build_message(
                        "group", agent_id, content, group_id=group_id
                    )
                    for member_id in group["members"]:
                        self._mailboxes[int(member_id)].append(message)
                    self._total_messages_sent += 1
                    self._record_communication(
                        message_type="group",
                        sender_id=agent_id,
                        content=content,
                        group_id=group_id,
                        recipient_count=len(group["members"]),
                    )

            self._latest_event = str(
                action.get("event")
                or f"{self._agent_names.get(agent_id, agent_id)}: {self._actions[agent_id]}"
            )
            return self._snapshot_agent(agent_id)

    async def load_replay_tail(
        self,
        db_path: str | Path,
        latest_step: int,
    ) -> dict[str, Any]:
        """Restore environment state from the latest replay rows without rerunning agents."""
        async with self._lock:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            try:
                columns = {
                    row["name"]
                    for row in conn.execute(
                        "PRAGMA table_info(pixel_town_social_agent_state)"
                    ).fetchall()
                }
                optional_columns = [
                    column
                    for column in (
                        "map_id",
                        "tile_x",
                        "tile_y",
                        "location_id",
                        "movement_status",
                        "target_location_id",
                        "path_json",
                    )
                    if column in columns
                ]
                selected_columns = [
                    "agent_id",
                    "name",
                    "location",
                    "action",
                    "status",
                    "emotion",
                    "last_message",
                    *optional_columns,
                ]
                agent_rows = conn.execute(
                    f"""
                    SELECT {", ".join(selected_columns)}
                    FROM pixel_town_social_agent_state
                    WHERE step = ?
                    """,
                    (latest_step,),
                ).fetchall()
                env_row = conn.execute(
                    """
                    SELECT total_messages_sent, current_phase, latest_event, latest_communications
                    FROM pixel_town_social_env_state
                    WHERE step = ?
                    """,
                    (latest_step,),
                ).fetchone()
            finally:
                conn.close()

            for row in agent_rows:
                agent_id = int(row["agent_id"])
                self._agent_names[agent_id] = str(
                    row["name"] or self._agent_names.get(agent_id, f"Agent {agent_id}")
                )
                self._locations[agent_id] = str(row["location"] or "Town square")
                location_id = (
                    str(row["location_id"])
                    if "location_id" in row.keys() and row["location_id"]
                    else self._resolve_location_id(row["location"])
                )
                if location_id is None:
                    location_id = self._default_location_id(agent_id)
                self._location_ids[agent_id] = location_id
                if "tile_x" in row.keys() and "tile_y" in row.keys() and row["tile_x"] is not None and row["tile_y"] is not None:
                    self._tiles[agent_id] = (int(row["tile_x"]), int(row["tile_y"]))
                else:
                    self._tiles[agent_id] = self._location_tile(location_id)
                self._movement_statuses[agent_id] = (
                    str(row["movement_status"])
                    if "movement_status" in row.keys() and row["movement_status"]
                    else "idle"
                )
                self._movement_targets[agent_id] = (
                    str(row["target_location_id"])
                    if "target_location_id" in row.keys() and row["target_location_id"]
                    else None
                )
                self._movement_paths[agent_id] = [self._tiles[agent_id]]
                self._movement_progress[agent_id] = 0.0
                self._actions[agent_id] = str(row["action"] or "waiting")
                self._statuses[agent_id] = str(row["status"] or "ready")
                self._emotions[agent_id] = str(row["emotion"] or "neutral")
                last_message = str(row["last_message"] or "")
                self._mailboxes[agent_id] = (
                    [
                        self._build_message(
                            "restored",
                            0,
                            last_message,
                            group_id=1,
                        )
                    ]
                    if last_message
                    else []
                )

            if env_row is not None:
                self._total_messages_sent = int(env_row["total_messages_sent"] or 0)
                self._current_phase = str(env_row["current_phase"] or "setup")
                self._latest_event = str(env_row["latest_event"] or "")
                try:
                    communications = json.loads(
                        env_row["latest_communications"] or "[]"
                    )
                except json.JSONDecodeError:
                    communications = []
                self._step_communications = (
                    communications if isinstance(communications, list) else []
                )

            self._step_counter = int(latest_step) + 1
            return {
                "restored": True,
                "latest_step": latest_step,
                "agent_count": len(agent_rows),
                "current_phase": self._current_phase,
            }

    async def step(self, tick: int, t: datetime) -> None:
        async with self._lock:
            self.t = t
            self._advance_movements(tick)
            records = [self._snapshot_agent(agent_id) for agent_id in sorted(self._agent_names)]
            active_locations = {record["location"] for record in records}
            env_record = {
                "total_messages_sent": self._total_messages_sent,
                "active_groups": len(self._groups),
                "total_agents": len(self._agent_names),
                "active_location_count": len(active_locations),
                "current_phase": self._current_phase,
                "latest_event": self._latest_event,
                "latest_communications": json.dumps(self._step_communications),
            }
            self._step_communications = []

        await self._write_agent_state_batch(step=self._step_counter, t=t, records=records)
        await self._write_env_state(step=self._step_counter, t=t, **env_record)
        self._step_counter += 1

    def _advance_movements(self, tick: int) -> None:
        del tick
        for agent_id, status in list(self._movement_statuses.items()):
            if status != "moving":
                continue
            path = self._movement_paths.get(agent_id) or []
            target_location_id = self._movement_targets.get(agent_id)
            if not path or target_location_id is None:
                self._movement_statuses[agent_id] = "idle"
                continue
            distance = max(1, len(path) - 1)
            tiles_this_step = max(1.0, self._movement_tiles_per_second)
            if distance > 1 and self._movement_min_steps_per_trip > 1:
                tiles_this_step = min(
                    tiles_this_step,
                    max(1.0, distance / float(self._movement_min_steps_per_trip)),
                )
            self._movement_progress[agent_id] = (
                self._movement_progress.get(agent_id, 0.0) + tiles_this_step
            )
            next_index = min(int(self._movement_progress[agent_id]), len(path) - 1)
            self._tiles[agent_id] = path[next_index]
            if next_index >= len(path) - 1:
                self._finish_movement(agent_id, target_location_id)

    def _finish_movement(self, agent_id: int, location_id: str) -> None:
        location = self._locations_by_id[location_id]
        self._location_ids[agent_id] = location_id
        self._locations[agent_id] = str(location["name"])
        self._tiles[agent_id] = self._location_tile(location_id)
        self._movement_statuses[agent_id] = "idle"
        self._movement_targets[agent_id] = None
        self._movement_paths[agent_id] = [self._tiles[agent_id]]
        self._movement_progress[agent_id] = 0.0
        self._statuses[agent_id] = "active"
        self._actions[agent_id] = f"arrived at {location['name']}"

    def _build_message(
        self,
        message_type: str,
        sender_id: int,
        content: str,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        message = {
            "type": message_type,
            "sender_id": sender_id,
            "sender_name": self._display_name(sender_id),
            "content": content,
            "timestamp": self.t.isoformat() if hasattr(self, "t") else "",
        }
        if group_id is not None:
            message["group_id"] = group_id
            message["group_name"] = self._groups.get(group_id, {}).get("name", f"Group {group_id}")
        return message

    def _record_communication(
        self,
        message_type: str,
        sender_id: int,
        content: str,
        receiver_id: int | None = None,
        group_id: int | None = None,
        recipient_count: int | None = None,
    ) -> None:
        communication = {
            "type": message_type,
            "sender_id": sender_id,
            "sender_name": self._display_name(sender_id),
            "content": content,
        }
        if receiver_id is not None:
            communication["receiver_id"] = receiver_id
            communication["receiver_name"] = self._agent_names.get(
                receiver_id, f"Agent {receiver_id}"
            )
        if group_id is not None:
            communication["group_id"] = group_id
            communication["group_name"] = self._groups.get(group_id, {}).get(
                "name", f"Group {group_id}"
            )
        if recipient_count is not None:
            communication["recipient_count"] = recipient_count
        self._step_communications.append(communication)

    def _display_name(self, agent_id: int) -> str:
        if int(agent_id) == 0:
            return "Town system"
        return self._agent_names.get(agent_id, f"Agent {agent_id}")

    def _public_location(self, location: dict[str, Any]) -> dict[str, Any]:
        location_id = str(location["id"])
        tile = self._location_tile(location_id)
        public = {
            "id": location_id,
            "name": location["name"],
            "aliases": location.get("aliases", []),
            "anchor_tile": {"x": tile[0], "y": tile[1]},
            "interaction_ids": location.get("interaction_ids", []),
        }
        if location.get("scene_type"):
            public["scene_type"] = location["scene_type"]
        if location.get("bounds"):
            public["bounds"] = location["bounds"]
        if location.get("source_address"):
            public["source_address"] = location["source_address"]
        if location.get("source_object"):
            public["source_object"] = location["source_object"]
        return public

    def _public_interaction(self, interaction: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": interaction["id"],
            "name": interaction["name"],
            "description": interaction.get("description", ""),
            "allowed_location_ids": interaction.get("allowed_location_ids", []),
        }

    def _available_interactions(self, location_id: str | None) -> list[dict[str, Any]]:
        location_interaction_ids = (
            self._locations_by_id.get(location_id or "", {}).get("interaction_ids", [])
        )
        interactions = []
        for interaction in self._interactions_by_id.values():
            allowed = interaction.get("allowed_location_ids") or []
            if interaction["id"] in location_interaction_ids or not allowed or location_id in allowed:
                interactions.append(self._public_interaction(interaction))
        return interactions

    def _render_template(
        self,
        template: str,
        agent_id: int,
        params: dict[str, Any],
    ) -> str:
        values = {
            "agent_id": agent_id,
            "agent_name": self._agent_names.get(agent_id, f"Agent {agent_id}"),
            "location": self._locations.get(agent_id, ""),
            **{str(key): value for key, value in params.items()},
        }
        try:
            return template.format(**values)
        except Exception:
            return template

    def _snapshot_agent(self, agent_id: int) -> dict[str, Any]:
        messages = self._mailboxes.get(agent_id, [])
        last_message = messages[-1]["content"] if messages else ""
        tile = self._tiles.get(agent_id, (0, 0))
        location_id = self._location_ids.get(agent_id)
        path = self._movement_paths.get(agent_id) or [tile]
        available_interactions = self._available_interactions(location_id)
        return {
            "agent_id": agent_id,
            "name": self._agent_names.get(agent_id, f"Agent {agent_id}"),
            "location": self._locations.get(agent_id, "Town square"),
            "action": self._actions.get(agent_id, "waiting"),
            "status": self._statuses.get(agent_id, "ready"),
            "emotion": self._emotions.get(agent_id, "neutral"),
            "message_count": len(messages),
            "last_message": last_message,
            "recent_messages": list(messages[-5:]),
            "current_phase": self._current_phase,
            "latest_event": self._latest_event,
            "groups": self._groups,
            "map_id": self._map_id,
            "tile_x": tile[0],
            "tile_y": tile[1],
            "location_id": location_id,
            "movement_status": self._movement_statuses.get(agent_id, "idle"),
            "target_location_id": self._movement_targets.get(agent_id),
            "path_json": json.dumps([{"x": x, "y": y} for x, y in path]),
            "available_interactions_json": json.dumps(available_interactions, ensure_ascii=False),
        }

    def _dump_state(self) -> dict[str, Any]:
        return {
            "map_manifest_path": str(self._map_manifest_path),
            "agent_names": self._agent_names,
            "locations": self._locations,
            "location_ids": self._location_ids,
            "tiles": self._tiles,
            "movement_statuses": self._movement_statuses,
            "movement_targets": self._movement_targets,
            "movement_paths": self._movement_paths,
            "movement_progress": self._movement_progress,
            "actions": self._actions,
            "statuses": self._statuses,
            "emotions": self._emotions,
            "mailboxes": self._mailboxes,
            "groups": self._groups,
            "total_messages_sent": self._total_messages_sent,
            "step_communications": self._step_communications,
            "step_counter": self._step_counter,
            "current_phase": self._current_phase,
            "latest_event": self._latest_event,
        }

    def _load_state(self, state: dict[str, Any]) -> None:
        self._agent_names = {int(k): v for k, v in state.get("agent_names", {}).items()}
        self._locations = {int(k): v for k, v in state.get("locations", {}).items()}
        self._location_ids = {int(k): v for k, v in state.get("location_ids", {}).items()}
        self._tiles = {
            int(k): tuple(v)  # type: ignore[misc]
            for k, v in state.get("tiles", {}).items()
        }
        self._movement_statuses = {
            int(k): v for k, v in state.get("movement_statuses", {}).items()
        }
        self._movement_targets = {
            int(k): v for k, v in state.get("movement_targets", {}).items()
        }
        self._movement_paths = {
            int(k): [tuple(tile) for tile in path]  # type: ignore[misc]
            for k, path in state.get("movement_paths", {}).items()
        }
        self._movement_progress = {
            int(k): float(v) for k, v in state.get("movement_progress", {}).items()
        }
        self._actions = {int(k): v for k, v in state.get("actions", {}).items()}
        self._statuses = {int(k): v for k, v in state.get("statuses", {}).items()}
        self._emotions = {int(k): v for k, v in state.get("emotions", {}).items()}
        self._mailboxes = defaultdict(
            list, {int(k): v for k, v in state.get("mailboxes", {}).items()}
        )
        self._groups = {int(k): v for k, v in state.get("groups", {}).items()}
        self._total_messages_sent = int(state.get("total_messages_sent", 0))
        step_communications = state.get("step_communications")
        self._step_communications = (
            step_communications if isinstance(step_communications, list) else []
        )
        self._step_counter = int(state.get("step_counter", 0))
        self._current_phase = str(state.get("current_phase", "setup"))
        self._latest_event = str(state.get("latest_event", ""))
        for agent_id in self._agent_names:
            location_id = self._location_ids.get(agent_id) or self._resolve_location_id(
                self._locations.get(agent_id)
            )
            if location_id is None:
                location_id = self._default_location_id(agent_id)
            location = self._locations_by_id[location_id]
            self._location_ids[agent_id] = location_id
            self._locations[agent_id] = str(location["name"])
            self._tiles.setdefault(agent_id, self._location_tile(location_id))
            self._movement_statuses.setdefault(agent_id, "idle")
            self._movement_targets.setdefault(agent_id, None)
            self._movement_paths.setdefault(agent_id, [self._tiles[agent_id]])
            self._movement_progress.setdefault(agent_id, 0.0)

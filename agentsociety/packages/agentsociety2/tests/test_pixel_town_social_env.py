from __future__ import annotations

import asyncio
from datetime import datetime
import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_PATH = _REPO_ROOT / "custom" / "envs" / "pixel_town_social_env.py"
_SPEC = importlib.util.spec_from_file_location("pixel_town_social_env", _ENV_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
PixelTownSocialEnv = _MODULE.PixelTownSocialEnv


def _write_map_package(tmp_path: Path, *, unreachable: bool = False) -> Path:
    width = 5
    height = 5
    collisions = [0] * (width * height)
    if unreachable:
        for y in range(height):
            collisions[y * width + 2] = 1

    (tmp_path / "map.json").write_text(
        json.dumps(
            {
                "type": "map",
                "width": width,
                "height": height,
                "tilewidth": 32,
                "tileheight": 32,
                "tilesets": [],
                "layers": [
                    {
                        "name": "Ground",
                        "type": "tilelayer",
                        "data": [0] * (width * height),
                    },
                    {
                        "name": "Collisions",
                        "type": "tilelayer",
                        "data": collisions,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "town.json"
    manifest.write_text(
        json.dumps(
            {
                "map_id": "test_town",
                "display_name": "Test Town",
                "tiled_map_path": "map.json",
                "tile_size": 32,
                "locations": [
                    {
                        "id": "park",
                        "name": "公园",
                        "aliases": ["Park", "公园"],
                        "anchor_tile": {"x": 0, "y": 0},
                        "interaction_ids": ["meet_friend"],
                    },
                    {
                        "id": "cafe",
                        "name": "咖啡馆",
                        "aliases": ["cafe"],
                        "anchor_tile": {"x": 4, "y": 0},
                        "interaction_ids": ["chat_over_coffee"],
                    },
                ],
                "interactions": [
                    {
                        "id": "meet_friend",
                        "name": "见朋友",
                        "description": "meet at park",
                        "allowed_location_ids": ["park"],
                        "effects": {
                            "action": "{agent_name} met a friend {message}",
                            "status": "active",
                            "emotion": "focused",
                            "latest_event": "{agent_name} met a friend",
                        },
                    },
                    {
                        "id": "chat_over_coffee",
                        "name": "咖啡聊天",
                        "description": "chat at cafe",
                        "allowed_location_ids": ["cafe"],
                        "effects": {
                            "action": "{agent_name} chatted at the cafe",
                            "status": "active",
                            "emotion": "focused",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_pixel_town_alias_movement_and_replay_fields(tmp_path: Path) -> None:
    async def scenario() -> None:
        manifest = _write_map_package(tmp_path)
        env = PixelTownSocialEnv(
            agent_id_name_pairs=[[1, "Alice"]],
            initial_locations={"1": "Park"},
            map_manifest_path=str(manifest),
            movement_tiles_per_second=8,
        )

        initial = await env.observe_agent(1)
        assert initial["location_id"] == "park"
        assert initial["tile_x"] == 0
        assert initial["tile_y"] == 0
        assert initial["movement_status"] == "idle"
        assert json.loads(initial["available_interactions_json"])[0]["id"] == "meet_friend"

        move = await env.move_agent(1, "咖啡馆")
        assert move["ok"] is True
        assert move["path_length"] == 5

        moving = await env.observe_agent(1)
        assert moving["movement_status"] == "moving"
        assert moving["target_location_id"] == "cafe"

        await env.step(10, datetime(2026, 5, 9, 12, 0, 0))
        still_moving = await env.observe_agent(1)
        assert still_moving["movement_status"] == "moving"
        assert still_moving["tile_x"] == 1
        assert still_moving["tile_y"] == 0

        await env.step(10, datetime(2026, 5, 9, 12, 1, 0))
        await env.step(10, datetime(2026, 5, 9, 12, 2, 0))
        arrived = await env.observe_agent(1)
        assert arrived["location_id"] == "cafe"
        assert arrived["location"] == "咖啡馆"
        assert arrived["movement_status"] == "idle"
        assert arrived["tile_x"] == 4
        assert arrived["tile_y"] == 0
        assert json.loads(arrived["path_json"]) == [{"x": 4, "y": 0}]

    asyncio.run(scenario())


def test_pixel_town_unreachable_move_does_not_change_position(tmp_path: Path) -> None:
    async def scenario() -> None:
        manifest = _write_map_package(tmp_path, unreachable=True)
        env = PixelTownSocialEnv(
            agent_id_name_pairs=[[1, "Alice"]],
            initial_locations={"1": "公园"},
            map_manifest_path=str(manifest),
        )

        move = await env.move_agent(1, "cafe")
        assert move["ok"] is False
        assert move["error"] == "unreachable"

        observed = await env.observe_agent(1)
        assert observed["location_id"] == "park"
        assert observed["movement_status"] == "idle"
        assert observed["tile_x"] == 0
        assert observed["tile_y"] == 0

    asyncio.run(scenario())


def test_pixel_town_interactions_are_location_scoped(tmp_path: Path) -> None:
    async def scenario() -> None:
        manifest = _write_map_package(tmp_path)
        env = PixelTownSocialEnv(
            agent_id_name_pairs=[[1, "Alice"]],
            initial_locations={"1": "公园"},
            map_manifest_path=str(manifest),
            movement_tiles_per_second=10,
        )

        unavailable = await env.interact(1, "chat_over_coffee")
        assert unavailable["ok"] is False
        assert unavailable["error"] == "interaction_not_available_here"

        meet = await env.interact(1, "meet_friend", {"message": "hello"})
        assert meet["ok"] is True
        observed = await env.observe_agent(1)
        assert observed["action"] == "Alice met a friend hello"
        assert observed["status"] == "active"
        assert observed["emotion"] == "focused"

        assert (await env.move_agent(1, "cafe"))["ok"] is True
        await env.step(1, datetime(2026, 5, 9, 12, 0, 0))
        await env.step(1, datetime(2026, 5, 9, 12, 1, 0))
        await env.step(1, datetime(2026, 5, 9, 12, 2, 0))
        chat = await env.interact(1, "chat_over_coffee")
        assert chat["ok"] is True
        observed = await env.observe_agent(1)
        assert observed["action"] == "Alice chatted at the cafe"

    asyncio.run(scenario())


def test_default_manifest_binds_required_real_scenes() -> None:
    async def scenario() -> None:
        env = PixelTownSocialEnv(
            agent_id_name_pairs=[[1, "Alice"]],
            initial_locations={"1": "park"},
            movement_tiles_per_second=1000,
        )

        locations = await env.list_locations()
        by_id = {location["id"]: location for location in locations["locations"]}
        for location_id in ("home", "school", "library", "cafe", "park", "supply_store", "market", "pharmacy", "pub", "dorm"):
            assert location_id in by_id
            assert by_id[location_id]["bounds"]["w"] >= 4
            assert by_id[location_id]["scene_type"]
            assert by_id[location_id]["source_address"].startswith("the Ville:")

        removed_move = await env.move_agent(1, "prison")
        assert removed_move["ok"] is False
        assert removed_move["error"] == "unknown_location"

        cafe_move = await env.move_agent(1, "cafe")
        assert cafe_move["ok"] is True
        assert cafe_move["path_length"] > 1
        await env.step(1, datetime(2026, 5, 9, 12, 0, 0))
        still_moving = await env.observe_agent(1)
        assert still_moving["movement_status"] == "moving"
        await env.step(1, datetime(2026, 5, 9, 12, 1, 0))
        await env.step(1, datetime(2026, 5, 9, 12, 2, 0))
        cafe_action = await env.interact(1, "chat_over_coffee")
        assert cafe_action["ok"] is True

    asyncio.run(scenario())

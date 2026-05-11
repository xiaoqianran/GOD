from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from agentsociety2.storage import ColumnDef, ReplayWriter, TableSchema


def test_replay_writer_adds_new_columns_to_existing_dynamic_table(tmp_path: Path) -> None:
    asyncio.run(_replay_writer_adds_new_columns_to_existing_dynamic_table(tmp_path))


async def _replay_writer_adds_new_columns_to_existing_dynamic_table(tmp_path: Path) -> None:
    db_path = tmp_path / "sqlite.db"
    table_v1 = TableSchema(
        name="pixel_town_social_agent_state",
        columns=[
            ColumnDef("agent_id", "INTEGER", nullable=False),
            ColumnDef("step", "INTEGER", nullable=False),
            ColumnDef("location", "TEXT"),
        ],
        primary_key=["agent_id", "step"],
    )
    writer = ReplayWriter(db_path)
    await writer.init()
    await writer.register_table(table_v1)
    await writer.write(
        "pixel_town_social_agent_state",
        {"agent_id": 1, "step": 0, "location": "Town square"},
    )
    await writer.close()

    table_v2 = TableSchema(
        name="pixel_town_social_agent_state",
        columns=[
            *table_v1.columns,
            ColumnDef("map_id", "TEXT"),
            ColumnDef("tile_x", "INTEGER"),
            ColumnDef("tile_y", "INTEGER"),
        ],
        primary_key=["agent_id", "step"],
    )
    writer = ReplayWriter(db_path)
    await writer.init()
    await writer.register_table(table_v2)
    await writer.write(
        "pixel_town_social_agent_state",
        {
            "agent_id": 1,
            "step": 1,
            "location": "工具棚",
            "map_id": "the_ville",
            "tile_x": 56,
            "tile_y": 64,
        },
    )
    await writer.close()

    conn = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(pixel_town_social_agent_state)"
            ).fetchall()
        }
        row = conn.execute(
            """
            SELECT map_id, tile_x, tile_y
            FROM pixel_town_social_agent_state
            WHERE agent_id = 1 AND step = 1
            """
        ).fetchone()
    finally:
        conn.close()

    assert {"map_id", "tile_x", "tile_y"}.issubset(columns)
    assert row == ("the_ville", 56, 64)

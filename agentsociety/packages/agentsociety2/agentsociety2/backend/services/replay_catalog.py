"""Replay metadata catalog access helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import MetaData, Table, inspect as sa_inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from agentsociety2.storage.replay_metadata import (
    COLUMN_CATALOG_TABLE,
    DATASET_CATALOG_TABLE,
)

_REQUEST_CATALOG_CACHE_KEY = "__replay_dataset_catalog"
_REQUEST_REFLECTION_CACHE_KEY = "__replay_reflected_tables"
_PROCESS_CACHE_LOCK = asyncio.Lock()
_DATASET_CATALOG_CACHE: dict[tuple[str, int], List[Dict[str, Any]]] = {}
_REFLECTED_TABLE_CACHE: dict[tuple[str, int, str], Table] = {}


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _loads_json(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return default


def _get_session_db_cache_key(session: AsyncSession) -> tuple[str, int]:
    db_path = session.info.get("replay_db_path")
    if not db_path:
        bind = session.bind
        database = getattr(getattr(bind, "url", None), "database", None)
        if database:
            db_path = str(Path(database).resolve())
    if not db_path:
        raise RuntimeError("Replay session is missing replay_db_path metadata")

    mtime_ns = session.info.get("replay_db_mtime_ns")
    if mtime_ns is None:
        try:
            mtime_ns = Path(str(db_path)).stat().st_mtime_ns
        except FileNotFoundError:
            mtime_ns = 0
    return (str(db_path), int(mtime_ns))


def _get_column_map(dataset: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {column["column_name"]: column for column in dataset.get("columns", [])}


def _get_column_names(dataset: Dict[str, Any]) -> List[str]:
    return [column["column_name"] for column in dataset.get("columns", [])]


def _normalize_dataset_value(column: Optional[Dict[str, Any]], value: Any) -> Any:
    if value is None:
        return None

    sqlite_type = str((column or {}).get("sqlite_type") or "").upper()
    if sqlite_type == "JSON":
        return jsonable_encoder(_loads_json(value, value))

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="ignore")
    return jsonable_encoder(value)


def normalize_dataset_row(dataset: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw dataset row into a JSON-safe dict."""

    column_map = _get_column_map(dataset)
    return {
        key: _normalize_dataset_value(column_map.get(key), value)
        for key, value in row.items()
    }


def _validate_selected_columns(
    dataset: Dict[str, Any],
    columns: Optional[List[str]],
) -> List[str]:
    available = _get_column_names(dataset)
    available_set = set(available)
    selected = columns or available
    if not selected:
        raise HTTPException(
            status_code=500,
            detail=f"Dataset '{dataset['dataset_id']}' has no column metadata",
        )

    invalid = [column for column in selected if column not in available_set]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Dataset '{dataset['dataset_id']}' received unknown columns: "
                f"{invalid}"
            ),
        )
    return selected


def _validate_order_columns(
    dataset: Dict[str, Any],
    order_by: Optional[str],
) -> List[str]:
    available = set(_get_column_names(dataset))
    order_columns = [order_by] if order_by else list(dataset.get("default_order") or [])
    if not order_columns:
        raise HTTPException(
            status_code=500,
            detail=f"Dataset '{dataset['dataset_id']}' is missing default_order metadata",
        )
    invalid = [column for column in order_columns if column not in available]
    if invalid:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Dataset '{dataset['dataset_id']}' references unknown order column(s) "
                f"{invalid}"
            ),
        )
    return order_columns


def _build_filter_clauses(
    dataset: Dict[str, Any],
    *,
    step: Optional[int] = None,
    entity_id: Optional[int] = None,
    start_step: Optional[int] = None,
    end_step: Optional[int] = None,
    max_step: Optional[int] = None,
) -> tuple[List[str], Dict[str, Any]]:
    available = set(_get_column_names(dataset))
    step_key = dataset.get("step_key")
    entity_key = dataset.get("entity_key")
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if entity_id is not None:
        if not entity_key or entity_key not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{dataset['dataset_id']}' does not support entity_id filtering",
            )
        clauses.append(f"{_quote_identifier(entity_key)} = :entity_id")
        params["entity_id"] = entity_id

    if step is not None:
        if not step_key or step_key not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{dataset['dataset_id']}' does not support step filtering",
            )
        clauses.append(f"{_quote_identifier(step_key)} = :step")
        params["step"] = step
        return clauses, params

    if start_step is not None:
        if not step_key or step_key not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{dataset['dataset_id']}' does not support step filtering",
            )
        clauses.append(f"{_quote_identifier(step_key)} >= :start_step")
        params["start_step"] = start_step

    if end_step is not None:
        if not step_key or step_key not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{dataset['dataset_id']}' does not support step filtering",
            )
        clauses.append(f"{_quote_identifier(step_key)} <= :end_step")
        params["end_step"] = end_step

    if max_step is not None:
        if not step_key or step_key not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset '{dataset['dataset_id']}' does not support step filtering",
            )
        clauses.append(f"{_quote_identifier(step_key)} <= :max_step")
        params["max_step"] = max_step

    return clauses, params


def _build_select_sql(
    dataset: Dict[str, Any],
    *,
    selected_columns: List[str],
    where_clauses: List[str],
    order_by: Optional[str],
    desc: bool,
    latest_per_entity: bool,
) -> tuple[str, str, Dict[str, Any]]:
    quoted_name = _quote_identifier(dataset["table_name"])
    select_columns_sql = ", ".join(_quote_identifier(column) for column in selected_columns)
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    order_columns = _validate_order_columns(dataset, order_by)
    entity_key = dataset.get("entity_key")
    step_key = dataset.get("step_key")

    if latest_per_entity:
        if not entity_key or not step_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Dataset '{dataset['dataset_id']}' does not support latest_per_entity"
                ),
            )
        inner_sql = (
            f"SELECT {select_columns_sql}, "
            f"ROW_NUMBER() OVER (PARTITION BY {_quote_identifier(entity_key)} "
            f"ORDER BY {_quote_identifier(step_key)} DESC) AS __row_num "
            f"FROM {quoted_name}{where_sql}"
        )
        from_sql = f"FROM ({inner_sql}) AS filtered WHERE __row_num = 1"
        order_sql = (
            f" ORDER BY {_quote_identifier(entity_key)} {'DESC' if desc else 'ASC'}"
        )
        return select_columns_sql, from_sql, {"order_sql": order_sql}

    order_sql = ", ".join(
        f"{_quote_identifier(column)} {'DESC' if desc else 'ASC'}"
        for column in order_columns
    )
    from_sql = f"FROM {quoted_name}{where_sql}"
    return select_columns_sql, from_sql, {"order_sql": f" ORDER BY {order_sql}"}


async def ensure_replay_catalog_exists(session: AsyncSession) -> None:
    """Require metadata catalog tables to exist in the replay database."""

    def _get_tables(sync_session):
        return set(sa_inspect(sync_session.connection()).get_table_names())

    table_names = await session.run_sync(_get_tables)
    required = {DATASET_CATALOG_TABLE, COLUMN_CATALOG_TABLE}
    missing = required - table_names
    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Replay metadata catalog is missing. "
                f"Expected tables: {sorted(required)}; missing: {sorted(missing)}"
            ),
        )


async def load_dataset_catalog(session: AsyncSession) -> List[Dict[str, Any]]:
    """Load all replay datasets with column metadata."""

    cached = session.info.get(_REQUEST_CATALOG_CACHE_KEY)
    if cached is not None:
        return cached

    cache_key = _get_session_db_cache_key(session)
    async with _PROCESS_CACHE_LOCK:
        process_cached = _DATASET_CATALOG_CACHE.get(cache_key)
    if process_cached is not None:
        session.info[_REQUEST_CATALOG_CACHE_KEY] = process_cached
        return process_cached

    await ensure_replay_catalog_exists(session)
    dataset_result = await session.execute(
        text(
            f"SELECT dataset_id, table_name, module_name, kind, title, description, "
            f"entity_key, step_key, time_key, default_order_json, capabilities_json, version, created_at "
            f"FROM {DATASET_CATALOG_TABLE} ORDER BY dataset_id"
        )
    )
    datasets: Dict[str, Dict[str, Any]] = {}
    for row in dataset_result.all():
        item = dict(row._mapping)
        item["default_order"] = _loads_json(item.pop("default_order_json", None), [])
        item["capabilities"] = _loads_json(item.pop("capabilities_json", None), [])
        item["columns"] = []
        datasets[item["dataset_id"]] = item

    column_result = await session.execute(
        text(
            f"SELECT dataset_id, column_name, sqlite_type, logical_type, analysis_role, title, description, "
            f"unit, enum_json, example_json, nullable, tags_json "
            f"FROM {COLUMN_CATALOG_TABLE} ORDER BY dataset_id, column_name"
        )
    )
    for row in column_result.all():
        item = dict(row._mapping)
        dataset_id = item.pop("dataset_id")
        item["enum_values"] = _loads_json(item.pop("enum_json", None), None)
        item["example"] = _loads_json(item.pop("example_json", None), None)
        item["tags"] = _loads_json(item.pop("tags_json", None), [])
        item["nullable"] = bool(item["nullable"])
        if dataset_id in datasets:
            datasets[dataset_id]["columns"].append(item)

    catalog = list(datasets.values())
    session.info[_REQUEST_CATALOG_CACHE_KEY] = catalog
    async with _PROCESS_CACHE_LOCK:
        _DATASET_CATALOG_CACHE[cache_key] = catalog
    return catalog


async def get_dataset_by_id(session: AsyncSession, dataset_id: str) -> Dict[str, Any]:
    datasets = await load_dataset_catalog(session)
    for dataset in datasets:
        if dataset["dataset_id"] == dataset_id:
            return dataset
    raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")


async def find_dataset_by_capability(
    session: AsyncSession,
    capability: str,
    *,
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    datasets = await load_dataset_catalog(session)
    matches = []
    for dataset in datasets:
        if capability not in dataset.get("capabilities", []):
            continue
        if kind is not None and dataset.get("kind") != kind:
            continue
        matches.append(dataset)
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"No replay dataset found for capability '{capability}'",
        )
    matches.sort(key=lambda item: item["dataset_id"])
    return matches[0]


async def reflect_dataset_table(session: AsyncSession, dataset: Dict[str, Any]) -> Table:
    table_name = dataset["table_name"]
    request_cache = session.info.setdefault(_REQUEST_REFLECTION_CACHE_KEY, {})
    if table_name in request_cache:
        return request_cache[table_name]

    cache_key = (*_get_session_db_cache_key(session), table_name)
    async with _PROCESS_CACHE_LOCK:
        process_cached = _REFLECTED_TABLE_CACHE.get(cache_key)
    if process_cached is not None:
        request_cache[table_name] = process_cached
        return process_cached

    def _do(sync_session):
        conn = sync_session.connection()
        return Table(table_name, MetaData(), autoload_with=conn)

    table = await session.run_sync(_do)
    request_cache[table_name] = table
    async with _PROCESS_CACHE_LOCK:
        _REFLECTED_TABLE_CACHE[cache_key] = table
    return table


async def fetch_dataset_rows(
    session: AsyncSession,
    dataset: Dict[str, Any],
    *,
    order_by: Optional[str] = None,
    desc: bool = False,
    step: Optional[int] = None,
    entity_id: Optional[int] = None,
    start_step: Optional[int] = None,
    end_step: Optional[int] = None,
    max_step: Optional[int] = None,
    columns: Optional[List[str]] = None,
    latest_per_entity: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fetch dataset rows with metadata-driven filtering and JSON-safe values."""

    selected_columns = _validate_selected_columns(dataset, columns)
    where_clauses, params = _build_filter_clauses(
        dataset,
        step=step,
        entity_id=entity_id,
        start_step=start_step,
        end_step=end_step,
        max_step=max_step,
    )
    select_columns_sql, from_sql, extras = _build_select_sql(
        dataset,
        selected_columns=selected_columns,
        where_clauses=where_clauses,
        order_by=order_by,
        desc=desc,
        latest_per_entity=latest_per_entity,
    )

    sql = f"SELECT {select_columns_sql} {from_sql}{extras['order_sql']}"
    query_params = dict(params)
    if limit is not None:
        sql += " LIMIT :limit"
        query_params["limit"] = limit
        if offset:
            sql += " OFFSET :offset"
            query_params["offset"] = offset
    elif offset:
        raise HTTPException(
            status_code=400,
            detail="offset requires a finite limit",
        )

    result = await session.execute(text(sql), query_params)
    rows = [normalize_dataset_row(dataset, dict(row._mapping)) for row in result.all()]
    return {
        "columns": selected_columns,
        "rows": rows,
    }


async def count_dataset_rows(
    session: AsyncSession,
    dataset: Dict[str, Any],
    *,
    step: Optional[int] = None,
    entity_id: Optional[int] = None,
    start_step: Optional[int] = None,
    end_step: Optional[int] = None,
    max_step: Optional[int] = None,
    latest_per_entity: bool = False,
) -> int:
    """Count dataset rows using the same filtering semantics as fetch_dataset_rows."""

    selected_columns = _validate_selected_columns(dataset, None)
    where_clauses, params = _build_filter_clauses(
        dataset,
        step=step,
        entity_id=entity_id,
        start_step=start_step,
        end_step=end_step,
        max_step=max_step,
    )
    _, from_sql, _ = _build_select_sql(
        dataset,
        selected_columns=selected_columns,
        where_clauses=where_clauses,
        order_by=None,
        desc=False,
        latest_per_entity=latest_per_entity,
    )
    result = await session.execute(text(f"SELECT COUNT(*) {from_sql}"), params)
    return int(result.scalar() or 0)


async def query_dataset_rows(
    session: AsyncSession,
    dataset: Dict[str, Any],
    *,
    page: int,
    page_size: int,
    order_by: Optional[str] = None,
    desc: bool = False,
    step: Optional[int] = None,
    entity_id: Optional[int] = None,
    start_step: Optional[int] = None,
    end_step: Optional[int] = None,
    max_step: Optional[int] = None,
    columns: Optional[List[str]] = None,
    latest_per_entity: bool = False,
) -> Dict[str, Any]:
    """Query rows from a dataset using metadata-driven filtering."""

    offset = (page - 1) * page_size
    total = await count_dataset_rows(
        session,
        dataset,
        step=step,
        entity_id=entity_id,
        start_step=start_step,
        end_step=end_step,
        max_step=max_step,
        latest_per_entity=latest_per_entity,
    )
    rows = await fetch_dataset_rows(
        session,
        dataset,
        order_by=order_by,
        desc=desc,
        step=step,
        entity_id=entity_id,
        start_step=start_step,
        end_step=end_step,
        max_step=max_step,
        columns=columns,
        latest_per_entity=latest_per_entity,
        limit=page_size,
        offset=offset,
    )
    return {
        "columns": rows["columns"],
        "rows": rows["rows"],
        "total": total,
    }

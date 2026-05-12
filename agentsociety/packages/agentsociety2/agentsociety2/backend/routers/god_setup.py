"""GOD startup setup and experiment-draft APIs."""

from __future__ import annotations

import json
import os
import re
import asyncio
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import json_repair
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agentsociety2.config import extract_json
from agentsociety2.society.models import InitConfig, StepsConfig

router = APIRouter(prefix="/api/v1/god/setup", tags=["god-setup"])


ENV_DEFAULTS = {
    "GOD_LLM_API_BASE": "https://api.openai.com/v1",
    "GOD_LLM_MODEL": "gpt-5.4",
    "GOD_EMBEDDING_MODEL": "text-embedding-3-large",
    "GOD_EXPERIMENT": "god_town",
    "GOD_EXPERIMENT_RUN": "1",
    "GOD_BACKEND_HOST": "127.0.0.1",
    "GOD_BACKEND_PORT": "8001",
    "GOD_FRONTEND_PORT": "5174",
}

MODEL_KEYS = (
    "GOD_LLM_API_KEY",
    "GOD_LLM_API_BASE",
    "GOD_LLM_MODEL",
    "GOD_EMBEDDING_API_KEY",
    "GOD_EMBEDDING_API_BASE",
    "GOD_EMBEDDING_MODEL",
    "GOD_BACKEND_HOST",
    "GOD_BACKEND_PORT",
    "GOD_FRONTEND_PORT",
)

SENSITIVE_KEYS = {"GOD_LLM_API_KEY", "GOD_EMBEDDING_API_KEY"}

DEFAULT_DRAFT_BACKGROUND = (
    "请生成一个安全、边界清晰的社会角色压力模拟：参与者被分配为管理者、观察者、"
    "普通参与者等角色，重点观察权力、规则、协作和情绪变化，不允许羞辱、伤害或强迫行为。"
)


class ModelConfigPayload(BaseModel):
    GOD_LLM_API_KEY: str | None = None
    GOD_LLM_API_BASE: str | None = None
    GOD_LLM_MODEL: str | None = None
    GOD_EMBEDDING_API_KEY: str | None = None
    GOD_EMBEDDING_API_BASE: str | None = None
    GOD_EMBEDDING_MODEL: str | None = None
    GOD_BACKEND_HOST: str | None = None
    GOD_BACKEND_PORT: str | None = None
    GOD_FRONTEND_PORT: str | None = None


class DraftBasics(BaseModel):
    title: str = Field("斯坦福监狱实验适配模拟", min_length=1)
    background: str = Field(DEFAULT_DRAFT_BACKGROUND, min_length=1)
    agent_count: int = Field(10, ge=1, le=50)
    language: str = "zh"
    start_t: str = "2026-05-11T08:20:00+08:00"
    num_steps: int = Field(4, ge=1, le=100)
    tick: int = Field(1800, ge=1)
    movement_tiles_per_second: float = Field(8.0, gt=0)
    movement_min_steps_per_trip: int = Field(3, ge=1)


class GenerateDraftRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    llm_config: ModelConfigPayload | None = Field(default=None, alias="model_config")
    basics: DraftBasics = Field(default_factory=DraftBasics)


class PublishRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    draft: dict[str, Any]
    llm_config: ModelConfigPayload | None = Field(default=None, alias="model_config")
    requested_hypothesis_id: str | None = None
    experiment_id: str = "1"
    start_immediately: bool = False


class StartRequestPayload(BaseModel):
    hypothesis_id: str | None = None
    experiment_id: str | None = None
    workspace_path: str | None = None


def _god_root() -> Path:
    raw = os.getenv("GOD_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()

    cwd = Path.cwd().resolve()
    if cwd.name == "agentsociety" and (cwd.parent / "scripts" / "god.sh").exists():
        return cwd.parent
    if (cwd / "scripts" / "god.sh").exists():
        return cwd
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "god.sh").exists():
            return parent
    return cwd


def _env_file() -> Path:
    return Path(os.getenv("GOD_ENV_FILE", str(_god_root() / ".env"))).expanduser().resolve()


def _workspace_path() -> Path:
    raw = os.getenv("LIVE_WORKSPACE_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return (_god_root() / "agentsociety" / "quick_experiments").resolve()


def _state_dir() -> Path:
    return (_god_root() / ".god").resolve()


def _current_experiment_file() -> Path:
    return _state_dir() / "current_experiment.json"


def _start_request_file() -> Path:
    return _state_dir() / "run" / "start-request.json"


def _latest_draft_file() -> Path:
    return _state_dir() / "run" / "latest-draft.json"


def _read_env(path: Path | None = None) -> dict[str, str]:
    path = path or _env_file()
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_values(values: dict[str, str]) -> None:
    path = _env_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    out: list[str] = []
    for line in existing_lines:
        if "=" not in line or line.lstrip().startswith("#"):
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        if out and out[-1] != "":
            out.append("")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _merged_env() -> dict[str, str]:
    env = {**ENV_DEFAULTS, **_read_env()}
    for key in MODEL_KEYS:
        if os.getenv(key):
            env[key] = os.environ[key]
    return env


def _redact_value(key: str, value: str | None) -> dict[str, Any]:
    if not value:
        return {"configured": False, "value": ""}
    if key in SENSITIVE_KEYS:
        tail = value[-4:] if len(value) >= 4 else "****"
        return {"configured": True, "value": f"••••{tail}"}
    return {"configured": True, "value": value}


def _sanitize_slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text[:48] or f"custom_{uuid.uuid4().hex[:8]}"


def _experiment_path(workspace: Path, hypothesis_id: str, experiment_id: str) -> Path:
    return workspace / f"hypothesis_{hypothesis_id}" / f"experiment_{experiment_id}"


def _load_map_manifest() -> dict[str, Any]:
    path = _god_root() / "agentsociety" / "custom" / "maps" / "the_ville" / "town.yaml"
    if not path.exists():
        path = Path.cwd() / "custom" / "maps" / "the_ville" / "town.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _known_location_ids() -> list[str]:
    manifest = _load_map_manifest()
    locations = manifest.get("locations") or []
    return [str(item.get("id")) for item in locations if isinstance(item, dict) and item.get("id")]


def _map_locations_for_status() -> list[dict[str, Any]]:
    try:
        locations = _load_map_manifest().get("locations", [])
    except Exception:
        return []
    return [item for item in locations if isinstance(item, dict)]


def _map_location_prompt() -> str:
    manifest = _load_map_manifest()
    lines: list[str] = []
    for item in manifest.get("locations") or []:
        if not isinstance(item, dict):
            continue
        interactions = ", ".join(str(v) for v in item.get("interaction_ids", []) or [])
        aliases = ", ".join(str(v) for v in item.get("aliases", []) or [])[:120]
        lines.append(
            f"- {item.get('id')}: {item.get('name')} | aliases: {aliases} | interactions: {interactions}"
        )
    return "\n".join(lines)


def _fallback_location(index: int, known_locations: list[str]) -> str:
    if not known_locations:
        return "park"
    preferred = ["home", "school", "library", "cafe", "park", "supply_store", "market", "pharmacy", "town_square"]
    ordered = [loc for loc in preferred if loc in known_locations] or known_locations
    return ordered[index % len(ordered)]


def _default_context(title: str, background: str) -> dict[str, Any]:
    return {
        "title": title,
        "background": background,
        "simulation_goal": "Run a grounded pixel-town social simulation based on the operator-provided scenario.",
        "world_setting": "The experiment uses the existing The Ville pixel-town map and maps scenario roles onto available town locations.",
        "ethical_boundaries": [
            "Keep the simulation fictional, bounded, and non-abusive.",
            "Do not instruct agents to perform humiliation, coercion, physical harm, or real-world illegal activity.",
            "For high-pressure scenarios, model decision-making, role pressure, and communication without graphic or harmful content.",
        ],
        "map_adaptation": "No new map is generated in v1; all locations are adapted to The Ville.",
    }


def _default_agent(agent_id: int, title: str, background: str, known_locations: list[str]) -> dict[str, Any]:
    name = f"Jiuwen Agent {agent_id}"
    role = "participant" if agent_id > 1 else "coordinator"
    profile = {
        "name": name,
        "age": 25 + agent_id,
        "role": role,
        "household": "Lives in the simulated town for the duration of the experiment.",
        "persona": "Observant, socially responsive, and consistent with the assigned scenario role.",
        "skills": ["observation", "conversation", "routine planning"],
        "daily_routine": "Follow the scenario role while preserving ordinary needs such as rest, food, and social contact.",
        "relationships": "Knows the other participants through the shared experiment setting.",
        "goal": f"Participate in {title} while staying within the scenario boundaries.",
        "constraints": "Avoid harmful, coercive, or humiliating behavior.",
        "scenario": background[:700],
        "scenario_role": role,
    }
    return {
        "agent_id": agent_id,
        "agent_type": "JiuwenClawAgent",
        "kwargs": {
            "id": agent_id,
            "name": name,
            "profile": profile,
            "jiuwenclaw_ws_url": "ws://127.0.0.1:19092",
            "session_id": f"generated_agent_{agent_id}",
            "mode": "agent.plan",
            "trusted_dirs": [],
            "enable_memory": True,
            "enable_daily_life": True,
            "enable_skill_runtime": True,
            "request_timeout": 900,
            "channel_id": "agentsociety",
            "experiment_context": _default_context(title, background),
        },
        "_initial_location": _fallback_location(agent_id - 1, known_locations),
    }


def _normalize_draft(raw: dict[str, Any], basics: DraftBasics) -> dict[str, Any]:
    known_locations = _known_location_ids()
    warnings: list[str] = list(raw.get("warnings") or [])

    context = raw.get("experiment_context")
    if not isinstance(context, dict):
        context = {}
    context = {
        **_default_context(basics.title, basics.background),
        **context,
    }
    if not context.get("title"):
        context["title"] = basics.title
    if not context.get("background"):
        context["background"] = basics.background

    init_config = raw.get("init_config")
    if not isinstance(init_config, dict):
        init_config = {}

    agents = init_config.get("agents")
    if not isinstance(agents, list):
        agents = []
    normalized_agents: list[dict[str, Any]] = []
    for index in range(basics.agent_count):
        source = agents[index] if index < len(agents) and isinstance(agents[index], dict) else {}
        default_agent = _default_agent(index + 1, basics.title, basics.background, known_locations)
        merged = deepcopy(default_agent)
        merged.update({k: v for k, v in source.items() if k in {"agent_id", "agent_type", "kwargs"}})
        merged["agent_id"] = int(merged.get("agent_id") or index + 1)
        merged["agent_type"] = str(merged.get("agent_type") or "JiuwenClawAgent")
        kwargs = merged.get("kwargs") if isinstance(merged.get("kwargs"), dict) else {}
        default_kwargs = default_agent["kwargs"]
        profile = kwargs.get("profile") if isinstance(kwargs.get("profile"), dict) else {}
        default_profile = default_kwargs["profile"]
        name = str(kwargs.get("name") or profile.get("name") or default_profile["name"])
        profile = {
            **default_profile,
            **profile,
            "name": str(profile.get("name") or name),
            "scenario": str(profile.get("scenario") or context.get("background") or "")[:1200],
            "scenario_role": str(profile.get("scenario_role") or profile.get("role") or "participant"),
        }
        kwargs = {
            **default_kwargs,
            **kwargs,
            "id": merged["agent_id"],
            "name": name,
            "profile": profile,
            "experiment_context": context,
        }
        merged["kwargs"] = kwargs
        normalized_agents.append(merged)

    initial_locations: dict[str, str] = {}
    raw_initial_locations: dict[str, Any] = {}
    for module in init_config.get("env_modules") or []:
        if isinstance(module, dict):
            module_locations = module.get("kwargs", {}).get("initial_locations")
            if isinstance(module_locations, dict):
                raw_initial_locations.update(module_locations)
    for index, agent in enumerate(normalized_agents):
        raw_location = str(
            raw_initial_locations.get(str(agent["agent_id"]))
            or agent.pop("_initial_location", "")
            or _fallback_location(index, known_locations)
        )
        if raw_location not in known_locations:
            warnings.append(
                f"Agent {agent['agent_id']} initial location '{raw_location}' is not in The Ville; mapped to a valid location."
            )
            raw_location = _fallback_location(index, known_locations)
        initial_locations[str(agent["agent_id"])] = raw_location

    source_env_kwargs: dict[str, Any] = {}
    if init_config.get("env_modules") and isinstance(init_config["env_modules"][0], dict):
        source_env_kwargs = init_config["env_modules"][0].get("kwargs") or {}

    env_module = {
        "module_type": "PixelTownSocialEnv",
        "kwargs": {
            "agent_id_name_pairs": [
                [agent["agent_id"], agent["kwargs"]["name"]] for agent in normalized_agents
            ],
            "initial_locations": initial_locations,
            "default_group_name": str(source_env_kwargs.get("default_group_name") or f"{basics.title} Chat"),
            "map_manifest_path": "custom/maps/the_ville/town.yaml",
            "movement_tiles_per_second": float(
                source_env_kwargs.get("movement_tiles_per_second", basics.movement_tiles_per_second)
            ),
            "movement_min_steps_per_trip": int(
                source_env_kwargs.get("movement_min_steps_per_trip", basics.movement_min_steps_per_trip)
            ),
        },
    }

    normalized_init = {
        "env_modules": [env_module],
        "agents": normalized_agents,
        "codegen_router": init_config.get("codegen_router") or {"final_summary_enabled": True},
    }
    validated_init = InitConfig.model_validate(normalized_init).model_dump(mode="json")

    steps = raw.get("steps") if isinstance(raw.get("steps"), dict) else {}
    if not isinstance(steps.get("steps"), list):
        steps["steps"] = [{"type": "run", "num_steps": basics.num_steps, "tick": basics.tick}]
    steps["start_t"] = str(steps.get("start_t") or basics.start_t)
    validated_steps = StepsConfig.model_validate(steps).model_dump(mode="json")

    if "The Ville" not in str(context.get("map_adaptation", "")):
        warnings.append("v1 uses the existing The Ville map; scenario-specific places are adapted to known map locations.")

    return {
        "experiment_context": context,
        "init_config": validated_init,
        "steps": validated_steps,
        "readme": str(raw.get("readme") or _readme_for_draft(context, validated_init, validated_steps)),
        "warnings": sorted(set(str(item) for item in warnings if str(item).strip())),
    }


def _readme_for_draft(context: dict[str, Any], init_config: dict[str, Any], steps: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {context.get('title', 'GOD Experiment')}",
            "",
            "## Background",
            str(context.get("background", "")),
            "",
            "## Simulation Goal",
            str(context.get("simulation_goal", "")),
            "",
            "## Configuration",
            f"- Agents: {len(init_config.get('agents', []))}",
            f"- Start: {steps.get('start_t')}",
            f"- Steps: {len(steps.get('steps', []))}",
            "",
            "## Map Adaptation",
            str(context.get("map_adaptation", "Uses The Ville pixel-town map.")),
        ]
    )


async def _call_openai_compatible(
    *,
    api_key: str,
    api_base: str,
    model: str,
    basics: DraftBasics,
) -> dict[str, Any]:
    base = api_base.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    schema = {
        "experiment_context": {
            "title": "string",
            "background": "string",
            "simulation_goal": "string",
            "world_setting": "string",
            "ethical_boundaries": ["string"],
            "map_adaptation": "string",
        },
        "init_config": {
            "env_modules": [
                {
                    "module_type": "PixelTownSocialEnv",
                    "kwargs": {
                        "initial_locations": {"1": "park"},
                        "default_group_name": "string",
                    },
                }
            ],
            "agents": [
                {
                    "agent_id": 1,
                    "agent_type": "JiuwenClawAgent",
                    "kwargs": {
                        "id": 1,
                        "name": "string",
                        "profile": {
                            "name": "string",
                            "age": 30,
                            "role": "string",
                            "household": "string",
                            "persona": "string",
                            "skills": ["string"],
                            "daily_routine": "string",
                            "relationships": "string",
                            "goal": "string",
                            "constraints": "string",
                            "scenario_role": "string",
                        },
                    },
                }
            ],
        },
        "steps": {
            "start_t": basics.start_t,
            "steps": [{"type": "run", "num_steps": basics.num_steps, "tick": basics.tick}],
        },
        "readme": "markdown string",
        "warnings": ["string"],
    }
    system_prompt = (
        "You are GOD, an experiment initialization agent for a fictional LLM-agent pixel town. "
        "Return only one strict JSON object. Do not use markdown. "
        "Use safe, bounded social-science simulation framing. For prison/authority scenarios, "
        "model role pressure and communication without abuse, humiliation, physical harm, or illegal acts. "
        "v1 cannot generate a new map; choose only valid The Ville location ids."
    )
    user_prompt = (
        f"Create a complete experiment draft.\n\n"
        f"Title: {basics.title}\n"
        f"Language: {basics.language}\n"
        f"Agent count: {basics.agent_count}\n"
        f"Start time: {basics.start_t}\n"
        f"Run plan: {basics.num_steps} steps, tick {basics.tick} seconds\n"
        f"Operator scenario/background:\n{basics.background}\n\n"
        f"Available The Ville locations and interactions:\n{_map_location_prompt()}\n\n"
        f"Required JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
    )
    timeout_seconds = float(os.getenv("GOD_SETUP_DRAFT_TIMEOUT", "240"))
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            response = await session.post(
                url,
                headers={
                    "authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.5,
                    "response_format": {"type": "json_object"},
                },
            )
            text = await response.text()
            if response.status >= 400:
                raise HTTPException(status_code=502, detail=f"Draft model request failed: {text[:600]}")
            payload = json.loads(text)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Draft model request timed out after {int(timeout_seconds)} seconds. "
                "Please try a faster model/provider, reduce agent count, or set GOD_SETUP_DRAFT_TIMEOUT higher."
            ),
        ) from exc
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=f"Draft model request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Draft model returned a non-JSON HTTP response") from exc
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    json_text = extract_json(content) or content
    parsed = json_repair.loads(json_text)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Draft model returned non-object JSON")
    return parsed


def _write_current_experiment(hypothesis_id: str, experiment_id: str, workspace_path: Path) -> dict[str, Any]:
    payload = {
        "hypothesis_id": hypothesis_id,
        "experiment_id": experiment_id,
        "workspace_path": str(workspace_path),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _current_experiment_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _read_current_experiment() -> dict[str, Any] | None:
    path = _current_experiment_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write_start_request(hypothesis_id: str, experiment_id: str, workspace_path: Path) -> dict[str, Any]:
    payload = {
        "request_id": uuid.uuid4().hex,
        "hypothesis_id": hypothesis_id,
        "experiment_id": experiment_id,
        "workspace_path": str(workspace_path),
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _start_request_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _write_latest_draft(basics: DraftBasics, draft: dict[str, Any]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "basics": basics.model_dump(mode="json"),
        "draft": draft,
    }
    path = _latest_draft_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@router.get("/status")
async def setup_status() -> dict[str, Any]:
    env = _merged_env()
    current = _read_current_experiment()
    hypothesis_id = str((current or {}).get("hypothesis_id") or env.get("GOD_EXPERIMENT") or "")
    experiment_id = str((current or {}).get("experiment_id") or env.get("GOD_EXPERIMENT_RUN") or "1")
    workspace = Path((current or {}).get("workspace_path") or _workspace_path()).expanduser().resolve()
    config_path = _experiment_path(workspace, hypothesis_id, experiment_id) / "init" / "init_config.json"
    has_current = current is not None and config_path.exists()
    return {
        "god_root": str(_god_root()),
        "env_file": str(_env_file()),
        "workspace_path": str(workspace),
        "map_locations": _map_locations_for_status(),
        "model_config": {key: _redact_value(key, env.get(key)) for key in MODEL_KEYS},
        "current_experiment": current,
        "default_experiment": {
            "hypothesis_id": env.get("GOD_EXPERIMENT", "god_town"),
            "experiment_id": env.get("GOD_EXPERIMENT_RUN", "1"),
            "config_exists": config_path.exists(),
        },
        "needs_setup": not bool(env.get("GOD_LLM_API_KEY")) or not has_current,
    }


@router.post("/model-config")
async def save_model_config(payload: ModelConfigPayload) -> dict[str, Any]:
    values = {
        key: str(value).strip()
        for key, value in payload.model_dump().items()
        if value is not None and str(value).strip() != ""
    }
    for key, default in ENV_DEFAULTS.items():
        if key in MODEL_KEYS and key not in values:
            values[key] = _merged_env().get(key, default)
    if values:
        _write_env_values(values)
    return await setup_status()


@router.post("/generate-draft")
async def generate_draft(request: GenerateDraftRequest) -> dict[str, Any]:
    env = _merged_env()
    model_config = request.llm_config or ModelConfigPayload()
    api_key = model_config.GOD_LLM_API_KEY or env.get("GOD_LLM_API_KEY") or ""
    api_base = model_config.GOD_LLM_API_BASE or env.get("GOD_LLM_API_BASE") or ENV_DEFAULTS["GOD_LLM_API_BASE"]
    model = model_config.GOD_LLM_MODEL or env.get("GOD_LLM_MODEL") or ENV_DEFAULTS["GOD_LLM_MODEL"]
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="GOD_LLM_API_KEY is required to generate an experiment draft")
    try:
        raw = await _call_openai_compatible(
            api_key=api_key.strip(),
            api_base=api_base.strip(),
            model=model.strip(),
            basics=request.basics,
        )
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Draft model request timed out") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Draft model request failed: {exc}") from exc
    draft = _normalize_draft(raw, request.basics)
    _write_latest_draft(request.basics, draft)
    return draft


@router.post("/publish")
async def publish_experiment(request: PublishRequest) -> dict[str, Any]:
    basics = DraftBasics(
        title=str(request.draft.get("experiment_context", {}).get("title") or "Custom GOD Experiment"),
        background=str(request.draft.get("experiment_context", {}).get("background") or "Custom GOD experiment"),
        agent_count=max(1, len(request.draft.get("init_config", {}).get("agents", []) or [1])),
    )
    draft = _normalize_draft(request.draft, basics)
    workspace = _workspace_path()
    workspace.mkdir(parents=True, exist_ok=True)

    base_slug = _sanitize_slug(
        request.requested_hypothesis_id
        or str(draft["experiment_context"].get("title") or basics.title)
    )
    hypothesis_id = base_slug
    suffix = 2
    while (workspace / f"hypothesis_{hypothesis_id}").exists():
        hypothesis_id = f"{base_slug}_{suffix}"
        suffix += 1

    experiment_id = _sanitize_slug(str(request.experiment_id or "1"))
    exp_dir = _experiment_path(workspace, hypothesis_id, experiment_id)
    init_dir = exp_dir / "init"
    init_dir.mkdir(parents=True, exist_ok=False)

    (init_dir / "init_config.json").write_text(
        json.dumps(draft["init_config"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (init_dir / "steps.yaml").write_text(
        yaml.safe_dump(draft["steps"], allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (init_dir / "experiment_context.json").write_text(
        json.dumps(draft["experiment_context"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (exp_dir / "README.md").write_text(str(draft["readme"]).rstrip() + "\n", encoding="utf-8")
    (exp_dir / "EXPERIMENT.md").write_text(str(draft["readme"]).rstrip() + "\n", encoding="utf-8")
    hyp_dir = workspace / f"hypothesis_{hypothesis_id}"
    (hyp_dir / "HYPOTHESIS.md").write_text(
        f"# {draft['experiment_context'].get('title')}\n\n{draft['experiment_context'].get('background')}\n",
        encoding="utf-8",
    )
    (hyp_dir / "SIM_SETTINGS.json").write_text(
        json.dumps(
            {
                "agentClasses": ["JiuwenClawAgent"],
                "envModules": ["PixelTownSocialEnv"],
                "experimentContext": draft["experiment_context"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    env_values = {
        "GOD_EXPERIMENT": hypothesis_id,
        "GOD_EXPERIMENT_RUN": experiment_id,
    }
    if request.llm_config:
        env_values.update(
            {
                key: str(value).strip()
                for key, value in request.llm_config.model_dump().items()
                if value is not None and str(value).strip() != ""
            }
        )
    _write_env_values(env_values)
    current = _write_current_experiment(hypothesis_id, experiment_id, workspace)
    start_request = (
        _write_start_request(hypothesis_id, experiment_id, workspace)
        if request.start_immediately
        else None
    )
    return {
        "hypothesis_id": hypothesis_id,
        "experiment_id": experiment_id,
        "workspace_path": str(workspace),
        "experiment_path": str(exp_dir),
        "current_experiment": current,
        "start_request": start_request,
        "warnings": draft["warnings"],
    }


@router.post("/start-request")
async def create_start_request(payload: StartRequestPayload) -> dict[str, Any]:
    current = _read_current_experiment() or {}
    hypothesis_id = payload.hypothesis_id or current.get("hypothesis_id") or _merged_env().get("GOD_EXPERIMENT")
    experiment_id = payload.experiment_id or current.get("experiment_id") or _merged_env().get("GOD_EXPERIMENT_RUN") or "1"
    workspace = Path(payload.workspace_path or current.get("workspace_path") or _workspace_path()).expanduser().resolve()
    if not hypothesis_id:
        raise HTTPException(status_code=400, detail="No current experiment is configured")
    return _write_start_request(str(hypothesis_id), str(experiment_id), workspace)

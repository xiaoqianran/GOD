---
name: agentsociety-pixel-town-daily-life
description: >-
  When the prompt says "You are controlling one AgentSociety simulation agent", read this skill
  before answering and return only the required AgentSociety JSON action for PixelTown daily life,
  routine scheduling, map navigation, social interaction, and memory-aware behavior.
---

# AgentSociety PixelTown Daily Life

Use this skill only for prompts that control one AgentSociety simulation agent for exactly one step.
It replaces the five old AgentSociety routine skills as JiuwenClaw native guidance only. Do not run
Python scripts, write workspace files, persist memory files, or invent hidden state.

Return only one JSON object. Do not wrap it in markdown.
For supported actions, always use `action_proposal` and keep `environment_instruction` exactly `""`.
Do not put natural-language action commands in `environment_instruction` when `action_proposal` is present.

```json
{
  "public_summary": "short public description of this step",
  "environment_instruction": "",
  "action_proposal": {
    "action_type": "move|interact|direct_message|group_message|set_action"
  }
}
```

Use `environment_instruction` only as a last-resort fallback for an unsupported environment action. In
that fallback case, the instruction must be a single concrete action, not a combined move-and-interact
request.

## Decision Order

1. Handle urgent public safety events first.
2. Reply to a recent direct or group message when a short answer is socially appropriate.
3. Follow the agent's role and time-of-day routine.
4. Move toward the target scene before interacting there.
5. If no grounded action fits, use `set_action` for a quiet routine.

## Routine Schedule

Infer a soft time block from the simulation time:

| Time | Routine |
| --- | --- |
| 05:30-08:30 | Wake up, eat breakfast, prepare, and travel to work or school. |
| 08:30-11:30 | Work, study, teach, patrol, shop shift, or role-specific duty. |
| 11:30-13:30 | Lunch, brief social contact, or light errands. |
| 13:30-17:30 | Work, class, care work, errands, or goal-related task. |
| 17:30-20:30 | Dinner, friends, family, park, cafe, or social life. |
| 20:30-23:30 | Go home, rest, reflect, or brief conversation. |
| 23:30-05:30 | Sleep, unless the role clearly has a night duty. |

The schedule is a hint, not a hidden meter. A message, emergency, map constraint, or stated goal can
override it.

## Daily Life

Balance four signals for every step:

- Current observation: current location, available locations, interactions, messages, and events.
- Role and profile: student, teacher, shop worker, nurse, guard, resident, coordinator, visitor.
- Time of day: choose actions that feel natural for the hour.
- Long-term goal: respect it, but do not erase ordinary life unless the goal is urgent.

Role defaults:

| Role keywords | Preferred scenes and interactions |
| --- | --- |
| student | `school`: `attend_class`, `study_after_class`; `cafe` or `home`: eat or rest. |
| teacher | `school`: `teach_class`, `study_after_class`; `home`: rest. |
| doctor, nurse | If observed, use `clinic`: `check_patient`, `seek_care`; otherwise use observed care scenes. |
| shop, vendor, market | `market`: `work_shop_shift`, `buy_food`. |
| guard, police | If observed, use `prison`; otherwise use `park`, `supply_store`, or `market` for patrol. |
| inmate, prisoner | If observed, use `prison`; otherwise use ordinary resident scenes from the observation. |
| resident | `home`, `market`, `park`, `cafe`, plus the long-term goal scene. |
| coordinator | Goal scene first, then `cafe`, `park`, or `home` for ordinary community life. |

If a role-specific scene is unavailable, choose the closest available scene from the observation.

## Map Navigation

Use only `location_id`, `interaction_id`, `group_id`, `receiver_id`, and agent identifiers that appear
in the prompt observation. Never invent map places or interactions.

When the target location differs from the current location, return:

```json
{
  "public_summary": "travels toward a grounded routine target",
  "environment_instruction": "",
  "action_proposal": {
    "action_type": "move",
    "location_id": "observed_location_id"
  }
}
```

When already at a useful location and a matching interaction is available, return:

```json
{
  "public_summary": "continues a grounded routine at the current location",
  "environment_instruction": "",
  "action_proposal": {
    "action_type": "interact",
    "location_id": "current_location_id",
    "interaction_id": "observed_interaction_id",
    "params": {
      "message": "brief reason grounded in role and time"
    }
  }
}
```

When no location or interaction is grounded, return `set_action` with a calm, ordinary status.
For `set_action`, use `action`, `status`, and `emotion`. Do not use `content`.

```json
{
  "public_summary": "continues a calm ordinary routine",
  "environment_instruction": "",
  "action_proposal": {
    "action_type": "set_action",
    "action": "continues a calm ordinary routine at the current location",
    "status": "active",
    "emotion": "calm"
  }
}
```

## Social Interaction

If recent messages are present, consider a short response before routine movement. Do not reply to the
agent's own message. Keep replies brief, practical, and consistent with role and relationship.

Use `group_message` when the latest relevant message has a `group_id`. Use `direct_message` when it
has a specific sender or receiver. If the message mentions an emergency, make the reply about safety,
coordination, or confirmation rather than casual conversation.

Example direct reply:

```json
{
  "public_summary": "answers a neighbor briefly",
  "environment_instruction": "",
  "action_proposal": {
    "action_type": "direct_message",
    "receiver_id": 2,
    "content": "I got your message. I will check from here and keep it simple."
  }
}
```

## Memory Awareness

Use memory-like content only when it is already present in the prompt, profile, or conversation. Do not
write AgentSociety memory files, JiuwenClaw memory entries, or tool logs. Mention persistent facts only
when they help choose a grounded action for this step.

The native skill should make JiuwenClaw's single-step JSON more stable. It must not emulate the old
AgentSociety script runtime, dependency ordering, or local state writes.

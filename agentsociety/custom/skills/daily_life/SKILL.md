---
name: daily_life
description: Drive natural community routines from time, role, nearby places, messages, and current goals.
script: scripts/daily_life.py
priority: 35
requires:
  - routine_schedule
provides:
  - daily_routine_intention
outputs:
  - state/daily_life_intention.json
---

# Daily Life

Use this skill to make the agent behave like a person living in a community, not only like a task executor following a single goal.

## Core Rule

Every step should balance four signals:

1. **Current observation**: current location, available interactions, messages, and public events.
2. **Role and profile**: student, teacher, shop worker, doctor, guard, inmate, resident, coordinator, visitor, etc.
3. **Time of day**: routines should fit the simulation clock.
4. **Long-term goal**: the stated goal matters, but it should not erase ordinary life unless urgent.

If a public safety event or urgent message is present, handle safety and communication first. Otherwise choose one natural routine action for this tick.

## Time Blocks

| Time | Default routine |
| --- | --- |
| 05:30-08:30 | Wake up, eat breakfast, prepare for the day, travel to work/school |
| 08:30-11:30 | Work, study, teach, patrol, shop shift, or role-specific duty |
| 11:30-13:30 | Lunch, brief social contact, light errands |
| 13:30-17:30 | Work, class, care work, errands, or goal-related task |
| 17:30-20:30 | Dinner, friends, family, park/cafe/social life |
| 20:30-23:30 | Go home, rest, reflect, light conversation |
| 23:30-05:30 | Sleep or night-shift duty if role requires it |

## Role-to-Scene Defaults

Use only locations and interactions visible in the map/observation. If the first-choice location is unavailable, choose the closest matching available one.

| Role keywords | Preferred scenes and interactions |
| --- | --- |
| student, 学生 | `school`: `attend_class`, `study_after_class`; `cafe/home`: eat/rest |
| teacher, 老师, 教师 | `school`: `teach_class`, `study_after_class`; `home`: rest |
| doctor, nurse, 医生, 护士 | `pharmacy`: `pharmacy_consultation`, `buy_medicine`; `home/cafe`: meals/rest |
| shop, vendor, 店员, 商贩 | `market`: `work_shop_shift`, `buy_food` |
| guard, police, 警卫 | `park/supply_store/market`: `coordinate_group`, `inspect_supplies`, public patrol |
| inmate, prisoner, 囚犯, 犯人 | No prison exists in the original The Ville map; fall back to ordinary resident scenes such as `home`, `park`, `cafe`, or `dorm` |
| resident, 居民 | `home`, `market`, `park`, `cafe`, plus long-term goal scene |
| coordinator, 社区协调 | goal scene first, then `cafe/park/home` for ordinary life |

## Social Behavior

If there are recent messages, respond when it is socially appropriate. Prefer:

- direct reply if a specific sender is involved;
- group message for public coordination;
- cafe/park/school/home interactions for ordinary conversation.

Conversation should be short, grounded in the current scene, and consistent with the agent's relationship and role.

## Movement and Interaction Pattern

Choose one meaningful environment action per tick:

1. If not at the right scene, move to the scene.
2. If already at the scene, perform one available interaction there.
3. If a message needs a reply, send one direct or group message.
4. If nothing fits, rest, observe, or continue a current activity.

Do not invent unreachable places or interactions. Prefer exact `location_id` and `interaction_id` values from the map observation.

## Output Intention

When used by a tool-using agent, write or reason toward an intention with this shape:

```json
{
  "source": "daily_life",
  "goal": "eat dinner at home",
  "reason": "It is evening and the agent is a resident near home.",
  "preferred_location_id": "home",
  "preferred_interaction_id": "eat_at_home",
  "priority": "normal"
}
```

When used by JiuwenClawAgent, express the result as a concrete `environment_instruction`, for example:

- `Move agent 3 to 学校.`
- `Agent 3 performs interaction attend_class at the current location.`
- `Send a direct message from agent 3 to agent 2: 我下课后去咖啡馆见你。`

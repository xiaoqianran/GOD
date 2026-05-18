---
instruction: '下一步请你在西门以 group_message 公开提示：代表团已到达北京大学西门，将按公开流程进入校园并前往百周年纪念讲堂；只说公开流程，不描述安保或管制。请使用
  action_proposal: action_type=group_message, public=true。'
target:
  type: agent
  agent_id: 22
---

已识别为集合/移动干预，直接调用环境寻路到：达北京大学西门
没有 agent 成功开始移动；请检查地点名称是否是地图 manifest 中的 location/alias。
目标: 王协调员 (agent_id=22)
下一次 Run Step/Auto 会推进路径并写入 replay；若 tick 足够大，会在同一个 step 内到达。

王协调员 (agent_id=22): move failed: {'ok': False, 'error': 'unknown_location', 'agent_id': 22, 'location': '达北京大学西门', 'known_locations': ['west_gate', 'east_gate', 'south_gate', 'weiming_lake', 'boya_pagoda', 'library', 'centennial_hall', 'teaching_building', 'dormitory', 'canteen', 'gymnasium', 'lab_building', 'admin_building', 'campus_green']}

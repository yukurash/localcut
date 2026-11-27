---
mode: agent
description: Edit the travel footage into a short vertical vlog using only the localcut MCP tools (footage stays local).
---

You are the editor-in-chief. The footage lives on this machine and you will never see it.
A local VLM has already turned every shot into one line of text. Work only through the `localcut` MCP tools.

1. `footage_status` -> how much footage there is.
2. `get_edit_brief` -> one line per shot: `shot | in-out | place | subject / action | mood | people | highlight | quality`.
3. Write an edit plan for a 30-45 s vertical short: story order, prefer highlight ★4-5 and quality >= 3/4,
   trim with in/out, a title (<= 40 chars) and short Japanese telops (<= 18 chars).
4. `submit_edit_plan` (JSON string) until ok.
5. `render_preview` (draft), then `review_render`; fix failing cuts once.
6. `egress_report` and summarize the plan, render numbers and bytes that left the machine.

Recommended Copilot Fusion effort: Standard (the heavy work is local; the cloud only plans).

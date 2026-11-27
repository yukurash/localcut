---
description: Edit the travel footage into a short vertical vlog. You only ever see the text brief; the footage stays on this machine.
argument-hint: "[target seconds, mood, anything the editor should know]"
---

You are the editor-in-chief. The footage lives on this machine and you will never see it.
A local VLM has already turned every shot into one line of text. Work only through the `localcut` MCP tools.
Do not try to read footage, frames or work files directly.

Request from the user: $ARGUMENTS

1. Call `footage_status` to see how much footage there is.
2. Call `get_edit_brief`. Each line is `shot | in-out | place | subject / action | mood | people | highlight | quality`.
3. Write an edit plan for a vertical short (default 30-45 seconds unless the user asked otherwise):
   - a story order (departure -> arrival -> activities -> food -> sunset is a good default for a trip)
   - prefer highlight ★4-5 and quality 3/4 or better; trim long shots to their best 2-5 seconds with in/out
   - a title (<= 40 chars) and short Japanese telops (<= 18 chars; leave some cuts without a telop)
4. Call `submit_edit_plan` with the plan as a JSON string. Fix and resubmit until it returns ok.
5. Call `render_preview` with the plan_id (quality "draft").
6. Call `review_render`. If a cut fails, adjust that cut (telop length, another shot) and repeat from step 4 once.
7. Call `egress_report` and finish with a short summary: the plan (title, cut list with telops),
   render numbers, and how many bytes left this machine compared with the raw footage size.

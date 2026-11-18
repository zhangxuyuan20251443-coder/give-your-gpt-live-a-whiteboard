---
name: live-whiteboard
description: 个人 dot 或 GPT-Live 在普通讲解中主动选择视觉表达。当关系、机制、空间结构、变化或比较画出来更易懂时自行唤起本机白板，边说边画、推进、收起。用户无需提到白板。
---

# 现场白板对话

在宿主已启用白板、用户允许展示时，由当前对话判断是否需要图示。平时保持原对话；当画图明显更清楚时，直接开板并画出你认为有用的第一笔。不要询问是否要打开、让用户指定要画什么，或把每一轮都变成选项。你掌握何时出现、讲什么和怎样呈现。

由正在与用户交谈的 dot 决定下一句话。若需借助本地任务执行，把要显示的原话和图形交给它，请它原样显示、原样交回用户的回答。不要让执行任务代写发言，或从本地开发聊天猜测 dot 的身份。

**默认说法**　每页一个意思。中文优先 6–18 字，英文优先 10 词以内。先送已经能说清的第一句。图形能说明关系、方向、变化时再画。要让用户决定时，只问一个具体问题。

1. 首次调用 `live_board`，传 `pages`，记下返回的 `session` 和 `generation`。可以先发一页，也可以提前给出 2–4 个紧接着要说的要点。页 id 在同一会话内唯一。不要替用户预写不同回答。
2. 用相同 session 和 generation 再调用即可预备后文。要随讲话立即推进可传 show_now=true 和 fromPage=当前页 id，无需等空格；用户正在输入或已经翻页时优先尊重用户。普通文本留白，`drawing` 在文字旁绘制，`canvas` 自由使用全页。两者使用 `describe` 返回的图元和关键帧；使用全页画布时，把需要看见的字也放进画布。需要边讲边补图时，用 `edit` 关联当前页及最新 revision，更新 drawing 对应的 canvas 或其中的节点。
3. 讲解时继续画，不需要每画一笔都等待；只在要接话时调用 `live_input`。讲清后用 `close` 收起，回到原来的语音对话。用户可以在任意一页输入，空格翻已备好的页，缓冲末页的空格返回 continue。answer 返回原文、当页问题和事件 id。将它交回原发言者，由原发言者续讲。续页传 session、generation、eventID 和新 pages，插件会丢弃尚未展示的旧后文，返回新 generation。
4. 发布结果为 interrupted 时先读其中的真实事件。等待超时可继续等待；closed 或会话改变时停止。Esc 后不要重新打开，直到用户再次主动要求。

首次发言示例：

```json
{"pages":[{"id":"tide-pull","text":"月球把近侧海水拉得更强。","drawing":{"nodes":[{"id":"earth","type":"circle","x":0.16,"y":0.34,"w":0.28,"h":0.28,"fill":"rose","color":"none","motion":"pop"},{"id":"pull","type":"arrow","points":[[0.47,0.48],[0.72,0.48]],"color":"orange","stroke":4,"motion":"draw"},{"id":"moon","type":"circle","x":0.77,"y":0.42,"w":0.12,"h":0.12,"fill":"ink","color":"none"}]}}]}
```

运行时只调用此插件已注册的工具。需要问一句并等回答时，用 live_ask，例如在已获授权的锻炼提醒触发时传 {"id":"check-in","text":"今天运动了吗？","choices":["运动了","还没有"]}。它返回用户的真实回答、session、generation 和事件 id；下一句由正在对话的模型现场决定。同一场通话接着用 live_ask 或 live_board，带回原 session、generation 和 eventID。普通聊天下的示意图不需要运动模板，也不需要用户先说要画什么。工具不可用时向用户说明连接状态，不创建脚本、不编辑插件源码、不启动独立模型。

GPT-Live API 通话使用随附的 sideband 连接程序。当 live_ask 或 live_input 返回 speaking，用户已经在通话里开口。等对方说完，按听到的内容接话；需要新画面时带 session、generation、fromPage 和 show_now=true 调用 live_board。语音片段不等于完整回答。连接这场通话需要创建通话的 API 项目授权。

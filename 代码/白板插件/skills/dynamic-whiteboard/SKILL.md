---
name: dynamic-whiteboard
description: 把回答的要点、动态示意图或一个需要用户拍板的问题，送到用户 Mac 上的原生全屏白板（Dot 白板）。当关系、机制、流程、变化、对比画出来比文字更清楚，或用户说「用白板」「画给我看」「一步步讲」时使用；用户不必提到白板。与用哪个模型、是否在语音通话无关，只要能运行本机命令即可。
---

# 动态白板 · 输出端

白板可以直接承载当前回答。每页讲一个意思，画面已经说清的内容无需在聊天里再写一遍。什么时候开板、画什么、何时收起，都由你判断，不用先问用户要不要。

宿主已接入 MCP 时直接调用 `whiteboard_say`、`whiteboard_ask` 等工具。有本机命令执行能力时使用技能目录下的 `scripts/board.py`。

```sh
W="<本技能目录>/scripts/board.py"      # 例如 ~/.codex/skills/dynamic-whiteboard/scripts/board.py
python3 -B "$W" say "声音，从振动开始。"
```

每次调用输出一行 JSON。`ok` 表示成功与否，`status` 说明发生了什么，`hint` 告诉你下一步怎么做，照着做就行。会话、版本号、回答编号都由脚本自己维护，你不需要记任何 id。

## 什么时候用

适合用白板的情况：
- 机制和因果，比如潮汐、声音传播、注意力机制
- 流程和循环，比如水循环、请求的一生
- 变化和对比，比如振幅大小、前后两种方案
- 空间关系
- 一段较长的讲解，可以拆成几步，一步一页

不用白板的情况：
- 一句话就能答完的事实
- 代码、表格、长清单
- 用户刚按 Esc 收起白板（脚本会返回 `dismissed`）

## 命令

| 命令 | 作用 |
|---|---|
| `say "句1" "句2"` 或 `say <<'JSON' … JSON` | 送 1–8 页。白板没开就打开；用户已看完前面的页就立刻显示，否则排在后面按空格看 |
| `say --now …` / `say --queue …` | 强制立刻跳到新页 / 只排队 |
| `say --new --topic 标题 …` | 新开一块白板（替换正在显示的文稿或别的内容），左上角显示标题 |
| `ask "问题？" --choice 甲 --choice 乙 [--wait 45]` | 显示一个问题并等用户点选或打字，最多等 120 秒 |
| `wait [--wait 45]` | 继续等用户在白板上的输入 |
| `edit '{"node":"arrow","set":{"color":"orange"}}'` | 原位修改当前页：改图元、`add` 加图元、`remove` 删图元、`text` 换主句 |
| `close` | 讲完收起 |
| `status` | 白板开着吗、在第几页、用户有没有留话 |
| `check …` | 只校验不显示，返回展开后的图元；画复杂的图之前先用它 |
| `describe` / `doctor` / `demo` | 速查语法 / 检查安装 / 播放示例 |
| `present --file 文稿.json` | 播放一份完整的多页文稿（例：`examples/声音怎样传播.白板.json`） |

## 怎么讲

1. **一页一个意思。**中文 6–18 字，英文 10 个词以内。页面上的字是你此刻要说的那句话，不是标题，也不是摘要。
2. **先出第一句。**能说清的第一页马上发，接下来紧挨着的 1–3 个要点可以一起发，用户按空格往下看。
3. **图是为了说明关系。**方向、因果、变化、对比用 `drawing`，图画在文字旁；想自由排版整页用 `canvas`，这时页面上要看见的字也要放进画布。纯文字页留白就好。
4. **边讲边画。**先画骨架，讲到哪一步就用 `edit` 的 `add` 补哪一笔，不要一次堆满 12 个图元。
5. **当用户的事实、偏好或决定会改变下一步时提问**，用 `ask`，一次只问一个具体问题，选项最多 3 个。不要替用户预写不同回答的后续页。
6. **收起要等用户看完。**同一个话题继续 `say` 就行。话题结束、用户转去做别的事，再 `close`。不要发完页就马上收起，用户还没看。

带图的一页（JSON 用单引号 heredoc 传入，最省转义）：

```sh
python3 -B "$W" say --topic 潮汐 <<'JSON'
{"text":"月球把近侧海水拉得更强。","drawing":{"nodes":[
  {"id":"earth","type":"circle","x":0.06,"y":0.28,"w":0.3,"h":0.44,"fill":"rose","color":"none","motion":"pop"},
  {"id":"moon","type":"circle","x":0.82,"y":0.42,"w":0.1,"h":0.16,"fill":"ink","color":"none","motion":"pop","delay":0.2},
  {"id":"pull","type":"curve","from":[0.8,0.5],"to":[0.4,0.5],"bend":0.12,"head":true,"color":"orange","stroke":4}
]}}
JSON
```

讲到下一步，就在同一张图上补一笔：

```sh
python3 -B "$W" edit '{"add":[{"id":"bulge","type":"circle","x":0.02,"y":0.22,"w":0.38,"h":0.56,"color":"orange","stroke":2,"motion":"fade"}],"text":"海水被拉出一个鼓包。"}'
```

## 画图速查

画布坐标从左上角起算，x、y、w、h 都取 0–1，y 轴向下。`drawing` 的 0–1 指文字旁边的配图区，`canvas` 的 0–1 指整页。

- **基础图元**：`text`、`rect`、`circle`、`line`、`polyline`、`arrow`（箭头画在最后一个点）、`bezier`（点数须是 4、7、10…）
- **图形宏**：脚本会先把宏展开成基础图元，手写贝塞尔太容易出错，优先用宏
  - `wave`：正弦波，可设 `cycles`、`amp`、`decay`
  - `curve`：从 `from` 到 `to` 的弧线，`head:true` 带箭头
  - `flow`：2–5 步，自动加箭头
  - `cycle`：3–5 项首尾相接的循环
  - `bars`：1–6 根柱子，可加 `labels`
- **颜色**：`ink`、`orange`、`rose`、`muted`、`none`，或 `#RRGGBB`。品牌色：橙 `#F7513C`、浅橙 `#FF8066`、粉 `#FA70AB`
- **动效**：`motion` 可选 `fade`、`rise`、`slide`、`pop`、`draw`（线条逐笔画出）；另有 `delay`（0–1 秒）、`duration`（0.1–2 秒）、`marker`（沿路径移动的圆点）、`timeline`（自编关键帧）
- **限制**：每页最多 12 个图元（宏按展开后计算），画布文字合计 ≤80 字，单个 text ≤40 字
- **跨页变形**：相邻两页用同一个图元 id，翻页时这个图元会就地变形，适合表现「同一个东西变了」

完整字段说明见 `references/canvas.md`。拿来就能用的版式（对比、流程、循环、时间线、柱状、逐步揭示）见 `references/recipes.md`。

## 用户的回应

白板上的输入只有在你调用 `ask` 或 `wait` 时才会交给你。要是你调用 `say`、`edit`、`close` 时用户已经写了东西，脚本会返回 `interrupted`，并带上他的原话。

| status | 意思 | 你该做 |
|---|---|---|
| `shown` / `queued` / `edited` | 已显示 / 已排队 / 已修改 | 继续讲 |
| `answer` | 用户点选或打字，原话在 `answer` 里，`on_page` 是他当时看的那页 | 据此决定下一句，用 `say` 回应（脚本会自动接在这条回答后面） |
| `continue` | 用户在最后一页按了空格，意思是「继续」 | 讲下一个要点 |
| `interrupted` | 用户插话了，你这次的操作没有执行 | 先回应他的原话，再继续 |
| `timeout` | 还没回应 | 可以再 `wait` 一两次，否则用文字继续 |
| `closed` / `dismissed` | 用户按 Esc 收起了白板 | 用文字继续；用户再次想看时才用 `say --new` |
| `editing` | 用户正在白板上打字 | `wait` 等他发出来 |
| `busy` | 白板正在放别的内容 | 确认要替换再加 `--new` |
| `invalid` | 页面不合规 | 按 `hint` 改，可以先用 `check` 试 |

问题返回 `queued` 时，继续用 `wait` 收取互动。以 `on_page` 判断用户回答的是哪一页。

如果宿主限制单条命令的时长，就用短一点的 `--wait`（比如 20 秒）多等几轮。

## 出问题时

- 窗口没出现，或返回 `opening`、`not-installed`、`launch-failed`：运行 `python3 -B "$W" doctor`，按每项的 `fix` 修复，再运行 `demo` 确认。
- 白板工具用不了时，告诉用户连接状态，然后用文字继续。不要改插件源码，也不要另写脚本去驱动播放器。
- 可选：只支持 MCP 的宿主可以运行 `python3 -B "$W" mcp`，工具名为 `whiteboard_say`、`whiteboard_ask`、`whiteboard_wait`、`whiteboard_edit`、`whiteboard_close`、`whiteboard_status`、`whiteboard_check`、`whiteboard_describe`，参数与命令行相同。

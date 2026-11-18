# 动态白板 · 输出端 skill 2.0

把 Dot 白板从 GPT-Live 里拆出来，做成一个独立的输出端 skill。任何能运行本机命令的大模型（Codex、Claude Code、个人 dot 的本地任务等）都能在回答时调用它：送一句话、画一张会动的图，或者问一个问题再等回答。只支持 MCP 的宿主也可以接入。

给模型看的说明在 `SKILL.md`，这份 README 是写给你的。

## 为什么之前接不进 GPT-Live

`GPT-Live白板.py` 只能挂到「你自己用 API 创建」的 GPT-Live 通话上：需要那场通话的 `session.id` 和创建它的 API 密钥。ChatGPT 自带的语音和个人 dot 的主对话都不会把这两样交给本地插件，所以这条路从结构上就接不通，不是代码 bug。这个 skill 不再依赖它。

## 安装

1. 把整个 `dynamic-whiteboard` 文件夹放到宿主读取技能的目录，例如：
   - Codex：`~/.codex/skills/dynamic-whiteboard`
   - Claude Code：`~/.claude/skills/dynamic-whiteboard`
   - 其他宿主：放到它读取技能的目录即可，路径里有中文没关系
2. 使用系统 Python 检查环境，再播放内置示例。
   ```sh
   python3 -B ~/.codex/skills/dynamic-whiteboard/scripts/board.py doctor
   python3 -B ~/.codex/skills/dynamic-whiteboard/scripts/board.py demo
   ```
   `doctor` 的每个失败项都附带 `fix` 命令。`demo` 弹出「声音怎样传播」就说明链路通了。

只支持 MCP 的宿主，在它的 MCP 配置里加一项（路径换成你的实际路径）：

```json
{"mcpServers": {"dynamic_whiteboard": {"type": "stdio", "command": "/usr/bin/python3",
  "args": ["-B", "/Users/你/.codex/skills/dynamic-whiteboard/scripts/board.py", "mcp"]}}}
```

## 和 1.4 插件比，改了什么

- **一个入口。**模型只调用 `scripts/board.py`：`say`、`ask`、`wait`、`edit`、`close`。会话 id、generation、revision、eventID 都由脚本自动维护。CLI 和 MCP 共用当前现场会话。
- **智能翻页。**用户还没看完前面的页时，新页自动排在后面，不再一下跳过用户没看到的内容。
- **插话不丢。**用户在白板上打了字，模型下一次调用 `say`、`edit` 或 `close` 时会拿到原话（`interrupted`），它回应之后再继续；按空格「继续」会自动续上。
- **尊重 Esc。**用户按 Esc 后 20 分钟内，模型不能自动重开，除非显式加 `--new`。用户正在打字时，不收起白板，也不强行跳页。
- **图形宏。**`wave`、`curve`、`flow`、`cycle`、`bars` 由脚本展开成基础图元，模型不用再手算贝塞尔控制点。原生播放器接收展开后的基础图元。
- **边讲边画。**`edit` 支持 `add`、`remove`、整组修改；用户刚作答时，改好的图会自动作为新的一页接在回答后面。
- **能自查。**`check` 不开窗口就能校验，`doctor` 检查系统、隔离属性、签名、脚本和数据目录。常见输入错误附带 `hint`，模型能自己改正。
- **说明重写。**SKILL.md 只讲模型需要的内容，完整语法和 12 个已验证的版式放在 `references/` 里。

## 文件

```
dynamic-whiteboard/
├── SKILL.md                 给模型看的使用说明
├── README.md                给你看的这份
├── Dot 白板.app             原生播放器（AppKit / Core Animation）
├── scripts/
│   ├── board.py             统一入口（命令行 + 可选 MCP）
│   ├── shapes.py            图形宏
│   ├── whiteboard.py        播放器文件协议（未改）
│   ├── canvas_schema.py     图元校验
│   ├── 演示文稿.py          文稿模型及输入保护
│   ├── 现场白板.py          现场会话与整批发页
│   └── 当前聊天.py          播放器的聊天跟随功能要用（未改）
├── references/canvas.md     完整画布语法和宏参数
├── references/recipes.md    12 个已验证的版式
└── examples/声音怎样传播.白板.json
```

没有带进来的：`GPT-Live白板.py` 和它依赖的 `连接依赖.zip`（websocket 库）。需要时，原插件包里仍然有。

## 需要知道的

- 本机测试使用 Apple 芯片 Mac、macOS 27.0.1 和系统 Python 3.9.6。三页示例、八页整批追加、空格、Esc、原位改图、输入保护、中文文本和选项回传均通过原生播放器验证。跨页曲线的原位变形通过 Core Animation 图层身份和路径动画检查。
- 同一时刻由一个对话主导现场白板。新旧两套共用同一个数据目录 `~/Library/Application Support/DotWhiteboard` 和同一个窗口，可以并存。建议停用旧插件里的 GPT-Live 连接，免得两边同时往白板写内容。
- 白板上的输入，只有在模型调用 `ask` 或 `wait`（或下一次 `say`）时才会交给它。这是「输出端」的天然边界：模型不在等的时候，用户的话会先存在白板上。

# Give Your GPT Live a Whiteboard

A model can open a native Mac whiteboard mid-conversation, sketch an idea, ask a question and use your answer on the next page. The host decides when to draw and what to say.

**[Download the standalone skill for Apple silicon](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/download/v2.0.0/dynamic-whiteboard-skill-2.0.0-macos-arm64.zip)** · [Version 2.0 release](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/tag/v2.0.0)

![A native animation showing how vibration travels](代码/白板插件/assets/native-demo.gif)

## Install on a Mac

The bundled player requires Apple silicon and macOS 27 or later. Extract the ZIP and place the entire `dynamic-whiteboard` folder in your host’s skills directory. For Codex, use `~/.codex/skills/`. Test it with the system Python 3.

```sh
W="$HOME/.codex/skills/dynamic-whiteboard/scripts/board.py"
/usr/bin/python3 -B "$W" doctor
/usr/bin/python3 -B "$W" demo
```

The demo plays three pages about sound. Press **Space** to advance, or **Esc** to close. Space stays in the text field while you type. [Installation details](代码/白板插件/skills/dynamic-whiteboard/README.md)

## Use it in a conversation

A model with local command access can show pages with `say`, ask a question with `ask`, update shapes with `edit`, resume waiting with `wait` and dismiss the board with `close`. For example, a host can start an exercise check-in with this call.

```sh
/usr/bin/python3 -B "$W" ask "Have you exercised today?" --choice "Yes" --choice "Not yet"
```

The call returns the viewer’s reply. The host uses it to write the next page. The skill tracks session IDs, queues unread pages and preserves text in progress. Models can compose text, paths and keyframes directly or use the wave, curve, flow, cycle and bar macros. [Drawing reference](代码/白板插件/skills/dynamic-whiteboard/references/canvas.md) · [Layout recipes](代码/白板插件/skills/dynamic-whiteboard/references/recipes.md)

For a local stdio MCP host, start `/usr/bin/python3 -B "/absolute/path/to/dynamic-whiteboard/scripts/board.py" mcp`. It exposes eight tools for displaying, asking, waiting, editing, closing, inspecting state, validating and describing the canvas. The host supplies the model and scheduling. The standalone skill runs without an API key.

## Plugin and native source

The full plugin lives in [代码/白板插件](代码/白板插件/). Install from that directory when using the complete plugin checkout. Its manifests also expose the 1.4 tools for existing integrations. The optional voice adapter in `运行时/scripts/GPT-Live白板.py` targets developer-owned GPT-Live API sessions. Autonomous invocation from the built-in ChatGPT voice experience remains unverified.

[Native Swift sources](代码/桌面白板/源码/) power the AppKit and Core Animation player. To rebuild both plugin players from a checkout, run `./代码/构建播放器.sh` on a Mac with the Xcode Command Line Tools. The [1.4 release](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/tag/v1.4.0) preserves the original plugin layout.

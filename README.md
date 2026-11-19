# Give Your GPT Live a Whiteboard

A conversation model can open a whiteboard, build a drawing as it explains, ask a question, and use the viewer’s answer on the next page.

**[Download the standalone 4.0 Mac skill](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/download/v4.0.0/dynamic-whiteboard-skill-4.0.0-macos-arm64.zip)** · [Release notes](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/tag/v4.0.0)

## Run on a Mac

Extract the ZIP and place the entire `dynamic-whiteboard` directory in your host’s skills directory. The release includes the Apple silicon app, local rendering engine, drawing tools and examples. It was tested on macOS 27.0.1 with the system Python 3.

```sh
W="$HOME/.codex/skills/dynamic-whiteboard/scripts/board.py"
/usr/bin/python3 -B "$W" doctor
/usr/bin/python3 -B "$W" demo 潮汐
```

The tide demo has three pages. Try `demo 哑铃训练` for six animated exercise pages, or `demo 声音怎样传播` to play a 2.0 document. Press Space to continue, type or choose an answer, and press Esc to close. While typing, Space stays in the text field.

## Draw during a conversation

The host supplies the model and decides when to draw. Use `say` for up to eight pages, `ask` to collect a reply, `edit` to change the drawing in place and `wait` to resume listening. For a local stdio MCP connection, run `/usr/bin/python3 -B "/absolute/path/to/dynamic-whiteboard/scripts/board.py" mcp`. The eight tools share the same board as the CLI.

```sh
/usr/bin/python3 -B "$W" ask "Have you exercised today?" --choice "Yes" --choice "Not yet"
```

Version 4 uses an AppKit window with a persistent system WebKit view. A sketch can combine styled text, bundled icons, paths, gradients, camera movements and animation. The renderer reports layout measurements back to the caller. Rendering and interaction run locally. [Sketch guide](代码/白板插件/skills/dynamic-whiteboard/references/sketch.md) · [Scene format](代码/白板插件/skills/dynamic-whiteboard/references/scene.md)

## Plugin and source

[The full plugin](代码/白板插件/) includes the standalone skill and the legacy tools for existing integrations. The optional voice adapter targets developer-owned GPT-Live API sessions. Autonomous invocation and reply delivery in a hosted ChatGPT voice call remain unverified. Use the [native window source](代码/白板插件/skills/dynamic-whiteboard/native/) and [rendering engine](代码/白板插件/skills/dynamic-whiteboard/engine/) to change the player. Run `./代码/构建播放器.sh` to rebuild both the current and compatibility players.

The [2.0 release](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/tag/v2.0.0) preserves the previous Core Animation player and standalone download. [Installation details](代码/白板插件/skills/dynamic-whiteboard/README.md) · [1.4 release](https://github.com/zhangxuyuan20251443-coder/give-your-gpt-live-a-whiteboard/releases/tag/v1.4.0)

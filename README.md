# Give Your GPT Live a Whiteboard

A macOS whiteboard that a conversation model can open, draw on and hand back to you. The model chooses what to show. The plugin renders short pages with AppKit and Core Animation and returns your input to the caller. It runs without a local language model.

![A native animation showing how vibration travels](assets/native-demo.gif)

## Try the first draft

The bundled player targets Apple Silicon and macOS 27 or later. The tool server uses the system Python 3. Run the following from a checkout to open an interactive page on your Mac.

```sh
/usr/bin/python3 -B '运行时/scripts/演示文稿.py' present \
  --file examples/hello.json
```

Press **Space** to continue and **Esc** to leave. You can also type or select an answer on an interactive page. While you are typing, the space bar stays in the text field. The example is an offline document. Live follow-up pages come from a connected model.

## Connect a host

The root `plugin.json` and `mcp.json` describe a local desktop plugin. A desktop host can load the bundled skill and start its MCP server. For a host that accepts a stdio command, use `/usr/bin/python3 -B "/absolute/path/to/运行时/scripts/演示文稿.py" mcp`.

- `live_board` opens the board, streams new pages into the same session and can advance as the speaker talks.
- `live_ask` displays a question and returns a choice or typed reply. `live_input` can also wait for input on an existing board.
- `describe`, `read_document` and `edit` let the model inspect the drawing vocabulary and update existing shapes. `close` puts the board away.

For example, a model can call `live_ask` with the following arguments when an exercise reminder arrives.

```json
{"id":"exercise","text":"Have you moved today?","choices":["Yes","Not yet"]}
```

The result includes the user's answer and an event ID. The model can use those to draw the next page in the same session. The host owns scheduling and the conversation. The player supports text, paths, arrows, shapes and keyframe animation.

## GPT-Live integration status

A developer who owns a GPT-Live API voice session can register this plugin's tools and connect the bundled adapter. Run `/usr/bin/python3 -B '运行时/scripts/GPT-Live白板.py' --tool-config` to print the settings to merge at session creation. Supply the owning project's `OPENAI_API_KEY` and `OPENAI_LIVE_SESSION_ID` through the environment, then run the same command without `--tool-config`.

Local tests exercised the installed renderer, voice-interruption events and tool replies with a simulated Live connection. Autonomous invocation from a personal dot during a hosted ChatGPT voice call still needs verification.

## Rebuild the native player

Run `./build.sh` on a Mac with the Xcode Command Line Tools installed. It compiles the two Swift files in `Sources/` and signs the bundled app locally. The Python tool server and the WebSocket transport are included in the checkout.

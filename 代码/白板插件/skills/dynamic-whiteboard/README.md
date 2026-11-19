# 动态白板 4.0

模型可以在同一场对话里开板、画图、提问，再按你的回答续页。每页都能用文字、图形、镜头和动画重新编排。渲染引擎随包提供，在同一个窗口更新画面。

## 安装和试用

在 Apple 芯片 Mac 上解压，将整个 `dynamic-whiteboard` 文件夹放进宿主的技能目录。Codex 的目录是 `~/.codex/skills/`。安装包带有已编译的 AppKit / WebKit 窗口，使用系统 Python 3。

```sh
W="$HOME/.codex/skills/dynamic-whiteboard/scripts/board.py"
/usr/bin/python3 -B "$W" doctor
/usr/bin/python3 -B "$W" demo 潮汐
```

`demo 哑铃训练` 播放六页动作示意，`demo 声音怎样传播` 回放旧版三页文稿。空格往下看，末页按空格会向模型返回「继续」。输入过程中可以打空格，回车提交，Esc 收起窗口。按 Esc 后 20 分钟内，普通发页会尊重退出状态。

## 接入对话

能执行本机命令的模型可以按 [SKILL.md](SKILL.md) 调用 `say`、`ask`、`wait`、`edit` 和 `close`。宿主使用 stdio MCP 时，以系统 Python 启动安装目录的 `scripts/board.py mcp`，即可使用八个 `whiteboard_*` 工具。模型负责决定何时开板和说什么。回答会回到正在等待的调用，或由下一次工具调用取回。

```sh
/usr/bin/python3 -B "$W" ask "今天运动了吗？" --choice "运动了" --choice "还没有"
```

## 画面与兼容性

- 每次可送 1–8 页。速写支持富文本、渐变、路径、镜头推拉、沿线动画、同名元素变形和 1541 个内置图标。用 `check` 可以预估版面，原生窗口显示后会回传实测布局。
- 可用的图元、时间和版式范围见[场景规范](references/scene.md)与[速写参考](references/sketch.md)。2.0 的 `drawing`、`canvas` 和已有 JSON 文稿可继续传入，旧文稿在新引擎中转换绘制。[旧画布说明](references/canvas.md) · [旧版图形配方](references/recipes.md)
- 原生窗口内使用系统 WebKit。本机服务只监听回环地址，跟随窗口退出。源码安装可以运行 `board.py build` 重新编译。有本机浏览器时，缺少原生窗口也可通过浏览器显示。
- 此发行包在 Apple 芯片、macOS 27.0.1 和系统 Python 3.9.6 上验证。单独的压缩包可供本机命令或 MCP 宿主使用。ChatGPT 内置语音自主调用、取回回答的完整流程仍待实测。
- [Lucide 图标许可](engine/LICENSE-lucide.txt)随安装包分发。

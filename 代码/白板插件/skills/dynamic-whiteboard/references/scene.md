# 场景 JSON（底层格式）

速写会编译成这种场景，渲染引擎只认它。日常用速写就够了；只有需要逐个数值精确控制时，才直接写场景：`say --json '{"pages":[{"text":"…","board":{…}}]}'`。

```json
{"v": 2, "transition": "blend", "bg": "paper",
 "cam": [{"at": 1.5, "x": 40, "y": 52, "z": 1.3, "dur": 1.2}],
 "els": [
   {"id": "t1", "k": "text", "x": 8, "y": 20, "size": 7, "weight": 300, "runs": [{"t": "潮汐从哪来？"}]},
   {"id": "t2", "k": "text", "x": 8, "y": 32, "size": 10, "runs": [{"t": "月球在"}, {"t": "拉", "b": 1, "c": "orange"}, {"t": "海水"}], "at": 0.15},
   {"id": "earth", "k": "circle", "x": 30, "y": 66, "r": 10, "fill": "#7FB2E5", "at": 0.3},
   {"id": "pull", "k": "path", "d": "M1232 330 C1100 380 900 480 672 580", "stroke": "orange", "sw": 5.4, "head": "end", "loop": ["flow"], "at": 0.45}
 ]}
```

**单位：**x、y 为舞台宽、高的 %；`size`、`r` 为高度 %；`path.d` 用 1600×1000 的舞台像素。

**元素公共字段：**
- `id`：字母、数字、`-`、`_`，同页唯一。
- `k`：元素类型，见下表。
- 时间：`at`（出场秒）、`dur`、`in`（出场效果）、`ease`、`loop`（持续动作数组）。
- 运动：`move`（[dx, dy]，单位 %）、`moveAt`、`moveDur`、`along`（路径元素的 id）、`alongDur`、`alongLoop`。
- 质感：`alpha`、`rot`、`top`、`glow`、`shadow`。
- 位置：`rel`（`{"to": id, "side": "below|above|left|right|on", "gap": 2}`）。
- 自定义关键帧：`kf`，格式 `{"x"|"y"|"scale"|"rotate"|"opacity": [[秒, 值], …]}`。

| k | 专有字段 |
|---|---|
| `text` | `x` `y` `align`（l/c/r）`w`（换行宽度 %）`size` `font` `weight` `color` `lh` `ls` `nowrap` `count` `runs`：`[{t, b?, c?, hl?, st?, i?}]` |
| `circle` | `x` `y` `r` `fill` `stroke` `sw` `dash`（dash/dots） |
| `rect` | `x` `y` `w` `h` `rx` `fill` `stroke` `sw` `dash` |
| `path` | `d` `fill` `stroke` `sw` `dash` `head`（start/end/both）`dot`（`{c, r, dur}`） |
| `icon` | `name` `x` `y` `size` `color` `fill` `sw` |
| `image` | `src`（本机绝对路径）`x` `y` `w` `h` `rx` `fit` |

**颜色**可用 `ink muted line paper orange peach pink white black`，或 `#RRGGBB`。`fill` 还可以写成 `a>b` 表示渐变。

## 旧格式

旧版播放器的 `drawing` / `canvas` 图元页（0–1 坐标，见 `examples/声音怎样传播.白板.json`），以及只有标题的页，仍然可以 `say` 或 `present`。宿主会把它们自动转换成场景显示。新内容请用速写。

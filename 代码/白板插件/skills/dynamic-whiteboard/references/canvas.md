# 画布语法（完整版）

`board.py describe` 是这份文档的速查版。所有内容都是有限的纯数据：不能写 URL、脚本或表达式。

## 页面

```json
{"text": "这一页要说的一句话", "choices": ["选项"], "drawing": {"nodes": [{"id": "dot", "type": "circle", "x": 0.4, "y": 0.3, "w": 0.2, "h": 0.2}]}, "id": "intro"}
```

| 字段 | 说明 |
|---|---|
| `text` | 必填，≤120 字，建议 6–18 字。纯文字页和 `drawing` 页直接显示它；`canvas` 页把它当页标题，页面上要看见的字放进画布 |
| `choices` | 可选，最多 3 个，每个 ≤16 字。无论有没有选项，用户都可以在任意一页打字回答 |
| `drawing` | 文字旁的配图区。坐标 0–1 指这块配图区 |
| `canvas` | 整页自由画布。坐标 0–1 指整页 |
| `id` | 可省略，脚本自动生成并保证不重复 |

`drawing` 和 `canvas` 二选一。没有图的页面是对话页：暖白纸面，宋体提问、苹方陈述，右侧有一条橙粉曲线随提问、输入和等待变形。

## 画布对象

```json
{"nodes": [{"id": "dot", "type": "circle", "fill": "orange"}], "transition": "crossfade"}
```

- `nodes`：1–12 个图元，宏按展开后计数。
- `transition`：本页进场方式，可选 `crossfade`（默认）、`cut`、`lift`、`push`。

## 坐标

- 原点在左上角，x 向右，y 向下，全部是 0–1 的比例。
- `text`、`rect`、`circle` 用外框 `x y w h` 定位。
- `line`、`polyline`、`arrow`、`bezier` 用 `points: [[x, y], …]` 定位。

## 通用字段

| 字段 | 取值 |
|---|---|
| `id` | 字母、数字、`-`、`_`，≤48 字符，页内唯一。要改的图元、要跨页变形的图元都应该命名 |
| `color` | 描边或文字颜色。可选 `ink`（默认）、`orange`、`rose`、`muted`、`none`，或 `#RRGGBB` |
| `fill` | 填充色，取值同 `color`，默认 `none` |
| `stroke` | 线宽 1–10 |
| `motion` | 进场动效：`none`、`fade`（默认）、`rise`、`slide`、`pop`、`draw`。`draw` 让线条逐笔画出 |
| `delay` | 0–1 秒，用来错峰进场 |
| `duration` | 0.1–2 秒 |
| `marker` | 只能放在 `line`、`polyline`、`bezier` 上：`{"radius": 2–18, "duration": 0.1–4, "color": "ink"}`，一个圆点沿路径移动。三个字段都要给 |
| `timeline` | 自编关键帧，见下文 |

品牌色：橙 `#F7513C`、浅橙 `#FF8066`、粉 `#FA70AB`。深色正文用 `ink`，次要信息用 `muted`。

## 基础图元

| type | 字段 | 说明 |
|---|---|---|
| `text` | `text`(1–40 字) `x y w h` `size` `weight` `align` `effect` `color` | `size` 0.03–0.6，是字号上限。字放不下 `w` 时会被缩小，所以大字要给足 `w`。`weight` 可选 `light`、`regular`、`semibold`；`align` 可选 `left`、`center`、`right`；`effect` 可选 `none`、`underline`、`outline` |
| `rect` | `x y w h` `fill` `color` `stroke` | 只要实心色块时，设 `color:"none"` |
| `circle` | `x y w h` `fill` `color` `stroke` | 外框内切的圆或椭圆。画布不是正方形，w=h 可能显示成椭圆；看到椭圆就按宽高比调小 `w` |
| `line` | `points`（2 个） | 直线 |
| `polyline` | `points`（2–32 个） | 折线 |
| `arrow` | `points`（2 个以上） | 箭头画在最后一个点 |
| `bezier` | `points` 共 4、7、10…个 | `[起点, 控制1, 控制2, 终点, 控制1, 控制2, 终点, …]`。手写容易出错，优先用 `wave`、`curve` 宏 |

## 关键帧 timeline

```json
{"id": "track", "type": "line", "points": [[0.1, 0.5], [0.9, 0.5]], "timeline": [
  {"property": "x", "keys": [[0, -0.05], [0.6, 0]], "easing": "ease-out"},
  {"property": "draw", "keys": [[0, 0], [0.1, 0], [0.7, 1]]}
]}
```

- 每个图元 1–7 条轨道，同一属性不能重复。
- 每条轨道 2–24 帧。每帧是 `[秒, 值]`，从 0 秒开始，时间严格递增，最长 8 秒。
- `easing` 可选 `linear`、`ease`（默认）、`ease-in`、`ease-out`。

| property | 值域 | 含义 |
|---|---|---|
| `x` / `y` | −1–1 | 相对原位置的位移，单位是画布比例 |
| `scale` | 0.05–3 | 缩放 |
| `rotation` | −720–720 | 旋转角度 |
| `opacity` | 0–1 | 透明度 |
| `draw` | 0–1 | 线条描出的比例（文字不支持） |

系统开启「减少动态效果」时，播放器直接呈现终态，所以别把信息只放在动画里。

## 限制

| 项 | 上限 |
|---|---|
| 一次 `say` | 1–8 页（播放器每批收 4 页，脚本会自动分批） |
| 一页图元 | 12 个（宏按展开后计算） |
| 一页画布文字 | 合计 80 字 |
| 单个 text | 40 字 |
| 页面 `text` | 120 字 |
| choices | 3 个，每个 16 字 |
| 等待 | 0–120 秒 |
| 白板保留 | 最近 80 页，文稿最大 512 KiB |

## 图形宏

脚本会把宏展开成基础图元，播放器看不到宏。宏的 `id` 省略时自动生成，形如 `wave1`。`edit` 可以用宏的 `id` 一次改动或删除它展开出的整组图元。

### wave：正弦波

```json
{"type": "wave", "id": "w", "x": 0.5, "y": 0.3, "w": 0.45, "h": 0.4, "cycles": 2, "amp": 1, "decay": 1, "flip": false, "color": "orange", "stroke": 3}
```

- `cycles`：0.5–5 个完整周期。
- `amp`：振幅，0–1，表示占半高的比例。
- `decay`：0.1–1，小于 1 时每半周衰减，适合表现阻尼。
- `flip`：设为 true 时第一段向下。
- 可以带线条样式和 `marker`，默认 `motion: draw`。
- 展开为 1 个 `bezier`，id 与宏相同。

### curve：弧线和弯箭头

```json
{"type": "curve", "id": "pull", "from": [0.8, 0.5], "to": [0.4, 0.5], "bend": 0.2, "head": true, "color": "orange", "stroke": 4}
```

- `bend`：−1–1，表示弯曲量，正负决定弯向哪一侧。
- `head: true` 在终点加箭头，箭头在曲线画完时出现。
- 展开为 `id`（bezier），加上 `id-head`（arrow）。

### flow：步骤加箭头

```json
{"type": "flow", "id": "steps", "items": ["听见", "理解", "回应"], "x": 0.04, "y": 0.38, "w": 0.92, "h": 0.24, "direction": "row"}
```

- `items` 2–5 个，逐个错峰进场。
- `direction` 可选 `row`、`column`。
- 还可设 `size`、`weight`、`color`（文字）、`arrow_color`（默认 orange）、`stroke`、`motion`。
- 展开为 `steps-0…`（text）和 `steps-to1…`（arrow），共 2k−1 个图元。

### cycle：首尾相接的循环

```json
{"type": "cycle", "id": "loop", "items": ["蒸发", "凝结", "降水", "汇流"], "x": 0.25, "y": 0.08, "w": 0.5, "h": 0.84}
```

- `items` 3–5 个，从正上方开始顺时针排开。
- `heads`：4 项及以下默认带箭头（3k 个图元），5 项不能带箭头（2k 个图元）。
- 还可设 `size`、`weight`、`color`、`arrow_color`、`stroke`。
- 展开为 `loop-0…`（text）、`loop-arc0…`（bezier）和 `loop-arc0-head…`（arrow）。

### bars：柱状对比

```json
{"type": "bars", "id": "sales", "values": [3, 6, 12], "labels": ["一月", "二月", "三月"], "x": 0.52, "y": 0.1, "w": 0.44, "h": 0.8, "color": "orange"}
```

- `values`：1–6 个非负数。
- `labels`：可选，与 `values` 等长。
- `max`：可选，指定比例尺上限。
- `colors`：可选，逐根指定颜色，与 `values` 等长。
- 展开为 `sales-0…`（rect）和 `sales-label0…`（text）。

## edit

```json
{"node": "pull", "set": {"color": "#FA70AB"},
 "changes": [{"node": "earth", "set": {"fill": "orange"}}],
 "add": [{"id": "bulge", "type": "circle", "x": 0.02, "y": 0.2, "w": 0.38, "h": 0.6, "color": "orange"}],
 "remove": ["moon"],
 "text": "新的主句",
 "transition": "cut"}
```

- 所有字段都可省略，至少给一项。`page` 指定要改的页 id，省略时改当前页。
- 执行顺序：先 set，再 remove，最后 add。
- 新加的图元按自己的 `motion` 进场，留下的图元原位变形。
- 用户已经作答时，回合已经切换：改好的图会作为一页新内容接在回答后面。

## 跨页变形

同一会话的相邻页面采用相同布局、都为节点命名，并复用相同类型和 id 的图元时，翻页会对其路径、位置或样式做原位过渡。新增图元按各自的 motion 入场。使用 cut 或切换配图与整页布局时直接切换。适合表现「同一个东西变了」，例如同一条波振幅变大，或同一个词移到新位置。

## 完整文稿（present）

```json
{"version": 1, "title": "声音怎样传播",
 "pages": [{"id": "vibration", "title": "声音，从振动开始。"}]}
```

- 页面字段：`id`、`title`、`body`（≤160 字）、`canvas`、`interaction`、`scene`。
  - `interaction` 可设 `choices`、`placeholder`。
  - `scene` 只用于纯文字页：`layout` 可选 `editorial`、`focus`、`countdown`；`motion` 可选 `slide`、`rise`、`quiet`、`pop`、`sweep`、`breathe`；`accent` 可选 `orange`、`ink`、`rose`；`decoration` 可选 `none`、`strides`、`rings`。
- 1–80 页，canvas 里也可以用宏。
- 用户用空格和方向键翻页，⌘S 另存为可编辑 JSON，⌘O 重新打开。

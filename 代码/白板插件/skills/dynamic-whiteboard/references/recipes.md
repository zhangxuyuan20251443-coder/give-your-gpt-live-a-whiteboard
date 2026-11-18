# 版式配方

下面每段 JSON 都通过了 `board.py check`，可以直接 `say`（或 `ask`、`edit`）。改字、改颜色、改位置都行，结构保持就好。坐标说明见 `canvas.md`。

送页的通用写法：

```sh
python3 -B "$W" say <<'JSON'
（下面任意一段页面 JSON）
JSON
```

## 1 杂志式两行：一句话里的重点

适合开场和结论。浅色引子加橙色重点，一条细线收尾。

```json
{"text":"现在，动起来。","canvas":{"transition":"lift","nodes":[
  {"id":"lead","type":"text","text":"现在，","x":0.04,"y":0.1,"w":0.6,"h":0.32,"size":0.3,"weight":"light","motion":"rise"},
  {"id":"key","type":"text","text":"动起来。","x":0.14,"y":0.46,"w":0.7,"h":0.34,"size":0.32,"weight":"semibold","color":"#F7513C","motion":"rise","delay":0.15},
  {"id":"rule","type":"line","points":[[0.04,0.9],[0.96,0.9]],"color":"#F7513C","stroke":2,"motion":"draw","delay":0.35}
]}}
```

## 2 因果：A 导致 B

```json
{"text":"压力升高，沸点也升高。","drawing":{"nodes":[
  {"id":"cause","type":"text","text":"压力 ↑","x":0.02,"y":0.38,"w":0.34,"h":0.2,"size":0.14,"align":"center","motion":"rise"},
  {"id":"link","type":"arrow","points":[[0.38,0.48],[0.62,0.48]],"color":"orange","stroke":4,"motion":"draw","delay":0.3},
  {"id":"effect","type":"text","text":"沸点 ↑","x":0.64,"y":0.38,"w":0.34,"h":0.2,"size":0.14,"align":"center","color":"orange","weight":"semibold","motion":"rise","delay":0.6}
]}}
```

## 3 对比：同一种东西的两种状态

```json
{"text":"振幅越大，听起来越响。","drawing":{"nodes":[
  {"id":"soft-label","type":"text","text":"小振幅","x":0.02,"y":0.02,"w":0.3,"h":0.1,"size":0.08,"color":"muted"},
  {"id":"soft","type":"wave","x":0.02,"y":0.12,"w":0.96,"h":0.3,"cycles":3,"amp":0.35,"color":"rose","stroke":4},
  {"id":"loud-label","type":"text","text":"大振幅","x":0.02,"y":0.5,"w":0.3,"h":0.1,"size":0.08,"color":"muted"},
  {"id":"loud","type":"wave","x":0.02,"y":0.6,"w":0.96,"h":0.38,"cycles":3,"color":"orange","stroke":5,"delay":0.3}
]}}
```

## 4 流程：一步接一步

```json
{"text":"一次请求的旅程","canvas":{"nodes":[
  {"id":"title","type":"text","text":"一次请求的旅程","x":0.04,"y":0.08,"w":0.6,"h":0.16,"size":0.14,"weight":"semibold"},
  {"id":"steps","type":"flow","items":["浏览器","DNS","服务器","数据库"],"x":0.04,"y":0.45,"w":0.92,"h":0.2}
]}}
```

要竖排，给 flow 加上 `"direction":"column"`，再把 `w` 调窄、`h` 调高。

## 5 循环：首尾相接

```json
{"text":"水循环","canvas":{"nodes":[
  {"id":"loop","type":"cycle","items":["蒸发","凝结","降水","汇流"],"x":0.3,"y":0.06,"w":0.4,"h":0.88,"arrow_color":"#FA70AB"}
]}}
```

4 项循环刚好占满 12 个图元。还想加标题，就改用 3 项，或者加 `"heads":false` 去掉箭头。

## 6 柱状：数量对比

```json
{"text":"三个月，销量翻了两番。","drawing":{"nodes":[
  {"id":"sales","type":"bars","values":[3,6,12],"labels":["一月","二月","三月"],"x":0.08,"y":0.08,"w":0.84,"h":0.84,"colors":["#FF8066","#FA70AB","#F7513C"]}
]}}
```

## 7 时间线：几个阶段

```json
{"text":"一棵树的四个阶段","canvas":{"nodes":[
  {"id":"axis","type":"line","points":[[0.05,0.55],[0.95,0.55]],"color":"muted","stroke":2,"motion":"draw","duration":1.2},
  {"id":"d1","type":"circle","x":0.115,"y":0.52,"w":0.02,"h":0.06,"fill":"orange","color":"none","motion":"pop","delay":0.2},
  {"id":"d2","type":"circle","x":0.365,"y":0.52,"w":0.02,"h":0.06,"fill":"orange","color":"none","motion":"pop","delay":0.4},
  {"id":"d3","type":"circle","x":0.615,"y":0.52,"w":0.02,"h":0.06,"fill":"orange","color":"none","motion":"pop","delay":0.6},
  {"id":"d4","type":"circle","x":0.865,"y":0.52,"w":0.02,"h":0.06,"fill":"#F7513C","color":"none","motion":"pop","delay":0.8},
  {"id":"l1","type":"text","text":"种子","x":0.025,"y":0.64,"w":0.2,"h":0.12,"size":0.08,"align":"center","motion":"rise","delay":0.25},
  {"id":"l2","type":"text","text":"发芽","x":0.275,"y":0.64,"w":0.2,"h":0.12,"size":0.08,"align":"center","motion":"rise","delay":0.45},
  {"id":"l3","type":"text","text":"成树","x":0.525,"y":0.64,"w":0.2,"h":0.12,"size":0.08,"align":"center","motion":"rise","delay":0.65},
  {"id":"l4","type":"text","text":"结果","x":0.775,"y":0.64,"w":0.2,"h":0.12,"size":0.08,"align":"center","color":"#F7513C","weight":"semibold","motion":"rise","delay":0.85}
]}}
```

圆点的外框是画布比例。如果看起来是椭圆，就按画布的宽高比把 `w` 调小一点。

## 8 逐步揭示：先骨架，讲一步补一笔

第一步，`say` 骨架：

```json
{"text":"月球把近侧海水拉得更强。","drawing":{"nodes":[
  {"id":"earth","type":"circle","x":0.06,"y":0.28,"w":0.3,"h":0.44,"fill":"rose","color":"none","motion":"pop"},
  {"id":"moon","type":"circle","x":0.82,"y":0.42,"w":0.1,"h":0.16,"fill":"ink","color":"none","motion":"pop","delay":0.2}
]}}
```

讲到引力时，`edit` 补上箭头：

```json
{"add":[{"id":"pull","type":"curve","from":[0.8,0.5],"to":[0.4,0.5],"bend":0.12,"head":true,"color":"orange","stroke":4}]}
```

讲到潮峰时，再补一个轮廓并换主句：

```json
{"add":[{"id":"bulge","type":"circle","x":0.02,"y":0.22,"w":0.38,"h":0.56,"color":"orange","stroke":2,"motion":"fade"}],"text":"近侧和远侧各鼓起一个潮峰。"}
```

## 9 跨页变形：同一个东西变了

两页用同一个 id `string`，翻页时这条波原位变大。

```json
{"pages":[
  {"text":"轻轻拨一下。","drawing":{"nodes":[{"id":"string","type":"wave","x":0.05,"y":0.3,"w":0.9,"h":0.4,"cycles":3,"amp":0.3,"color":"rose","stroke":3}]}},
  {"text":"用力拨，振幅变大。","drawing":{"nodes":[{"id":"string","type":"wave","x":0.05,"y":0.08,"w":0.9,"h":0.84,"cycles":3,"color":"orange","stroke":5,"motion":"none"}]}}
]}
```

两页的 `cycles` 保持一致，点数才相同，变形最顺。

## 10 沿路径移动：信号、粒子、路线

```json
{"text":"信号沿着这条路走。","drawing":{"nodes":[
  {"id":"route","type":"bezier","points":[[0.05,0.7],[0.3,0.1],[0.6,0.9],[0.95,0.3]],"color":"orange","stroke":3,"motion":"draw","marker":{"radius":7,"duration":1.6,"color":"ink"}}
]}}
```

## 11 推进的波前：关键帧错峰

```json
{"text":"振动向远处传递。","drawing":{"nodes":[
  {"id":"f0","type":"bezier","points":[[0.1,0.15],[0.25,0.32],[0.25,0.68],[0.1,0.85]],"color":"#F7513C","stroke":3,
   "timeline":[{"property":"draw","keys":[[0,0],[0.05,0],[0.6,1]]},{"property":"x","keys":[[0,-0.05],[0.6,0]],"easing":"ease-out"}]},
  {"id":"f1","type":"bezier","points":[[0.38,0.15],[0.53,0.32],[0.53,0.68],[0.38,0.85]],"color":"#FF8066","stroke":4,
   "timeline":[{"property":"draw","keys":[[0,0],[0.2,0],[0.75,1]]},{"property":"x","keys":[[0,-0.05],[0.75,0]],"easing":"ease-out"}]},
  {"id":"f2","type":"bezier","points":[[0.66,0.15],[0.81,0.32],[0.81,0.68],[0.66,0.85]],"color":"#FA70AB","stroke":5,
   "timeline":[{"property":"draw","keys":[[0,0],[0.35,0],[0.9,1]]},{"property":"x","keys":[[0,-0.05],[0.9,0]],"easing":"ease-out"}]}
]}}
```

## 12 提问：只在需要用户拍板时

用 `ask`，一次一个问题，最多 3 个选项。用户也可以直接打字。

```json
{"text":"你更想先弄懂哪一段？","choices":["振动","传播","响度"]}
```

拿到 `answer` 之后，按他的选择继续 `say`，不用再问一遍。

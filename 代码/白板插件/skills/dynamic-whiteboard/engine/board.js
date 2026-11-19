/* 动态白板 · 渲染引擎
 * 读 content.json 的页面（page.board 场景），画在 1600×1000 的舞台上。
 * 坐标：x 为宽度 %，y 为高度 %；字号、半径为高度 %。
 * 同 id 的元素跨页 / 编辑时就地变形；新元素按 at 出场；离开的元素淡出。
 */
(() => {
  'use strict';
  const W = 1600, H = 1000, SX = 16, SY = 10;
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (s) => document.querySelector(s);
  const PAL = { ink: '#2F2526', muted: '#9B8177', line: '#E8DAD1', paper: '#FBF5EF', orange: '#F7513C', peach: '#FF8066',
    pink: '#FA70AB', rose: '#FA70AB', white: '#FFFFFF', black: '#1C1617' };
  const FONTS = {
    sans: '"PingFang SC", -apple-system, "Helvetica Neue", "Noto Sans CJK SC", "Noto Sans SC", sans-serif',
    serif: '"Songti SC", "STSong", "Noto Serif CJK SC", "Noto Serif SC", serif',
    kai: '"Kaiti SC", "STKaiti", "KaiTi", "Noto Serif CJK SC", serif',
    hand: '"Hannotate SC", "HanziPen SC", "Kaiti SC", "STKaiti", "Noto Serif CJK SC", cursive',
    round: '"Yuanti SC", "STYuanti", "PingFang SC", "Noto Sans CJK SC", sans-serif',
    mono: '"SF Mono", "Menlo", "Noto Sans Mono CJK SC", monospace',
  };
  const EASE = { out: 'cubic-bezier(.16,1,.3,1)', back: 'cubic-bezier(.34,1.56,.64,1)', smooth: 'cubic-bezier(.45,0,.2,1)',
    linear: 'linear', in: 'cubic-bezier(.55,0,1,.45)', spring: 'cubic-bezier(.34,1.56,.64,1)' };
  const world = $('#world'), under = $('#under'), over = $('#over'), texts = $('#texts'), defs = $('#defs');
  const input = $('#input');
  let ICONS = {};

  const S = { content: null, showID: null, pageID: null, rev: null, turn: null, index: 0, pages: [], recs: new Map(),
    t0: 0, waiting: false, leaving: false, rafs: new Set(), seen: new Set(), title: '', editing: false };

  // ---------- 工具 ----------
  const col = (c, fallback) => {
    if (c === undefined || c === null) return fallback === undefined ? 'none' : col(fallback);
    if (c === 'none' || c === false) return 'none';
    return PAL[c] || c;
  };
  const rgba = (c, a) => {
    const h = col(c);
    if (!/^#[0-9a-f]{6}$/i.test(h)) return h;
    const n = parseInt(h.slice(1), 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  };
  const div = (cls) => { const e = document.createElement('div'); if (cls) e.className = cls; return e; };
  const svg = (tag, attrs) => { const e = document.createElementNS(NS, tag); if (attrs) setA(e, attrs); return e; };
  const setA = (e, attrs) => { for (const k in attrs) { if (attrs[k] === null || attrs[k] === undefined) e.removeAttribute(k); else e.setAttribute(k, attrs[k]); } };
  const now = () => performance.now();
  const anim = (rec, target, frames, opt) => {
    try { const a = target.animate(frames, opt); rec.anims.push(a); return a; } catch (e) { return null; }
  };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function gradient(spec) {
    const parts = spec.split('>').map((s) => col(s.trim()));
    const id = 'g' + parts.join('').replace(/[^a-z0-9]/gi, '');
    if (!document.getElementById(id)) {
      const g = svg('linearGradient', { id, x1: '0', y1: '0', x2: '1', y2: '1' });
      parts.forEach((c, i) => g.append(svg('stop', { offset: parts.length > 1 ? i / (parts.length - 1) : 0, 'stop-color': c })));
      defs.append(g);
    }
    return `url(#${id})`;
  }
  const fillOf = (f) => (!f || f === 'none') ? 'none' : (String(f).includes('>') ? gradient(f) : col(f));

  // ---------- 舞台缩放 ----------
  function fit() {
    const k = Math.min(innerWidth / W, innerHeight / H);
    const st = $('#stage');
    st.style.transform = `translate(${(innerWidth - W * k) / 2}px, ${(innerHeight - H * k) / 2}px) scale(${k})`;
  }
  addEventListener('resize', fit);

  // ---------- 元素 ----------
  function make(d) {
    const rec = { id: d.id, k: d.k, d: null, anims: [], extras: [] };
    if (d.k === 'text' || d.k === 'image') {
      const outer = div('el ' + (d.k === 'text' ? 'text' : 'imgel')), mv = div('mv'), inn = div('in');
      const body = d.k === 'text' ? div('body') : document.createElement('img');
      outer.append(mv); mv.append(inn); inn.append(body);
      texts.append(outer);
      Object.assign(rec, { outer, mv, inn, body, html: true });
    } else {
      const pos = svg('g', { class: 'pos' }), mv = svg('g', { class: 'mv' }), inn = svg('g', { class: 'in' });
      pos.append(mv); mv.append(inn);
      const shape = d.k === 'circle' ? svg('circle') : d.k === 'rect' ? svg('rect') : d.k === 'icon' ? svg('g', { class: 'ico' }) : svg('path');
      inn.append(shape);
      (d.top ? over : under).append(pos);
      Object.assign(rec, { outer: pos, mv, inn, shape, html: false, layer: d.top ? over : under });
    }
    return rec;
  }

  function renderRuns(body, d) {
    body.textContent = '';
    const split = d.in === 'type' || d.in === 'chars';
    for (const r of d.runs || [{ t: d.text || '' }]) {
      const span = document.createElement('span');
      if (r.b) span.style.fontWeight = Math.min(900, Math.max(600, (d.weight || 400) + 200));
      if (r.c) span.style.color = col(r.c);
      if (r.i) span.style.fontStyle = 'italic';
      if (r.st) span.classList.add('st');
      if (r.hl) {
        const hc = r.hl === true || r.hl === 1 ? 'pink' : r.hl;
        span.classList.add('hl');
        span.style.backgroundImage = `linear-gradient(transparent 58%, ${rgba(hc, 0.5)} 58%, ${rgba(hc, 0.5)} 94%, transparent 94%)`;
      }
      if (split) {
        for (const ch of Array.from(r.t)) {
          if (ch === '\n') { span.append(document.createElement('br')); continue; }
          const c = document.createElement('span'); c.className = 'ch'; c.textContent = ch; span.append(c);
        }
      } else span.textContent = r.t;
      body.append(span);
    }
  }

  function paintText(rec, d) {
    const o = rec.outer, b = rec.body, al = d.align || 'l';
    o.style.left = d.x * SX + 'px'; o.style.top = d.y * SY + 'px';
    o.style.translate = al === 'c' ? '-50% 0' : al === 'r' ? '-100% 0' : '0 0';
    const px = (d.size || 6) * SY;
    b.style.fontSize = px + 'px';
    b.style.fontFamily = FONTS[d.font] || FONTS.sans;
    b.style.fontWeight = d.weight || 400;
    b.style.color = col(d.color, 'ink');
    b.style.textAlign = al === 'c' ? 'center' : al === 'r' ? 'right' : 'left';
    b.style.lineHeight = d.lh || (px > 70 ? 1.08 : 1.22);
    b.style.letterSpacing = d.ls !== undefined ? d.ls + 'em' : (px > 90 ? '-0.03em' : px > 50 ? '-0.015em' : '0');
    if (d.w) { b.style.width = d.w * SX + 'px'; b.style.maxWidth = ''; }
    else {
      const room = al === 'c' ? 2 * Math.min(d.x, 100 - d.x) : al === 'r' ? d.x : 100 - d.x;
      b.style.width = 'max-content'; b.style.maxWidth = Math.max(80, (room - 3) * SX) + 'px';
    }
    b.classList.toggle('nowrap', !!d.nowrap);
    b.style.textShadow = d.glow ? `0 0 ${px * 0.4}px ${rgba(d.glow === true ? (d.color || 'orange') : d.glow, 0.55)}` : '';
    const key = JSON.stringify([d.runs, d.text, d.in === 'type' || d.in === 'chars']);
    if (rec.runsKey !== key) { renderRuns(b, d); rec.runsKey = key; }
  }

  function paintImage(rec, d) {
    const o = rec.outer;
    o.style.left = d.x * SX + 'px'; o.style.top = d.y * SY + 'px';
    o.style.width = d.w * SX + 'px'; o.style.height = d.h * SY + 'px';
    o.style.borderRadius = (d.rx || 0) * SY + 'px'; o.style.overflow = 'hidden';
    rec.body.style.objectFit = d.fit || 'cover';
    const src = 'file?p=' + encodeURIComponent(d.src);
    if (rec.body.getAttribute('src') !== src) rec.body.setAttribute('src', src);
  }

  function iconPx(d) { return (d.size || 8) * SY; }

  // 箭头头部：跟着路径末端的切线走，变形时一起更新
  function heads(rec, d) {
    const want = d.head ? (d.head === 'both' ? ['start', 'end'] : [d.head]) : [];
    rec.heads = rec.heads || {};
    for (const k of Object.keys(rec.heads)) if (!want.includes(k)) { rec.heads[k].remove(); delete rec.heads[k]; }
    if (!want.length) return;
    const L = lenOf(rec.shape);
    if (!L) return;
    const sw = d.sw || 3.6, size = 12 + sw * 2.4;
    for (const which of want) {
      let h = rec.heads[which];
      if (!h) { h = svg('path'); rec.heads[which] = h; rec.inn.append(h); }
      const tip = rec.shape.getPointAtLength(which === 'end' ? L : 0);
      const back = rec.shape.getPointAtLength(which === 'end' ? Math.max(0, L - size * 0.8) : Math.min(L, size * 0.8));
      const a = Math.atan2(tip.y - back.y, tip.x - back.x);
      const p = (r, da) => `${(tip.x - size * Math.cos(a + da) * r).toFixed(1)} ${(tip.y - size * Math.sin(a + da) * r).toFixed(1)}`;
      setA(h, { d: `M${p(1, -0.45)} L${tip.x.toFixed(1)} ${tip.y.toFixed(1)} L${p(1, 0.45)} L${p(0.62, 0)} Z` });
      h.style.fill = col(d.stroke, 'ink'); h.style.stroke = col(d.stroke, 'ink'); h.style.strokeWidth = sw * 0.5; h.style.strokeLinejoin = 'round';
    }
  }

  function paintShape(rec, d) {
    const s = rec.shape;
    if (d.k === 'circle') setA(s, { cx: d.x * SX, cy: d.y * SY, r: Math.max(0.5, d.r * SY) });
    else if (d.k === 'rect') setA(s, { x: d.x * SX, y: d.y * SY, width: Math.max(0.5, d.w * SX), height: Math.max(0.5, d.h * SY), rx: (d.rx || 0) * SY });
    else if (d.k === 'path') { setA(s, { d: d.d }); heads(rec, d); }
    else if (d.k === 'icon') {
      if (rec.iconName !== d.name) {
        s.innerHTML = ICONS[d.name] || ICONS['circle-help'] || '<circle cx="12" cy="12" r="10"/>';
        rec.iconName = d.name;
      }
      const px = iconPx(d);
      setA(s, { transform: `translate(${d.x * SX - px / 2},${d.y * SY - px / 2}) scale(${px / 24})` });
    }
    const st = s.style;
    if (d.k === 'icon') {
      const px = iconPx(d);
      st.stroke = col(d.color, 'ink');
      st.strokeWidth = d.sw ? d.sw * 24 / px : 24 * Math.max(2.4, px / 42) / px;
      st.setProperty('--icofill', d.fill ? fillOf(d.fill) : 'none');
      for (const c of s.children) c.style.fill = d.fill ? fillOf(d.fill) : 'none';
    } else {
      st.fill = fillOf(d.fill);
      st.stroke = col(d.stroke, 'none');
      st.strokeWidth = d.sw || 0;
      st.strokeLinecap = 'round'; st.strokeLinejoin = 'round';
      const sw = d.sw || 2;
      st.strokeDasharray = d.dash === 'dots' ? `0 ${sw * 2.6}` : d.dash === 'dash' ? `${sw * 4.5} ${sw * 3.2}` : '';
    }
    st.filter = d.glow ? `drop-shadow(0 0 ${d.k === 'path' ? 10 : 18}px ${rgba(d.glow === true ? (d.stroke || d.fill || d.color || 'orange') : d.glow, 0.6)})`
      : d.shadow ? 'drop-shadow(0 10px 18px rgba(60,30,20,.18))' : '';
  }

  function paintCommon(rec, d) {
    rec.outer.style.opacity = d.alpha !== undefined ? d.alpha : '';
    rec.outer.style.rotate = d.rot ? d.rot + 'deg' : '';
    if (!rec.html) rec.outer.style.transformBox = 'fill-box';
  }

  function paint(rec, d) {
    if (d.k === 'text') paintText(rec, d);
    else if (d.k === 'image') paintImage(rec, d);
    else paintShape(rec, d);
    paintCommon(rec, d);
    rec.d = d;
  }

  // 舞台坐标下的最终外框（忽略动画）
  function boxOf(rec) {
    const d = rec.d;
    if (!d) return null;
    if (d.k === 'text') {
      const w = rec.body.offsetWidth, h = rec.body.offsetHeight;
      const left = d.x * SX - (d.align === 'c' ? w / 2 : d.align === 'r' ? w : 0);
      return { x: left, y: d.y * SY, w, h };
    }
    if (d.k === 'image') return { x: d.x * SX, y: d.y * SY, w: d.w * SX, h: d.h * SY };
    if (d.k === 'icon') { const px = iconPx(d); return { x: d.x * SX - px / 2, y: d.y * SY - px / 2, w: px, h: px }; }
    try { const b = rec.shape.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height }; } catch (e) { return null; }
  }

  // 相对定位：below / above / left / right / on @id
  function resolveRel(d) {
    if (!d.rel || !S.recs.has(d.rel.to)) return d;
    const ref = boxOf(S.recs.get(d.rel.to));
    if (!ref) return d;
    const gap = d.rel.gap !== undefined ? d.rel.gap : 2;
    const out = Object.assign({}, d);
    const cx = (ref.x + ref.w / 2) / SX, cy = (ref.y + ref.h / 2) / SY;
    const side = d.rel.side;
    if (d.k === 'text') {
      if (side === 'below') { out.x = cx; out.y = (ref.y + ref.h) / SY + gap; out.align = 'c'; }
      else if (side === 'above') { out.x = cx; out.y = ref.y / SY - gap - (d.size || 6) * (d.lh || 1.22); out.align = 'c'; }
      else if (side === 'left') { out.x = ref.x / SX - gap; out.y = cy - (d.size || 6) * 0.61; out.align = 'r'; }
      else if (side === 'right') { out.x = (ref.x + ref.w) / SX + gap; out.y = cy - (d.size || 6) * 0.61; out.align = 'l'; }
      else if (side === 'on') { out.x = cx; out.y = cy - (d.size || 6) * 0.61; out.align = 'c'; }
    } else {
      const own = ownSize(d);
      let tx = cx, ty = cy;
      if (side === 'below') ty = (ref.y + ref.h) / SY + gap + own.h / 2;
      else if (side === 'above') ty = ref.y / SY - gap - own.h / 2;
      else if (side === 'left') tx = ref.x / SX - gap * 0.625 - own.w / 2;
      else if (side === 'right') tx = (ref.x + ref.w) / SX + gap * 0.625 + own.w / 2;
      if (d.k === 'circle' || d.k === 'icon') { out.x = tx; out.y = ty; }
      else if (d.k === 'rect' || d.k === 'image') { out.x = tx - own.w / 2; out.y = ty - own.h / 2; }
    }
    return out;
  }
  function ownSize(d) {
    if (d.k === 'circle') return { w: d.r * 2 * SY / SX, h: d.r * 2 };
    if (d.k === 'icon') return { w: (d.size || 8) * SY / SX, h: d.size || 8 };
    return { w: d.w || 0, h: d.h || 0 };
  }

  // ---------- 动画 ----------
  const DEF_IN = { text: 'rise', circle: 'pop', rect: 'fade', path: 'draw', icon: 'draw', image: 'zoom' };
  function entryOf(d) {
    if (d.in) return d.in;
    if (d.k === 'rect' && (!d.fill || d.fill === 'none')) return 'draw';
    if (d.k === 'path' && d.fill && d.fill !== 'none' && !d.stroke) return 'pop';
    return DEF_IN[d.k] || 'fade';
  }
  function durOf(d, type, len) {
    if (d.dur) return d.dur;
    if (type === 'draw') return clamp(0.45 + (len || 400) / 1100, 0.5, 2.2);
    if (type === 'type') return 0;
    if (type === 'zoom' || type === 'blur') return 0.9;
    return 0.7;
  }

  function lenOf(el) { try { return el.getTotalLength(); } catch (e) { return 0; } }

  function entry(rec, d, base, delayExtra) {
    if (d.kf) return keyframes(rec, d, base);
    const type = entryOf(d);
    const t = rec.inn;
    const delay = Math.max(0, base + ((d.at || 0) + (delayExtra || 0)) * 1000 - now());
    const easing = EASE[d.ease] || EASE.out;
    let dur = durOf(d, type) * 1000;
    const o = { duration: dur, delay, easing, fill: 'backwards' };
    const tr = (f) => [{ opacity: 0, transform: f }, { opacity: 1, transform: 'none' }];
    switch (type) {
      case 'none': break;
      case 'fade': anim(rec, t, [{ opacity: 0 }, { opacity: 1 }], o); break;
      case 'rise': anim(rec, t, tr('translateY(30px)'), o); break;
      case 'drop': anim(rec, t, tr('translateY(-70px)'), Object.assign({}, o, { easing: EASE.back })); break;
      case 'up': anim(rec, t, tr('translateY(140px)'), o); break;
      case 'down': anim(rec, t, tr('translateY(-140px)'), o); break;
      case 'left': anim(rec, t, tr('translateX(-200px)'), o); break;
      case 'right': anim(rec, t, tr('translateX(200px)'), o); break;
      case 'slide': anim(rec, t, tr('translateX(-60px)'), o); break;
      case 'pop': anim(rec, t, tr('scale(.35)'), Object.assign({}, o, { easing: EASE.back, duration: Math.max(dur, 650) })); break;
      case 'zoom': anim(rec, t, tr('scale(1.7)'), o); break;
      case 'spin': anim(rec, t, tr('rotate(-220deg) scale(.3)'), Object.assign({}, o, { easing: EASE.back, duration: Math.max(dur, 900) })); break;
      case 'blur': anim(rec, t, [{ opacity: 0, filter: 'blur(22px)', transform: 'scale(1.06)' }, { opacity: 1, filter: 'blur(0)', transform: 'none' }], o); break;
      case 'wipe': anim(rec, t, [{ clipPath: 'inset(-10% 100% -10% -10%)' }, { clipPath: 'inset(-10% -10% -10% -10%)' }], Object.assign({}, o, { easing: EASE.smooth })); break;
      case 'grow': t.style.transformOrigin = '50% 100%'; anim(rec, t, [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }], Object.assign({}, o, { easing: EASE.out })); break;
      case 'stretch': t.style.transformOrigin = '0% 50%'; anim(rec, t, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], Object.assign({}, o, { easing: EASE.out })); break;
      case 'bounce':
        anim(rec, t, [{ opacity: 0, transform: 'translateY(-160px)', offset: 0 }, { opacity: 1, transform: 'translateY(0)', offset: 0.45 },
          { transform: 'translateY(-36px)', offset: 0.62 }, { transform: 'translateY(0)', offset: 0.78 }, { transform: 'translateY(-10px)', offset: 0.89 },
          { opacity: 1, transform: 'translateY(0)', offset: 1 }], Object.assign({}, o, { duration: Math.max(dur, 1000), easing: 'ease-out' }));
        break;
      case 'type': case 'chars': {
        const chars = rec.body ? rec.body.querySelectorAll('.ch') : [];
        const step = type === 'type' ? 55 : 38;
        chars.forEach((c, i) => {
          const oc = { duration: type === 'type' ? 1 : 520, delay: delay + i * step, easing: type === 'type' ? 'linear' : EASE.back, fill: 'backwards' };
          anim(rec, c, type === 'type' ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'translateY(.45em) scale(.7)' }, { opacity: 1, transform: 'none' }], oc);
        });
        dur = chars.length * step + 400;
        break;
      }
      case 'draw': dur = drawIn(rec, d, delay); break;
      default: anim(rec, t, [{ opacity: 0 }, { opacity: 1 }], o);
    }
    const end = delay + dur;
    rec.endAt = now() + end;
    afterEntry(rec, d, end);
  }

  function drawIn(rec, d, delay) {
    const shapes = d.k === 'icon' ? Array.from(rec.shape.children) : [rec.shape];
    const dashed = d.dash && d.k !== 'icon';
    if (dashed) {
      anim(rec, rec.inn, [{ clipPath: 'inset(-5% 100% -5% -5%)' }, { clipPath: 'inset(-5% -5% -5% -5%)' }], { duration: 900, delay, easing: EASE.smooth, fill: 'backwards' });
      return 900;
    }
    let total = 0;
    const lens = shapes.map((s) => { const l = lenOf(s); total += l; return l; });
    const scale = d.k === 'icon' ? iconPx(d) / 24 : 1;
    const dur = (d.dur || clamp(0.45 + total * scale / 1100, 0.5, 2.2)) * 1000;
    let acc = 0;
    shapes.forEach((s, i) => {
      const l = lens[i] || 1;
      const start = d.k === 'icon' ? delay + (acc / (total || 1)) * dur * 0.6 : delay;
      const len = d.k === 'icon' ? Math.max(dur * 0.55, 300) : dur;
      acc += l;
      s.style.strokeDasharray = `${l} ${l}`;
      const a = anim(rec, s, [{ strokeDashoffset: l }, { strokeDashoffset: 0 }], { duration: len, delay: start, easing: EASE.smooth, fill: 'backwards' });
      if (a) a.onfinish = () => { s.style.strokeDasharray = ''; if (d.k !== 'icon') paintShape(rec, rec.d); };
    });
    const filled = d.k !== 'icon' && d.fill && d.fill !== 'none';
    if (filled) anim(rec, rec.shape, [{ fillOpacity: 0 }, { fillOpacity: 1 }], { duration: dur * 0.6, delay: delay + dur * 0.55, easing: EASE.out, fill: 'backwards' });
    Object.values(rec.heads || {}).forEach((h) => anim(rec, h, [{ opacity: 0, transform: 'scale(.4)' }, { opacity: 1, transform: 'none' }],
      { duration: 260, delay: delay + dur * 0.92, easing: EASE.back, fill: 'backwards' }));
    return dur;
  }

  function keyframes(rec, d, base) {
    // 高级：自定义关键帧 {prop: [[秒, 值], …]}，prop 为 x、y（%）、scale、rotate、opacity
    const props = d.kf;
    const T = Math.max(0.1, ...Object.values(props).map((ks) => ks[ks.length - 1][0]));
    const times = Array.from(new Set([].concat(...Object.values(props).map((ks) => ks.map((k) => k[0]))))).sort((a, b) => a - b);
    const val = (ks, t) => {
      if (t <= ks[0][0]) return ks[0][1];
      for (let i = 1; i < ks.length; i++) if (t <= ks[i][0]) { const [t0, v0] = ks[i - 1], [t1, v1] = ks[i]; return v0 + (v1 - v0) * (t - t0) / (t1 - t0); }
      return ks[ks.length - 1][1];
    };
    const frames = times.map((t) => {
      const x = props.x ? val(props.x, t) * SX : 0, y = props.y ? val(props.y, t) * SY : 0;
      const sc = props.scale ? val(props.scale, t) : 1, ro = props.rotate ? val(props.rotate, t) : 0;
      const f = { offset: t / T, transform: `translate(${x}px,${y}px) rotate(${ro}deg) scale(${sc})` };
      if (props.opacity) f.opacity = val(props.opacity, t);
      return f;
    });
    if (frames[0].offset !== 0) frames.unshift(Object.assign({}, frames[0], { offset: 0 }));
    if (frames[frames.length - 1].offset !== 1) frames.push(Object.assign({}, frames[frames.length - 1], { offset: 1 }));
    const delay = Math.max(0, base + (d.at || 0) * 1000 - now());
    anim(rec, rec.inn, frames, { duration: T * 1000, delay, easing: EASE[d.ease] || 'ease-in-out', fill: 'both', iterations: d.repeat ? Infinity : 1 });
    afterEntry(rec, d, delay + T * 1000);
  }

  const LOOPS = {
    float: [[{ transform: 'translateY(0)' }, { transform: 'translateY(-16px)' }], { duration: 2600, direction: 'alternate', easing: EASE.smooth }],
    pulse: [[{ transform: 'scale(1)' }, { transform: 'scale(1.08)' }], { duration: 1200, direction: 'alternate', easing: EASE.smooth }],
    sway: [[{ transform: 'rotate(-5deg)' }, { transform: 'rotate(5deg)' }], { duration: 2200, direction: 'alternate', easing: EASE.smooth }],
    turn: [[{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], { duration: 12000, easing: 'linear' }],
    spinfast: [[{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], { duration: 2400, easing: 'linear' }],
    blink: [[{ opacity: 1 }, { opacity: 0.2 }], { duration: 900, direction: 'alternate', easing: EASE.smooth }],
    breathe: [[{ opacity: 0.7, transform: 'scale(.97)' }, { opacity: 1, transform: 'scale(1.03)' }], { duration: 2400, direction: 'alternate', easing: EASE.smooth }],
    shake: [[{ transform: 'translateX(0)' }, { transform: 'translateX(-7px)' }, { transform: 'translateX(7px)' }, { transform: 'translateX(0)' }], { duration: 500, easing: 'linear' }],
    orbit: [[0, 45, 90, 135, 180, 225, 270, 315, 360].map((a) => ({ transform: `translate(${Math.cos(a * Math.PI / 180) * 14}px,${Math.sin(a * Math.PI / 180) * 14}px)` })), { duration: 4200, easing: 'linear' }],
    bob: [[{ transform: 'translateY(0) rotate(-2deg)' }, { transform: 'translateY(-10px) rotate(2deg)' }], { duration: 1700, direction: 'alternate', easing: EASE.smooth }],
  };

  function afterEntry(rec, d, endDelay) {
    const loops = d.loop || [];
    loops.forEach((name, i) => {
      if (name === 'flow' || name === 'dot') return;
      const L = LOOPS[name];
      if (!L) return;
      const target = i === 0 ? rec.mv : (rec.mv2 || (rec.mv2 = wrapInner(rec)));
      anim(rec, target, L[0], Object.assign({}, L[1], { delay: endDelay + 80, iterations: name === 'shake' ? 3 : Infinity }));
    });
    if (d.move) {
      const [mx, my] = d.move;
      const at = d.moveAt !== undefined ? Math.max(0, S.t0 + d.moveAt * 1000 - now()) : endDelay + 120;
      anim(rec, rec.outer, [{ transform: 'translate(0,0)' }, { transform: `translate(${mx * SX}px,${my * SY}px)` }],
        { duration: (d.moveDur || 1.2) * 1000, delay: at, easing: EASE.smooth, fill: 'both' });
    }
    if (d.along) followPath(rec, d, endDelay);
    if (d.k === 'path' && (d.dot || loops.includes('flow') || loops.includes('dot'))) runners(rec, d, endDelay);
    if (d.k === 'text') {
      rec.body.querySelectorAll('.hl').forEach((h, i) => {
        anim(rec, h, [{ backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%' }], { duration: 650, delay: endDelay + 60 + i * 180, easing: EASE.smooth, fill: 'backwards' });
      });
      if (d.count) countUp(rec, d, endDelay);
    }
  }

  function wrapInner(rec) {
    // 第二个持续动作需要独立的一层
    const extra = rec.html ? div('mv') : svg('g', { class: 'mv' });
    const child = rec.inn;
    rec.mv.replaceChild(extra, child); extra.append(child);
    return extra;
  }

  function loopRaf(rec, fn, delay) {
    const start = now() + delay;
    const gen = rec.gen || 0;
    const tick = () => {
      if (!rec.alive || (rec.gen || 0) !== gen) return;
      const t = now() - start;
      if (t >= 0 && fn(t) === false) return;
      const id = requestAnimationFrame(tick); rec.raf = id;
    };
    const id = requestAnimationFrame(tick); rec.raf = id;
  }

  function runners(rec, d, delay) {
    const path = rec.shape, L = lenOf(path);
    if (!L) return;
    const flowing = (d.loop || []).includes('flow');
    const n = flowing ? (d.flowN || 3) : 1;
    const c = col((d.dot && d.dot.c) || d.stroke || 'ink');
    const r = (d.dot && d.dot.r) || Math.max(5, (d.sw || 3) * 1.6);
    const period = ((d.dot && d.dot.dur) || (flowing ? Math.max(1.6, L / 320) : Math.max(1.0, L / 520))) * 1000;
    const dots = [];
    for (let i = 0; i < n; i++) {
      const dot = svg('circle', { r, fill: c, opacity: 0 });
      (rec.layer || under).append(dot); dots.push(dot); rec.extras.push(dot);
    }
    loopRaf(rec, (t) => {
      dots.forEach((dot, i) => {
        let p = (t / period + i / n);
        if (!flowing && p > 1) { dot.setAttribute('opacity', 0); return; }
        p = flowing ? p % 1 : Math.min(1, p);
        const pt = path.getPointAtLength(L * p);
        const fade = flowing ? Math.min(1, Math.min(p, 1 - p) * 8) : (p < 0.06 ? p / 0.06 : p > 0.94 ? (1 - p) / 0.06 : 1);
        setA(dot, { cx: pt.x, cy: pt.y, opacity: fade });
      });
      if (!flowing && t > period + 50) return false;
    }, delay);
  }

  function followPath(rec, d, delay) {
    const ref = S.recs.get(d.along);
    if (!ref || !ref.shape || !ref.shape.getPointAtLength) return;
    const L = lenOf(ref.shape);
    const box = boxOf(rec);
    if (!L || !box) return;
    const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
    const period = (d.alongDur || Math.max(1.6, L / 300)) * 1000;
    const repeat = (d.loop || []).includes('flow') || d.alongLoop;
    loopRaf(rec, (t) => {
      let p = t / period;
      if (!repeat && p >= 1) p = 1;
      const pt = ref.shape.getPointAtLength(L * (repeat ? p % 1 : p));
      rec.outer.style.transform = `translate(${pt.x - cx}px,${pt.y - cy}px)`;
      if (!repeat && p >= 1) return false;
    }, delay);
  }

  function countUp(rec, d, delay) {
    const walker = document.createTreeWalker(rec.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) { if (/\d/.test(node.nodeValue)) break; }
    if (!node) return;
    const full = node.nodeValue, m = full.match(/\d+(\.\d+)?/);
    if (!m) return;
    const target = parseFloat(m[0]), dec = (m[1] || '').length - (m[1] ? 1 : 0);
    const dur = Math.max(900, (d.dur || 1.2) * 1000);
    const set = (v) => { node.nodeValue = full.slice(0, m.index) + v.toFixed(dec) + full.slice(m.index + m[0].length); };
    set(0);
    loopRaf(rec, (t) => {
      const p = Math.min(1, t / dur), e = 1 - Math.pow(1 - p, 3);
      set(target * e);
      if (p >= 1) return false;
    }, Math.max(0, delay - (d.dur || 0.7) * 1000));
  }

  // ---------- 变形 ----------
  function numbers(s) { return (s || '').match(/-?\d*\.?\d+(?:e-?\d+)?/gi) || []; }
  // 路径逐数字插值；弧线命令里的两个标志位（0/1）不插值，直接取目标值
  function interpD(a, b, e) {
    const na = numbers(a);
    let i = 0, cmd = '', arg = 0;
    return String(b).replace(/([MLCQZAHVSTmlcqzahvst])|(-?\d*\.?\d+(?:e-?\d+)?)/g, (m, c, n) => {
      if (c) { cmd = c; arg = 0; return c; }
      const tv = +n, fv = na[i] !== undefined ? +na[i] : tv;
      i++;
      const flag = (cmd === 'A' || cmd === 'a') && (arg % 7 === 3 || arg % 7 === 4);
      arg++;
      return flag ? String(Math.round(tv)) : (fv + (tv - fv) * e).toFixed(2);
    });
  }
  function skeleton(s) { return (s || '').replace(/-?\d*\.?\d+(?:e-?\d+)?/gi, '#'); }

  function tween(rec, from, to, ms) {
    // from/to: {attr: value}；数字插值，d 路径在结构相同的情况下逐个数字插值
    const keys = Object.keys(to).filter((k) => from[k] !== undefined && String(from[k]) !== String(to[k]));
    if (!keys.length) return;
    const start = now();
    const ease = (p) => p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
    const step = () => {
      if (!rec.alive) return;
      const p = Math.min(1, (now() - start) / ms), e = ease(p);
      const target = rec.d.k === 'icon' ? rec.shape : rec.shape;
      for (const k of keys) {
        if (k === 'd') target.setAttribute(k, interpD(from[k], to[k], e));
        else if (k === 'transform') {
          const a = numbers(from[k]), b = numbers(to[k]);
          let i = 0;
          target.setAttribute(k, String(to[k]).replace(/-?\d*\.?\d+(?:e-?\d+)?/gi, () => { const v = +a[i] + (+b[i] - +a[i]) * e; i++; return v.toFixed(2); }));
        } else target.setAttribute(k, +from[k] + (+to[k] - +from[k]) * e);
      }
      if (keys.includes('d')) heads(rec, rec.d);
      if (p < 1) requestAnimationFrame(step);
      else { for (const k of keys) target.setAttribute(k, to[k]); if (keys.includes('d')) heads(rec, rec.d); }
    };
    requestAnimationFrame(step);
  }

  function geomAttrs(rec) {
    const s = rec.shape, out = {};
    for (const k of ['cx', 'cy', 'r', 'x', 'y', 'width', 'height', 'rx', 'd', 'transform']) if (s.hasAttribute(k)) out[k] = s.getAttribute(k);
    return out;
  }

  function sameLook(a, b) {
    const strip = (d) => { const o = Object.assign({}, d); for (const k of ['at', 'dur', 'in', 'ease', 'loop', 'move', 'moveAt', 'moveDur', 'along', 'alongDur', 'kf', 'rel', 'line']) delete o[k]; return JSON.stringify(o); };
    return strip(a) === strip(b);
  }

  function settle(rec) {
    // 停掉旧的持续动作、沿线圆点、移动，保留元素本身
    rec.gen = (rec.gen || 0) + 1;
    rec.extras.forEach((x) => x.remove()); rec.extras = [];
    rec.anims.forEach((a) => { try { a.finish(); } catch (e) { /* ignore */ } });
    rec.anims = [];
    [rec.mv, rec.mv2, rec.outer].forEach((n) => { if (n) n.getAnimations().forEach((a) => a.cancel()); });
    rec.outer.style.transform = '';
  }

  function morph(rec, d) {
    settle(rec);
    morphShape(rec, d);
    afterEntry(rec, rec.d, 760);
  }

  function morphShape(rec, d) {
    if (rec.html) {
      const before = boxOf(rec);
      const textChanged = d.k === 'text' && JSON.stringify([d.runs, d.text]) !== JSON.stringify([rec.d.runs, rec.d.text]);
      if (textChanged) ghost(rec);
      paint(rec, d);
      const after = boxOf(rec);
      if (before && after && !textChanged) {
        const dx = before.x - after.x, dy = before.y - after.y, sx = before.w / (after.w || 1), sy = before.h / (after.h || 1);
        if (Math.abs(dx) + Math.abs(dy) > 0.5 || Math.abs(sx - 1) > 0.01) {
          rec.outer.style.transformOrigin = '0 0';
          anim(rec, rec.outer, [{ transform: `translate(${dx}px,${dy}px) scale(${sx},${sy})` }, { transform: 'none' }], { duration: 700, easing: EASE.smooth });
        }
      } else if (textChanged) {
        if (before && after) {
          anim(rec, rec.outer, [{ transform: `translate(${before.x - after.x}px,${before.y - after.y}px)` }, { transform: 'none' }], { duration: 650, easing: EASE.smooth });
        }
        anim(rec, rec.inn, [{ opacity: 0 }, { opacity: 1 }], { duration: 450, delay: 120, easing: EASE.out, fill: 'backwards' });
      }
      return;
    }
    if (d.k === 'icon' && d.name !== rec.d.name) {
      ghost(rec); paint(rec, d);
      anim(rec, rec.inn, [{ opacity: 0, transform: 'scale(.6)' }, { opacity: 1, transform: 'none' }], { duration: 500, easing: EASE.back, fill: 'backwards' });
      return;
    }
    const from = geomAttrs(rec);
    const fromD = rec.d;
    rec.shape.style.transition = 'fill .7s, stroke .7s, stroke-width .7s, opacity .7s';
    paint(rec, d);
    const to = geomAttrs(rec);
    if (to.d && from.d && skeleton(to.d) !== skeleton(from.d)) {
      ghost(rec, fromD); delete to.d;
      anim(rec, rec.inn, [{ opacity: 0 }, { opacity: 1 }], { duration: 500, easing: EASE.out });
    }
    for (const k in to) rec.shape.setAttribute(k, from[k] !== undefined ? from[k] : to[k]);
    tween(rec, from, to, 750);
  }

  function ghost(rec) {
    // 旧样子的副本淡出，用于内容变化时的交叉淡化
    const clone = rec.outer.cloneNode(true);
    clone.style.pointerEvents = 'none';
    rec.outer.parentNode.insertBefore(clone, rec.outer);
    const a = clone.animate([{ opacity: getComputedStyle(rec.outer).opacity }, { opacity: 0 }], { duration: 380, easing: EASE.out, fill: 'forwards' });
    a.onfinish = () => clone.remove();
  }

  function remove(rec, how) {
    rec.alive = false;
    rec.anims.forEach((a) => { try { a.cancel(); } catch (e) { /* ignore */ } });
    rec.extras.forEach((x) => x.remove());
    const node = rec.outer;
    if (how === 'cut') { node.remove(); return; }
    const frames = how === 'push' ? [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateX(-90px)' }]
      : how === 'lift' ? [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-60px)' }]
        : how === 'zoom' ? [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(1.12)' }]
          : [{ opacity: 1 }, { opacity: 0 }];
    if (!rec.html) node.style.transformBox = 'fill-box';
    const target = rec.html ? rec.mv : rec.mv;
    target.getAnimations().forEach((a) => a.cancel());
    const a = target.animate(frames, { duration: how === 'blend' ? 320 : 420, easing: EASE.in, fill: 'forwards' });
    a.onfinish = () => node.remove();
  }

  // ---------- 场景 ----------
  function sceneOf(page) {
    return (page && page.board) || { v: 2, els: [] };
  }

  function camTo(c) {
    const z = c ? (c.z || 1) : 1, x = c ? c.x : 50, y = c ? c.y : 50;
    return `translate(${W / 2 - x * SX * z}px, ${H / 2 - y * SY * z}px) scale(${z})`;
  }

  function camera(scene) {
    world.getAnimations().forEach((a) => a.cancel());
    const cams = scene.cam || [];
    if (!cams.length) {
      if (S.camActive) world.animate([{ transform: S.camLast || 'none' }, { transform: 'none' }], { duration: 700, easing: EASE.smooth });
      world.style.transform = ''; S.camActive = false; S.camLast = null;
      return;
    }
    let last = 'none';
    let t = 0;
    const frames = [{ offset: 0, transform: S.camLast || 'none' }];
    const T = Math.max(...cams.map((c) => (c.at || 0) + (c.dur || 1.2))) * 1000 || 1;
    cams.forEach((c) => {
      const at = (c.at || 0) * 1000, dur = (c.dur || 1.2) * 1000;
      const target = c.reset ? 'none' : camTo(c);
      if (at > t) frames.push({ offset: at / T, transform: last, easing: EASE.smooth });
      else frames[frames.length - 1].easing = EASE.smooth;
      frames.push({ offset: (at + dur) / T, transform: target });
      last = target; t = at + dur;
    });
    frames.forEach((f, i) => { if (i && f.offset <= frames[i - 1].offset) f.offset = Math.min(1, frames[i - 1].offset + 0.0001); });
    frames[frames.length - 1].offset = 1;
    world.animate(frames, { duration: T, fill: 'forwards' });
    S.camActive = true; S.camLast = last;
  }

  function show(page, how, isEdit) {
    const scene = sceneOf(page);
    const els = scene.els || [];
    const keep = new Set(els.map((e) => e.id));
    const trans = isEdit ? 'blend' : (how || scene.transition || 'blend');
    for (const [id, rec] of S.recs) {
      if (!keep.has(id) || rec.k !== (els.find((e) => e.id === id) || {}).k) { remove(rec, trans); S.recs.delete(id); }
    }
    S.t0 = now() + (isEdit ? 0 : (trans === 'push' || trans === 'lift' ? 160 : 60));
    const fresh = [];
    for (const raw of els) {
      try {
        let rec = S.recs.get(raw.id);
        if (rec) {
          const d = resolveRel(raw);
          if (!sameLook(rec.d, d)) morph(rec, d);
          rec.d = d; rec.raw = raw;
          (rec.html ? texts : rec.layer).append(rec.outer);
        } else {
          rec = make(raw); rec.alive = true;
          S.recs.set(raw.id, rec);
          paint(rec, raw);
          fresh.push([rec, raw]);
        }
      } catch (e) { console.error('element', raw && raw.id, e); }
    }
    // 相对定位依赖已画好的元素：先全部画上，再解析位置
    for (const [rec, raw] of fresh) { if (raw.rel) { try { paint(rec, resolveRel(raw)); } catch (e) { /* ignore */ } } }
    for (const [rec] of fresh) { try { entry(rec, rec.d, S.t0, 0); } catch (e) { console.error('entry', rec.id, e); } }
    if (!isEdit) camera(scene);
    else if (scene.cam && JSON.stringify(scene.cam) !== JSON.stringify(S.lastCam)) camera(scene);
    S.lastCam = scene.cam;
    document.body.style.background = scene.bg ? col(scene.bg) : '';
    clearTimeout(S.reportTimer);
    S.reportTimer = setTimeout(report, 450);
  }

  // ---------- 排版检查（真实测量） ----------
  function report() {
    if (!S.pageID) return;
    const warnings = [];
    const recs = Array.from(S.recs.values()).filter((r) => r.alive && r.d);
    const boxes = new Map();
    recs.forEach((r) => { const b = boxOf(r); if (b) boxes.set(r.id, b); });
    const txt = recs.filter((r) => r.d.k === 'text');
    const area = (b) => b.w * b.h;
    for (let i = 0; i < txt.length; i++) for (let j = i + 1; j < txt.length; j++) {
      const a = boxes.get(txt[i].id), b = boxes.get(txt[j].id);
      if (!a || !b) continue;
      const ix = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), iy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ix > 4 && iy > 4 && ix * iy > 0.1 * Math.min(area(a), area(b))) warnings.push({ type: 'overlap', a: txt[i].id, b: txt[j].id });
    }
    for (const r of recs) {
      if (r.d.k !== 'path' || r.id.endsWith('-head')) continue;
      const L = lenOf(r.shape);
      if (!L) continue;
      const pts = [];
      for (let s = 0; s <= L; s += 9) pts.push(r.shape.getPointAtLength(s));
      for (const t of txt) {
        const b = boxes.get(t.id);
        if (!b) continue;
        const px = b.w * 0.06, py = b.h * 0.18;
        const hits = pts.filter((p) => p.x > b.x + px && p.x < b.x + b.w - px && p.y > b.y + py && p.y < b.y + b.h - py).length;
        if (hits >= 2) warnings.push({ type: 'cross', a: r.id, b: t.id });
      }
    }
    for (const r of recs) {
      const b = boxes.get(r.id);
      if (!b || r.id.endsWith('-head')) continue;
      if (b.x < -8 || b.y < -8 || b.x + b.w > W + 8 || b.y + b.h > H + 8) warnings.push({ type: 'out', a: r.id });
      if (r.d.k === 'text' && (r.d.size || 6) * SY < 15) warnings.push({ type: 'tiny', a: r.id });
    }
    const filled = recs.filter((r) => r.d.k !== 'text' && (r.d.fill && r.d.fill !== 'none'));
    for (const t of txt) {
      const b = boxes.get(t.id);
      for (const f of filled) {
        const c = boxes.get(f.id);
        if (!b || !c) continue;
        const ix = Math.min(b.x + b.w, c.x + c.w) - Math.max(b.x, c.x), iy = Math.min(b.y + b.h, c.y + c.h) - Math.max(b.y, c.y);
        if (ix > 0 && iy > 0 && ix * iy > 0.5 * area(b) && sameish(col(t.d.color, 'ink'), fillOf(f.d.fill))) warnings.push({ type: 'contrast', a: t.id, b: f.id });
      }
    }
    const out = {};
    boxes.forEach((b, id) => { out[id] = [b.x / SX, b.y / SY, b.w / SX, b.h / SY].map((v) => Math.round(v * 10) / 10); });
    host.send({ type: 'layout', showID: S.showID, pageID: S.pageID, rev: S.rev, warnings, boxes: out });
  }
  const sameish = (a, b) => a === b;

  // ---------- 外框与交互 ----------
  function chrome(page) {
    const doc = (S.content && S.content.document) || {};
    $('#title span').textContent = doc.title || '';
    const pager = $('#pager');
    pager.textContent = '';
    if (S.pages.length > 1) S.pages.forEach((p, i) => { const b = document.createElement('b'); if (i === S.index) b.className = 'on'; else if (S.seen.has(p.id)) b.className = 'seen'; pager.append(b); });
    const choices = ((page && page.interaction) || {}).choices || [];
    const box = $('#choices');
    box.textContent = '';
    choices.forEach((c, i) => {
      const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = c;
      btn.addEventListener('mousedown', (e) => e.preventDefault());
      btn.addEventListener('click', () => answer(c, true, btn));
      btn.title = String(i + 1);
      box.append(btn);
    });
    const asking = choices.length > 0 || /[？?]\s*$/.test((page && page.title) || '');
    document.body.classList.toggle('asking', asking);
    if (page && page.interaction && page.interaction.placeholder) input.placeholder = page.interaction.placeholder;
    else input.placeholder = asking ? '直接打字回答，Enter 发送' : '说点什么…  Enter 发送';
  }

  function setWaiting(on) {
    S.waiting = on;
    document.body.classList.toggle('waiting', on);
  }

  function goto(i, how) {
    if (i < 0 || i >= S.pages.length || i === S.index) return;
    const page = S.pages[i];
    S.index = i; S.pageID = page.id; S.seen.add(page.id);
    show(page, how);
    chrome(page);
    host.send({ type: 'nav', showID: S.showID, index: i, pageID: page.id });
  }

  function next() {
    if (S.leaving) return;
    if (S.index < S.pages.length - 1) goto(S.index + 1, 'push');
    else if (!S.waiting) { host.send({ type: 'continue', showID: S.showID, pageID: S.pageID }); setWaiting(true); }
  }
  function prev() { if (S.index > 0) goto(S.index - 1, 'blend'); }

  function answer(text, choice, btn) {
    text = (text || '').trim();
    if (!text || S.leaving || S.waiting) return;
    if (btn) btn.classList.add('picked');
    host.send({ type: 'answer', showID: S.showID, pageID: S.pageID, text, choice: !!choice });
    input.value = ''; typing(false); setWaiting(true);
  }

  function typing(on) {
    document.body.classList.toggle('typing', on);
    if (on !== S.editing) { S.editing = on; host.send({ type: 'editing', on }); }
  }

  let composing = false;
  input.addEventListener('compositionstart', () => { composing = true; typing(true); });
  input.addEventListener('compositionend', () => { composing = false; typing(!!input.value); });
  input.addEventListener('input', () => typing(!!input.value || composing));
  input.addEventListener('blur', () => { setTimeout(() => { if (!S.leaving) input.focus({ preventScroll: true }); }, 0); });
  input.addEventListener('keydown', (e) => {
    wake();
    if (e.isComposing || composing || e.keyCode === 229) return;
    const empty = !input.value;
    if (e.key === 'Escape') { e.preventDefault(); dismiss(); return; }
    if (e.key === 'Enter') { e.preventDefault(); if (!empty) answer(input.value, false); return; }
    if (!empty) return;
    if (e.key === ' ' || e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); next(); return; }
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); prev(); return; }
    const choices = $('#choices').children;
    if (/^[1-9]$/.test(e.key) && choices.length >= +e.key && !e.metaKey && !e.ctrlKey) { e.preventDefault(); choices[+e.key - 1].click(); }
  });
  $('#ask').addEventListener('submit', (e) => { e.preventDefault(); answer(input.value, false); });
  document.addEventListener('mousedown', (e) => { if (e.target.tagName !== 'BUTTON') setTimeout(() => input.focus({ preventScroll: true }), 0); });

  let idleTimer = 0;
  function wake() {
    document.body.classList.remove('idle');
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (!document.body.classList.contains('typing')) document.body.classList.add('idle'); }, 2800);
  }
  addEventListener('mousemove', wake);

  function leave(kind) {
    if (S.leaving) return;
    S.leaving = true;
    document.body.classList.add('leaving');
    const sent = host.send({ type: kind, showID: S.showID });
    Promise.all([sent, new Promise(resolve => setTimeout(resolve, 350))]).finally(() => host.quit());
  }
  function dismiss() { leave('dismiss'); }

  // ---------- 应用状态 ----------
  function apply(content) {
    if (!content || !content.document) return;
    const doc = content.document;
    const pages = doc.pages || [];
    if (content.action === 'close' && content.showID === S.showID) { leave('closed'); return; }
    if (content.action === 'close') return;
    const newShow = content.showID !== S.showID;
    const prevContent = S.content;
    S.content = content; S.pages = pages;
    if (newShow) {
      S.showID = content.showID; S.seen = new Set(); S.pageID = null; S.rev = null; setWaiting(false);
      host.send({ type: 'shown', showID: S.showID });
    }
    const idx = clamp(content.pageIndex || 0, 0, Math.max(0, pages.length - 1));
    const page = pages[idx];
    if (!page) return;
    const pageChanged = page.id !== S.pageID;
    const revChanged = content.documentRevision !== S.rev;
    if (content.turnID !== S.turn) { S.turn = content.turnID; setWaiting(false); }
    S.index = idx; S.rev = content.documentRevision;
    if (pageChanged) {
      S.pageID = page.id; S.seen.add(page.id);
      show(page, newShow ? 'blend' : undefined, false);
    } else if (revChanged || (prevContent && prevContent.writtenAt !== content.writtenAt && content.action === 'edit')) {
      show(page, 'blend', true);
    }
    chrome(page);
  }

  // ---------- 宿主 ----------
  const wk = !!(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.board);
  let pendingSend = Promise.resolve();
  const host = {
    send(evt) {
      const body = JSON.stringify({ showID: S.showID, turnID: S.turn, ...evt });
      pendingSend = pendingSend.then(() => fetch('event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })).catch(() => {});
      return pendingSend;
    },
    quit() {
      if (wk) window.webkit.messageHandlers.board.postMessage('quit');
      else { document.body.innerHTML = ''; try { window.close(); } catch (e) { /* ignore */ } }
    },
  };

  async function poll() {
    let since = '';
    for (;;) {
      try {
        const r = await fetch('state?since=' + encodeURIComponent(since), { cache: 'no-store' });
        if (r.status === 200) {
          const j = await r.json();
          since = j.v;
          apply(j.content);
        } else if (r.status === 410) { leave('closed'); return; }
      } catch (e) { await new Promise((ok) => setTimeout(ok, 400)); }
      if (S.leaving) return;
    }
  }

  async function boot() {
    fit();
    try { ICONS = await (await fetch('icons.json')).json(); } catch (e) { ICONS = {}; }
    try { await document.fonts.ready; } catch (e) { /* ignore */ }
    input.focus({ preventScroll: true });
    wake();
    host.send({ type: 'ready' });
    poll();
  }
  window.__board = { apply, state: S, report };
  boot();
})();

'use strict';
// Concept board helper: clones each concept's <template> into a night and a day frame and
// draws the dials. Static mock-ups only; nothing here ships.
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
  function dial(node) {
    const pct = Number(node.dataset.pct); const state = node.dataset.state || ''; const t = node.dataset.t;
    const R = 22; const C = 2 * Math.PI * R;
    const svg = el('svg', { viewBox: '0 0 50 50', 'aria-hidden': 'true' });
    svg.append(el('circle', { class: 'track', cx: 25, cy: 25, r: R }));
    if (state !== 'failed' && state !== 'empty' && pct > 0) {
      svg.append(el('circle', { class: 'arc', cx: 25, cy: 25, r: R, 'stroke-dasharray': (C * pct / 100).toFixed(2) + ' ' + C.toFixed(2), transform: 'rotate(-90 25 25)' }));
    }
    if (t != null && state !== 'failed') {
      const a = Number(t) * 2 * Math.PI; const sx = Math.sin(a); const cy = -Math.cos(a);
      const p = (r) => ({ x: (25 + sx * r).toFixed(2), y: (25 + cy * r).toFixed(2) });
      const a1 = p(R - 5); const a2 = p(R + 5.5);
      svg.append(el('line', { class: 'tick-halo', x1: a1.x, y1: a1.y, x2: a2.x, y2: a2.y }));
      svg.append(el('line', { class: 'tick', x1: a1.x, y1: a1.y, x2: a2.x, y2: a2.y }));
    }
    const val = document.createElement('span'); val.className = 'val';
    if (state === 'failed') val.textContent = '?';
    else if (state === 'empty') val.textContent = 'empty';
    else { const s = document.createElement('span'); s.append(String(pct)); const u = document.createElement('small'); u.textContent = '%'; s.append(u); val.append(s); }
    node.append(svg, val);
  }
  document.querySelectorAll('.concept').forEach((section) => {
    const tpl = section.querySelector('template'); const frames = section.querySelector('.frames');
    for (const [theme, label] of [['dark', 'Night'], ['light', 'Day']]) {
      const wrap = document.createElement('div'); wrap.className = 'frame-wrap';
      const cap = document.createElement('span'); cap.textContent = label + ' · 400 px';
      const frame = document.createElement('div'); frame.className = 'frame ' + section.dataset.c; frame.dataset.theme = theme;
      frame.append(tpl.content.cloneNode(true));
      wrap.append(cap, frame); frames.append(wrap);
    }
  });
  document.querySelectorAll('.dial').forEach(dial);
})();

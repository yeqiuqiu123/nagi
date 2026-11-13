'use strict';
// The page is the panel's drawing at page scale:
//  - the rose page line is the panel's now line, continued, and follows its travel;
//  - the trunk leaves the panel's own rail at its last node, and each section hangs from it
//    on a branch, drawn once as it comes into view;
//  - every quoted panel string (tray legend, the "says" table) is computed by the panel's own
//    model from the same demo fixture, so the page never says something the panel wouldn't.
(() => {
  const $ = (id) => document.getElementById(id);
  const page = $('page'); const geo = $('geo'); const frame = $('frame'); const line = $('pageline');
  const SVG = 'http://www.w3.org/2000/svg';
  const R = 10; // the panel's branch elbow radius
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const narrow = window.matchMedia('(max-width: 900px)');
  const svg = (tag, attrs) => { const el = document.createElementNS(SVG, tag); for (const k in attrs) el.setAttribute(k, attrs[k]); return el; };
  const inner = () => { try { return frame.contentDocument; } catch { return null; } };
  const W = () => { try { return frame.contentWindow; } catch { return null; } };

  // ---- Copy the install command --------------------------------------------------
  document.querySelectorAll('[data-copy]').forEach((button) => {
    const status = button.parentElement.querySelector('[role="status"]');
    button.addEventListener('click', async () => {
      const text = $(button.dataset.copy).textContent.replace(/\s+/g, ' ').trim();
      let ok = false;
      try { await navigator.clipboard.writeText(text); ok = true; } catch {}
      button.textContent = ok ? 'Copied' : 'Copy';
      // Confirmed in words on screen and to screen readers; a failure says what to do instead.
      if (status) { status.classList.toggle('sr', ok); status.textContent = ok ? 'Copied the install command.' : "Couldn't copy. Select the command and copy it yourself."; }
      if (ok) setTimeout(() => { button.textContent = 'Copy'; if (status) status.textContent = ''; }, 2400);
    });
  });

  // ---- The page line: measured at rest, following the panel's travel ----------------
  function nowRest() {
    const d = inner(); const nl = d && d.getElementById('nowline');
    if (!nl || !nl.offsetParent) return null;
    const cs = d.defaultView.getComputedStyle(nl);
    const moving = cs.transform === 'none' ? 0 : new DOMMatrixReadOnly(cs.transform).m42;
    const r = nl.getBoundingClientRect();
    return r.top - moving + r.height / 2;
  }
  function measure() {
    const y = nowRest();
    // A layout measurement (never animated, never per frame): the opening's first row and the
    // page line sit at the panel's line. CSS holds the same values as defaults per width.
    if (y != null) {
      const at = Math.round(y * 2) / 2;
      $('opening').style.gridTemplateRows = 'calc(var(--demo-top) + ' + at + 'px) auto';
      line.style.top = 'calc(var(--demo-top) + ' + (at - 1) + 'px)';
    }
    draw();
  }
  let following = false;
  // Reduced motion: the panel never travels, so the page line never moves either.
  const useReducedMotion = () => reduced.matches;
  function follow() {
    const d = inner(); const nl = d && d.getElementById('nowline');
    if (useReducedMotion()) { line.style.transform = ''; line.style.opacity = ''; }
    else if (nl) {
      const cs = d.defaultView.getComputedStyle(nl);
      const m = cs.transform === 'none' ? 0 : new DOMMatrixReadOnly(cs.transform).m42;
      line.style.transform = m ? 'translateY(' + m + 'px)' : '';
      line.style.opacity = cs.opacity === '1' ? '' : cs.opacity;
    }
    if (following) requestAnimationFrame(follow);
  }
  // Follow only while the panel is on screen.
  new IntersectionObserver((entries) => {
    const on = entries.some((e) => e.isIntersecting);
    if (on && !following) { following = true; requestAnimationFrame(follow); } else if (!on) following = false;
  }).observe(frame);

  // ---- Trunk and branches ---------------------------------------------------------------
  const drawn = new Set();
  let io = null;
  function draw() {
    const pr = page.getBoundingClientRect();
    const fr = frame.getBoundingClientRect();
    const sections = [...document.querySelectorAll('.branch')];
    if (!sections.length) return;
    geo.replaceChildren();
    // The trunk leaves the panel's own rail (its --trunk-x) at the panel's last node.
    const d = inner();
    const panelEl = d && d.getElementById('panel');
    const rail = panelEl ? parseFloat(d.defaultView.getComputedStyle(panelEl).getPropertyValue('--trunk-x')) || 22 : 22;
    const tx = fr.left - pr.left + rail;
    const last = d && [...d.querySelectorAll('#ended .ended-line, #past [data-node="anchor"], #past .proj-name')].pop();
    const lr = last && last.getBoundingClientRect();
    // Start at the bottom of the panel's last ring (r 4, 2 px stroke) and draw over the panel's
    // lower edge, so the stroke is continuous from the panel's rail into the page.
    const top = lr && lr.height ? Math.min(fr.top - pr.top + lr.top + lr.height / 2 + 5, fr.bottom - pr.top) : fr.bottom - pr.top - 14;
    const nodes = sections.map((s) => {
      const h = s.querySelector('h2'); const hr = h.getBoundingClientRect();
      const lh = parseFloat(getComputedStyle(h).lineHeight) || hr.height;
      return { s, x: hr.left - pr.left - 16, y: hr.top - pr.top + Math.min(hr.height, lh) / 2 };
    });
    const end = Math.max(...nodes.map((n) => n.y)) - R;
    const trunk = svg('path', { d: `M${tx} ${top} V${end}` });
    geo.prepend(trunk);
    // PROTOTYPE: each section's node is one of the panel's own.
    const KIND = { running: ['n-running', 5], computer: ['n-ring', 3], limit: ['n-ring', 4], parent: ['n-parent', 4.5], asks: ['n-ask', 5], pending: ['n-pending', 3.5] };
    nodes.forEach(({ s, x, y }) => {
      const [cls, r] = KIND[s.dataset.node] || ['n', 4];
      const path = svg('path', { d: `M${tx} ${y - R} Q${tx} ${y} ${tx + R} ${y} H${x - r - 1}` });
      const node = svg('circle', { class: cls, cx: x, cy: y, r });
      path.dataset.section = s.id;
      geo.append(path, node);
      const waiting = !drawn.has(s.id) && !reduced.matches;
      if (waiting) { const len = path.getTotalLength(); path.style.strokeDasharray = len + ' ' + len; path.style.strokeDashoffset = String(len); node.classList.add('wait'); }
      // A parent's children hang from its own rail, as in the panel: 22 px in, 10 px elbows.
      const kids = [...s.querySelectorAll('.kids > li')];
      if (kids.length) {
        const g = svg('g', { 'data-kids': s.id }); if (waiting) g.classList.add('wait');
        const ys = kids.map((li) => { const b = li.querySelector('b').getBoundingClientRect(); return b.top - pr.top + b.height / 2; });
        g.append(svg('path', { d: `M${x} ${y + r + 1} V${ys[ys.length - 1] - R}` }));
        kids.forEach((li, i) => { const [c, kr] = KIND[li.dataset.node]; g.append(svg('path', { d: `M${x} ${ys[i] - R} Q${x} ${ys[i]} ${x + R} ${ys[i]} H${x + 22 - kr - 1}` }), svg('circle', { class: c, cx: x + 22, cy: ys[i], r: kr })); });
        geo.append(g);
      }
    });
    geo.setAttribute('height', page.scrollHeight);
    watch(sections);
  }
  // Each branch draws once as its section comes into view: 260 ms, the panel's draw.
  function watch(sections) {
    if (reduced.matches || !('IntersectionObserver' in window)) return;
    if (!io) io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (!e.isIntersecting || drawn.has(e.target.id)) return;
      drawn.add(e.target.id); io.unobserve(e.target);
      const path = geo.querySelector(`path[data-section="${e.target.id}"]`);
      if (!path) return;
      const node = path.nextElementSibling; if (node) node.classList.remove('wait');
      const kg = geo.querySelector(`g[data-kids="${e.target.id}"]`); if (kg) kg.classList.remove('wait');
      const len = path.getTotalLength();
      path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }], { duration: 260, easing: 'cubic-bezier(0.77, 0, 0.175, 1)', fill: 'forwards' })
        .onfinish = () => { path.style.strokeDasharray = ''; path.style.strokeDashoffset = ''; };
    }), { rootMargin: '0px 0px -20% 0px' });
    sections.forEach((s) => { if (!drawn.has(s.id)) io.observe(s); });
  }

  // ---- The panel's own words, from the same fixture --------------------------------
  function quote() {
    const w = W(); const demo = w && w.NagiDemo; const M = w && w.NagiModel;
    if (!demo || !M || !demo.envelope) return;
    const now = w.Date.now();
    document.querySelectorAll('[data-tray]').forEach((el) => {
      const env = demo.envelope(el.dataset.tray);
      if (env) el.textContent = M.traySources(env, now) || '';
    });
    const vm = (scene) => M.buildSources(demo.envelope(scene), { now }).vm;
    const limits = vm('limits').limits.find((l) => l.pct == null && /tried/.test(l.date));
    const story = vm('empty').limits;
    const dated = story.find((l) => !l.head && l.pct != null && !l.empty);
    const off = vm('offline').hero;
    const set = (key, text) => { const el = document.querySelector(`[data-say="${key}"]`); if (el && text) el.textContent = text; };
    // The panel's own parts, never joined by the site.
    if (limits) set('tried', limits.date);
    if (dated) { set('reset-pct', dated.pct + '% left'); set('reset-date', dated.date); }
    if (off && off.alert) { set('offline-alert', off.alert); set('offline-sub', off.subs[0]); }
  }

  let ready = false;
  function onReady() {
    if (ready) return; ready = true;
    measure(); quote();
  }
  frame.addEventListener('panelresize', () => { measure(); if (!ready) onReady(); });
  // The quotes need only the panel's model and fixture, not its first draw.
  frame.addEventListener('load', () => { quote(); try { W().NagiDemo.on(() => quote()); } catch {} });
  window.addEventListener('message', (event) => {
    if (event.origin === location.origin && event.data && event.data.nagiPanel === 'ready') { ready = false; onReady(); }
  });
  window.addEventListener('resize', () => requestAnimationFrame(measure));
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
  window.addEventListener('load', draw);
  draw();
})();

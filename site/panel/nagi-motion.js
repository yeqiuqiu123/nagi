'use strict';
// Nagi glance motion: the only two things that move (spec section 6).
//  1. What is new since the last look: the now line travels up across rows that
//     started since then, and their branches draw in spawn order. Occasional: only
//     on an open at least 30 minutes after the last one, with new rows.
//  2. That a silence ended: the stroke clears when the agent speaks again.
// Reduced motion: neither runs; the stroke simply disappears.
(() => {
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => reducedQuery.matches;
  // Canonical tokens from the motion rules: --ease-out and --ease-in-out.
  const EASE_OUT = 'cubic-bezier(0.23, 1, 0.32, 1)';
  const EASE_IN_OUT = 'cubic-bezier(0.77, 0, 0.175, 1)';
  const GATE_MS = 30 * 60000;

  function gateOpen(vm, opened, lastOpen) {
    return !reduced() && vm.mode === 'live' && lastOpen != null && opened - lastOpen >= GATE_MS && vm.newRows > 0;
  }

  function playOpen({ vm, opened, lastOpen, nowline, scroll, geo, rows }) {
    if (!gateOpen(vm, opened, lastOpen)) return;
    const anims = [];
    // Branches new since the last open draw in spawn order. Their nodes stay put and visible
    // throughout: no entrance from scale(0), no spring overshoot (motion rules 4 and 7).
    const fresh = [...geo.querySelectorAll('.branch[data-new]')].sort((a, b) => a.dataset.start - b.dataset.start);
    fresh.forEach((path, i) => {
      if (i >= 6) return; // at most six staggered; the rest are simply there
      const length = path.getTotalLength();
      const delay = 260 + i * 90;
      path.style.strokeDasharray = length + ' ' + length;
      anims.push(path.animate([{ strokeDashoffset: length }, { strokeDashoffset: 0 }], { duration: 260, delay, easing: EASE_IN_OUT, fill: 'backwards' }));
    });
    // The now line travels up from just below the lowest new row, crossing them.
    const lineTop = nowline.getBoundingClientRect().top;
    const floor = scroll.getBoundingClientRect().bottom - 4;
    const dy = Math.min(floor, Math.max(...rows.map((r) => r.getBoundingClientRect().bottom)) + 4) - lineTop;
    if (dy > 0) {
      // The sweep stays quieter than the rows it crosses: it fades up as it reaches now.
      const travel = nowline.animate([{ transform: `translateY(${dy}px)`, opacity: 0.45 }, { transform: 'none', opacity: 1 }], { duration: 700, easing: EASE_OUT, fill: 'backwards' });
      anims.push(travel);
      const pending = rows.map((r) => ({ r, y: r.getBoundingClientRect().top + r.getBoundingClientRect().height / 2 }));
      const watch = () => {
        const t = getComputedStyle(nowline).transform;
        const y = lineTop + new DOMMatrixReadOnly(t === 'none' ? undefined : t).m42;
        for (const p of pending) {
          if (p.done || y > p.y) continue;
          p.done = true;
          const dot = geo.querySelector(`circle[data-key="${CSS.escape(p.r.dataset.key)}"]`);
          // The crossed row's node settles from ×1.6 on --ease-out: critically damped, no overshoot.
          if (dot) anims.push(dot.animate([{ transform: 'scale(1.6)' }, { transform: 'none' }], { duration: 320, easing: EASE_OUT }));
        }
        if (travel.playState === 'running' || travel.playState === 'pending') requestAnimationFrame(watch);
      };
      requestAnimationFrame(watch);
    }
    // Any click or key snaps everything to the end state.
    const snap = () => { anims.forEach((a) => { try { a.finish(); } catch {} }); };
    window.addEventListener('pointerdown', snap, { capture: true, once: true });
    window.addEventListener('keydown', snap, { capture: true, once: true });
  }

  // The stroke a row carried before it spoke again scales back to nothing.
  function clearSilence(row, lull, before) {
    if (reduced()) return;
    const ghost = lull || document.createElement('span');
    if (!lull) { ghost.className = 'lull'; ghost.setAttribute('aria-hidden', 'true'); row.append(ghost); }
    ghost.classList.remove('hidden', 'late');
    if (before >= 0.5) ghost.classList.add('late');
    const a = ghost.animate([{ transform: `scaleX(${before})` }, { transform: 'scaleX(0)' }], { duration: 240, easing: EASE_OUT, fill: 'forwards' });
    a.onfinish = () => { ghost.classList.add('hidden'); if (!lull) ghost.remove(); };
  }

  window.NagiMotion = Object.freeze({ playOpen, clearSilence, reduced, gateOpen });
})();

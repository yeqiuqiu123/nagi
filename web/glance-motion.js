'use strict';
// Nagi glance motion: the only two things that move (design/v3/project-bar.md, Motion).
//  1. What a limit lost since the last look: on an open, a dial whose percent changed
//     sweeps from the old value to the new one. Never on the first open; never when
//     nothing changed.
//  2. Who is new since the last look: their branches draw in spawn order. Occasional: only
//     on an open at least 30 minutes after the last one.
// Reduced motion: neither runs; values simply appear.
(() => {
  const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => reducedQuery.matches;
  // The canonical --ease-in-out from the motion rules.
  const EASE_IN_OUT = 'cubic-bezier(0.77, 0, 0.175, 1)';
  // A critically damped spring, 450 ms perceptual (no overshoot: an arc never claims more
  // than was read). Generated with Motion's CSS spring tool.
  const SPRING = 'linear(0, 0.0507, 0.1614, 0.2915, 0.4192, 0.5342, 0.6326, 0.714, 0.7796, 0.8317, 0.8723, 0.9038, 0.9279, 0.9462, 0.96, 0.9704, 0.9781, 0.9839, 0.9882, 0.9913, 0.9937, 0.9954, 0.9966, 0.9975, 0.9982, 0.9987, 1)';
  const GATE_MS = 30 * 60000;

  function gateOpen(vm, opened, lastOpen) {
    return !reduced() && vm.mode === 'live' && lastOpen != null && opened - lastOpen >= GATE_MS && vm.newRows > 0;
  }

  // Dials whose value changed since the last open sweep from where they were.
  function sweepDials(dials, before, anims) {
    if (!before) return;
    dials.querySelectorAll('.arc').forEach((arc) => {
      const was = before[arc.dataset.key]; const now = Number(arc.dataset.pct);
      if (typeof was !== 'number' || Math.abs(was - now) < 1) return;
      const length = arc.getTotalLength();
      const dash = (pct) => (length * pct / 100).toFixed(2) + ' ' + length.toFixed(2);
      anims.push(arc.animate([{ strokeDasharray: dash(was) }, { strokeDasharray: dash(now) }], { duration: 800, easing: SPRING, fill: 'backwards' }));
    });
  }

  function playOpen({ vm, opened, lastOpen, lastDials, geo, dials }) {
    if (reduced() || vm.mode !== 'live') return;
    const anims = [];
    sweepDials(dials, lastDials, anims);
    if (gateOpen(vm, opened, lastOpen)) {
      // Branches new since the last open draw in spawn order. Their nodes stay put and visible
      // throughout: no entrance from scale(0), no spring overshoot.
      const fresh = [...geo.querySelectorAll('.branch[data-new]')].sort((a, b) => a.dataset.start - b.dataset.start);
      fresh.forEach((path, i) => {
        if (i >= 6) return; // at most six staggered; the rest are simply there
        const length = path.getTotalLength();
        if (!length) return;
        path.style.strokeDasharray = length + ' ' + length;
        anims.push(path.animate([{ strokeDashoffset: length }, { strokeDashoffset: 0 }], { duration: 260, delay: 160 + i * 90, easing: EASE_IN_OUT, fill: 'backwards' }));
      });
    }
    if (!anims.length) return;
    // Any click or key snaps everything to the end state.
    const snap = () => { anims.forEach((a) => { try { a.finish(); } catch {} }); };
    window.addEventListener('pointerdown', snap, { capture: true, once: true });
    window.addEventListener('keydown', snap, { capture: true, once: true });
  }

  window.NagiMotion = Object.freeze({ playOpen, reduced, gateOpen });
})();

'use strict';
// Embeds the real glance panel (site/panel/, synced from web/) as a live demo.
// Markup: <div class="demo" data-scene="story"><iframe class="demo-frame" …></iframe>
//          <div class="demo-controls">…<button data-demo="toggle">…</button><button data-demo="replay">…</button></div></div>
// The panel reports its natural height (as it does to the native shells); the frame follows it.
(() => {
  const frames = new Map();
  window.addEventListener('message', (event) => {
    if (event.origin !== location.origin || !event.data || typeof event.data.nagiPanel !== 'string') return;
    const frame = [...frames.keys()].find((f) => f.contentWindow === event.source);
    if (!frame) return;
    const [kind, value] = event.data.nagiPanel.split(':');
    if (kind === 'height') {
      // First draw: only now does the demo (frame, controls, page line) become visible.
      const demo = frame.closest('.demo'); demo.classList.add('drawn');
      const host = demo.closest('.opening'); if (host) host.classList.add('drawn');
      frame.style.height = Math.max(320, Math.min(900, Number(value) || 0)) + 'px';
      frame.dispatchEvent(new CustomEvent('panelresize', { bubbles: true }));
    }
    if (kind === 'ready') frames.get(frame).ready();
  });

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Narrow screens: the panel relays out at the width it's given (it supports 320 px and up).
  // CSS zoom (the Mac app's density) would misplace the panel's SVG geometry in browsers.
  document.querySelectorAll('.demo').forEach((demo) => {
    const frame = demo.querySelector('iframe');
    if (frame.dataset.src) {
      const q = new URLSearchParams({ scene: demo.dataset.scene || 'story' });
      // Off-screen at load (phones), the panel waits until it's nearly in view, or until a
      // section that quotes it comes into view (data-wake), whichever is first.
      frame.loading = 'lazy';
      const wake = demo.dataset.wake && document.querySelectorAll(demo.dataset.wake);
      if (wake && wake.length) {
        const io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting)) { frame.loading = 'eager'; io.disconnect(); } });
        wake.forEach((el) => io.observe(el));
      }
      frame.src = frame.dataset.src + '?' + q;
    }
    const toggle = demo.querySelector('[data-demo="toggle"]');
    const replay = demo.querySelector('[data-demo="replay"]');
    const state = { started: false };
    const api = () => { try { return frame.contentWindow.NagiDemo; } catch { return null; } };
    const sync = (s) => {
      if (!toggle) return;
      const had = document.activeElement;
      toggle.hidden = s.done;
      toggle.textContent = s.playing ? 'Pause' : 'Play';
      toggle.setAttribute('aria-pressed', String(!s.playing));
      // Replay appears once the story is paused or over, never beside Pause.
      if (replay) replay.hidden = !(s.done || (!s.playing && s.beat > 0));
      // Keyboard focus never falls to the page: it moves to whichever control remains.
      if (had && had.hidden && (had === toggle || had === replay)) (had === toggle ? replay : toggle).focus();
    };
    // The demo API exists as soon as the panel page has loaded; its first draw may wait for us.
    frame.addEventListener('load', () => frames.get(frame).ready());
    frames.set(frame, { ready() {
      const d = api();
      // The frame's window survives a reload; its demo API doesn't, so wire each API once.
      if (!d || state.wired === d) return;
      state.wired = d;
      d.on(sync);
      // The story plays when it scrolls into view, once; reduced motion waits for Play.
      if (state.replay) { state.replay = false; state.started = true; d.play(); return; }
      if (d.scene === 'story' && !reduced.matches && !state.started) {
        // The open plays once the panel's now line (at rest) is on screen: data-start names it.
        // ...or once the panel's slot is well inside the screen, so a short phone never shows
        // an empty space where the panel will be.
        const mark = (demo.dataset.start && document.querySelector(demo.dataset.start)) || frame;
        const go = (entries) => { if (!state.started && entries.some((e) => e.isIntersecting)) { state.started = true; d.play(); stop(); } };
        const ioLine = new IntersectionObserver(go, { threshold: 0 });
        const ioSlot = new IntersectionObserver(go, { rootMargin: '0px 0px -15% 0px', threshold: 0 });
        const stop = () => { ioLine.disconnect(); ioSlot.disconnect(); };
        ioLine.observe(mark); ioSlot.observe(frame);
      }
    } });
    if (toggle) toggle.addEventListener('click', () => {
      const d = api(); if (!d) return;
      state.started = true;
      if (toggle.textContent === 'Pause') d.pause(); else d.play();
    });
    // Replay reloads the panel page; it plays again as soon as it is ready.
    if (replay) replay.addEventListener('click', () => { const d = api(); if (!d) return; state.started = false; state.replay = true; if (toggle) { toggle.hidden = false; toggle.textContent = 'Pause'; toggle.focus(); } d.replay(); });
    // A width change can change the panel's natural height: let it measure itself again.
    let resizeTimer = 0;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { try { if (demo.classList.contains('drawn')) frame.contentWindow.NagiGlance.refresh(); } catch {} }, 150);
    });
  });
})();

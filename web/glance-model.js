'use strict';
// Nagi glance view model: turns /api/glance and /api/limits (contract v2) into
// what the panel and the tray print. Pure; no DOM. Times print in local time.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NagiModel = api;
})(typeof self !== 'undefined' ? self : this, function () {
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const ACTIVE = new Set(['queued', 'preparing', 'starting', 'running', 'waiting']);
  const STATE_WORD = { completed: 'completed', failed: 'failed', interrupted: 'stopped', idle: 'idle' };
  const PROVIDERS = [['codex', 'Codex'], ['claude', 'Claude'], ['cursor', 'Cursor']];
  // Codex and Claude always get a line (a missing read says so); others only when a source reads them.
  const OPTIONAL_PROVIDERS = new Set(['cursor']);
  const MODEL_WORDS = [[/opus/i, 'Opus'], [/sonnet/i, 'Sonnet'], [/haiku/i, 'Haiku'], [/fable/i, 'Fable'],
    [/sol/i, 'Sol'], [/grok/i, 'Grok'], [/gemini/i, 'Gemini'], [/gpt/i, 'GPT']];

  const ms = (iso) => { const t = iso ? Date.parse(iso) : NaN; return Number.isFinite(t) ? t : null; };
  const pad = (n) => String(n).padStart(2, '0');
  // Times truncate to the minute.
  const hm = (t) => { const d = new Date(t); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  const sameDay = (a, b) => new Date(a).toDateString() === new Date(b).toDateString();
  const day = (t) => DAYS[new Date(t).getDay()];
  const longDate = (t) => { const d = new Date(t); return day(t) + ' ' + d.getDate() + ' ' + MONTHS[d.getMonth()] + ' ' + hm(t); };
  // Dates first: today prints `today HH:mm`, another day the weekday, date and time.
  const dateFrom = (t, now) => (sameDay(t, now) ? 'today ' + hm(t) : longDate(t));
  const shortFrom = (t, now) => (sameDay(t, now) ? hm(t) : day(t) + ' ' + hm(t));
  const dur = (span) => {
    const m = Math.floor(Math.max(0, span) / 60000);
    if (m < 1) return Math.floor(Math.max(0, span) / 1000) + ' s';
    if (m < 60) return m + ' m';
    const h = Math.floor(m / 60);
    if (h < 24) return h + ' h ' + pad(m % 60) + ' m';
    return Math.floor(h / 24) + ' d ' + (h % 24) + ' h';
  };
  const ago = (span) => (span < 2000 ? 'just now' : dur(span) + ' ago');
  // The panel's status column and dials print compact durations: 45s, 7m, 3h 29m, 2d 4h.
  const short = (span) => {
    const sec = Math.floor(Math.max(0, span) / 1000);
    if (sec < 60) return sec + 's';
    const m = Math.floor(sec / 60);
    if (m < 60) return m + 'm';
    const h = Math.floor(m / 60);
    if (h < 24) return h + 'h' + (m % 60 ? ' ' + (m % 60) + 'm' : '');
    return Math.floor(h / 24) + 'd' + (h % 24 ? ' ' + (h % 24) + 'h' : '');
  };
  // A reset time under a dial is absolute and short: today the time, within the week the
  // weekday and time, later the date. The full date is always in the dial's detail and label.
  const whenShort = (t, now) => {
    if (sameDay(t, now)) return hm(t);
    if (t - now < 6.5 * 86400000) return day(t) + ' ' + hm(t);
    const d = new Date(t); return d.getDate() + ' ' + MONTHS[d.getMonth()];
  };
  // How much of a window's time is left, 0..1, for the tick on its dial. Only windows whose
  // length Nagi knows get one: five hours, seven days, a calendar month. Never a guess.
  const WINDOW_MS = { five_hour: 5 * 3600000, weekly: 7 * 86400000 };
  function timeLeft(kind, resets, now) {
    let length = WINDOW_MS[kind] || null;
    if (kind === 'monthly') { const start = new Date(resets); start.setMonth(start.getMonth() - 1); length = resets - start.getTime(); }
    if (!length || resets == null) return null;
    const left = (resets - now) / length;
    return left > 1.001 ? null : Math.min(1, Math.max(0, left));
  }
  // Provider brand colour, keyed by the T3 provider instance driver (never guessed from a model name).
  // T3 drivers, plus the provider names direct sources (Claude Code, Codex, Cursor) report.
  const PROVIDER_KEYS = { claudeAgent: 'claude', claude: 'claude', codex: 'codex', grok: 'grok', antigravity: 'gemini', cursor: 'cursor' };
  const providerKey = (driver) => (Object.prototype.hasOwnProperty.call(PROVIDER_KEYS, driver) ? PROVIDER_KEYS[driver] : null);
  const modelWord = (model) => {
    if (!model) return 'model unknown';
    for (const [re, word] of MODEL_WORDS) if (re.test(model)) return word;
    return model;
  };
  // Percent left never rounds a non-empty window to 0 or a partly used one to 100.
  const percent = (p) => (p <= 0 ? 0 : p >= 100 ? 100 : Math.min(99, Math.max(1, Math.round(p))));
  const projectName = (title) => (title === 'No project' ? 'no project' : title);

  // T3's projectIdentity.ts, ported exactly: NFKC, the \p{L}\p{N} words rule, and the
  // ×31 hash over PROJECT_ICON_COLORS in T3's order.
  const ICON_COLORS = ['gray', 'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal', 'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose'];
  function projectIdentity(projectName) {
    const normalized = String(projectName).normalize('NFKC').trim();
    const words = normalized.match(/[\p{L}\p{N}]+/gu) || [];
    let monogram = 'PR';
    if (words[0]) {
      const glyphs = Array.from(words[0]);
      const first = glyphs[0] ?? 'P';
      const second = glyphs.slice(1).find((g) => /\p{N}/u.test(g)) ?? (words.length > 1 ? Array.from(words.at(-1) ?? '')[0] : glyphs.at(-1)) ?? first;
      monogram = Array.from(`${first}${second}`.toUpperCase()).slice(0, 2).join('');
    }
    const seed = normalized.toLocaleLowerCase('en-US') || 'project';
    let index = 0;
    for (const glyph of seed) index = (index * 31 + (glyph.codePointAt(0) ?? 0)) % ICON_COLORS.length;
    return { monogram, color: ICON_COLORS[index] ?? 'blue' };
  }

  // A repeated project prefix (`Docs:` under Lantern Docs) is dimmed, never removed.
  function splitPrefix(title, project) {
    const m = /^([^:]{1,24}):\s+(.+)$/.exec(title);
    if (!m) return { prefix: '', rest: title };
    const words = new Set(String(project).toLowerCase().split(/\s+/));
    return m[1].toLowerCase().split(/\s+/).every((w) => words.has(w)) ? { prefix: m[1] + ':', rest: m[2] } : { prefix: '', rest: title };
  }

  function agentsMode(agents) {
    const status = agents && agents.status;
    if (status === 'ok' || status === 'quiet') return 'live';
    if (status === 'last_known' && agents.data) return 'dated';
    if (status === 'not_set_up') return 'not_set_up';
    if (status === 'unsupported') return 'unsupported';
    if (status === 'unavailable' && agents.reason === 'checking') return 'checking';
    return 'never';
  }

  // One row per thread. State precedence on a live running row: asks you, then stuck,
  // then the plain silence stroke. Dated rows carry no alarms and no strokes.
  function rowModel(a, ctx, project, depth) {
    const active = ACTIVE.has(a.state);
    const started = ms(a.startedAt);
    const activity = ms(a.lastActivityAt);
    const ref = ctx.dated ? ctx.checked : ctx.now;
    const w = a.waitingOnYou || {};
    const asks = active && !ctx.dated && !!(w.question || w.approval);
    const stuck = active && !ctx.dated && !asks && a.stuck === true;
    let silent = activity == null ? null : Math.max(0, ctx.now - activity);
    if (silent != null && ctx.reduced) silent = Math.floor(silent / 60000) * 60000;
    const meta = [modelWord(a.model)];
    let state = null;
    let silence = null;
    if (!active) {
      meta.push(STATE_WORD[a.state] || a.state);
    } else {
      if (asks) state = { text: 'asks you · ' + dur(silent || 0), cls: 'asks' };
      else if (stuck) state = { text: 'silent ' + dur(silent || 0), cls: 'stuck' };
      if (a.state === 'queued' || a.state === 'preparing' || a.state === 'starting') meta.push(a.state);
      else {
        if (started != null) meta.push(dur(ref - started));
        if (a.state === 'waiting' && !asks) meta.push('waiting');
        if (ctx.dated) meta.push('last seen ' + hm(ctx.checked));
        else if (!state && silent != null) meta.push(ago(silent));
      }
      const known = a.liveness === 'recent' || a.liveness === 'inactive';
      if (a.state === 'running' && !ctx.dated && !asks && known && a.stuck !== null && silent != null) {
        const f = stuck ? 1 : Math.min(1, silent / (ctx.stuckMinutes * 60000));
        silence = { f, cls: f < 1 / 3 ? 'hidden' : f < 0.5 ? 'quiet' : 'late' };
      }
    }
    const kids = (a.children || []).map((c) => rowModel(c, ctx, project, depth + 1));
    const latest = Math.max(active && started != null ? started : -Infinity, ...kids.map((k) => k.latest));
    // What needs the owner comes first: asks you, then stuck, then the newest.
    const urgency = Math.max(asks ? 2 : stuck ? 1 : 0, ...kids.map((k) => k.urgency));
    kids.sort((x, y) => (y.urgency - x.urgency) || (y.latest - x.latest) || (x.title < y.title ? -1 : 1));
    // The status column: the model and run time, then a state only when there is one to say.
    // A healthy row says nothing more; silence speaks from a third of the stuck threshold.
    let run = ''; let note = null;
    if (active) {
      if (a.state === 'queued' || a.state === 'preparing' || a.state === 'starting') run = a.state;
      else if (started != null) run = short(ref - started);
      if (asks) note = { text: 'asks you · ' + short(silent || 0), cls: 'asks' };
      else if (stuck) note = { text: 'silent ' + short(silent || 0), cls: 'stuck' };
      else if (ctx.dated) note = { text: 'last seen ' + hm(ctx.checked), cls: 'dated' };
      else if (a.state === 'waiting') note = { text: 'waiting', cls: 'quiet' };
      else if (silence && silence.cls !== 'hidden') note = { text: 'silent ' + short(silent), cls: silence.cls };
      else if (!silence && a.state === 'running' && silent != null && silent >= 60000) note = { text: short(silent) + ' ago', cls: 'quiet' };
    }
    const parts = splitPrefix(a.title, project);
    const href = (a.links && (a.links.desktop || a.links.web)) || '';
    const label = a.title + '. ' + (state ? state.text + ', ' : '') + meta.join(', ') + '.' + (href ? ' Opens in ' + ctx.appName + '.' : '');
    return {
      id: a.id, title: a.title, prefix: parts.prefix, rest: parts.rest, depth,
      kind: active ? 'running' : 'parent', state: a.state, asks, stuck, meta, provider: providerKey(a.provider),
      pending: active && a.state !== 'running' && !asks, stateWord: state, silence,
      model: meta[0], run, note, urgency, dated: !!ctx.dated,
      silentMs: silent, started, latest, isNew: ctx.lastOpen != null && active && started != null && started > ctx.lastOpen,
      href, label, children: kids,
    };
  }

  function walk(rows, fn) { for (const r of rows) { fn(r); walk(r.children, fn); } }

  // A source that never measures a provider, or whose measure another source now gives, says nothing.
  const SILENT_LIMITS = new Set(['preferred_direct_source', 'not_measured_here']);
  // Reasons the owner can act on get their own words instead of a bare "couldn't check".
  const LIMIT_REASONS = {
    claude_login_expired: 'open Claude Code to sign in again',
    claude_login_missing: 'sign in to Claude Code to see limits',
    claude_login_invalid: "couldn't read your Claude Code sign-in",
    codex_login_missing: 'sign in to Codex to see limits',
    codex_login_expired: 'open Codex to sign in again',
    codex_login_invalid: "couldn't read your Codex sign-in",
    codex_account_changed: 'Codex sign-in changed; checking the new account',
    codex_usage_opt_in: 'reconnect Codex in Settings → Sources to see limits',
    cursor_login_missing: 'sign in to Cursor to see limits',
    cursor_login_expired: 'sign in to Cursor again to see limits',
    cursor_login_invalid: "couldn't read Cursor's sign-in; encrypted sign-ins aren't supported yet",
  };

  function limitLines(limits, ctx) {
    const valued = []; const failed = []; const absent = [];
    const providers = (limits && limits.providers) || {};
    for (const [key, name] of PROVIDERS) {
      const src = providers[key];
      if (!src && OPTIONAL_PROVIDERS.has(key)) continue;
      const status = src ? src.status : 'unavailable';
      if (src && status === 'unsupported' && SILENT_LIMITS.has(src.reason)) continue;
      if ((status === 'ok' || status === 'last_known') && src.data && src.data.accounts && src.data.accounts.length) {
        const tried = "couldn't check · tried " + hm(ctx.limitsDownAt != null ? ctx.limitsDownAt : ms(src.attemptedAt) || ctx.now);
        for (const acc of src.data.accounts) {
          // Each account keeps its own truth: fresh, dated (as of its own check) or unavailable.
          const accStatus = status === 'last_known' && (acc.status || 'ok') === 'ok' ? 'last_known' : acc.status || 'ok';
          if (accStatus === 'unsupported') {
            absent.push({ name: acc.label, pct: null, empty: false, date: 'no limits for this account type', label: acc.label + ': no limits for this account type', subs: [],
              provider: key, state: 'absent', short: ['no limits', 'this account'] });
            continue;
          }
          // Windows that have already reset are never shown, on every render.
          const wins = [...(acc.windows || []), ...(acc.secondaryWindows || [])].map((w) => ({
            label: w.label, kind: w.kind, left: percent(w.remainingPercent), resets: ms(w.resetsAt),
          })).filter((w) => w.resets != null && w.resets > ctx.now).sort((x, y) => x.left - y.left);
          if (!wins.length || accStatus === 'unavailable') {
            failed.push({ name: acc.label, pct: null, empty: false, date: tried, label: acc.label + ': ' + tried, subs: [],
              provider: key, state: 'failed', short: tried.split(' · ') });
            continue;
          }
          // `empty` needs fresh, unexpired evidence; a retained 0 is a dated percentage.
          const fresh = accStatus === 'ok' && ctx.limitsDownAt == null && !ctx.dated;
          const checked = ms(acc.checkedAt) || ms(src.checkedAt);
          const asOf = accStatus === 'last_known' && ctx.limitsDownAt == null && !ctx.dated && checked != null ? 'as of ' + hm(checked) : '';
          const isEmpty = (w) => fresh && w.left === 0;
          // Every limit line reads name, % left, date. A fresh empty window says `empty` and until when.
          const until = (w) => (isEmpty(w) ? 'until ' : '') + dateFrom(w.resets, ctx.now);
          const words = (w) => (isEmpty(w) ? 'empty until ' : w.left + '% left, resets ') + longDate(w.resets);
          // The dial: what's left, how much of the window's time is left, and whether the value
          // is fresh. A window at or under the alert level is low; a dated value is never low.
          const line = (w, name, sub) => ({ name, pct: w.left, empty: isEmpty(w), sub,
            date: until(w), stamp: asOf && wins.length === 1 ? asOf : '', label: (sub ? acc.label + ' ' : '') + name + ': ' + words(w) + (asOf ? ', ' + asOf : ''),
            window: w.label, when: whenShort(w.resets, ctx.now), timeLeft: timeLeft(w.kind, w.resets, ctx.now), dated: !fresh, asOf,
            low: fresh && w.left > 0 && w.left <= ctx.alertAt });
          const about = { provider: key, state: 'value', checked: fresh ? checked : null };
          if (wins.length === 1) {
            valued.push({ ...line(wins[0], acc.label, false), lowest: wins[0].left, subs: [], ...about });
          } else {
            // Several windows: the account heads its own lines, lowest window first.
            valued.push({ ...about, name: acc.label, pct: null, head: true, empty: isEmpty(wins[0]), lowest: wins[0].left, date: '', stamp: asOf,
              label: acc.label + ', ' + wins.length + ' windows, lowest first' + (asOf ? ', ' + asOf : ''),
              subs: wins.map((w) => line(w, w.label, true)) });
          }
        }
        continue;
      }
      let words;
      if (status === 'not_set_up') words = 'not set up on this computer';
      else if (status === 'unsupported') words = 'no limits for this account type';
      else if (!src || src.reason === 'checking') words = 'checking…';
      else if (src.reason === 'account_unverified') words = "its logs don't say which account";
      else if (LIMIT_REASONS[src.reason]) words = LIMIT_REASONS[src.reason];
      else words = "couldn't check · tried " + hm(ctx.limitsDownAt != null ? ctx.limitsDownAt : ms(src.attemptedAt) || ctx.now);
      const absentish = status === 'not_set_up' || status === 'unsupported' || (src && src.reason === 'account_unverified');
      const brief = status === 'not_set_up' ? ['not set up', ''] : status === 'unsupported' ? ['no limits', 'this account']
        : !src || src.reason === 'checking' ? ['checking…', ''] : src.reason === 'account_unverified' ? ['unknown', 'account']
          : LIMIT_SHORT[src.reason] || words.split(' · ');
      const line = { name, pct: null, empty: false, date: words, label: name + ': ' + words, subs: [],
        provider: key, state: absentish ? 'absent' : !src || src.reason === 'checking' ? 'checking' : 'failed', short: brief };
      (status === 'not_set_up' || status === 'unsupported' || (src && src.reason === 'account_unverified') ? absent : failed).push(line);
    }
    valued.sort((x, y) => x.lowest - y.lowest);
    return [...valued, ...failed, ...absent];
  }

  // The same reasons, short enough to sit under a dial; the sentence stays in its detail.
  const LIMIT_SHORT = {
    claude_login_expired: ['sign in again', 'in Claude Code'], claude_login_missing: ['sign in', 'to see limits'], claude_login_invalid: ["couldn't read", 'your sign-in'],
    codex_login_missing: ['sign in', 'to see limits'], codex_login_expired: ['sign in again', 'in Codex'], codex_login_invalid: ["couldn't read", 'your sign-in'],
    codex_account_changed: ['new sign-in', 'checking…'], codex_usage_opt_in: ['reconnect', 'to see limits'],
    cursor_login_missing: ['sign in', 'to see limits'], cursor_login_expired: ['sign in again', 'in Cursor'], cursor_login_invalid: ["couldn't read", 'your sign-in'],
  };

  // Dials: one group per account, one cell per window, from the same lines the detail prints.
  // Window names shorten to their last part (`Weekly · Fable` → `Fable`) unless that collides.
  function dialGroups(lines, tag) {
    return (lines || []).map((l) => {
      const cell = (w, name) => ({ state: w.empty ? 'empty' : w.dated ? 'dated' : w.low ? 'low' : 'value', pct: w.pct, timeLeft: w.timeLeft,
        w: name, d: w.dated && w.asOf ? w.asOf : w.when, label: w.label });
      let cells; let rows;
      if (l.head) {
        const lasts = l.subs.map((x) => String(x.name).split(' · ').pop());
        const names = new Set(lasts).size === lasts.length ? lasts : l.subs.map((x) => x.name);
        cells = l.subs.map((x, i) => cell(x, names[i]));
        rows = l.subs.map((x) => ({ name: x.name, pct: x.pct, empty: x.empty, date: x.date }));
      } else if (l.pct != null) {
        cells = [cell(l, String(l.window || 'Limit').split(' · ').pop())];
        rows = [{ name: l.window || 'Limit', pct: l.pct, empty: l.empty, date: l.date }];
      } else {
        cells = [{ state: l.state || 'failed', pct: null, timeLeft: null, w: (l.short || [l.date])[0], d: (l.short || [])[1] || '', label: l.label }];
        rows = [{ name: '', pct: null, empty: false, date: l.date }];
      }
      const rank = l.pct != null || l.head ? 0 : l.state === 'absent' ? 2 : 1;
      const by = tag ? 'read by ' + tag.name + (tag.label ? ' · ' + tag.label : '') : '';
      const stamp = l.stamp || (l.checked != null ? 'checked ' + hm(l.checked) : '');
      return { key: (tag ? tag.id + ':' : '') + (l.provider || '') + ':' + l.name, name: l.name, provider: l.provider || null, source: tag || null, showSource: false,
        rank, lowest: l.lowest != null ? l.lowest : 101, cells, rows, about: [by, stamp].filter(Boolean).join(' · '),
        label: l.label + (by ? ', ' + by : '') + '.' };
    });
  }

  function limitsFrom(limits) {
    let oldest = null;
    for (const [key] of PROVIDERS) {
      const src = limits && limits.providers && limits.providers[key];
      if (!src || (src.status !== 'ok' && src.status !== 'last_known')) continue;
      for (const at of [ms(src.checkedAt), ...((src.data && src.data.accounts) || []).map((a) => (a.status === 'last_known' ? ms(a.checkedAt) : null))]) {
        if (at != null && (oldest == null || at < oldest)) oldest = at;
      }
    }
    return oldest;
  }

  function rangeText(from, to, now) {
    if (from == null) return '';
    if (sameDay(from, to)) return (sameDay(from, now) ? hm(from) : day(from) + ' ' + hm(from)) + (hm(from) === hm(to) ? '' : '–' + hm(to));
    return day(from) + ' ' + hm(from) + '–' + day(to) + ' ' + hm(to);
  }

  function endedModel(data, ctx) {
    const projects = data.ended || [];
    let top = 0; let sub = 0;
    const groups = projects.map((p) => {
      const counts = { completed: 0, failed: 0, interrupted: 0 };
      let from = null; let to = null; const problems = new Map();
      const scan = (a, depth) => {
        if (!a.contextOnly && !ACTIVE.has(a.state)) {
          if (depth === 0) top++; else sub++;
          if (a.state in counts) counts[a.state]++;
          const end = ms(a.endedAt);
          if (end != null) { if (from == null || end < from) from = end; if (to == null || end > to) to = end; }
          if (a.state === 'failed' || a.state === 'interrupted') {
            const key = (a.parentId || '') + '\u0000' + a.title + '\u0000' + a.state;
            const g = problems.get(key) || { n: 0, title: a.title, state: a.state, model: modelWord(a.model), provider: providerKey(a.provider), from: end, to: end, href: '' };
            g.n++;
            if (end != null && (g.from == null || end < g.from)) g.from = end;
            if (end != null && (g.to == null || end >= g.to)) { g.to = end; g.href = (a.links && (a.links.desktop || a.links.web)) || g.href; }
            if (!g.href) g.href = (a.links && (a.links.desktop || a.links.web)) || '';
            problems.set(key, g);
          }
        }
        (a.children || []).forEach((c) => scan(c, depth + 1));
      };
      p.agents.forEach((a) => scan(a, 0));
      const parts = [];
      if (counts.completed) parts.push(counts.completed + ' completed');
      if (counts.failed) parts.push(counts.failed + ' failed');
      if (counts.interrupted) parts.push(counts.interrupted + ' stopped');
      const range = rangeText(from, to, ctx.now);
      return {
        id: p.id, title: projectName(p.title), last: to == null ? -Infinity : to,
        icon: { ...(p.icon && typeof p.icon === 'object' && p.icon.kind ? p.icon : { kind: 'auto' }), fallback: projectIdentity(p.title) },
        summary: parts.join(', ') + (range ? ' · ' + range : ''), counts, range,
        problems: [...problems.values()].sort((x, y) => (y.to || 0) - (x.to || 0)).map((g) => ({
          title: (g.n > 1 ? g.n + ' × ' : '') + g.title,
          meta: g.model + ' · ' + STATE_WORD[g.state] + ' ' + rangeText(g.from, g.to, ctx.now),
          model: g.model, provider: g.provider, when: STATE_WORD[g.state] + ' ' + rangeText(g.from, g.to, ctx.now),
          href: g.href,
        })),
        n: parts.length,
      };
    }).filter((g) => g.n).sort((x, y) => y.last - x.last);
    const count = data.counts ? data.counts.ended : top + sub;
    const sinceAt = ctx.now - ctx.endedHours * 3600000;
    const since = ctx.endedHours > 144 ? longDate(sinceAt) : day(sinceAt) + ' ' + hm(sinceAt);
    const names = projects.map((p) => projectName(p.title));
    const split = top + ' ' + (top === 1 ? 'thread' : 'threads') + (sub ? ' and ' + sub + ' sub-agent' + (sub === 1 ? '' : 's') : '');
    // The outcome bar and its words: every ended thread once, by how it ended.
    const totals = groups.reduce((t, g) => ({ completed: t.completed + g.counts.completed, failed: t.failed + g.counts.failed, stopped: t.stopped + g.counts.interrupted }), { completed: 0, failed: 0, stopped: 0 });
    const span = ctx.endedHours <= 48 ? ctx.endedHours + ' h' : Math.round(ctx.endedHours / 24) + ' d';
    return {
      totals, span,
      count, since, top, sub, split, projects: names.join(', '), groups,
      lastEnd: groups.length ? groups[0].last : null,
      label: count + ' ended since ' + since + ': ' + split + ', in ' + names.join(', ') + '.',
    };
  }

  // Settings: the server clamps too; the sheet shows the nearest allowed value first.
  const SETTINGS = { stuckMinutes: { min: 5, max: 120, fallback: 15 }, endedExpiryHours: { min: 1, max: 168, fallback: 24 },
    limitAlertPercent: { min: 1, max: 50, fallback: 10 } };
  function clampSetting(key, raw, fallback) {
    const f = SETTINGS[key];
    const text = String(raw == null ? '' : raw).trim();
    const n = /^-?\d+(\.\d+)?$/.test(text) ? Math.round(Number(text)) : NaN;
    if (Number.isNaN(n)) return { value: fallback != null ? fallback : f.fallback, clamped: false, invalid: true };
    const value = Math.min(f.max, Math.max(f.min, n));
    return { value, clamped: value !== n, invalid: false };
  }

  // Tray label: unreachable `–` replaces the count, then `?` outranks `●`, which outranks `0%`.
  // `empty` in the tray needs a fresh ok account with an unexpired window at 0.
  function freshEmpty(limits, now) {
    for (const [key] of PROVIDERS) {
      const src = limits && limits.providers && limits.providers[key];
      if (!src || src.status !== 'ok' || !src.data) continue;
      for (const acc of src.data.accounts || []) {
        if ((acc.status || 'ok') !== 'ok') continue;
        for (const w of [...(acc.windows || []), ...(acc.secondaryWindows || [])]) if (w.remainingPercent <= 0 && ms(w.resetsAt) > now) return acc;
      }
    }
    return null;
  }

  function trayLabel(glance, limits, now) {
    const mode = agentsMode(glance && glance.agents);
    if (mode === 'checking') return '';
    if (mode === 'not_set_up') return '·'; // not a failure: no count, no dash
    if (mode !== 'live') return '–';
    const counts = (glance.agents.data && glance.agents.data.counts) || { running: 0, waitingOnYou: 0, stuck: 0 };
    const empty = !!freshEmpty(limits, now != null ? now : Date.now());
    const mark = counts.waitingOnYou > 0 ? '?' : counts.stuck > 0 ? '●' : empty ? 'empty' : '';
    return [counts.running > 0 ? String(counts.running) : '', mark].filter(Boolean).join(' · ');
  }

  function build(glance, limits, opts) {
    opts = opts || {};
    const now = opts.now != null ? opts.now : Date.now();
    const agents = (glance && glance.agents) || { status: 'unavailable', reason: 'checking' };
    const settings = (glance && glance.settings) || { stuckMinutes: 15, endedExpiryHours: 24 };
    // If Nagi's own reader stops answering after a good read, everything shown is dated.
    const readerDown = opts.readerDownAt != null;
    let mode = agentsMode(agents);
    if (readerDown) mode = glance && (mode === 'live' || mode === 'dated') ? 'dated' : 'never';
    const dated = mode === 'dated';
    const checked = ms(agents.checkedAt) || now;
    const ctx = { now, dated, checked, reduced: !!opts.reduced, limitsDownAt: opts.limitsDownAt != null ? opts.limitsDownAt : null, lastOpen: opts.lastOpen != null ? opts.lastOpen : null,
      stuckMinutes: settings.stuckMinutes || 15, endedHours: settings.endedExpiryHours || 24, appName: opts.appName || 'T3 Code',
      // A dial turns yellow at the owner's own alert level; with the alert off, at its default.
      alertAt: typeof settings.limitAlertPercent === 'number' ? settings.limitAlertPercent : SETTINGS.limitAlertPercent.fallback };
    const app = ctx.appName;
    const data = (mode === 'live' || dated) && agents.data ? agents.data : null;
    const projects = data ? data.projects.map((p) => {
      const rows = p.agents.map((a) => rowModel(a, ctx, p.title, 1));
      rows.sort((x, y) => (y.urgency - x.urgency) || (y.latest - x.latest) || (x.title < y.title ? -1 : 1));
      // T3's icon: its override, its favicon (by opaque key), else the monogram T3 derives from the title.
      const icon = p.icon && typeof p.icon === 'object' && p.icon.kind ? p.icon : { kind: 'auto' };
      return { id: p.id, title: projectName(p.title), rows, latest: Math.max(-Infinity, ...rows.map((r) => r.latest)), urgency: Math.max(0, ...rows.map((r) => r.urgency)),
        icon: { ...icon, fallback: projectIdentity(p.title) } };
    }).sort((x, y) => (y.urgency - x.urgency) || (y.latest - x.latest) || (x.title < y.title ? -1 : 1)) : [];
    const all = [];
    projects.forEach((p) => walk(p.rows, (r) => all.push(r)));
    const counts = data && data.counts ? data.counts : { running: 0, waitingOnYou: 0, stuck: 0, ended: 0 };
    const asks = dated ? 0 : counts.waitingOnYou;
    const stuck = dated ? 0 : counts.stuck;
    const ended = data ? endedModel(data, ctx) : null;

    // With no count to show, the numeral slot holds a quiet dash, never a 56 px slab.
    const hero = { num: '—', word: '', dim: false, quiet: true, calm: false, time: '', alert: '', subs: [], words: [] };
    let message = '';
    if (mode === 'live' || dated) {
      hero.num = String(counts.running); hero.word = 'running'; hero.quiet = false;
    }
    if (mode === 'live') {
      hero.time = hm(now);
      if (asks) hero.words.push({ text: asks + ' asks you', cls: 'asks', target: 'asks' });
      if (stuck) hero.words.push({ text: stuck + ' stuck', cls: 'stuck', target: 'stuck' });
      const running = all.filter((r) => r.state === 'running' && r.silentMs != null);
      if (!hero.words.length && running.length) {
        const quietest = Math.max(...running.map((r) => r.silentMs));
        hero.subs.push(quietest < 60000 ? 'all active just now' : 'all spoke in the last ' + dur(quietest));
        hero.fine = true; // nothing to say: the header stays a count
      }
      else if (!hero.words.length && !counts.running && ended && ended.lastEnd != null) { hero.subs.push('nothing running since ' + shortFrom(ended.lastEnd, now)); hero.since = shortFrom(ended.lastEnd, now); }
      hero.idle = !counts.running && !hero.words.length;
    } else if (dated) {
      hero.dim = true; hero.alert = readerDown ? "Can't reach Nagi" : "Can't reach " + app;
      hero.subs.push('tried ' + hm(readerDown ? opts.readerDownAt : ms(agents.attemptedAt) || now) + ' · list from ' + hm(checked));
      const lim = limitsFrom(limits);
      if (lim != null) hero.subs.push('limits from ' + hm(lim));
    } else if (mode === 'checking') {
      hero.alert = 'Checking ' + app + '…'; hero.calm = true;
    } else if (mode === 'not_set_up') {
      // Not set up is a state of this computer, not a failure: no attempt time, no alarm.
      hero.alert = app + ' not set up'; hero.calm = true;
      message = app + " isn't connected on this computer.";
    } else if (readerDown) {
      hero.alert = "Can't reach Nagi";
      hero.subs.push('tried ' + hm(opts.readerDownAt));
      message = "Nagi's local reader isn't answering.";
    } else {
      hero.alert = mode === 'unsupported' ? "Can't read " + app : "Can't reach " + app;
      hero.subs.push('tried ' + hm(ms(agents.attemptedAt) || now));
      message = mode === 'unsupported' ? 'This version of ' + app + " isn't supported yet." : "Nagi hasn't read " + app + ' on this computer yet.';
    }
    // An observation with omitted threads never claims that nothing ran.
    const incomplete = !!data && (data.omittedRows > 0 || (data.warnings || []).includes('rows_omitted'));
    // A source that only sees what happens after it was connected (hooks, logs) never claims a full history.
    const partial = !!data && (data.warnings || []).includes('partial_coverage');
    if (mode === 'live' && !projects.length && ended && !ended.count) {
      message = incomplete ? "Activity in the last " + ctx.endedHours + " h couldn't be fully read."
        : partial ? 'Nothing seen from ' + app + ' yet. Nagi sees a session once it does something after you connected.'
          : 'Nothing ran in the last ' + ctx.endedHours + ' h.';
    }
    if (incomplete && !counts.running) { hero.subs = hero.subs.filter((t) => !t.startsWith('nothing running since')); hero.since = ''; }
    const omitted = data && data.omittedRows > 0 ? data.omittedRows + (data.omittedRows === 1 ? " thread couldn't be read." : " threads couldn't be read.")
      : data && (data.warnings || []).includes('stale_source') ? 'A session went quiet without finishing, so Nagi stopped showing it.' : '';
    const limitWarnings = PROVIDERS.some(([key]) => { const src = limits && limits.providers && limits.providers[key]; return src && src.warnings && src.warnings.length; });
    const heroLabel = (mode === 'live' || dated ? counts.running + ' running' : hero.alert) + hero.words.map((w) => ', ' + w.text).join('');

    return {
      mode, now, nowTime: hm(now), platform: glance && glance.platform === 'macos' ? 'Mac' : 'Linux',
      hero, heroLabel, message, omitted, projects,
      limits: limitLines(limits, ctx), dated,
      // A limits read that failed after a good one says so once, with both times.
      limitNote: ctx.limitsDownAt != null && !dated && limitsFrom(limits) != null
        ? "couldn't refresh · tried " + hm(ctx.limitsDownAt) + ' · as of ' + hm(limitsFrom(limits))
        : limitWarnings ? "Some limit windows couldn't be read." : '',
      ended: ended && ended.count ? ended : null,
      newRows: all.filter((r) => r.isNew).length,
      warnings: [...((glance && glance.warnings) || []), ...((data && data.warnings) || [])],
      settings,
    };
  }

  // ---- Sources (API v1 envelope) -------------------------------------------------------
  // Harness names and order follow the source catalog; labels are the owner's own.
  const HARNESSES = [['t3', 'T3 Code'], ['openbot', 'OpenBot'], ['pi', 'Pi'], ['omp', 'oh-my-pi'], ['codex', 'Codex'],
    ['claude', 'Claude Code'], ['cursor', 'Cursor'], ['hermes', 'Hermes'], ['openclaw', 'OpenClaw'], ['opencode', 'OpenCode']];
  const harnessName = (id) => (HARNESSES.find(([k]) => k === id) || [id, id])[1];
  const sourceGlance = (env, s) => ({ version: 2, platform: env.platform, checkedAt: env.checkedAt, agents: s.agents,
    settings: env.settings, warnings: [...(env.warnings || []), ...(s.warnings || [])] });
  // A direct source measures one provider only; the other's "unsupported" is not its business.
  const DIRECT_HARNESSES = new Set(['claude', 'codex', 'cursor']);
  const sourceLimits = (s) => {
    const providers = { ...(s.limits || {}) };
    if (s.source && DIRECT_HARNESSES.has(s.source.harness)) {
      for (const [key, value] of Object.entries(providers)) {
        if (value && value.status === 'unsupported' && value.reason === 'account_unsupported') providers[key] = { ...value, reason: 'not_measured_here' };
      }
      // A provider this source doesn't report at all isn't "checking" here either.
      for (const [key] of PROVIDERS) if (!providers[key]) providers[key] = { status: 'unsupported', reason: 'not_measured_here' };
    }
    return { providers };
  };
  const sourceOpts = (opts, s) => ({ ...opts, appName: harnessName(s.source && s.source.harness) });
  const LIVE = new Set(['ok', 'quiet']);
  // Cursor's hooks can't tell a chat T3 runs from one you run yourself, so with a local T3 also
  // connected a Cursor count may repeat T3's. Such counts stay beside the total, never inside it.
  const overlapping = (sources) => {
    const t3 = sources.some((s) => s.source && s.source.harness === 't3' && s.source.placement === 'local');
    return (s) => t3 && s.source && s.source.harness === 'cursor';
  };

  // ---- The panel's one view (v3): dials, a watch list, one Ended line and a source rail ----
  // Source chips: a two-letter monogram per app, numbered when one app is connected twice.
  const MONOGRAMS = { t3: 'T3', claude: 'CC', codex: 'CX', cursor: 'CU', openbot: 'OB', pi: 'PI', omp: 'OM', hermes: 'HE', openclaw: 'OC', opencode: 'OP' };
  function sourceTags(sources) {
    const seen = {};
    return sources.map((s) => {
      const harness = s.source.harness;
      const n = seen[harness] = (seen[harness] || 0) + 1;
      const several = sources.filter((x) => x.source.harness === harness).length > 1;
      const mono = MONOGRAMS[harness] || String(harnessName(harness)).slice(0, 2).toUpperCase();
      return { id: s.source.id, harness, mono, chip: several && n > 1 ? mono + '·' + n : mono, name: harnessName(harness), label: s.source.label,
        // A second connection of the same app is told apart by the owner's own label.
        showLabel: several };
    });
  }

  // What one source says on the rail: a count when it is being read, words only when it
  // can't be read or has seen nothing yet. The sentence stays in its detail.
  function railItem(tag, s, v) {
    const a = s.agents || {};
    const running = ((a.data || {}).counts || {}).running || 0;
    const tried = ms(a.attemptedAt);
    const unseen = v.mode === 'live' && !v.projects.length && !v.ended && ((a.data || {}).warnings || []).includes('partial_coverage');
    const state = v.mode === 'live' ? (unseen ? 'waiting' : running ? 'live' : 'idle') : v.mode === 'checking' ? 'checking'
      : v.mode === 'not_set_up' ? 'absent' : 'down';
    const words = state === 'waiting' ? 'no sessions yet' : state === 'checking' ? 'checking…' : state === 'absent' ? 'not set up'
      : v.mode === 'unsupported' ? 'not supported' : state === 'down' ? "can't reach" + (tried != null ? ' · ' + hm(tried) : '') : '';
    const detail = v.mode === 'live' ? v.message : [v.hero.alert, ...v.hero.subs, v.message].filter(Boolean).join(' · ');
    const name = tag.name + (tag.showLabel || tag.label !== 'This computer' ? ' · ' + tag.label : '');
    return { ...tag, state, count: state === 'live' ? running : null, words, detail, title: name,
      label: name + ': ' + (words || (running ? running + ' running' : 'nothing running')) + '.' };
  }

  function compose(view, items, extra) {
    const vm = view.vm;
    const many = items.length > 1;
    const tags = many ? sourceTags(items.map((i) => i.s)) : [];
    // Dials: every account of every source, lowest first, then failed reads, then absent ones.
    const dials = [];
    const notes = [];
    items.forEach((i, n) => {
      dials.push(...dialGroups(i.vm.limits, many ? tags[n] : null));
      if (i.vm.limitNote) notes.push((many ? tags[n].name + ': ' : '') + i.vm.limitNote);
    });
    dials.sort((x, y) => (x.rank - y.rank) || (x.lowest - y.lowest));
    // A source chip sits beside an account only when two sources report the same provider.
    if (many) {
      const sourcesBy = {};
      dials.forEach((d) => { (sourcesBy[d.provider] = sourcesBy[d.provider] || new Set()).add(d.source.id); });
      dials.forEach((d) => { d.showSource = sourcesBy[d.provider].size > 1; });
    }
    // The watch list: every source's projects in one list, what needs the owner first; a
    // source that can't be reached keeps its dated rows, last.
    const list = [];
    items.forEach((i, n) => i.vm.projects.forEach((p) => list.push({ ...p, key: (many ? tags[n].id + ':' : '') + p.id, source: many ? tags[n] : null, dated: i.vm.mode === 'dated' })));
    list.sort((x, y) => (Number(x.dated) - Number(y.dated)) || (y.urgency - x.urgency) || (y.latest - x.latest) || (x.title < y.title ? -1 : 1));
    // One Ended line. Its count sums each source's own count, leaving out a count that may
    // repeat another source's; every group stays tagged with the source that read it.
    let ended = null;
    const withEnded = items.map((i, n) => ({ e: i.vm.ended, tag: many ? tags[n] : null, aside: extra && extra.maybeTwice ? extra.maybeTwice(i.s) : false })).filter((x) => x.e);
    if (withEnded.length) {
      const counted = withEnded.filter((x) => !x.aside);
      const sum = (fn) => counted.reduce((t, x) => t + fn(x.e), 0);
      const first = withEnded[0].e;
      const totals = { completed: sum((e) => e.totals.completed), failed: sum((e) => e.totals.failed), stopped: sum((e) => e.totals.stopped) };
      const groups = withEnded.flatMap((x) => x.e.groups.map((g) => ({ ...g, key: (x.tag ? x.tag.id + ':' : '') + g.id, source: x.tag })))
        .sort((x, y) => y.last - x.last);
      const count = sum((e) => e.count);
      const problems = [totals.failed ? totals.failed + ' failed' : '', totals.stopped ? totals.stopped + ' stopped' : ''].filter(Boolean).join(', ');
      ended = { count, span: first.span, since: first.since, totals, problems, groups,
        split: many ? '' : first.split,
        label: count + ' ended since ' + first.since + (problems ? ': ' + problems : '') + '.' };
    }
    const rail = many ? items.map((i, n) => railItem(tags[n], i.s, i.vm)) : [];
    const said = items.map((i, n) => (i.vm.omitted ? (many ? tags[n].name + ': ' : '') + i.vm.omitted : '')).filter(Boolean);
    vm.dials = dials; vm.dialNotes = notes; vm.list = list; vm.endedAll = ended; vm.rail = rail; vm.notes = said;
    return view;
  }

  // One source renders through exactly today's single glance. Several sources keep every
  // read source-local: their own truth, limits and Ended line, grouped harness → computer.
  function buildSources(env, opts) { return composeAll(sourcesView(env, opts)); }
  function composeAll(built) { return compose(built.view, built.items, built.extra); }
  function sourcesView(env, opts) {
    opts = opts || {};
    const now = opts.now != null ? opts.now : Date.now();
    const sources = (env && Array.isArray(env.sources)) ? env.sources : [];
    const one = (view, s) => ({ view, items: [{ s: s || { agents: null }, vm: view.vm }] });
    if (opts.readerDownAt != null && !env) return one({ kind: 'single', vm: build(null, null, opts) });
    if (!sources.length) {
      // Nothing connected yet: a calm invitation, never a failure.
      const vm = build({ agents: { status: 'not_set_up', reason: 'no_sources' }, settings: env && env.settings, platform: env && env.platform }, null, opts);
      vm.hero.alert = 'Nothing connected yet'; vm.hero.subs = []; vm.heroLabel = vm.hero.alert;
      vm.message = 'Choose the agent apps Nagi should watch.';
      vm.limits = []; vm.limitNote = '';
      return one({ kind: 'empty', vm });
    }
    if (sources.length === 1) {
      return one({ kind: 'single', vm: build(sourceGlance(env, sources[0]), sourceLimits(sources[0]), sourceOpts(opts, sources[0])), source: sources[0].source }, sources[0]);
    }
    const items = sources.map((s) => ({ s, vm: build(sourceGlance(env, s), sourceLimits(s), sourceOpts(opts, s)) }));
    const readerDown = opts.readerDownAt != null;
    const live = readerDown ? [] : items.filter((i) => LIVE.has(i.s.agents && i.s.agents.status) && i.vm.mode === 'live');
    const maybeTwice = overlapping(sources);
    const count = (i, key) => (((i.s.agents.data || {}).counts || {})[key] || 0);
    const sum = (key) => live.reduce((n, i) => n + (maybeTwice(i.s) ? 0 : count(i, key)), 0);
    const aside = live.filter((i) => maybeTwice(i.s)).reduce((n, i) => n + count(i, 'running'), 0);
    const hero = { num: '—', word: '', dim: false, quiet: true, calm: false, time: '', alert: '', subs: [], words: [] };
    const unread = items.length - live.length;
    if (live.length) {
      // A total sums fresh, source-local counts only, and says when some sources weren't read.
      hero.num = String(sum('running')); hero.word = 'running'; hero.quiet = false; hero.time = hm(now);
      if (sum('waitingOnYou')) hero.words.push({ text: sum('waitingOnYou') + ' asks you', cls: 'asks', target: 'asks' });
      if (sum('stuck')) hero.words.push({ text: sum('stuck') + ' stuck', cls: 'stuck', target: 'stuck' });
      if (aside) hero.subs.push(aside + ' more in Cursor, possibly the same as T3\u2019s');
      if (unread) hero.subs.push(unread + ' of ' + items.length + " sources can't be read right now");
      else if (!hero.words.length) {
        let quietest = -1;
        live.forEach((i) => i.vm.projects.forEach((p) => walk(p.rows, (r) => { if (r.state === 'running' && r.silentMs != null) quietest = Math.max(quietest, r.silentMs); })));
        if (quietest >= 0) hero.subs.push(quietest < 60000 ? 'all active just now' : 'all spoke in the last ' + dur(quietest));
      }
    } else if (readerDown) {
      hero.alert = "Can't reach Nagi"; hero.dim = true; hero.subs.push('tried ' + hm(opts.readerDownAt));
    } else {
      hero.alert = "Can't read your sources";
    }
    const many = items.length > 1;
    const groups = [];
    for (const i of items) {
      const harness = i.s.source.harness;
      let g = groups.find((x) => x.harness === harness);
      if (!g) { g = { harness, name: harnessName(harness), sources: [] }; groups.push(g); }
      const v = i.vm;
      const state = v.mode === 'live' ? '' : [v.hero.alert, ...v.hero.subs].filter(Boolean).join(' · ');
      g.sources.push({ id: i.s.source.id, label: i.s.source.label, placement: i.s.source.placement, vm: v, state,
        coverage: i.s.coverage || {}, warnings: i.s.warnings || [] });
    }
    const heroLabel = (live.length ? hero.num + ' running' : hero.alert) + hero.words.map((w) => ', ' + w.text).join('') + (hero.subs.length ? ', ' + hero.subs.join(', ') : '');
    hero.fine = hero.subs.length === 1 && /^all (active|spoke)/.test(hero.subs[0]);
    hero.idle = !!live.length && hero.num === '0' && !hero.words.length;
    return { items, extra: { maybeTwice }, view: {
      kind: 'multi', showHarness: many, showComputer: many,
      vm: {
        mode: live.length ? 'live' : 'dated', now, nowTime: hm(now), hero, heroLabel, message: '', omitted: '', projects: [],
        limits: [], limitNote: '', ended: null, newRows: items.reduce((n, i) => n + i.vm.newRows, 0),
        warnings: [...(env.warnings || [])], settings: env.settings,
        // Limits stay source-qualified: each source's own account lines under its own name.
        limitGroups: items.map((i) => ({ label: harnessName(i.s.source.harness) + ' · ' + i.s.source.label, lines: i.vm.limits, note: i.vm.limitNote })),
        groups,
      },
    } };
  }

  // The tray reads the same envelope: one mark at a time, never live alarms from unread sources.
  function traySources(env, now) {
    const sources = (env && Array.isArray(env.sources)) ? env.sources : [];
    if (!sources.length) return '·';
    if (sources.length === 1) return trayLabel(sourceGlance(env, sources[0]), sourceLimits(sources[0]), now);
    const live = sources.filter((s) => LIVE.has(s.agents && s.agents.status) && s.agents.data);
    if (!live.length) return sources.every((s) => s.agents && s.agents.status === 'unavailable' && s.agents.reason === 'checking') ? '' : '–';
    const maybeTwice = overlapping(sources);
    const sum = (key) => live.reduce((n, s) => n + (maybeTwice(s) ? 0 : ((s.agents.data.counts || {})[key] || 0)), 0);
    const empty = live.some((s) => freshEmpty(sourceLimits(s), now != null ? now : Date.now()));
    const mark = sum('waitingOnYou') > 0 ? '?' : sum('stuck') > 0 ? '●' : empty ? 'empty' : '';
    return [sum('running') > 0 ? String(sum('running')) : '', mark].filter(Boolean).join(' · ');
  }

  // ---- Setup planning (pure; the sheet in glance-setup.js renders it) ---------------------
  // One target per (app, place) the owner ticked, in catalog order then the order shown.
  function setupTargets(apps, placesByApp, catalog) {
    const names = Object.fromEntries((catalog || []).map((c) => [c.id, c.displayName]));
    const targets = [];
    for (const app of apps) {
      for (const place of placesByApp[app] || []) {
        targets.push({ key: app + '|' + place.key, app, appName: names[app] || harnessName(app), place: place.key,
          placeLabel: place.label, remote: place.key.startsWith('peer:'), manual: place.key === 'address',
          context: place.context || null, peerRef: place.peerRef || null,
          label: place.defaultLabel, status: 'ready', error: null });
      }
    }
    return targets;
  }

  // Connect targets strictly one at a time. Only 'ready' targets run: a failed one waits for
  // the owner's own Try again, and a skipped one never runs. Nothing is retried automatically.
  async function connectInSequence(targets, connectOne, onChange) {
    for (const target of targets) {
      if (target.status !== 'ready') continue;
      target.status = 'connecting'; target.error = null;
      if (onChange) onChange(target);
      let result;
      try { result = await connectOne(target); } catch { result = { ok: false, code: 'network' }; }
      target.status = result && result.ok ? 'connected' : 'failed';
      target.error = result && result.ok ? null : (result && (result.code || result.words)) || 'network';
      if (result && result.words) target.words = result.words;
      if (result && result.source) target.source = result.source;
      if (onChange) onChange(target);
    }
    return targets;
  }

  return { build, buildSources, traySources, dialGroups, short, whenShort, timeLeft, setupTargets, connectInSequence, harnessName, HARNESSES, trayLabel, freshEmpty, projectIdentity, ICON_COLORS, providerKey, clampSetting, SETTINGS, dur, ago, hm, longDate, dateFrom, modelWord, percent, splitPrefix, agentsMode, ACTIVE };
});

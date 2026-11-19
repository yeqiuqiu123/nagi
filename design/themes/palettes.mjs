// The lead's palette workbench: the three built-in themes and the contrast pairs each must clear.
// The shipped copy is THEMES in web/glance-theme.js; tests/glance-theme.test.cjs is the standing check.
//   node design/themes/palettes.mjs
export const hex2rgb = (h) => [1,3,5].map((i) => parseInt(h.slice(i,i+2),16));
const lin = (c) => { c/=255; return c<=0.04045? c/12.92 : ((c+0.055)/1.055)**2.4; };
export const lum = (h) => { const [r,g,b]=hex2rgb(h).map(lin); return 0.2126*r+0.7152*g+0.0722*b; };
export const cr = (a,b) => { const x=lum(a), y=lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
export const mix = (a,b,p) => { const x=hex2rgb(a), y=hex2rgb(b); return '#'+x.map((v,i)=>Math.round(v*p+y[i]*(1-p)).toString(16).padStart(2,'0')).join(''); };
export const T = {
 violet: {
  dark: { bg:'#18131d', sheet:'#241d2b', scrim:'#0d0a10', title:'#f5f1f8', 'title-context':'#e2dbe9', secondary:'#cdc4d6', tertiary:'#a397b0', stroke:'#9486a3', hair:'#3a3142', track:'#463c50',
    rose:'#ff7aa5', 'rose-text':'#ff9dbb', wash:'#2a1b28', amber:'#e6c84a', 'amber-text':'#ecd27a', 'wash-amber':'#272118',
    'pv-claude':'#e2977f','pv-claude-node':'#d97757','pv-codex':'#13c197','pv-codex-node':'#10a37f','pv-gemini':'#7caaf7','pv-gemini-node':'#4285f4',
    'hx-t3':'#f58ac0','hx-codex':'#13c197','hx-claude':'#e2977f', focus:'#cdc4d6', hover:'#211a27', control:'#2c2433','control-border':'#8b7f99','control-text':'#f5f1f8',
    green:'#3fc98a','green-text':'#6fdcaa', red:'#ff4d42','red-text':'#ff958c', blue:'#5b9dff','blue-text':'#8dbbff', accent:'#b59cf7','accent-ink':'#18131d' },
  light: { bg:'#f2f0f6', sheet:'#fbfafd', scrim:'#c9c4d3', title:'#17121c','title-context':'#2b2432', secondary:'#403849', tertiary:'#645b70', stroke:'#6b6280', hair:'#dcd7e4', track:'#d2cbdc',
    rose:'#c8235f','rose-text':'#8f103c', wash:'#efe0ea', amber:'#7d6800','amber-text':'#594a00','wash-amber':'#f0ead2',
    'pv-claude':'#7b331c','pv-claude-node':'#d15a34','pv-codex':'#085240','pv-codex-node':'#0e9071','pv-gemini':'#0943a3','pv-gemini-node':'#317af3',
    'hx-t3':'#8f1245','hx-codex':'#085240','hx-claude':'#7b331c', focus:'#403849', hover:'#e8e5ee', control:'#ffffff','control-border':'#847a97','control-text':'#17121c',
    green:'#16804f','green-text':'#0b5231', red:'#d92d20','red-text':'#8e1a13', blue:'#2f6fe0','blue-text':'#123f96', accent:'#6a45d1','accent-ink':'#ffffff' } },
 graphite: {
  dark: { bg:'#1c1c1e', sheet:'#272729', scrim:'#0b0b0c', title:'#f5f5f7','title-context':'#e3e3e8', secondary:'#c9c9cf', tertiary:'#a1a1a8', stroke:'#8e8e93', hair:'#38383a', track:'#48484a',
    rose:'#ff6f91','rose-text':'#ff9bb1', wash:'#2f1e24', amber:'#f2cc3d','amber-text':'#f5d76e','wash-amber':'#2b2618',
    'pv-claude':'#eaa48e','pv-claude-node':'#d97757','pv-codex':'#3fd0a9','pv-codex-node':'#10a37f','pv-gemini':'#8fb6f9','pv-gemini-node':'#4285f4',
    'hx-t3':'#f794c6','hx-codex':'#3fd0a9','hx-claude':'#eaa48e', focus:'#409cff', hover:'#242426', control:'#303032','control-border':'#8e8e93','control-text':'#f5f5f7',
    green:'#32d074','green-text':'#6fe09b', red:'#ff4d42','red-text':'#ff9d95', blue:'#409cff','blue-text':'#85bcff', accent:'#409cff','accent-ink':'#0b0b0c' },
  light: { bg:'#ececee', sheet:'#f6f6f8', scrim:'#bcbcc2', title:'#1d1d1f','title-context':'#2c2c2e', secondary:'#3a3a3c', tertiary:'#5e5e63', stroke:'#6e6e73', hair:'#d6d6db', track:'#cdcdd2',
    rose:'#d30f45','rose-text':'#8f002a', wash:'#f3dfe4', amber:'#806600','amber-text':'#584600','wash-amber':'#efe8cf',
    'pv-claude':'#78311a','pv-claude-node':'#cf5630','pv-codex':'#075240','pv-codex-node':'#0d8a6c','pv-gemini':'#08409e','pv-gemini-node':'#2f74ea',
    'hx-t3':'#8f1245','hx-codex':'#075240','hx-claude':'#78311a', focus:'#0066d6', hover:'#e3e3e6', control:'#ffffff','control-border':'#7c7c82','control-text':'#1d1d1f',
    green:'#1b8048','green-text':'#0c5230', red:'#d92d20','red-text':'#8e1a13', blue:'#0066d6','blue-text':'#0a3f8f', accent:'#0066d6','accent-ink':'#ffffff' } },
 tide: {
  dark: { bg:'#0f1a1f', sheet:'#19272e', scrim:'#070d10', title:'#eef6f7','title-context':'#d8e5e8', secondary:'#bdd0d5', tertiary:'#8fa7ae', stroke:'#7f989f', hair:'#263840', track:'#30454e',
    rose:'#ff7aa5','rose-text':'#ff9dbb', wash:'#2a1c2a', amber:'#e9c84a','amber-text':'#efd57c','wash-amber':'#252416',
    'pv-claude':'#e89d86','pv-claude-node':'#dd7a5a','pv-codex':'#2ccb9f','pv-codex-node':'#12a983','pv-gemini':'#84b0f8','pv-gemini-node':'#4a8af5',
    'hx-t3':'#f58ac0','hx-codex':'#2ccb9f','hx-claude':'#e89d86', focus:'#62d3d8', hover:'#16242b', control:'#213138','control-border':'#7f989f','control-text':'#eef6f7',
    green:'#3fc98a','green-text':'#6fdcaa', red:'#ff4d42','red-text':'#ff958c', blue:'#5b9dff','blue-text':'#8dbbff', accent:'#62d3d8','accent-ink':'#070d10' },
  light: { bg:'#eaf2f2', sheet:'#f6fbfb', scrim:'#b9c9cb', title:'#0d1b1f','title-context':'#1d2e33', secondary:'#2f4248', tertiary:'#52666c', stroke:'#5c7279', hair:'#cfdcde', track:'#c4d4d7',
    rose:'#c8235f','rose-text':'#8f103c', wash:'#f0dfe8', amber:'#7a6500','amber-text':'#564700','wash-amber':'#ece9cb',
    'pv-claude':'#7b331c','pv-claude-node':'#cc5530','pv-codex':'#075240','pv-codex-node':'#0c876a','pv-gemini':'#0943a3','pv-gemini-node':'#2f74ea',
    'hx-t3':'#8f1245','hx-codex':'#075240','hx-claude':'#7b331c', focus:'#0a737a', hover:'#dde9ea', control:'#ffffff','control-border':'#6c838a','control-text':'#0d1b1f',
    green:'#157a4c','green-text':'#0a4f2f', red:'#d92d20','red-text':'#8e1a13', blue:'#2a6bdc','blue-text':'#123f96', accent:'#0a737a','accent-ink':'#ffffff' } },
};
export function checks(p) {
  const out = [];
  const need = (fg, bgs, min, what) => bgs.forEach((b) => { const r = cr(p[fg], typeof b === 'string' && b.startsWith('#') ? b : p[b]); out.push({ fg, on: b, r, min, ok: r >= min, what }); });
  const surf = ['bg','hover','wash','wash-amber','sheet','control'];
  need('title', surf, 12, 'title');
  need('title-context', ['bg','hover'], 10, 'context title');
  need('secondary', surf, 7, 'secondary');
  need('tertiary', ['bg','hover','sheet','control'], 4.5, 'tertiary');
  need('stroke', ['bg','hover','wash','wash-amber','sheet'], 3, 'stroke');
  need('rose-text', ['bg','hover','wash'], 7, 'rose word'); need('amber-text', ['bg','hover','wash-amber'], 7, 'amber word');
  need('rose', ['bg','hover','wash'], 3, 'rose mark'); need('amber', ['bg','hover','wash-amber'], 3, 'amber mark');
  for (const k of ['claude','codex','gemini']) { need('pv-'+k, ['bg','hover'], 7, 'provider word'); need('pv-'+k+'-node', ['bg','hover'], 3, 'provider mark'); }
  for (const k of ['t3','codex','claude']) { out.push((() => { const b = mix(p['hx-'+k], p.bg, .16); const r = cr(p['hx-'+k], b); return { fg:'hx-'+k, on:'chip tint', r, min:4.5, ok:r>=4.5 }; })());
    out.push((() => { const b = mix(p['hx-'+k], p.control, .16); const r = cr(p['hx-'+k], b); return { fg:'hx-'+k, on:'tile tint', r, min:4.5, ok:r>=4.5 }; })()); }
  for (const k of ['green','red','blue']) { need(k, ['bg','hover','wash','wash-amber','sheet','control'], 3, 'status mark'); need(k+'-text', ['bg','hover'], 7, 'status word'); need(k+'-text', ['wash','wash-amber','sheet','control'], 4.5, 'status word'); }
  need('control-border', ['control','sheet'], 3, 'control border'); need('focus', ['bg','hover','sheet','control'], 3, 'focus');
  need('accent', ['bg','hover','sheet','control'], 3, 'accent'); out.push({ fg:'accent-ink', on:'accent', r: cr(p['accent-ink'], p.accent), min:4.5, ok: cr(p['accent-ink'], p.accent) >= 4.5 });
  return out;
}
if (process.argv[1].endsWith('palettes.mjs')) {
  for (const [name, t] of Object.entries(T)) for (const mode of ['dark','light']) {
    const res = checks(t[mode]); const bad = res.filter((x) => !x.ok);
    console.log(name, mode, bad.length ? 'FAIL '+bad.length : 'ok', ' min margins:', res.sort((a,b)=>a.r/a.min-b.r/b.min).slice(0,4).map((x)=>`${x.fg}/${x.on} ${x.r.toFixed(2)}≥${x.min}`).join('; '));
    bad.forEach((x) => console.log('   ', x.fg, 'on', x.on, x.r.toFixed(2), '<', x.min));
  }
}

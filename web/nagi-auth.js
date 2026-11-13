'use strict';
(() => {
  const storageKey = 'nagi-session-v2';
  const nativeFetch = window.fetch.bind(window);
  const here = new URL(location.href);
  const tokenPattern = /^[A-Za-z0-9_-]{43}$/;
  // A native ticket may arrive as a same-document fragment navigation. Force a
  // new document so bootstrap reruns and the view's old ownerLocked state resets.
  window.addEventListener('hashchange', () => {
    if (/^#nagi-launch=[A-Za-z0-9_-]{43}$/.test(location.hash)) location.reload();
  });
  let session = null;
  let nativeNotified = false;
  function requestNativeAuth() {
    if (nativeNotified) return;
    nativeNotified = true;
    try { window.webkit?.messageHandlers?.nagiAuth?.postMessage('reauthenticate'); } catch {}
  }
  function clear() {
    session = null;
    try {
      sessionStorage.removeItem(storageKey);
      sessionStorage.removeItem('nagi-needs-v1');
    } catch {}
  }
  async function bootstrap() {
    const match = /^#nagi-launch=([A-Za-z0-9_-]{43})$/.exec(here.hash);
    if (match) {
      // Remove the only launch credential before fetching assets or source data.
      history.replaceState(null, '', here.pathname + here.search);
      clear();
      const response = await nativeFetch('/auth/redeem', {method:'POST', cache:'no-store', redirect:'error', credentials:'omit',
        headers:{'Content-Type':'application/json','X-Progress-Desk':'1'},
        body:JSON.stringify({ticket:match[1],path:here.pathname + here.search})});
      if (!response.ok) {
        if (response.status === 401) requestNativeAuth();
        throw Error('Launch expired. Open Nagi from its launcher again.');
      }
      const value = await response.json();
      if (!tokenPattern.test(value.token) || !Number.isSafeInteger(value.expiresAt)
          || value.expiresAt <= Date.now()/1000 || value.expiresAt > Date.now()/1000 + 905) throw Error('Invalid session');
      session = {token:value.token,expiresAt:value.expiresAt};
      sessionStorage.setItem(storageKey, JSON.stringify(session));
      if (value.fragment) history.replaceState(null, '', here.pathname + here.search + '#' + value.fragment);
    } else {
      try { session = JSON.parse(sessionStorage.getItem(storageKey)); } catch {}
    }
    if (!session || !tokenPattern.test(session.token) || session.expiresAt <= Date.now()/1000) clear();
  }
  const ready = bootstrap().catch(() => { clear(); });
  async function authenticatedFetch(input, options = {}) {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
    // Never forward a session header to another port, site or a static asset.
    const headers = new Headers(options.headers || (typeof input === 'object' ? input.headers : undefined));
    headers.delete('X-Nagi-Session');
    headers.delete('Authorization');
    if (url.origin !== here.origin || url.username || url.password || !url.pathname.startsWith('/api/')) {
      return nativeFetch(input, {...options, headers, credentials:'omit'});
    }
    await ready;
    if (session && session.expiresAt > Date.now()/1000) headers.set('X-Nagi-Session', session.token);
    else clear();
    const response = await nativeFetch(input, {...options, headers, credentials:'omit', redirect:'error'});
    if (response.status === 401 || response.status === 403) clear();
    if (response.status === 401) requestNativeAuth();
    return response;
  }
  window.NagiAuth = Object.freeze({fetch:authenticatedFetch, ready});
  window.fetch = authenticatedFetch;
})();

/* EOAgriTool application shell, state and API client. */
(() => {
  const pages = [
    ['/dashboard','Dashboard','⌂'], ['/fields','Fields','▦'],
    ['/climate','Climate','☼'], ['/water','Water','◌'],
    ['/reports','Reports','▤'], ['/notifications','Alerts','⚠'],
    ['/about','About','?'], ['/contacts','Contact','@']
  ];

  // Normalized current path (e.g. "/climate"); used for active nav state.
  const pathParts = location.pathname.replace(/\/$/, '').split('/');
  const currentPath = '/' + (pathParts.pop() || '');

  const shell = `<header class="site-header" data-app-header>
    <a class="brand" href="/dashboard" aria-label="EOAgriTool dashboard"><span class="brand-mark">🌾</span><span>EOAgriTool</span></a>
    <button class="menu-toggle" type="button" aria-label="Toggle navigation" aria-expanded="false">☰</button>
    <nav class="site-nav" aria-label="Primary navigation">${pages.map(([href,label,icon]) => `<a href="${href}" class="${currentPath === href ? 'active' : ''}"><span>${icon}</span>${label}</a>`).join('')}</nav>
    <div class="header-actions"><span class="live-dot">Live</span><button class="button secondary" data-action="logout" type="button">Sign out</button></div>
  </header>`;

  function installShell() {
    if (currentPath === '/' || document.querySelector('[data-app-header]')) return;
    document.body.insertAdjacentHTML('afterbegin', shell);
    const toggle = document.querySelector('.menu-toggle');
    const nav = document.querySelector('.site-nav');
    toggle?.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '×' : '☰';
    });
    nav?.querySelectorAll('a').forEach(a => a.addEventListener('click', () => nav.classList.remove('open')));
    document.querySelector('[data-action="logout"]')?.addEventListener('click', () => {
      localStorage.removeItem('eoagri-auth'); location.href = '/';
    });
  }

  const read = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const write = (key, value) => localStorage.setItem(key, JSON.stringify(value));
  const fields = () => read('fieldData', {fields: []}).fields || [];
  const saveFields = value => { write('fieldData', {fields: value}); window.dispatchEvent(new CustomEvent('eoagri:fields', {detail: value})); };

  async function recommendations(analysis, context = {}) {
    try {
      const response = await fetch('recommendations', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({analysis, context})});
      if (!response.ok) throw new Error('API unavailable');
      return (await response.json()).recommendations || [];
    } catch {
      return [{id:'local', category:'general', priority:'info', title:'Local advisory mode', description:'Live recommendations are unavailable; local scenario guidance is being used.', action:'Start the Quart backend to enable the recommendation API.'}];
    }
  }

  function toast(message) {
    const node = document.createElement('div'); node.className = 'toast'; node.textContent = message; node.setAttribute('role','status');
    document.body.appendChild(node); setTimeout(() => node.remove(), 2800);
  }
  function download(name, data, type='application/json') {
    const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([data], {type})); link.download = name; link.click(); URL.revokeObjectURL(link.href);
  }

  /**
   * Fetch JSON with timeout + normalized errors.
   * Always resolves to {ok, data, fetched_at, source, stale, error, code}.
   * Never throws — callers can always render a loading→result/error state.
   */
  async function fetchJSON(url, {timeoutMs = 12000} = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, {signal: controller.signal, headers: {Accept: 'application/json'}});
      let body = null;
      try { body = await res.json(); } catch { /* non-JSON body */ }
      if (!res.ok) {
        return {
          ok: false,
          data: null,
          fetched_at: body?.fetched_at ?? null,
          source: body?.source ?? 'unknown',
          stale: Boolean(body?.stale),
          error: body?.error || `Request failed (HTTP ${res.status})`,
          code: body?.code || `HTTP_${res.status}`,
        };
      }
      return {
        ok: true,
        data: body?.data ?? null,
        fetched_at: body?.fetched_at ?? null,
        source: body?.source ?? 'unknown',
        stale: Boolean(body?.stale),
        error: body?.error ?? null,
        code: body?.code ?? null,
      };
    } catch (err) {
      const timedOut = err && err.name === 'AbortError';
      return {
        ok: false,
        data: null,
        fetched_at: null,
        source: 'network',
        stale: false,
        error: timedOut ? 'Request timed out' : 'Network error',
        code: timedOut ? 'TIMEOUT' : 'NETWORK',
      };
    } finally {
      clearTimeout(timer);
    }
  }

  function formatRefreshedAt(iso) {
    if (!iso) return 'never';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return 'unknown';
    const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    if (mins < 1440) return `${Math.floor(mins / 60)} hr ago`;
    return `${Math.floor(mins / 1440)} day ago`;
  }

  window.EOAgri = {pages, read, write, fields, saveFields, recommendations, toast, download, fetchJSON, formatRefreshedAt};
  document.addEventListener('DOMContentLoaded', installShell);
})();
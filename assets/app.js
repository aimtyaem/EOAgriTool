/* EOAgriTool application shell, state and API client. */
(() => {
  const pages = [
    ['dashboard.html','Dashboard','⌂'], ['fields.html','Fields','▦'],
    ['climate.html','Climate','☼'], ['water.html','Water','◌'],
    ['reports.html','Reports','▤'], ['notifications.html','Alerts','⚠'],
    ['about.html','About','?'], ['contacts.html','Contact','@']
  ];
  const current = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const shell = `<header class="site-header" data-app-header>
    <a class="brand" href="dashboard.html" aria-label="EOAgriTool dashboard"><span class="brand-mark">🌾</span><span>EOAgriTool</span></a>
    <button class="menu-toggle" type="button" aria-label="Toggle navigation" aria-expanded="false">☰</button>
    <nav class="site-nav" aria-label="Primary navigation">${pages.map(([href,label,icon]) => `<a href="${href}" class="${current === href ? 'active' : ''}"><span>${icon}</span>${label}</a>`).join('')}</nav>
    <div class="header-actions"><span class="live-dot">Live</span><button class="button secondary" data-action="logout" type="button">Sign out</button></div>
  </header>`;

  function installShell() {
    if (current === 'index.html' || document.querySelector('[data-app-header]')) return;
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
      localStorage.removeItem('eoagri-auth'); location.href = 'index.html';
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

  window.EOAgri = {pages, read, write, fields, saveFields, recommendations, toast, download};
  document.addEventListener('DOMContentLoaded', installShell);
})();

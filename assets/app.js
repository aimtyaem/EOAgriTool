/* EOAgriTool shared navigation and interaction runtime. */
(() => {
  const pages = [
    ['dashboard.html', 'Dashboard', '⌂'],
    ['fields.html', 'Fields', '▦'],
    ['climate.html', 'Climate', '☼'],
    ['water.html', 'Water', '◌'],
    ['reports.html', 'Reports', '▤'],
    ['notifications.html', 'Alerts', '⚠'],
    ['about.html', 'About', '?'],
    ['contacts.html', 'Contact', '@']
  ];

  const current = (location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const isLogin = current === 'index.html' || current === '';

  function headerMarkup() {
    const links = pages.map(([href, label, icon]) => `
      <a href="${href}" class="${current === href ? 'active' : ''}" aria-current="${current === href ? 'page' : 'false'}">
        <span aria-hidden="true">${icon}</span><span>${label}</span>
      </a>`).join('');

    return `<header class="site-header" data-app-header>
      <a class="brand" href="dashboard.html" aria-label="EOAgriTool dashboard">
        <span class="brand-mark" aria-hidden="true">🌾</span><span>EOAgriTool</span>
      </a>
      <button class="menu-toggle" type="button" aria-label="Open navigation" aria-expanded="false">☰</button>
      <nav class="site-nav" aria-label="Primary navigation">${links}</nav>
      <div class="header-actions">
        <span class="live-dot">Live</span>
        <button class="button secondary" type="button" data-action="logout">Sign out</button>
      </div>
    </header>`;
  }

  function installHeader() {
    if (isLogin || document.querySelector('[data-app-header]')) return;
    document.body.insertAdjacentHTML('afterbegin', headerMarkup());
    const toggle = document.querySelector('.menu-toggle');
    const nav = document.querySelector('.site-nav');
    toggle?.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
      toggle.textContent = open ? '×' : '☰';
    });
    document.querySelectorAll('.site-nav a').forEach(link => link.addEventListener('click', () => {
      nav.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = '☰';
    }));
    document.querySelector('[data-action="logout"]')?.addEventListener('click', () => {
      localStorage.removeItem('eoagri-auth');
      location.href = 'index.html';
    });
  }

  function fields() {
    try { return JSON.parse(localStorage.getItem('fieldData') || '{"fields":[]}').fields || []; }
    catch { return []; }
  }

  function saveFields(value) {
    localStorage.setItem('fieldData', JSON.stringify({ fields: value }));
    window.dispatchEvent(new CustomEvent('eoagri:fields', { detail: value }));
  }

  async function recommendations(analysis, context = {}) {
    try {
      const response = await fetch('recommendations', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ analysis, context })
      });
      if (!response.ok) throw new Error('Recommendation API unavailable');
      return (await response.json()).recommendations || [];
    } catch {
      return [{
        id: 'local', category: 'general', priority: 'info',
        title: 'Local advisory mode',
        description: 'Live recommendations are unavailable; the page is using local guidance.',
        action: 'Start the Quart backend for live recommendations.'
      }];
    }
  }

  function toast(message) {
    const element = document.createElement('div');
    element.className = 'toast'; element.setAttribute('role', 'status'); element.textContent = message;
    document.body.appendChild(element);
    setTimeout(() => element.remove(), 2800);
  }

  function download(name, content, type = 'text/plain') {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([content], { type }));
    link.download = name; link.click(); URL.revokeObjectURL(link.href);
  }

  window.EOAgri = { pages, fields, saveFields, recommendations, toast, download };
  document.addEventListener('DOMContentLoaded', installHeader);
})();

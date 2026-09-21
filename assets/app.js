/* EOAgriTool shared client runtime */
(() => {
  const pages = [
    ['dashboard.html','Dashboard'], ['fields.html','Fields'], ['climate.html','Climate'],
    ['water.html','Water'], ['reports.html','Reports'], ['notifications.html','Alerts'],
    ['about.html','About'], ['contacts.html','Contact']
  ];
  const current = location.pathname.split('/').pop() || 'index.html';
  const nav = `<header class="site-header"><a class="brand" href="dashboard.html"><span class="brand-mark">🌾</span><span>EOAgriTool</span></a><button class="menu-toggle" aria-label="Toggle menu">☰</button><nav class="site-nav">${pages.map(([href,label]) => `<a href="${href}" class="${current === href ? 'active' : ''}">${label}</a>`).join('')}</nav><div class="header-actions"><span class="live-dot">● Live</span><button class="button secondary" data-action="logout" type="button">Sign out</button></div></header>`;
  document.addEventListener('DOMContentLoaded', () => {
    if (!document.querySelector('.site-header')) document.body.insertAdjacentHTML('afterbegin', nav);
    document.querySelector('.menu-toggle')?.addEventListener('click', () => document.querySelector('.site-nav')?.classList.toggle('open'));
    document.querySelector('[data-action="logout"]')?.addEventListener('click', () => { localStorage.removeItem('eoagri-auth'); location.href = 'index.html'; });
    document.querySelectorAll('[data-action="back-dashboard"]').forEach(b => b.addEventListener('click', () => location.href='dashboard.html'));
  });
  window.EOAgri = {
    fields() { try { return JSON.parse(localStorage.getItem('fieldData') || '{"fields":[]}').fields || []; } catch { return []; } },
    saveFields(fields) { localStorage.setItem('fieldData', JSON.stringify({fields})); window.dispatchEvent(new Event('eoagri:fields')); },
    async recommendations(analysis, context={}) {
      try { const r = await fetch('recommendations', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({analysis,context})}); if (!r.ok) throw Error(); return (await r.json()).recommendations; }
      catch { return [{id:'local', category:'general', priority:'info', title:'Local advisory mode', description:'The API is unavailable, so the dashboard is using local data.', action:'Start the backend with hypercorn app:app for live recommendations.'}]; }
    },
    toast(message) { const el=document.createElement('div'); el.className='toast'; el.textContent=message; document.body.appendChild(el); setTimeout(()=>el.remove(),2800); },
    download(name, content, type='text/plain') { const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([content],{type})); a.download=name; a.click(); URL.revokeObjectURL(a.href); }
  };
})();

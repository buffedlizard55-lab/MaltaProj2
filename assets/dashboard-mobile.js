/* No external dependencies. Never let a failed refresh make an expired pick look current. */
(() => {
  'use strict';
  const rows = [...document.querySelectorAll('[data-pick-row]')];
  const search = document.getElementById('dashboard-search');
  const select = document.getElementById('dashboard-basis');
  if (!search || !select) return;
  function filter() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(query) ||
        (select.value !== 'all' && row.dataset.basis !== select.value);
      if (!row.hidden) visible++;
    });
    document.getElementById('dashboard-count').textContent = `${visible} of ${rows.length} snapshot matches shown`;
    document.getElementById('dashboard-empty').hidden = visible !== 0;
  }
  function expire() {
    const now = Date.now();
    let expired = false;
    rows.forEach(row => {
      const expiry = Date.parse(row.dataset.expiry), lock = Date.parse(row.dataset.lock);
      if (!Number.isFinite(expiry) || !Number.isFinite(lock) || now >= Math.min(expiry, lock)) {
        expired = true;
        row.querySelector('[data-pick]').textContent = Number.isFinite(lock) && now >= lock ? 'Locked — not an open pick' : 'Expired — awaiting refresh';
        row.querySelectorAll('[data-prob]').forEach(el => { el.textContent = '—'; });
      }
    });
    document.getElementById('dashboard-freshness').hidden = !expired;
    filter();
  }
  search.addEventListener('input', filter);
  select.addEventListener('change', filter);
  document.addEventListener('visibilitychange', expire);
  setInterval(expire, 60000);
  expire();
})();

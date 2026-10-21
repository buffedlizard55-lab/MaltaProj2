/* Display-only: never creates a probability, odds, pick or inferred timestamp. */
(() => {
  const check = () => {
    const now = Date.now();
    document.querySelectorAll('tr[data-expiry]').forEach(row => {
      const expired = row.dataset.state === 'open' && Date.parse(row.dataset.expiry) <= now;
      row.classList.toggle('expired', expired);
      const note = row.querySelector('.expiry-note');
      if (note) note.textContent = expired ? 'Expired / locked — not a current recommendation. Await refresh.' : '';
    });
    document.querySelectorAll('[data-capture-expiry]').forEach(el => {
      const expired = Date.parse(el.dataset.captureExpiry) <= now;
      el.classList.toggle('expired', expired);
      el.querySelector('.capture-status').textContent = expired ? 'CAPTURE EXPIRED — do not use as current picks.' : 'Within the capture freshness window; each fixture also has its own lock.';
    });
  };
  const search = document.querySelector('#search');
  if (search) search.addEventListener('input', () => {
    let count = 0;
    document.querySelectorAll('tbody tr').forEach(row => {
      row.hidden = !row.textContent.toLowerCase().includes(search.value.trim().toLowerCase());
      if (!row.hidden) count++;
    });
    document.querySelector('#filter-count').textContent = `${count} matching fixtures`;
  });
  check(); setInterval(check, 30000);
})();

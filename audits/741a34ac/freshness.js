'use strict';
function updateFreshness() {
  const notice = document.querySelector('[data-expires]');
  const status = document.getElementById('freshness');
  if (!notice || !status) return;
  const expiry = Date.parse(notice.dataset.expires);
  status.textContent = !Number.isFinite(expiry) || Date.now() >= expiry
    ? 'STALE / UNVERIFIED — source observation expired. Open the picks page for its own timestamps.'
    : 'Retained inventory is within its four-hour audit window; current prices and rosters are not guaranteed.';
}
updateFreshness();
setInterval(updateFreshness, 60000);

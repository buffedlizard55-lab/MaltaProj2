/* Lightweight progressive enhancement: local-time display + row filtering. No dependencies. */
(function () {
  document.querySelectorAll('time[data-utc]').forEach(function (el) {
    var raw = el.getAttribute('data-utc');
    var d = new Date(raw);
    if (isNaN(d.getTime())) return;
    el.textContent = d.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
    el.title = raw;
  });
  var q = document.getElementById('q');
  var pricedOnly = document.getElementById('priced-only');
  var rows = Array.prototype.slice.call(document.querySelectorAll('tr.fixture'));
  var count = document.getElementById('count');
  function apply() {
    var term = (q && q.value || '').trim().toLowerCase();
    var onlyPriced = pricedOnly && pricedOnly.checked;
    var shown = 0;
    rows.forEach(function (r) {
      var okTerm = !term || (r.getAttribute('data-search') || '').indexOf(term) !== -1;
      var okPriced = !onlyPriced || r.getAttribute('data-priced') === '1';
      var show = okTerm && okPriced;
      r.style.display = show ? '' : 'none';
      if (show) shown++;
    });
    if (count) count.textContent = shown + ' of ' + rows.length + ' rows shown';
  }
  if (q) q.addEventListener('input', apply);
  if (pricedOnly) pricedOnly.addEventListener('change', apply);
  apply();
})();

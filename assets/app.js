
// Table filter + click-to-sort. No external dependencies (GitHub Pages safe).
document.addEventListener('DOMContentLoaded', function () {
  var input = document.getElementById('filter');
  if (input) {
    input.addEventListener('input', function () {
      var q = input.value.toLowerCase();
      document.querySelectorAll('table tbody tr').forEach(function (tr) {
        tr.style.display = tr.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
      });
    });
  }
  document.querySelectorAll('table.sortable thead th').forEach(function (th, i) {
    th.addEventListener('click', function () {
      var tb = th.closest('table').querySelector('tbody');
      var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
      var asc = th.dataset.asc !== '1';
      rows.sort(function (a, b) {
        var x = a.children[i] ? a.children[i].textContent.trim() : '';
        var y = b.children[i] ? b.children[i].textContent.trim() : '';
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      });
      th.dataset.asc = asc ? '1' : '0';
      rows.forEach(function (r) { tb.appendChild(r); });
    });
  });
});

'use strict';
const search = document.querySelector('#search');
const visibility = document.querySelector('#visibility');
if (search && visibility) {
  const rows = [...document.querySelectorAll('#matches tbody tr')];
  function filter() {
    const term = search.value.trim().toLocaleLowerCase();
    let count = 0;
    for (const row of rows) {
      const match = row.textContent.toLocaleLowerCase().includes(term) &&
        (!visibility.value || row.cells[3].textContent === visibility.value);
      row.hidden = !match;
      if (match) count++;
    }
    document.querySelector('#row-count').textContent = `${count} of ${rows.length} fixtures shown`;
  }
  search.addEventListener('input', filter);
  visibility.addEventListener('change', filter);
  filter();
}

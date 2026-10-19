(function(){
  'use strict';
  var rows = Array.prototype.slice.call(document.querySelectorAll('[data-row]'));
  var filter = document.getElementById('filter');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  var count = document.getElementById('filter-count');
  var mode = document.querySelector('[data-filter].active'); mode = mode ? mode.dataset.filter : 'all';
  function expired(row){
    if(row.dataset.status !== 'published') return false;
    var now = Date.now(), valid = Date.parse(row.dataset.validUntil || ''), lock = Date.parse(row.dataset.lock || '');
    return (isFinite(valid) && now >= valid) || (isFinite(lock) && now >= lock);
  }
  function protect(row){
    if(!expired(row) || row.dataset.expired) return;
    row.dataset.expired = 'true';
    Array.prototype.forEach.call(row.querySelectorAll('[data-probability]'), function(el){el.textContent='— expired'; el.classList.add('blank');});
    Array.prototype.forEach.call(row.querySelectorAll('[data-pick]'), function(el){el.textContent='Expired / locked — awaiting source refresh'; el.classList.add('blank');});
    var notice = document.getElementById('freshness-notice');
    if(notice){notice.hidden=false; notice.innerHTML='<h2>Snapshot values have expired</h2><p>Expired or locked probabilities and picks are hidden in this browser. The evidence trail remains for review; reload after the next automated refresh.</p>';}
  }
  function apply(){
    var needle = (filter && filter.value || '').toLowerCase(), visible = 0;
    rows.forEach(function(row){
      protect(row);
      var actual = row.dataset.status === 'published' && !row.dataset.expired ? 'published' : (row.dataset.status === 'published' ? 'expired' : 'unresolved');
      var match = (!needle || (row.dataset.search || '').indexOf(needle) !== -1) && (mode === 'all' || actual === mode);
      row.hidden = !match; if(match) visible++;
    });
    if(count) count.textContent = visible + ' fixture' + (visible === 1 ? '' : 's') + ' shown';
  }
  if(filter) filter.addEventListener('input', apply);
  buttons.forEach(function(button){button.addEventListener('click', function(){mode=button.dataset.filter;buttons.forEach(function(b){b.classList.toggle('active',b===button);});apply();});});
  apply(); setInterval(apply, 60000);
}());


(function(){
  var q=document.getElementById('q'), f=document.getElementById('filter'), cards=document.querySelectorAll('[data-card]');
  function apply(){
    var term=(q&&q.value||'').toLowerCase(), mode=f?f.value:'open', shown=0;
    cards.forEach(function(c){
      var hit=(!term || c.dataset.search.indexOf(term)>=0);
      var okMode = mode==='all' || (mode==='open' && c.dataset.open==='1') || (mode==='blank' && c.dataset.blank==='1');
      var show=hit&&okMode; c.classList.toggle('hidden',!show); if(show)shown++;
    });
    var out=document.getElementById('shown'); if(out) out.textContent=shown;
  }
  if(q)q.addEventListener('input',apply); if(f)f.addEventListener('change',apply); apply();
})();

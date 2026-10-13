
(function(){
  var q=document.getElementById('q'),b=document.getElementById('basis'),t=document.getElementById('tour'),
      s=document.getElementById('show'),cards=[].slice.call(document.querySelectorAll('article.card')),
      shown=document.getElementById('shown');
  function apply(){
    var term=(q&&q.value||'').toLowerCase(), bs=b&&b.value||'', tr=t&&t.value||'', sh=s&&s.value||'upcoming', n=0;
    cards.forEach(function(c){
      var ok=true;
      if(term && (c.dataset.search||'').indexOf(term)<0) ok=false;
      if(bs && c.dataset.basis!==bs) ok=false;
      if(tr && c.dataset.tour!==tr) ok=false;
      if(sh==='upcoming' && c.dataset.stale==='1') ok=false;
      if(sh==='stale' && c.dataset.stale!=='1') ok=false;
      if(sh==='nopick' && c.dataset.pick!=='0') ok=false;
      c.style.display = ok?'':'none'; if(ok) n++;
    });
    if(shown) shown.textContent = n;
  }
  [q,b,t,s].forEach(function(el){ if(el){ el.addEventListener('input',apply); el.addEventListener('change',apply);} });
  apply();
})();


(function(){
  var q=document.getElementById('q'),t=document.getElementById('tier'),
      tour=document.getElementById('tour'),up=document.getElementById('upcoming'),
      pick=document.getElementById('pickonly'),cards=[].slice.call(document.querySelectorAll('.card')),
      shown=document.getElementById('shown');
  function apply(){
    var s=(q&&q.value||'').toLowerCase(),tv=t&&t.value||'',to=tour&&tour.value||'',
        u=up&&up.checked,p=pick&&pick.checked,n=0;
    cards.forEach(function(c){
      var ok=true;
      if(s&&(c.dataset.search||'').indexOf(s)<0)ok=false;
      if(tv&&c.dataset.tier!==tv)ok=false;
      if(to&&c.dataset.tour!==to)ok=false;
      if(u&&c.dataset.future!=='1')ok=false;
      if(p&&c.dataset.pick!=='1')ok=false;
      c.style.display=ok?'':'none';if(ok)n++;
    });
    if(shown)shown.textContent=n;
  }
  [q,t,tour,up,pick].forEach(function(el){if(el){el.addEventListener('input',apply);el.addEventListener('change',apply);}});
  apply();
})();

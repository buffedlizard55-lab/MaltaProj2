
(function(){
  var q=document.getElementById('q'), ev=document.getElementById('ev'), tier=document.getElementById('tier');
  if(!document.querySelector('table')) return;
  var rows=[].slice.call(document.querySelectorAll('table tbody tr'));
  function apply(){
    var s=(q&&q.value||'').toLowerCase(), e=ev&&ev.value||'', t=tier&&tier.value||'';
    rows.forEach(function(tr){
      var txt=tr.innerText.toLowerCase();
      var okS=!s||txt.indexOf(s)>=0;
      var okE=!e||txt.indexOf(e.toLowerCase())>=0;
      var okT=!t||txt.indexOf(' '+t.toLowerCase()+' ')>=0||txt.indexOf(t.toLowerCase()+' pts')>=0;
      tr.style.display=(okS&&okE&&okT)?'':'none';
    });
  }
  [q,ev,tier].forEach(function(el){ if(el) el.addEventListener('input',apply); });
})();

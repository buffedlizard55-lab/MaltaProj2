(function(){
  var q=document.getElementById('q');
  if(q){q.addEventListener('input',function(){
    var v=q.value.trim().toLowerCase();
    document.querySelectorAll('[data-teams]').forEach(function(el){
      el.style.display=(!v||el.dataset.teams.indexOf(v)>=0)?'':'none';
    });
  });}
  document.querySelectorAll('[data-utc]').forEach(function(el){
    var d=new Date(el.dataset.utc);
    if(isNaN(d))return;
    var loc=d.toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',
      minute:'2-digit'});
    el.title=d.toISOString();
    var span=el.querySelector('.local');
    if(span){span.textContent=loc;}
  });
})();


(() => {
 function expire() {
  const now=Date.now(); let n=0;
  document.querySelectorAll('[data-deadline]').forEach(el=>{
   const until=Date.parse(el.dataset.deadline), lock=Date.parse(el.dataset.lock);
   const old=!Number.isFinite(until)||!Number.isFinite(lock)||now>=Math.min(until,lock);
   el.classList.toggle('expired',old); if(old)n++;
  });
  const note=document.querySelector('#expiry-note');
  if(note){note.hidden=!n;note.textContent='Some forecasts are expired, locked or unsupported. Estimates and risk selections are hidden; the dated research remains available. Use the current canonical board after its next automatic refresh.';}
 }
 expire(); setInterval(expire,30000);
})();

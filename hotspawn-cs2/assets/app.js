// Progressive enhancement: local times, lock countdowns, pick filters.
// Without JS every page still shows UTC times and all picks.
(function () {
  "use strict";
  function fmt(dt) {
    try {
      return new Intl.DateTimeFormat(undefined, {
        weekday: "short", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit"
      }).format(dt);
    } catch (e) { return dt.toLocaleString(); }
  }
  // Localise <time data-local> elements (title keeps the UTC value).
  document.querySelectorAll("time[data-local]").forEach(function (el) {
    var d = new Date(el.getAttribute("datetime"));
    if (!isNaN(d)) { el.textContent = fmt(d) + " (your time)"; }
  });
  // "Locks in Xh Ym" countdowns from data-lock timestamps.
  function tick() {
    var now = Date.now();
    document.querySelectorAll("[data-lock]").forEach(function (el) {
      var t = Date.parse(el.getAttribute("data-lock"));
      if (isNaN(t)) return;
      var s = Math.round((t - now) / 1000);
      if (s <= 0) { el.textContent = "locked"; return; }
      var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
      el.textContent = "locks in " + (d ? d + "d " : "") + h + "h " + m + "m";
    });
  }
  tick();
  setInterval(tick, 30000);
  // Filter chips on the picks page (data-filter buttons, cards carry data-tier/data-soon).
  var chips = document.querySelectorAll("[data-filter]");
  if (chips.length) {
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
        chip.setAttribute("aria-pressed", "true");
        var f = chip.getAttribute("data-filter");
        document.querySelectorAll(".card[data-tier]").forEach(function (card) {
          var show = f === "all" || card.getAttribute("data-tier") === f ||
                     (f === "soon" && card.getAttribute("data-soon") === "1");
          card.style.display = show ? "" : "none";
        });
        document.querySelectorAll(".dayhead").forEach(function (h) {
          var n = h.nextElementSibling, any = false;
          while (n && !n.classList.contains("dayhead")) {
            if (n.classList.contains("card") && n.style.display !== "none") any = true;
            n = n.nextElementSibling;
          }
          h.style.display = any ? "" : "none";
        });
      });
    });
  }
})();

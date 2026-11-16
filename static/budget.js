(function () {
  function fmt(n) { return Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 }); }

  function banner(text, color, bg) {
    var el = document.getElementById("budgetBanner");
    if (!el) {
      el = document.createElement("a");
      el.id = "budgetBanner";
      el.href = "/advisor";
      el.style.cssText = "display:block;text-decoration:none;padding:12px 16px;border-radius:10px;margin-bottom:16px;font-size:14px;font-weight:600";
      var main = document.querySelector("main.container");
      main.insertBefore(el, main.firstChild);
    }
    el.style.background = bg;
    el.style.color = color;
    el.textContent = text;
  }

  async function refresh() {
    try {
      var s = await (await fetch("/advisor/api/status")).json();
      var el = document.getElementById("budgetBanner");
      if (!s.budget || (s.state !== "over" && s.state !== "within")) { if (el) el.remove(); return; }
      if (s.state === "over") {
        banner("Budget alert: your latest estimated bill is Rs " + fmt(s.bill) + ", Rs " + fmt(s.diff) +
          " above your monthly budget of Rs " + fmt(s.budget) + ". Open the Advisor to see how to reduce it.", "#991b1b", "#fee2e2");
      } else {
        banner("Within budget: your latest estimated bill is Rs " + fmt(s.bill) + " (budget Rs " + fmt(s.budget) + ").", "#166534", "#dcfce7");
      }
    } catch (e) {}
  }

  if (typeof loadHistory === "function") {
    var original = loadHistory;
    loadHistory = async function () { await original(); refresh(); };
  }
  refresh();
})();
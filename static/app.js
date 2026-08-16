// 时效 Lite 前端交互：ack / 完成 / 测试推送（fetch /api/v1，同源带 session cookie）
(function () {
  function post(url, btn, onDone) {
    if (btn) { btn.disabled = true; }
    fetch(url, { method: "POST", credentials: "same-origin" })
      .then(r => { if (r.status === 401) { location.href = "/login"; throw new Error("unauthorized"); } return r.json(); })
      .then(d => {
        if (!d.ok) throw new Error(d.detail || JSON.stringify(d));
        if (onDone) onDone(d);
      })
      .catch(e => {
        alert("操作失败：" + e.message);
        if (btn) btn.disabled = false;
      });
  }

  document.addEventListener("click", function (ev) {
    var ackBtn = ev.target.closest(".ack-btn");
    if (ackBtn) {
      post("/api/v1/items/" + ackBtn.dataset.id + "/ack", ackBtn, function () {
        ackBtn.outerHTML = '<span class="tag ok">✅ 已确认</span>';
      });
      return;
    }
    var doneBtn = ev.target.closest(".done-btn");
    if (doneBtn) {
      post("/api/v1/items/" + doneBtn.dataset.id + "/done", doneBtn, function () { location.reload(); });
      return;
    }
    var testBtn = ev.target.closest(".test-btn");
    if (testBtn) {
      testBtn.textContent = "推送中…";
      post("/api/v1/items/" + testBtn.dataset.id + "/test-push", testBtn, function (d) {
        var okAll = d.results.every(r => r.ok);
        testBtn.textContent = okAll ? "已推送✓" : "有失败!";
        setTimeout(function () { testBtn.textContent = "测试"; }, 2500);
      });
      return;
    }
    var chip = ev.target.closest(".chip");
    if (chip) {
      var input = document.getElementById("remind-times");
      if (input) input.value = chip.dataset.times;
    }
  });

  // 自定义循环时才显示周期天数
  var cycleSel = document.getElementById("cycle-sel");
  function toggleCycleDays() {
    var wrap = document.getElementById("cycle-days-wrap");
    if (wrap && cycleSel) wrap.style.display = cycleSel.value === "custom" ? "" : "none";
  }
  if (cycleSel) { cycleSel.addEventListener("change", toggleCycleDays); toggleCycleDays(); }
})();

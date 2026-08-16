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
    if (chip && chip.dataset.times && document.getElementById("time-list") === null) {
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

  // ===== 事项表单：勾选提醒日 + 时间选择器 → 组装 JSON 隐藏字段 =====
  var form = document.getElementById("item-form");
  if (form) initItemForm(form);

  function initItemForm(f) {
    var days = JSON.parse(f.dataset.days || "[30,7,1,0]");
    var times = JSON.parse(f.dataset.times || '["09:00"]');

    // 勾选框回填
    f.querySelectorAll(".check input[data-day]").forEach(function (cb) {
      cb.checked = days.indexOf(parseInt(cb.dataset.day, 10)) >= 0;
    });
    // 自定义天数回填（不在预设里的）
    var preset = [30, 14, 7, 3, 1, 0];
    var extra = days.filter(function (d) { return preset.indexOf(d) < 0; });
    document.getElementById("custom-days").value = extra.join(", ");

    // 时间行构建
    var list = document.getElementById("time-list");
    function addTimeRow(val) {
      var row = document.createElement("div");
      row.className = "time-row";
      var inp = document.createElement("input");
      inp.type = "time";
      inp.className = "input";
      inp.value = val || "09:00";
      var del = document.createElement("button");
      del.type = "button";
      del.className = "chip del-time";
      del.textContent = "✕";
      del.addEventListener("click", function () {
        if (list.children.length > 1) row.remove(); else inp.value = "09:00";
      });
      row.appendChild(inp); row.appendChild(del);
      list.appendChild(row);
    }
    (times.length ? times : ["09:00"]).forEach(addTimeRow);
    document.getElementById("add-time").addEventListener("click", function () { addTimeRow("09:00"); });

    // 快捷时刻：清空重建
    f.querySelectorAll(".quick-times .chip[data-times]").forEach(function (c) {
      c.addEventListener("click", function () {
        list.innerHTML = "";
        JSON.parse(c.dataset.times).forEach(addTimeRow);
      });
    });

    // 提交前组装
    f.addEventListener("submit", function () {
      var set = {};
      f.querySelectorAll(".check input[data-day]:checked").forEach(function (cb) {
        set[parseInt(cb.dataset.day, 10)] = true;
      });
      document.getElementById("custom-days").value.split(/[,，\s]+/).forEach(function (s) {
        if (/^\d+$/.test(s.trim())) set[parseInt(s.trim(), 10)] = true;
      });
      var dayArr = Object.keys(set).map(Number).sort(function (a, b) { return b - a; });
      document.getElementById("remind-days").value = dayArr.length ? JSON.stringify(dayArr) : "[30,7,1,0]";

      var tArr = [];
      list.querySelectorAll("input[type=time]").forEach(function (i) {
        if (i.value && tArr.indexOf(i.value) < 0) tArr.push(i.value);
      });
      document.getElementById("remind-times").value = tArr.length ? JSON.stringify(tArr) : '["09:00"]';

      document.getElementById("cycle-days-hidden").value =
        (document.getElementById("cycle-days") || {}).value || "";
      document.getElementById("advance-days-hidden").value =
        (document.getElementById("advance-days-in") || {}).value || "30";
    });
  }
})();

// 时效 Lite 快速提醒 popup
const $ = (id) => document.getElementById(id);
const DEF_SERVER = ""; // 首次使用在 ⚙️ 里填自己的服务器地址

let cfg = { serverUrl: DEF_SERVER, apiToken: "" };
let candDates = []; // 🎯 识别出的候选日期 [{date, raw}]

function toast(text, ok = true) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ok ? 1400 : 2400);
}

function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function loadCfg() {
  const got = await chrome.storage.local.get(["serverUrl", "apiToken"]);
  cfg.serverUrl = got.serverUrl || DEF_SERVER;
  cfg.apiToken = got.apiToken || "";
  $("serverUrl").value = cfg.serverUrl;
  $("apiToken").value = cfg.apiToken;
  if (!cfg.apiToken || !cfg.serverUrl) $("cfg").classList.add("show");
}

async function saveCfg() {
  cfg.serverUrl = $("serverUrl").value.trim().replace(/\/$/, "");
  cfg.apiToken = $("apiToken").value.trim();
  await chrome.storage.local.set(cfg);
  $("cfgMsg").textContent = "已保存（未验证）";
  try {
    const r = await fetch(`${cfg.serverUrl}/healthz`);
    const j = await r.json();
    $("cfgMsg").textContent = j.ok ? "✅ 服务器连通" : "❌ 响应异常";
  } catch (e) {
    $("cfgMsg").textContent = "❌ 连不上服务器，检查地址";
  }
}

// ===== 🎯 智能识别：选中文字 → 日期 + 账号 =====
let lastSelError = "";

async function getSelectionText() {
  lastSelError = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    // 扫描所有框架（含 iframe）+ 输入框内选区，取最长的一段
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: () => {
        let s = "";
        try { s = window.getSelection().toString(); } catch (_) {}
        try {
          const el = document.activeElement;
          if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")
              && el.selectionStart != null && el.selectionStart !== el.selectionEnd) {
            s += "\n" + el.value.slice(el.selectionStart, el.selectionEnd);
          }
        } catch (_) {}
        return s.trim();
      },
    });
    const texts = (results || []).map(r => (r.result || "").trim()).filter(Boolean);
    if (texts.length) return texts.sort((a, b) => b.length - a.length)[0];
  } catch (e) {
    lastSelError = (e && e.message) || String(e);
  }
  // 兜底：右键菜单「用时效 Lite 提醒」存下的选中文字
  const got = await chrome.storage.local.get(["pendingText"]);
  return got.pendingText || "";
}

async function smartPick(silentIfEmpty = false) {
  const msg = $("msg");
  msg.textContent = "读取选中文字…";
  const sel = await getSelectionText();
  if (!sel.trim()) {
    msg.textContent = "";
    if (lastSelError) {
      toast(`读取选区失败：${lastSelError.slice(0, 60)}。可改用右键菜单「用时效 Lite 提醒」`, false);
    } else if (!silentIfEmpty) {
      toast("没读到选区：重新划选后别点别处，直接点插件图标；或对选中文字点右键菜单", false);
    }
    return;
  }
  chrome.storage.local.remove("pendingText");
  candDates = RLParser.findDates(sel);
  const accounts = RLParser.findAccounts(sel);

  // 日期：首选自动填 + 候选可切换
  if (candDates.length) {
    $("expireDate").value = candDates[0].date;
    const list = $("candList");
    list.innerHTML = "";
    candDates.forEach((c, i) => {
      const chip = document.createElement("span");
      chip.className = "chip" + (i === 0 ? " on" : "");
      chip.textContent = c.date;
      chip.addEventListener("click", () => {
        $("expireDate").value = c.date;
        list.querySelectorAll(".chip").forEach((x) => x.classList.remove("on"));
        chip.classList.add("on");
      });
      list.appendChild(chip);
    });
    $("cands").classList.add("show");
  } else {
    $("cands").classList.remove("show");
  }

  // 标题：取选中内容的第一行（去掉纯日期行）
  const lines = sel.trim().split(/\n+/).filter((l) => !/^\d{4}[-/.年]/.test(l.trim()));
  const firstLine = (lines[0] || sel.trim()).slice(0, 60);
  if (!$("title").value.trim()) $("title").value = firstLine;

  // 备注：账号信息 + 来源
  const noteParts = [];
  if (accounts.length) noteParts.push(...accounts);
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url) noteParts.push(`来源 ${tab.url}`);
  } catch (_) {}
  $("note").value = noteParts.join("\n");

  msg.textContent = candDates.length
    ? `✅ 识别到到期日 ${candDates[0].date}，请核对后提交` + (accounts.length ? `；账号 ${accounts.length} 项已入备注` : "")
    : "⚠️ 没识别到日期（可手动选），账号信息已入备注";
}

function selectedAdvDays() {
  const days = [];
  document.querySelectorAll("#advChips .chip.on").forEach((c) => days.push(parseInt(c.dataset.d, 10)));
  return days.length ? days : [30, 7, 1, 0];
}

async function submit() {
  const title = $("title").value.trim();
  const expireDate = $("expireDate").value;
  if (!title || !expireDate) { toast("内容和到期日必填", false); return; }
  if (!cfg.apiToken || !cfg.serverUrl) { toast("先配置服务器地址和 Token", false); $("cfg").classList.add("show"); return; }
  const times = $("remindTimes").value.split(/[,，\s]+/).filter(t => /^\d{1,2}:\d{2}$/.test(t)).map(t => t.length === 4 ? "0" + t : t);
  if (!times.length) { toast("推送时刻格式如 09:00", false); return; }
  $("submit").disabled = true;
  try {
    const r = await fetch(`${cfg.serverUrl}/api/v1/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.apiToken}` },
      body: JSON.stringify({
        title, category: $("category").value, note: $("note").value.trim(),
        expire_date: expireDate, cycle: "none",
        remind_days: selectedAdvDays(), remind_times: times,
      }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
    toast("✅ 已添加");
    setTimeout(() => window.close(), 900);
  } catch (e) {
    toast("失败: " + e.message, false);
  } finally {
    $("submit").disabled = false;
  }
}

async function insertTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  const cur = $("title").value.trim();
  const seg = `${tab.title || ""} ${tab.url || ""}`.trim();
  $("title").value = cur ? `${cur} ${seg}` : seg;
}

document.addEventListener("DOMContentLoaded", () => {
  loadCfg();
  // 默认选中「7天后」
  const today = new Date();
  $("expireDate").value = fmtDate(new Date(today.getTime() + 7 * 86400e3));
  markChip(7);

  $("gear").addEventListener("click", () => $("cfg").classList.toggle("show"));
  $("saveCfg").addEventListener("click", saveCfg);
  $("submit").addEventListener("click", submit);
  $("insertTab").addEventListener("click", insertTab);
  $("smartPick").addEventListener("click", smartPick);

  document.querySelectorAll("#dateChips .chip").forEach((c) => {
    c.addEventListener("click", () => {
      const days = parseInt(c.dataset.days, 10);
      $("expireDate").value = fmtDate(new Date(today.getTime() + days * 86400e3));
      markChip(days);
    });
  });
  $("expireDate").addEventListener("change", () => {
    const diff = Math.round((new Date($("expireDate").value) - today) / 86400e3);
    markChip(diff);
  });
  // 提前天数勾选
  document.querySelectorAll("#advChips .chip").forEach((c) => {
    c.addEventListener("click", () => c.classList.toggle("on"));
  });

  $("title").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
  });

  // 右键菜单「用时效 Lite 提醒」带入了选中文字 → 打开即自动识别
  chrome.storage.local.get(["pendingText"]).then((got) => {
    if (got.pendingText) smartPick(true);
  });
});

function markChip(days) {
  document.querySelectorAll("#dateChips .chip").forEach((c) =>
    c.classList.toggle("on", parseInt(c.dataset.days, 10) === days));
}

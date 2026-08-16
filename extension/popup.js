// 时效 Lite 快速提醒 popup
const $ = (id) => document.getElementById(id);
const DEF_SERVER = ""; // 首次使用在 ⚙️ 里填自己的服务器地址

let cfg = { serverUrl: DEF_SERVER, apiToken: "" };

function toast(text, ok = true) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ok ? 1200 : 2200);
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
  if (!cfg.apiToken) $("cfg").classList.add("show");
  if (!cfg.serverUrl) $("cfg").classList.add("show");
}

async function saveCfg() {
  cfg.serverUrl = $("serverUrl").value.trim().replace(/\/$/, "");
  cfg.apiToken = $("apiToken").value.trim();
  await chrome.storage.local.set(cfg);
  $("cfgMsg").textContent = "已保存（未验证）";
  // 验证连通性
  try {
    const r = await fetch(`${cfg.serverUrl}/healthz`);
    const j = await r.json();
    $("cfgMsg").textContent = j.ok ? "✅ 服务器连通" : "❌ 响应异常";
  } catch (e) {
    $("cfgMsg").textContent = "❌ 连不上服务器，检查地址";
  }
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
        remind_days: "default", remind_times: times,
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

// 右键菜单/快捷键带来的预填文字
async function loadPending() {
  const got = await chrome.storage.local.get(["pendingText"]);
  if (got.pendingText) {
    $("title").value = got.pendingText;
    $("title").focus();
    chrome.storage.local.remove("pendingText");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadCfg();
  loadPending();
  // 默认选中「7天后」
  const today = new Date();
  $("expireDate").value = fmtDate(new Date(today.getTime() + 7 * 86400e3));
  markChip(7);

  $("gear").addEventListener("click", () => $("cfg").classList.toggle("show"));
  $("saveCfg").addEventListener("click", saveCfg);
  $("submit").addEventListener("click", submit);
  $("insertTab").addEventListener("click", insertTab);

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

  $("title").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
  });
});

function markChip(days) {
  document.querySelectorAll("#dateChips .chip").forEach((c) =>
    c.classList.toggle("on", parseInt(c.dataset.days, 10) === days));
}

// 时效 Lite service worker：快捷键 + 右键菜单「把选中文字设为提醒」
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "rl-remind-selection",
    title: "⏰ 用时效 Lite 提醒：「%s」",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: "rl-remind-page",
    title: "⏰ 提醒我再看这个页面",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  let text = "";
  if (info.menuItemId === "rl-remind-selection") {
    text = info.selectionText || "";
  } else if (info.menuItemId === "rl-remind-page" && tab) {
    text = `${tab.title || "未命名页面"} ${tab.url || ""}`;
  }
  if (!text) return;
  await chrome.storage.local.set({ pendingText: text.slice(0, 500) });
  // Chrome 127+ 支持从 service worker 打开 popup；失败则用户点图标时也会读到预填
  try { await chrome.action.openPopup(); } catch (_) { /* ignore */ }
});

chrome.commands.onCommand.addListener(async (cmd) => {
  if (cmd === "open-quick-remind") {
    try { await chrome.action.openPopup(); } catch (_) { /* ignore */ }
  }
});

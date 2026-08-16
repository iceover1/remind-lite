// 时效 Lite · iOS 桌面小组件（Scriptable）
// 安装：App Store 装 Scriptable（免费）→ 新建脚本粘贴本文件全部内容 →
//       修改下面 SERVER/TOKEN 两行 → 桌面长按 → + → Scriptable → 选本脚本
// Variables intended to be customized — 修改这两行：
const SERVER = "http://<NAS_IP>:15809";  // 时效 Lite 地址（手机可达）
const TOKEN = "rl_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";       // 设置页的 API Token

const MAX_ROWS = 10;

async function loadItems() {
  const req = new Request(`${SERVER}/api/v1/items?status=active`);
  req.headers = { Authorization: `Bearer ${TOKEN}` };
  const data = await req.loadJSON();
  return (data && data.items ? data.items : [])
    .sort((a, b) => a.expire_date < b.expire_date ? -1 : 1)
    .slice(0, MAX_ROWS);
}

function colorFor(days, isDark) {
  if (days < 0) return new Color("#d3455b");
  if (days <= 3) return new Color("#c27400");
  return isDark ? new Color("#8b95a5") : new Color("#66707e");
}

const widget = new ListWidget();
const isDark = Device.isUsingDarkAppearance();

try {
  const items = await loadItems();
  const head = widget.addText("⏰ 到期提醒");
  head.font = Font.boldSystemFont(13);
  head.textColor = isDark ? new Color("#e6edf3") : new Color("#1f2733");
  widget.addSpacer(4);

  if (!items.length) {
    const empty = widget.addText("暂无到期事项 ✅");
    empty.font = Font.systemFont(12);
    empty.textColor = colorFor(99, isDark);
  }
  for (const it of items) {
    const row = widget.addText(
      `${it.days_left < 0 ? "❗️逾期" + (-it.days_left) + "天" : (it.days_left === 0 ? "⏰今天" : it.days_left + "天")}  ${it.title}`
    );
    row.font = Font.systemFont(11);
    row.lineLimit = 1;
    row.textColor = colorFor(it.days_left, isDark);
    widget.addSpacer(2);
  }
} catch (e) {
  const err = widget.addText("⚠️ 加载失败：" + e.message);
  err.font = Font.systemFont(11);
  err.textColor = new Color("#d3455b");
}

widget.url = SERVER;           // 点击小组件打开时效 Lite
widget.refreshAfterDate = new Date(Date.now() + 30 * 60 * 1000); // 30分钟自动刷新
Script.setWidget(widget);

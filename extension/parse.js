// 时效 Lite 选中文字识别引擎：日期（含美式/中文/无年份推断）+ 账号信息
// 纯正则，无网络请求；供 popup 使用
const RLParser = (() => {
  const MONTHS = {};
  ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    .forEach((m, i) => { MONTHS[m] = i + 1; });
  const MON_RE = "(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)";

  const TLD = new Set(("com org net cn io dev app cc cd me top xyz info online site store tech cloud live " +
    "life fun pro ai im eu us uk jp kr hk tw ru in co la to gg vc link icu zone team pw biz name mobi " +
    "asia tv fm am st ly be br ca au de fr es se ch nl pl pt mx ar cl").split(" "));

  const STRONG_KW = ["到期日期", "到期时间", "过期时间", "有效期至", "有效期限", "失效日期", "expiration", "expire"];
  const EXPIRE_KW = ["到期", "过期", "失效", "有效", "截止", "结束", "expire", "expiry", "expiration",
    "due", "renew", "valid", "deadline", "ends"];
  const REG_KW = ["注册日期", "注册时间", "创建", "申请", "签发", "开通", "issued", "created",
    "registered", "registration", "start date", "开始日期"];

  function pad(n) { return String(n).padStart(2, "0"); }
  function iso(y, m, d) { return `${y}-${pad(m)}-${pad(d)}`; }
  function valid(y, m, d) {
    if (m < 1 || m > 12 || d < 1 || d > 31) return false;
    return y >= 2000 && y <= 2099;
  }

  // 无年份时推断：今年该日未过取今年，已过取明年
  function inferYear(m, d) {
    const t = new Date();
    const y = t.getFullYear();
    const passed = (m < t.getMonth() + 1) || (m === t.getMonth() + 1 && d < t.getDate());
    return passed ? y + 1 : y;
  }

  function findDates(text) {
    const found = []; // {date, raw, pos, score}
    const push = (y, m, d, raw, pos) => {
      if (!valid(y, m, d)) return;
      const date = iso(y, m, d);
      if (found.some(f => f.date === date)) return;
      // 上下文打分：日期前 30 字符窗口
      const ctx = text.slice(Math.max(0, pos - 30), pos).toLowerCase();
      let score = 0;
      for (const k of STRONG_KW) if (ctx.includes(k)) score += 5;
      for (const k of EXPIRE_KW) if (ctx.includes(k)) score += 2;
      for (const k of REG_KW) if (ctx.includes(k)) score -= 6;
      const today = new Date();
      if (new Date(date) < new Date(today.toISOString().slice(0, 10))) score -= 1; // 过去日期轻微降权
      found.push({ date, raw, score });
    };

    let m;
    // 2027-08-16 / 2027/8/16 / 2027.8.16 / 2027年8月16日
    const re1 = /(\d{4})\s*[年.\-\/]\s*(\d{1,2})\s*[月.\-\/]\s*(\d{1,2})\s*日?/g;
    while ((m = re1.exec(text))) push(+m[1], +m[2], +m[3], m[0], m.index);
    // 美式 Jul 20, 2027 / Jul 20 2027 / Jul 20th 2027
    const re2 = new RegExp(MON_RE + "\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?\\s*,?\\s*(\\d{4})", "gi");
    while ((m = re2.exec(text))) push(+m[3], MONTHS[m[1].toLowerCase().slice(0, 3)], +m[2], m[0], m.index);
    // 美式倒装 20 Jul 2027 / 20-Jul-2027
    const re3 = new RegExp("(\\d{1,2})(?:st|nd|rd|th)?\\s*[-\\s]\\s*" + MON_RE + "\\.?\\s*,?\\s*(\\d{4})", "gi");
    while ((m = re3.exec(text))) push(+m[3], MONTHS[m[2].toLowerCase().slice(0, 3)], +m[1], m[0], m.index);
    // 美式纯数字 07/20/2027 / 7.20.2027（首段>12 视为 日/月/年）
    const re4 = /(\d{1,2})[.\/](\d{1,2})[.\/](\d{4})/g;
    while ((m = re4.exec(text))) {
      let mm = +m[1], dd = +m[2];
      if (mm > 12 && dd <= 12) { const t = mm; mm = dd; dd = t; } // 20/07/2026 → 7月20日
      push(+m[3], mm, dd, m[0], m.index);
    }
    // 中文无年份 8月16日
    const re5 = /(\d{1,2})\s*月\s*(\d{1,2})\s*日?/g;
    while ((m = re5.exec(text))) {
      if (/\d{4}/.test(text.slice(Math.max(0, m.index - 8), m.index))) continue; // 前面已有年份的会命中 re1，跳过
      const y = inferYear(+m[1], +m[2]);
      push(y, +m[1], +m[2], m[0], m.index);
    }

    // 排序：分数优先，同分取更晚的日期（到期日通常在未来）
    found.sort((a, b) => b.score - a.score || (a.date < b.date ? 1 : -1));
    return found.slice(0, 3);
  }

  function findAccounts(text) {
    const out = [];
    const seen = new Set();
    const add = (label, val) => {
      val = val.trim().replace(/[，。）)\]}；;、\s]+$/, "");
      if (!val || val.length < 2 || val.length > 60 || seen.has(val)) return;
      // 过滤误伤：纯数字、时间、IP 的不当作账号
      if (/^[\d.\s:\/]+$/.test(val)) return;
      seen.add(val);
      out.push(`${label} ${val}`);
    };

    let m;
    // 邮箱
    const mails = [];
    const reMail = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
    while ((m = reMail.exec(text))) { mails.push(m[0]); add("邮箱", m[0]); }
    // 域名（TLD 白名单过滤，排除邮箱里的域名和纯 IP）
    const reDom = /\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+([a-zA-Z]{2,12})\b/g;
    while ((m = reDom.exec(text))) {
      const dom = m[0];
      if (!TLD.has(m[1].toLowerCase())) continue;
      if (dom.includes("@")) continue;
      if (/^\d+\.\d+/.test(dom)) continue; // IP/版本号
      if (mails.some(e => e.endsWith("@" + dom) || e.endsWith(dom))) continue; // 邮箱的域名部分不重复记
      const label = /域名|domain/i.test(text.slice(Math.max(0, m.index - 12), m.index)) ? "域名" : "域名?";
      add(label, dom);
    }
    // 带标签的账号：管理员/账号/用户名 xxx（值可含空格，遇逗号/分号/右括号结束）
    const reLabel = /(管理员|账号|账户|用户名?|所有者|owner|user(?:name)?|account)\s*[:：为是]?\s*([A-Za-z0-9_.@\-\u4e00-\u9fa5 ]{2,40}?)(?=[\s]*[，,；;）)\n]|$)/g;
    while ((m = reLabel.exec(text))) add(m[1].replace(/名$/, ""), m[2]);
    // 「域名 xxx」显式标签（值可能是多级域名）
    const reDomLabel = /域名\s*[:：为是]?\s*([a-zA-Z0-9][\w.-]{2,60})/g;
    while ((m = reDomLabel.exec(text))) add("域名", m[1]);

    return out.slice(0, 6);
  }

  function buildNote(text, url) {
    const lines = findAccounts(text);
    if (url) lines.push(`来源 ${url}`);
    return lines.join("\n");
  }

  return { findDates, findAccounts, buildNote };
})();

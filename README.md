# ⏰ 时效 Lite（remind-lite）

> 自部署的轻量效期提醒系统：到期前按你设定的节奏推送到手机（Bark / MagicPush），配 Web 管理界面、Chrome 快速添加插件和一套 Token API。
>
> 单容器、SQLite 存储、零外部依赖、离线内网可用，数据完全归自己。

---

## ✨ 功能特性

### 提醒策略（核心）

- **效期事项**：名称 / 分类（域名、服务器、证件、订阅、质保…）/ 到期日 / 备注
- **循环周期**：不循环 / 每月 / 每年 / 自定义 N 天——到期后自动滚动到下一周期，续费类事项一次配置长期有效
- **提醒日 × 推送时刻 两维组合**：
  - 提醒日：到期前第 60/30/14/7/3/1/0 天任选（默认 30/7/1/0），也可窗口内每天
  - 推送时刻：一天内多个时点（如 09:00、13:09、20:00），推几次就配几个
- **「知道了」确认**：Web 今日概览点一下，当天剩余推送自动取消，第二天恢复
- **逾期不丢**：未完成的事项每天继续在设定时刻提醒
- **循环滚动**：每日 00:05 自动把已过期的循环事项滚到下一周期

### 推送

- **自适应双格式**：同一通道自动探测 [bark-server](https://github.com/Finb/bark-server)（`POST /push` JSON）与 [MagicPush](https://github.com/magiccode1412/magicpush)（`POST /api/push/<key>`）两种 API，都不行再回退 bark 经典 GET 路径，且严格校验 JSON 响应防止误报成功
- **多通道**：可同时推多台设备（自建服务器 / 官方 `api.day.app` 混用）
- **通知可点击**：推送附带跳转链接，点通知直达 Web 界面
- **发送日志**：每次推送落库（成功/失败/Bark 响应），失败可一键重发测试

### Web 界面

- 今日概览（今日提醒数 / 已逾期 / 7 天内到期 / 进行中 统计卡片 + 逐条确认）
- 效期管理：勾选式提醒日、时间选择器式推送时刻、快捷模板（早9点×1 / 早晚×2 / 三档×3）
- 深色模式自动适配、移动端友好
- 单用户密码登录 + API Token，表结构预留 `user_id` 可扩展多用户

### Chrome 插件（快速添加）

- 划选网页上的到期信息 → 点 **🎯 识别**：**自动识别到期日**（支持 `2027-08-16`、`2027年8月16日`、`Jul 20, 2027`、`20 Jul 2027`、`07/20/2027`、无年份 `8月16日` 自动推断），多日期并存时按关键词（到期/Expiration 加分、注册/Registration 减分）选对到期日，候选可点选切换
- **账号信息自动进备注**：识别 `域名 xxx`、`Administrator xxx`、邮箱、账号等（支持中英文标签、标签与值分行），并附来源 URL
- 快捷日期：明天 / 7天后 / 30天后 / 一年后
- 提前推送天数勾选（60/30/14/7/3/1/当天）
- 快捷键 `Ctrl/Cmd+Shift+U` 呼出；右键选中文字「⏰ 用时效 Lite 提醒」自动识别；`🔗本页` 插入当前页标题+链接

### REST API（`/api/v1`）

Agent / 脚本 / 插件共用一套 Bearer Token API，完整读写——可以让 AI 助手直接口头增改提醒。

---

## 🏗 架构

```
┌────────────┐   划选识别    ┌──────────────┐
│ Chrome 插件 │ ───────────▶ │              │
└────────────┘              │   时效 Lite   │
┌────────────┐   Bearer     │  FastAPI     │
│ 脚本/AI    │ ───────────▶ │  + APScheduler│
└────────────┘              │  + SQLite    │
┌────────────┐   会话Cookie  │      │        │
│  Web 浏览器 │ ───────────▶ │      │        │
└────────────┘              └──────┼────────┘
                                   │ 每分钟 tick
                                   ▼
                          ┌────────────────┐
                          │ bark-server 或  │──▶ 📱 手机 Bark 通知
                          │   MagicPush    │
                          └────────────────┘
```

- **后端**：Python 3.12 / FastAPI / APScheduler / SQLite（WAL 模式）
- **前端**：Jinja2 服务端渲染 + 原生 JS，无 CDN 依赖（内网/离线可用）
- **部署**：单容器 Docker，数据就是一个 `remindlite.db` 文件，备份即拷贝

## 📦 快速开始

```bash
git clone https://github.com/iceover1/remind-lite.git
cd remind-lite
cp .env.example .env    # 填：端口、初始密码、手机可达的服务地址
docker compose up -d --build
```

打开 `http://<NAS或服务器IP>:15809`，用 `.env` 里的账号密码登录。

**首次配置三步：**

1. **设置 → 修改密码**：改掉初始密码
2. **设置 → 添加推送通道**：
   - 自建 bark-server：服务器填 `http://<IP>:8080`，Key 填 Bark App 里复制的
   - 自建 MagicPush：服务器填 `http://<IP>:818`，Key 填推送地址里的 device key
   - 无自建服务：服务器填 `https://api.day.app`（官方 Bark）
3. **设置 → API Token**：复制 Token 给 Chrome 插件用（可随时重置，旧的立即失效）

**Chrome 插件安装：**

1. `chrome://extensions` → 打开「开发者模式」
2. 「加载已解压的扩展程序」→ 选择本仓库的 `extension/` 目录
3. 点插件图标 ⚙️ → 填服务器地址（`http://<IP>:15809`）+ API Token → 保存

---

## 🧩 Chrome 插件（部署与使用）

### 安装（二选一）

| 方式 | 步骤 | 适合 |
|---|---|---|
| **源码加载** | `git clone` 本仓库 → `chrome://extensions` → 开发者模式 → 「加载已解压的扩展程序」→ 选 `extension/` 目录 | 会用 git、想跟最新版 |
| **Release 附件** | [Releases](https://github.com/iceover1/remind-lite/releases) 下载 `时效Lite-plugin-vX.Y.Z.zip` → 解压 → 同上加载解压后的目录 | 不想 clone，点下载就用 |

**升级**：拉取最新代码（或解压新版覆盖）→ 插件卡片点 ↻ 刷新；manifest 加过权限时 Chrome 可能提示重新启用，确认即可。

### 配置（首次）

1. 打开时效 Lite Web → **设置** 页 → 复制 **API Token**
2. 点浏览器工具栏的插件图标 → 点右上角 **⚙️** → 填两项：
   - **服务器地址**：浏览器可达的地址（如 `http://192.168.x.x:15809`，手机热点/外网下填穿透或 Tailscale 地址）
   - **API Token**：粘贴上一步复制的
3. 点「保存」会自动做连通性测试（`/healthz`），显示 ✅ 即配置成功

### 功能速览

**🎯 智能识别（核心功能）**——在任意网页用鼠标划选到期信息 → 点 🎯 按钮（或划选后直接右键「⏰ 用时效 Lite 提醒」，插件打开即自动识别）：

- **日期识别**（识别结果自动填入「到期日」，多个日期时上方出现候选徽章可点选切换）：

  | 格式 | 示例 |
  |---|---|
  | ISO / 分隔符 | `2027-08-16`、`2027/8/16`、`2027.8.16` |
  | 中文 | `2027年8月16日`、`8月16日`（无年份自动推断：过了取明年） |
  | 美式月份 | `Jul 20, 2027`、`July 20 2027`、`Jul 20th, 2027` |
  | 美式倒装 | `20 Jul 2027`、`20-Jul-2027` |
  | 纯数字 | `07/20/2027`（`20/07/2027` 自动识别为日/月/年） |

- **多日期选对**：按关键词加权——「到期/过期/有效期/Expiration/due」附近加分，「注册/创建/Registration/issued」附近减分；实测 `注册日期 Jul 20, 2025 / 到期日期 Jul 20, 2027` 正确选中 2027
- **账号信息自动进备注**：识别 `域名 xxx`、`Administrator xxx`、邮箱、账号等（中英文标签均可，标签与值**分行**也能配对），末尾附来源 URL
- 识别支持 iframe 内选区和输入框内划选

**其他**：

- 快捷日期：明天 / 7天后 / 30天后 / 一年后，其他日期点日期框自选
- 提前推送天数勾选：60/30/14/7/3/1/当天（默认 30/7/1/0）——**识别到的是到期日，推送发生在它之前**
- 🔗本页：把当前标签页标题+链接插到内容里
- 快捷键 `Ctrl/Cmd+Shift+U` 呼出插件；`Ctrl/Cmd+Enter` 快速提交
- 右键菜单：选中任意文字 →「⏰ 用时效 Lite 提醒」

### 权限说明

| 权限 | 用途 |
|---|---|
| `storage` | 保存服务器地址与 Token（仅本机） |
| `activeTab` + `scripting` | 读取当前页选中文字（智能识别用，不注入不修改页面） |
| `contextMenus` | 右键菜单 |

## 📖 使用方式

### 网页

- **今日**：今天要推的事项一目了然，处理完点「知道了」（当天不再推）或「完成」（归档）
- **效期管理**：新建/编辑事项；域名、服务器续费类建议循环选「每年」，一劳永逸
- **发送日志**：核对每次推送结果

### 插件（推荐日常入口）

在任意网页（域名后台、订单页…）划选到期信息 → 点图标 → 🎯 识别 → 核对 → 添加。
或划选后直接右键「⏰ 用时效 Lite 提醒」，打开即自动识别。

### 口头/AI 指令

把 Token 给你的 AI 助手（需能访问你的服务器），然后：

> 「把护照提醒改到 2031 年 8 月」
> 「加一条 xxx.com 续费提醒，明年 3 月 20 号到期」
> 「今天的事项都处理了」

## 🔌 API 文档

认证：`Authorization: Bearer <token>`（Web 登录会话 Cookie 也可）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/items?due=today` | 今日应提醒事项 |
| `GET` | `/api/v1/items?status=active` | 全部事项 |
| `GET` | `/api/v1/items/{id}` | 单条 |
| `POST` | `/api/v1/items` | 新建 |
| `PATCH` | `/api/v1/items/{id}` | 修改 |
| `DELETE` | `/api/v1/items/{id}` | 删除（含日志） |
| `POST` | `/api/v1/items/{id}/ack` | 当日确认（当天剩余推送取消） |
| `POST` | `/api/v1/items/{id}/done` | 完成归档 |
| `POST` | `/api/v1/items/{id}/test-push` | 立即推一条测试 |
| `GET/POST/DELETE` | `/api/v1/channels` | 推送通道管理 |
| `GET` | `/api/v1/meta` | 分类等元信息 |

事项字段：

```jsonc
{
  "title": "xxx.com 域名续费",
  "category": "域名",            // 域名|服务器|证件|订阅|质保|其他
  "note": "续费入口 https://…",
  "expire_date": "2027-08-16",   // 到期日（推送发生在它之前）
  "cycle": "year",               // none|month|year|custom
  "cycle_days": null,            // cycle=custom 时的周期天数
  "advance_days": 30,            // 提前提醒窗口（天）
  "remind_days": [30, 7, 1, 0],  // 到期前第几天推（0=当天）；"all"=窗口内每天
  "remind_times": ["09:00", "20:00"]  // 当天哪些时刻推
}
```

示例：

```bash
T="rl_xxx"; B="http://<NAS_IP>:15809"

# 新增：明年 8 月 16 日到期，提前 30/7/1/0 天，每天早晚各推一次
curl -X POST "$B/api/v1/items" \
  -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"title":"xxx.com 域名续费","category":"域名","expire_date":"2027-08-16",
       "cycle":"year","remind_days":[30,7,1,0],"remind_times":["09:00","20:00"]}'

# 修改到期日
curl -X PATCH "$B/api/v1/items/3" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"title":"xxx.com 域名续费","category":"域名","expire_date":"2028-08-16","cycle":"year","remind_times":["09:00"]}'

# 测试推送
curl -X POST "$B/api/v1/items/3/test-push" -H "Authorization: Bearer $T"
```

## ⏱ 调度语义

每分钟 tick：当前 `HH:MM` 命中事项的 `remind_times`，且满足——

1. 今天是提醒日（`到期日 - remind_days 中的某值 == 今天`，或已逾期）
2. 今天没点过「知道了」（acks 表）
3. 该 (事项, 日期, 时刻) 没推过（防容器重启重复轰炸）

三条都满足才推。全部通道推送结果写入发送日志。

## ❓ FAQ

**换个端口？** `.env` 里改 `RL_PORT` 后 `docker compose up -d`。

**多台手机？** 设置页加多个通道即可，每个通道独立服务器+Key。

**手机不在内网怎么收到推送/打开网页？** 推送由服务器发起（服务器能出网即可）；点击通知跳转的地址填 `.env` 的 `RL_BASE_URL`（可以是内网穿透/Tailscale 地址）。Tailscale 用户填 Headscale IP 即可。

**备份？** 拷 `data/remindlite.db` 一个文件（建议停容器或用 `sqlite3 .backup`）。

**时区？** 固定 `Asia/Shanghai`，容器 `TZ` 已设置。

## 📁 目录结构

```
remind-lite/
├── app/            # FastAPI 后端（api/web/scheduler/bark/auth…）
├── templates/      # Jinja2 页面
├── static/         # CSS/JS
├── extension/      # Chrome MV3 插件（含识别引擎 parse.js）
├── Dockerfile
├── docker-compose.yml
└── .env.example    # 部署配置模板（真实 .env 不入库）
```

## 📝 更新日志

- **1.0.5** 嵌入页 `/embed/upcoming?token=`（导航站 iframe 卡片显示到期排序）；iOS Scriptable 桌面小组件脚本
- **1.0.4** 安全加固：登录限速锁定（5次/15分钟+Bark告警）、请求体1MB上限、用户名时序枚举防护、会话版本化（改密/改名踢旧会话）；新增修改用户名
- **1.0.3** 插件选区读取增强（iframe/输入框/右键自动识别）
- **1.0.2** 识别引擎支持英文分行标签（Domain/Administrator/Expiration date）
- **1.0.1** 表单空值修复；提醒日/推送时刻改勾选与时间控件；界面美化（统计栏/阴影/斑马纹表格）
- **1.0.0** 首版：核心提醒 + 推送 + Web + 插件 + 迁移

---

🔒 **隐私**：所有数据（事项、账号备注、Token）仅存本地 SQLite，除推送服务器外不外发任何数据；仓库与镜像不含任何真实地址或凭证。

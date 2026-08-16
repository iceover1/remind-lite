# 时效 Lite

自研轻量效期提醒系统，替代商业软件「时效管家（remind-flow）」。单容器部署，Bark/MagicPush 推送到手机。

> 部署环境相关的地址、账号全部通过 `.env` 配置（模板 `.env.example`），仓库内不含任何真实内网地址或凭证。

## 功能

- **效期管理**：事项（名称/分类/到期日/备注）、循环（每月/每年/自定义N天）、提前提醒窗口
- **推送策略**：提醒日（默认提前 30/7/1/0 天，或窗口内每天）× 当日多个时刻（如 09:00、20:00）
- **网页确认**：今日概览点「知道了」→ 当日剩余推送自动取消
- **推送通道**：自适应 bark-server / MagicPush（`POST /api/push/<key>`）两种格式，多通道
- **REST API**（`/api/v1`，Bearer Token）：Agent 口头指令 / 浏览器插件共用
- **Chrome 插件**：`extension/` 目录，快捷键 + 右键菜单快速添加提醒

## 部署（Docker）

```bash
cp .env.example .env   # 填入本环境的真实地址与初始密码
docker compose up -d --build
```

离线/内网环境可在有外网的机器构建后传输：

```bash
docker build -t remind-lite:1.0.0 .
docker save remind-lite:1.0.0 | gzip | ssh <user>@<nas> 'gunzip | docker load'
```

数据在 `./data/remindlite.db`（SQLite WAL），备份即拷此文件。

## 首次使用

1. 浏览器打开 `http://<NAS_IP>:15809`，用 `.env` 里 `RL_USERNAME/RL_PASSWORD` 登录
2. **设置页**：改密码、添加推送通道（MagicPush/Bark 服务器 + Device Key）、生成 API Token
3. **效期管理**：新建事项，快捷选推送时刻
4. Chrome 安装插件：`chrome://extensions` → 开发者模式 → 加载已解压 → 选 `extension/` 目录，配置服务器地址 + API Token

## API 速查

```bash
T="rl_xxx"   # 设置页生成的 Token
B="http://<NAS_IP>:15809"

# 今日该提醒的事项
curl -H "Authorization: Bearer $T" "$B/api/v1/items?due=today"

# 新增
curl -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  "$B/api/v1/items" -d '{"title":"护照","category":"证件","expire_date":"2031-08-01","remind_times":["09:00"]}'

# 修改 / 确认 / 完成 / 测试推送 / 删除
curl -X PATCH  -H "Authorization: Bearer $T" ... "$B/api/v1/items/1"  -d '{...}'
curl -X POST   -H "Authorization: Bearer $T" "$B/api/v1/items/1/ack"
curl -X POST   -H "Authorization: Bearer $T" "$B/api/v1/items/1/done"
curl -X POST   -H "Authorization: Bearer $T" "$B/api/v1/items/1/test-push"
curl -X DELETE -H "Authorization: Bearer $T" "$B/api/v1/items/1"
```

## 数据迁移

`migrate/convert.py`：从原时效管家 `remindflow.db`（SQLite）导出事项与推送通道为 `seed_*.json`（含隐私，不入 git）。原库副本放 `migrate/` 下执行：

```bash
python3 migrate/convert.py migrate/remindflow.db migrate/
```

## 调度语义

- 每分钟 tick：当前 HH:MM 命中事项 `remind_times` 且当日为提醒日、未 ack、该时刻未推过 → 推送
- 逾期未完成：每天继续在设定时刻提醒
- 每日 00:05：循环事项到期后自动滚动到下一周期
- 时区 Asia/Shanghai

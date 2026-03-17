下面这份流程，按当前 `main` 的实现来走，适用于“部署到 VPS + 配好 Lark bot + 启动服务 + 做全流程验证”。当前代码状态已经包含 Lark base URL 配置、加密回调解密、以及“群里必须 `@bot` 才响应”的约束。

可参考的仓库文件：
[.env.example](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.env.example)  
[config/scheduler.toml](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/scheduler.toml)  
[scripts/dev_live_check.sh](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/scripts/dev_live_check.sh)

**1. 先明确当前能力**
- 服务支持 3 类 Lark 能力：告警推送、daily summary 推送、群聊或私聊 bot 查询。
- bot 目前是只读的，查的是库里已有数据，不会代你触发外部动作。
- fresh deploy 后，bot 能先工作，但如果数据库里还没有数据，它会给“无内部数据”的受限回复。
- daily summary 是“上一自然日”的摘要；刚部署当天如果没有昨天的数据，手动触发也会因为 `no_data` 跳过，这是预期行为。

**2. 先在 Lark 后台准备好应用**
- 创建一个 bot app。
- 记录 `App ID` 和 `App Secret`。
- 配一个 `Verification Token`，稍后填到 `LARK_VERIFICATION_TOKEN`。
- 事件加密二选一：
  - 如果你打算开启事件加密，就生成一个 `Encrypt Key`，填到 `LARK_ENCRYPT_KEY`。
  - 如果你不启用事件加密，就让 Lark 后台也保持不加密，并把 `LARK_ENCRYPT_KEY` 留空。
- 事件回调 URL 设为：
  ```text
  https://<your-domain>/api/integrations/lark/events
  ```
- 开启消息事件订阅，至少要有 `im.message.receive_v1`。
- 把 bot 加进你要接收告警和 summary 的群。
- 准备好目标群的 `chat_id`：
  - `LARK_ALERT_CHAT_ID_PROD`
  - `LARK_SUMMARY_CHAT_ID_PROD`
- 如果你用的是飞书中国版，不是 Lark global，把：
  ```text
  LARK_BASE_URL=https://open.feishu.cn
  ```
  否则用默认：
  ```text
  LARK_BASE_URL=https://open.larksuite.com
  ```

**3. 准备 VPS**
- 推荐系统环境：
  - Python 3.13
  - PostgreSQL
  - git
  - Poetry
- 拉代码：
  ```bash
  git clone <your-repo-url> mantle-eco-monitor
  cd mantle-eco-monitor
  git checkout main
  ```
- 安装依赖时用这个命令，不要直接 `poetry install`：
  ```bash
  poetry install --no-root
  ```
  这个仓库当前更适合 `--no-root` 模式。

**4. 写生产 `.env`**
最少要配这些：

```env
DATABASE_URL=postgresql+asyncpg://monitor:<password>@127.0.0.1:5432/mantle_monitor

DUNE_API_KEY=
COINGECKO_API_KEY=
DUNE_STABLECOIN_VOLUME_QUERY_ID=0

AI_ENRICHMENT_ENABLED=false
LARK_DELIVERY_ENABLED=true
LARK_BOT_ENABLED=true
BOT_EXTERNAL_ACTIONS_ENABLED=false

LARK_APP_ID=<your_app_id>
LARK_APP_SECRET=<your_app_secret>
LARK_BASE_URL=https://open.larksuite.com
LARK_VERIFICATION_TOKEN=<your_verification_token>
LARK_ENCRYPT_KEY=<your_encrypt_key_or_blank>
LARK_ENVIRONMENT=prod
LARK_ALERT_CHAT_ID_PROD=<alert_chat_id>
LARK_SUMMARY_CHAT_ID_PROD=<summary_chat_id>

LLM_API_BASE=https://openrouter.ai/api/v1
LLM_API_KEY=<your_openrouter_key>
LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free
LLM_APP_NAME=mantle-eco-monitor
LLM_APP_URL=https://<your-domain>
LLM_TIMEOUT_SECONDS=30

SCHEDULER_ENABLED=true
SCHEDULER_PROFILE=prod

HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
```

注意：
- 如果告警和 summary 想发到同一个群，两个 `CHAT_ID` 填同一个即可。
- 如果不用 Dune，保持 `DUNE_API_KEY` 为空也可以，但 `source_health` 里 Dune 会显示失败，这是预期行为。
- `LLM_API_KEY` 不配的话，bot 和 daily summary 相关能力不会正常工作。

**5. 初始化数据库**
- 创建 PostgreSQL 数据库。
- 执行迁移：
  ```bash
  poetry run alembic upgrade head
  ```

**6. 启动前检查**
先确认调度配置能正常读到：

```bash
poetry run python -m src.scheduler list
```

你应该能看到 `prod` profile 下的这些 job，至少包含：
- `daily_summary`
- `source_health`
- `core_defillama`
- `core_growthepie`
- `core_l2beat`
- `core_coingecko`
- `core_dune`
- `eco_aave`
- `eco_protocols`
- `watchlist_refresh`

**7. 启动服务**
最简单启动方式：

```bash
poetry run uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000
```

如果你要长期运行，建议挂到 `systemd`。一个最小 service 示例：

```ini
[Unit]
Description=Mantle Eco Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/srv/mantle-eco-monitor
EnvironmentFile=/srv/mantle-eco-monitor/.env
ExecStart=/usr/local/bin/poetry run uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

然后：

```bash
sudo systemctl daemon-reload
sudo systemctl enable mantle-eco-monitor
sudo systemctl start mantle-eco-monitor
sudo systemctl status mantle-eco-monitor
```

**8. 先做 API 侧 smoke test**
服务起来后，先不要急着测 Lark，先测 API：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sources
curl http://127.0.0.1:8000/api/alerts
curl "http://127.0.0.1:8000/api/metrics/latest?entity=mantle&metric_name=tvl"
```

你要关注：
- `/api/health` 能返回 JSON
- DB 连接正常
- 服务没有 traceback
- 如果是 fresh deploy，`metrics/latest` 可能为空，这是正常的，因为还没跑采集

**9. 先手动跑采集，让 bot 有东西可查**
在生产第一次部署时，不要等 cron，先手动跑一轮关键 job：

```bash
poetry run python -m src.scheduler run source_health
poetry run python -m src.scheduler run core_l2beat
poetry run python -m src.scheduler run core_coingecko
poetry run python -m src.scheduler run core_defillama
poetry run python -m src.scheduler run core_growthepie
poetry run python -m src.scheduler run watchlist_refresh
poetry run python -m src.scheduler run eco_aave
poetry run python -m src.scheduler run eco_protocols
```

如果你启用了 Dune，再补：
```bash
poetry run python -m src.scheduler run core_dune
```

然后再查：

```bash
curl http://127.0.0.1:8000/api/health/sources
curl "http://127.0.0.1:8000/api/metrics/latest?entity=mantle&metric_name=tvl"
curl http://127.0.0.1:8000/api/alerts
```

**10. 再做 Lark 回调验证**
你可以按这个顺序测：

1. 在 Lark 后台保存事件回调 URL。  
预期：challenge/verification 成功。

2. 私聊 bot 发：
```text
mantle tvl latest
```
预期：
- bot 回复一张 card
- 有结论文本
- 有 source url

3. 群里 `@bot` 发：
```text
@bot show mantle tvl 7d
```
预期：
- bot 回复
- 返回趋势描述和 source url

4. 群里不 `@bot` 发普通消息：
```text
mantle tvl latest
```
预期：
- bot 不回复

5. 再测几个只读查询：
```text
@bot latest mantle alerts
@bot source health
@bot watchlist
```

**11. 告警推送验证**
这一项是数据依赖的，不一定 fresh deploy 立刻有 alert。验证方法是：

- 手动跑完核心采集 job 后，查看：
  ```bash
  curl http://127.0.0.1:8000/api/alerts
  ```
- 如果 API 里出现 `alert_events`，并且 `LARK_DELIVERY_ENABLED=true`，对应群里应该能看到 alert card。
- 如果 API 没 alert，但服务正常，这不代表 Lark 推送坏了，只代表当前数据没有触发规则。

**12. Daily summary 验证**
注意这个限制：
- `daily_summary` 汇总的是“上一自然日”
- fresh deploy 当天通常没有“昨天”的数据，所以手动触发可能返回 `no_data`

你可以先看 prod 调度时间，当前在 [config/scheduler.toml](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/scheduler.toml) 里是：
- `daily_summary`: `09:05 Asia/Shanghai`

如果你就是要立刻测 summary，有两个方式：
- 用已有历史数据的数据库
- 等到第二天，数据库里已经有前一天快照后再触发：
  ```bash
  poetry run python -m src.scheduler run daily_summary
  ```

**13. 生产观察清单**
上线后第一天建议盯这些：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sources
curl http://127.0.0.1:8000/api/alerts
```

再配合看：
- 服务日志
- Lark 群里是否有 alert card
- Lark bot 查询是否能稳定返回 source url
- `source_health` 是否只有预期的失败项

**14. 常见问题**
- `401 Invalid verification token`
  - `LARK_VERIFICATION_TOKEN` 和 Lark 后台不一致

- Lark 后台 challenge 失败
  - URL 不通
  - HTTPS 不可用
  - `LARK_BASE_URL` 配错不会影响 challenge，但会影响后续发消息/token 获取

- bot 在群里乱回复
  - 当前代码已经要求群聊必须 `@bot`
  - 如果还出现异常，检查 Lark 事件内容是否真的包含 mentions

- bot 不回复但接口正常
  - `LARK_BOT_ENABLED` 没开
  - `LLM_API_KEY` 没配
  - 数据库里没有可回答的数据，bot 会返回受限说明

- summary 不发
  - `LLM_API_KEY` 没配
  - 前一天没有数据
  - `LARK_SUMMARY_CHAT_ID_PROD` 没配

- alert 不发
  - `LARK_DELIVERY_ENABLED` 没开
  - 对应 job 没触发 alert
  - 群 `chat_id` 配错

**15. 我建议你的实际执行顺序**
1. 配 Lark app
2. 配 VPS `.env`
3. `poetry install --no-root`
4. `poetry run alembic upgrade head`
5. `poetry run python -m src.scheduler list`
6. 启服务
7. 测 `/api/health`
8. 手动跑一轮采集 job
9. 测 metrics / alerts API
10. 测私聊 bot
11. 测群里 `@bot`
12. 测群里不 `@bot`
13. 次日再测 `daily_summary`

如果你要，我下一步可以继续给你两样东西中的一个：
1. 一份可直接贴到 VPS 的 `systemd + nginx/caddy` 部署模板
2. 一份可直接执行的“上线检查清单”shell 脚本
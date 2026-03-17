# VPS Deployment And Lark E2E Guide

This guide covers the full path from server setup to end-to-end validation for:

- backend deployment on a VPS
- scheduler startup
- Lark bot callback setup
- alert delivery
- daily summary delivery
- bot query validation

The current `main` branch includes:

- Lark callback handling
- encrypted callback payload support
- group-message filtering so the bot only responds in group chats when it is explicitly mentioned
- OpenRouter defaults for the LLM client

## 1. Preconditions

Prepare these before touching the VPS:

- a VPS with Python 3.13 and PostgreSQL available
- a public HTTPS domain pointing to the VPS
- a Lark app with bot capability enabled
- the Lark app's:
  - `App ID`
  - `App Secret`
  - `Verification Token`
  - optional `Encrypt Key` if you enable encrypted callbacks
- the target Lark chat ids for:
  - alert delivery
  - summary delivery
- an OpenRouter API key

## 2. Lark Setup

### 2.1 Create Or Update The Lark App

In the Lark developer console:

1. Enable the bot capability.
2. Enable event subscriptions.
3. Subscribe to:
   - `im.message.receive_v1`
4. Set the callback URL to:

```text
https://<your-domain>/api/integrations/lark/events
```

5. Copy these values:
   - `App ID`
   - `App Secret`
   - `Verification Token`
   - `Encrypt Key` if event encryption is enabled

### 2.2 Decide Which Lark OpenAPI Domain You Need

Use one of:

- `https://open.larksuite.com` for Lark global
- `https://open.feishu.cn` for Feishu mainland

This value maps to `LARK_BASE_URL`.

### 2.3 Add The Bot To Delivery And Test Chats

Add the bot to the production group(s) that should receive:

- alerts
- daily summaries

If you want alerts and summaries in the same group, reuse the same `chat_id`.

## 3. VPS Preparation

SSH into the server and install the basic runtime:

```bash
python3 --version
git --version
psql --version
poetry --version
```

If Poetry is missing, install it first.

Clone the repo and switch to `main`:

```bash
git clone <your-repo-url> mantle-eco-monitor
cd mantle-eco-monitor
git checkout main
```

Install dependencies:

```bash
poetry install --no-root
```

## 4. Environment Configuration

Create a production `.env` in the repo root.

Use this as a template:

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

Notes:

- `LLM_API_KEY` is required for bot answers and daily summaries.
- If you enable callback encryption in the Lark console, `LARK_ENCRYPT_KEY` must match exactly.
- If you do not use Dune yet, leave `DUNE_API_KEY` empty. Source health will report Dune as failed, which is expected.

## 5. Database Initialization

Create the production database, then run migrations:

```bash
poetry run alembic upgrade head
```

If this fails, stop and fix DB connectivity before continuing.

## 6. Scheduler And Runtime Sanity Check

Before starting the web service, verify the scheduler config loads:

```bash
poetry run python -m src.scheduler list
```

Expected on `prod`:

- `core_defillama: cron`
- `core_growthepie: cron`
- `core_l2beat: cron`
- `core_dune: cron`
- `core_coingecko: cron`
- `daily_summary: cron`
- `eco_aave: cron`
- `eco_protocols: cron`
- `watchlist_refresh: cron`
- `source_health: cron`

## 7. Start The Service

Manual startup:

```bash
poetry run uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000
```

For long-running production use, prefer `systemd`.

Example service file:

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

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mantle-eco-monitor
sudo systemctl start mantle-eco-monitor
sudo systemctl status mantle-eco-monitor
```

## 8. Base API Smoke Test

Verify the service is reachable before touching Lark:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sources
curl http://127.0.0.1:8000/api/alerts
curl "http://127.0.0.1:8000/api/metrics/latest?entity=mantle&metric_name=tvl"
```

What to look for:

- `/api/health` returns JSON
- DB status is not broken
- no traceback in logs
- empty metric or alert lists are acceptable on a fresh deploy

## 9. First Data Backfill For Testing

Do not wait for cron on the first deployment. Run the main jobs manually:

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

If Dune is configured, also run:

```bash
poetry run python -m src.scheduler run core_dune
```

Then re-check:

```bash
curl http://127.0.0.1:8000/api/health/sources
curl "http://127.0.0.1:8000/api/metrics/latest?entity=mantle&metric_name=tvl"
curl http://127.0.0.1:8000/api/alerts
```

## 10. Lark Callback Validation

### 10.1 Callback Registration

Save the callback URL in the Lark developer console and confirm:

- challenge verification succeeds
- the callback remains active

If challenge verification fails:

- confirm the URL is public and HTTPS
- confirm `LARK_VERIFICATION_TOKEN` matches
- if encryption is enabled, confirm `LARK_ENCRYPT_KEY` matches

### 10.2 Private Chat Test

Send the bot a direct message:

```text
mantle tvl latest
```

Expected:

- one reply card
- a short answer
- at least one source URL

### 10.3 Group Mention Test

In a group where the bot is present:

```text
@bot show mantle tvl 7d
```

Expected:

- the bot replies
- the answer includes a concise result
- source URLs are included

### 10.4 Group Non-Mention Test

In the same group:

```text
mantle tvl latest
```

Expected:

- no bot reply

This is an important regression check for the group-filtering logic.

### 10.5 Extra Read-Only Query Tests

Try these:

```text
@bot latest mantle alerts
@bot source health
@bot watchlist
@bot daily summary
```

Expected:

- the bot answers when internal data exists
- if internal data does not exist, it returns a constrained explanation rather than inventing facts

## 11. Alert Delivery Validation

Alert delivery depends on real rule triggers. Validation steps:

1. Check whether alerts exist:

```bash
curl http://127.0.0.1:8000/api/alerts
```

2. If alert rows exist and `LARK_DELIVERY_ENABLED=true`, confirm the target chat receives alert cards.

3. If the API has no alerts, that is not automatically a deployment bug. It may just mean no thresholds fired yet.

## 12. Daily Summary Validation

Important behavior:

- daily summary uses the previous natural day
- a same-day fresh deploy may not have enough prior-day data

Current production scheduler timing from [config/scheduler.toml](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/scheduler.toml):

- `daily_summary` runs at `09:05 Asia/Shanghai`

To test manually:

```bash
poetry run python -m src.scheduler run daily_summary
```

Expected outcomes:

- if prior-day data exists and `LLM_API_KEY` is configured, a summary card is sent
- if not enough data exists, the job may skip with a `no_data` style result

## 13. Optional Local Dev-Live Smoke Check

For a local or staging-style validation path, the repo already includes:

```bash
./scripts/dev_live_check.sh up
./scripts/dev_live_check.sh check
./scripts/dev_live_check.sh full
./scripts/dev_live_check.sh down
```

This is useful for local QA, but it is not a substitute for PostgreSQL-backed production validation.

## 14. Production Observation Checklist

After the first deployment, verify:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sources
curl http://127.0.0.1:8000/api/alerts
```

Also inspect:

- service logs
- Lark alert group
- Lark summary group
- private and group bot interactions

## 15. Common Failure Modes

### `401 Invalid verification token`

Cause:

- `LARK_VERIFICATION_TOKEN` does not match the Lark console

### Callback verification fails when encryption is enabled

Cause:

- `LARK_ENCRYPT_KEY` does not match
- callback URL is correct, but encrypted payload cannot be decrypted

### Bot does not reply in direct messages

Check:

- `LARK_BOT_ENABLED=true`
- event subscription includes `im.message.receive_v1`
- `LLM_API_KEY` is set

### Bot replies in groups only when explicitly mentioned

Expected behavior:

- direct messages are processed
- group messages without `@bot` are ignored

### Alert cards are not being delivered

Check:

- `LARK_DELIVERY_ENABLED=true`
- `LARK_ALERT_CHAT_ID_PROD` is correct
- alert rows actually exist in `/api/alerts`

### Daily summary is not being delivered

Check:

- `LLM_API_KEY` is set
- `LARK_SUMMARY_CHAT_ID_PROD` is correct
- previous-day data exists

## 16. Recommended Execution Order

Follow this exact order:

1. Configure the Lark app
2. Prepare the VPS
3. Create production `.env`
4. Run `poetry install --no-root`
5. Run `poetry run alembic upgrade head`
6. Run `poetry run python -m src.scheduler list`
7. Start the service
8. Smoke-test the API
9. Run the key scheduler jobs manually
10. Validate metrics and alerts through HTTP
11. Validate Lark callback registration
12. Validate private-message bot interaction
13. Validate group `@bot` interaction
14. Validate group non-mention silence
15. Validate alert delivery when alerts exist
16. Validate daily summary when prior-day data exists

# Mantle Onchain Metrics Alert Rules Specification

> Version: 1.0 | Date: 2026-03-17
> Based on: Mantle Social Onchain Metrics AI Automation (PRD) + prd-simple.md + current codebase implementation

---

## 1. Alert Philosophy

The alert engine follows a **deterministic、可审计、低噪音**的设计原则：

- 基于明确阈值的规则触发，不依赖 AI 做第一层判断
- 所有触发条件可解释、可追溯
- 通过冷却期和抑制机制避免告警轰炸
- 历史数据比较基于一致的时间窗口

**核心原则：** 宁可漏报，不可误报。只有真正值得社交团队关注的信号才应该触发告警。

---

## 2. 监控范围

### 2.1 Core Monitor（链级别指标）

| 指标名 | 内部标识 | 单位 | 数据源 |
|--------|---------|------|--------|
| TVL (Total Value Locked) | `tvl` | USD | DefiLlama |
| Total Value Secured | `total_value_secured` | USD | L2BEAT |
| Daily Active Users (7D Rolling Avg) | `daily_active_users` | 数量 | Dune / growthepie |
| Active Addresses | `active_addresses` | 数量 | Dune / growthepie |
| Stablecoin Supply | `stablecoin_supply` | USD | DefiLlama |
| Stablecoin Market Cap | `stablecoin_mcap` | USD | DefiLlama |
| Chain Transactions | `chain_transactions` | 数量 | Dune / growthepie |
| Stablecoin Transfer Volume | `stablecoin_transfer_volume` | USD | Dune |
| DEX Volume | `dex_volume` | USD | DefiLlama / Dune |
| $MNT Volume | `mnt_volume` | USD | CoinGecko |
| $MNT Market Cap | `mnt_market_cap` | USD | CoinGecko |

### 2.2 Ecosystem Monitor（协议级别指标）

#### Aave（特殊处理）

| 指标名 | 内部标识 | 说明 |
|--------|---------|------|
| Supply / Deposits | `supply` | Aave 在 Mantle 上的存款总额 |
| Borrowed | `borrowed` | Aave 在 Mantle 上的借款总额 |
| Utilization | `utilization` | borrowed / supply 比率 |

#### DEX 协议（Merchant Moe, Agni Finance, Fluxion 等）

| 指标名 | 内部标识 |
|--------|---------|
| TVL | `tvl` |
| Volume | `volume` |

#### Non-DEX 协议（Ondo, Treehouse, CIAN 等）

| 指标名 | 内部标识 |
|--------|---------|
| TVL | `tvl` |

### 2.3 显式排除

以下内容 **绝不** 出现在任何告警或 AI 生成的文案中：

- $MNT 代币价格
- 价格变动百分比
- 价格比较
- 价格预测

---

## 3. 告警触发场景

系统共定义 **5 类告警触发场景**，每类场景有独立的检测逻辑。

### 3.1 百分比阈值告警 (Threshold Alert)

**触发条件：** 某个指标在指定时间窗口内的变动百分比达到或超过对应阈值。

**计算方式：**

```
change_pct = (current_value - anchor_value) / anchor_value
```

**时间窗口（主告警窗口）：**

| 窗口 | 标识 | 说明 | 用途 |
|------|------|------|------|
| 7 天 | `7d` | 当前值 vs 7 天前快照 | **主告警窗口**，日常监控 |
| 月初至今 | `mtd` | 当前值 vs 本月第 1 天快照 | **主告警窗口**，月度趋势 |

> 1M / 3M / 6M / YTD / 1Y / All Time 窗口主要用于叙事背景和月度/战略回顾，不作为主要告警触发窗口。

**阈值矩阵（通用指标）：**

| 严重级别 | 标识 | 变动幅度 | 是否进入内部 Feed | 是否推送 Lark |
|----------|------|---------|-------------------|--------------|
| Minor | `minor` | ≥ 10% | 仅存储，不展示 | 否 |
| Moderate | `moderate` | ≥ 15% | 进入内部告警 Feed | Phase 2 |
| High | `high` | ≥ 20% | 高优先级内部告警 | Phase 2 |
| Critical | `critical` | ≥ 30% | 最高优先级 | Phase 2 |

**Utilization 特殊阈值（Aave）：**

| 严重级别 | 变动幅度 |
|----------|---------|
| Minor | ≥ 5% |
| Moderate | ≥ 10% |
| High | ≥ 15% |
| Critical | ≥ 20% |

> Utilization 使用更低的阈值是因为资金利用率的微小变化往往意味着更大的市场意义。

**trigger_reason 格式：** `threshold_{pct}pct_{window}`

**示例：** TVL 在 7 天内从 $500M 涨到 $600M（+20%），触发 `high` 级别告警，`trigger_reason = "threshold_20pct_7d"`

---

### 3.2 历史新高告警 (ATH Alert)

**触发条件：** 某个指标的当前值超过历史上记录过的所有快照中的最大值。

**检测逻辑：**

```
if current_value > max(all_historical_snapshots_for_this_metric):
    → trigger ATH alert
```

**固定属性：**

| 字段 | 值 |
|------|-----|
| severity | `critical` |
| time_window | `all_time` |
| trigger_reason | `new_ath` |
| is_ath | `true` |
| change_pct | `null`（ATH 不依赖变动百分比） |

**优先级覆盖：** ATH 告警始终为 `critical` 级别，无论变动幅度大小。即使变动只有 1%，只要突破历史最高，就触发告警。

**示例：** TVL 从历史最高 $750M 升至 $755M，触发 ATH 告警。

---

### 3.3 里程碑突破告警 (Milestone Alert)

**触发条件：** 某个指标的当前值首次跨越预定义的里程碑数值（即上一个快照值 < 里程碑值 ≤ 当前值）。

**检测逻辑：**

```
for each milestone_value in configured_milestones[metric_name]:
    if previous_value < milestone_value <= current_value:
        → trigger milestone alert
```

**已配置里程碑：**

| 指标 | 里程碑值 |
|------|---------|
| TVL | $500M, $1B, $1.5B, $2B, $5B |
| Daily Active Users | 50K, 100K, 200K, 500K, 1M |
| Stablecoin Supply | $100M, $500M, $1B |
| DEX Volume | $50M, $100M, $500M, $1B |
| Chain Transactions | 100K, 500K, 1M, 5M |
| Borrowed (Aave) | $50M, $100M, $250M, $500M |
| Supply (Aave) | $100M, $250M, $500M, $1B |
| MNT Market Cap | $1B, $2B, $5B |

**固定属性：**

| 字段 | 值 |
|------|-----|
| severity | `high` |
| time_window | `milestone` |
| trigger_reason | `milestone_{formatted_value}`（如 `milestone_$500M`） |
| is_milestone | `true` |
| milestone_label | 可读的里程碑值（如 `$500M`） |

**示例：** TVL 从 $490M 涨到 $510M，跨越 $500M 里程碑，触发告警。

---

### 3.4 显著下跌告警 (Decline Alert)

**触发条件：** 某个指标在 7D 或 MTD 窗口内下跌超过 20%。

**检测逻辑：**

```
change_pct = (current_value - anchor_value) / anchor_value
if change_pct <= -0.20:
    → trigger decline alert
```

**时间窗口：** 7D 和 MTD（与 Threshold Alert 共享同样的窗口）

**固定属性：**

| 字段 | 值 |
|------|-----|
| severity | `critical` |
| trigger_reason | `decline_{pct}pct_{window}`（如 `decline_25pct_7d`） |

**重要说明：** 下跌告警的目的是让社交团队 **知晓** 情况，而非一定要发帖。社交团队在收到下跌告警后自行判断是否需要公开沟通。

**示例：** Daily Active Users 在 7 天内从 100K 跌至 75K（-25%），触发 `critical` 级别下跌告警。

---

### 3.5 多信号联合告警 (Multi-Signal Alert)

**触发条件：** 同一实体在单次评估周期内有 **2 个或以上** 指标同时命中 `high` 或 `critical` 级别告警。

**检测逻辑：**

```
group alerts by entity
for each entity:
    high_or_critical_alerts = [a for a in alerts if a.severity in ("high", "critical")]
    if len(high_or_critical_alerts) >= 2:
        → trigger multi-signal alert
```

**固定属性：**

| 字段 | 值 |
|------|-----|
| severity | `critical` |
| metric_name | `multi_signal` |
| time_window | `combined` |
| trigger_reason | `multi_signal:{metric1}, {metric2}, ...`（如 `multi_signal:dex_volume, tvl`） |

**抑制效果：** 当 multi-signal 告警存在时，该实体下 severity 低于 `high` 的单独告警会被抑制，避免重复通知。

**示例：** Mantle 的 TVL（+25%, 7D）和 DEX Volume（+35%, 7D）同时达到 `high` / `critical`，触发 multi-signal 联合告警。

---

## 4. 数据覆盖率要求

为防止因数据缺失导致的误报，系统在计算变动百分比前会检查数据覆盖率：

| 时间窗口 | 最低要求 |
|----------|---------|
| 7D | 8 天范围内至少有 6 个不同日期的快照 |
| MTD | 当月已过天数的 ≥ 80% 有快照 |

覆盖率不足时，`get_comparison_snapshot()` 返回 `None`，该窗口不生成阈值告警或下跌告警。快照照常存储，不影响后续评估。

---

## 5. 冷却期与抑制规则

### 5.1 冷却期 (Cooldown)

每次告警触发后进入冷却期，**相同 entity + metric_name + trigger_reason** 的组合在冷却期内不会重复触发。

| 严重级别 | 冷却时长 |
|----------|---------|
| Minor | 72 小时 |
| Moderate | 48 小时 |
| High | 24 小时 |
| Critical | 12 小时 |

> 越严重的告警冷却越短，因为需要更快地检测到后续变化。

### 5.2 Multi-Signal 抑制

当某个 entity 存在 multi-signal 联合告警时：

- 该 entity 下 severity 为 `minor` 或 `moderate` 的独立告警被抑制
- `high` 和 `critical` 级别的独立告警保留
- multi-signal 告警本身保留

### 5.3 Token-Level 抑制

以下指标在 `mantle:*` entity 下不生成告警（它们是 token 级别的分拆数据，避免与汇总数据重复告警）：

- `stablecoin_transfer_volume`
- `stablecoin_transfer_tx_count`

---

## 6. 告警内容字段

每条告警记录（`AlertEvent`）包含以下字段：

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `scope` | string | 监控域 | `core` / `ecosystem` / `stablecoin` |
| `entity` | string | 被监控实体 | `mantle` / `aave` / `merchant-moe` |
| `metric_name` | string | 指标名称 | `tvl` / `borrowed` / `multi_signal` |
| `current_value` | decimal | 当前值 | `755000000` |
| `previous_value` | decimal? | 对比基准值 | `450000000` |
| `formatted_value` | string? | 格式化后的可读值 | `$755M+` |
| `time_window` | string | 触发窗口 | `7d` / `mtd` / `all_time` / `milestone` / `combined` |
| `change_pct` | decimal? | 变动百分比 | `0.678` (即 67.8%) |
| `severity` | string | 严重级别 | `minor` / `moderate` / `high` / `critical` |
| `trigger_reason` | string | 触发原因标识 | `threshold_20pct_7d` / `new_ath` / `decline_25pct_mtd` |
| `source_platform` | string? | 数据来源平台 | `defillama` / `dune` / `l2beat` |
| `source_ref` | string? | 数据来源链接 | `https://defillama.com/chain/Mantle` |
| `detected_at` | datetime | 检测时间 (UTC) | `2026-03-17T01:42:00+00:00` |
| `is_ath` | boolean | 是否为 ATH | `true` / `false` |
| `is_milestone` | boolean | 是否为里程碑 | `true` / `false` |
| `milestone_label` | string? | 里程碑标签 | `$500M` / `$1B` |
| `cooldown_until` | datetime? | 冷却期截止 (UTC) | `2026-03-17T13:42:00+00:00` |
| `reviewed` | boolean | 是否已审阅 | `false` |
| `review_note` | string? | 审阅备注 | `已发推` |
| `ai_eligible` | boolean | 是否适合 AI 生成文案 | `true` / `false` |

---

## 7. 告警卡片格式（Lark Card）

### 7.1 卡片颜色编码

| 场景 | Header 颜色 | Header 前缀 |
|------|------------|------------|
| 指标上涨 (threshold/growth) | 🟢 绿色 (`green`) | 🟢 |
| 指标下跌 (decline) | 🔴 红色 (`red`) | 🔴 |
| ATH 或 Milestone | 💎 浅蓝色 (`wathet`) | 🟢 |

### 7.2 标准告警卡片模板

```
┌──────────────────────────────────────────────┐
│  🟢 MANTLE METRICS ALERT          [green]    │
├──────────────────────────────────────────────┤
│                                              │
│  📊 Metric: TVL (Total Value Locked)         │
│                                              │
│  📈 Movement: +66.00% (7D)                   │
│                                              │
│  💰 Current Value: $~755.0M                  │
│                                              │
│  🏆 Status: NEW ALL-TIME HIGH                │
│                                              │
│  📡 Source: DefiLlama (https://defillama...) │
│                                              │
│  ⏰ Detected: March 4, 2026 - 09:42 SGT     │
│                                              │
│  ✍️ Suggested Draft Copy:                    │
│  Placeholder - draft copy not generated yet. │
│                                              │
│  ⚡ Action Required:                         │
│  - Social: Review alert context and refine   │
│    for posting                               │
│  - Design: Prepare metric card or            │
│    lightweight visual                        │
│  - Target post window: Within 6 hours of     │
│    alert                                     │
│                                              │
└──────────────────────────────────────────────┘
```

### 7.3 卡片字段详解

| 字段 | 图标 | 来源 | 格式 |
|------|------|------|------|
| **Header Title** | 🟢/🔴 | severity + direction | `{prefix} MANTLE METRICS ALERT` |
| **Metric** | 📊 | `metric_name` → 可读标签 | `TVL (Total Value Locked)` |
| **Movement** | 📈/📉 | `change_pct` + `time_window` | `+66.00% (7D)` / `-25.30% (MTD)` |
| **Current Value** | 💰 | `formatted_value` 或 `current_value` 格式化 | `$~755.0M` / `~150.0K` |
| **Status** | 🏆 | 衍生自告警类型 | 见下方 Status 映射表 |
| **Source** | 📡 | `source_platform` + `source_ref` | `DefiLlama (https://...)` |
| **Detected** | ⏰ | `detected_at` 转换为 SGT (UTC+8) | `March 4, 2026 - 09:42 SGT` |
| **Draft Copy** | ✍️ | AI 生成（Phase 2+） | Phase 1 显示 placeholder |
| **Action Required** | ⚡ | 固定模板 | 见下方 |

### 7.4 Status 映射逻辑

| 条件 | Status 文案 |
|------|------------|
| `is_ath = true` 或 `trigger_reason = "new_ath"` | `NEW ALL-TIME HIGH` |
| `is_milestone = true` 且有 `milestone_label` | `MILESTONE REACHED: {milestone_label}` |
| `is_milestone = true` 但无 label | `MILESTONE REACHED` |
| 下跌方向 (change_pct < 0) | `SHARP DECLINE` |
| 上涨方向 (change_pct > 0) | `SIGNIFICANT UPWARD MOVE` |
| 其他 | `trigger_reason` 大写化 |

### 7.5 数值格式化规则

| 数值范围 | 格式 | 示例 |
|----------|------|------|
| ≥ 1T | `$~{x.x}T` | `$~1.2T` |
| ≥ 1B | `$~{x.x}B` | `$~1.5B` |
| ≥ 1M | `$~{x.x}M` | `$~755.0M` |
| ≥ 1K | `$~{x.x}K` | `$~150.0K` |
| < 1K | 原始值 | `$892` |

> 货币类指标（tvl, dex_volume, stablecoin_supply 等）加 `$` 前缀；
> 非货币类指标（daily_active_users, chain_transactions 等）不加前缀。

### 7.6 Movement 显示规则

- 正数变动：`+{pct}% ({window})`，图标 📈
- 负数变动：`{pct}% ({window})`（负号自带），图标 📉
- 百分比保留 2 位小数
- `change_pct` 为 null 时显示 `N/A ({window})`

### 7.7 Action Required 固定模板

```
⚡ Action Required:
- Social: Review alert context and refine for posting
- Design: Prepare metric card or lightweight visual
- Target post window: Within 6 hours of alert
```

---

## 8. 各场景告警卡片示例

### 8.1 ATH 告警（历史新高）

```
┌──────────────────────────────────────────────┐
│  🟢 MANTLE METRICS ALERT          [wathet]   │
├──────────────────────────────────────────────┤
│  📊 Metric: TVL (Total Value Locked)         │
│  📈 Movement: N/A (ALL_TIME)                 │
│  💰 Current Value: $~755.0M                  │
│  🏆 Status: NEW ALL-TIME HIGH                │
│  📡 Source: DefiLlama                        │
│  ⏰ Detected: March 4, 2026 - 09:42 SGT     │
│  ✍️ Suggested Draft Copy: [AI placeholder]   │
│  ⚡ Action Required: ...                     │
└──────────────────────────────────────────────┘
```

### 8.2 里程碑告警

```
┌──────────────────────────────────────────────┐
│  🟢 MANTLE METRICS ALERT          [wathet]   │
├──────────────────────────────────────────────┤
│  📊 Metric: DEX Volume                      │
│  📈 Movement: N/A (MILESTONE)                │
│  💰 Current Value: $~105.3M                  │
│  🏆 Status: MILESTONE REACHED: $100M         │
│  📡 Source: DefiLlama                        │
│  ⏰ Detected: March 10, 2026 - 14:20 SGT    │
│  ✍️ Suggested Draft Copy: [AI placeholder]   │
│  ⚡ Action Required: ...                     │
└──────────────────────────────────────────────┘
```

### 8.3 增长告警（阈值触发）

```
┌──────────────────────────────────────────────┐
│  🟢 MANTLE METRICS ALERT          [green]    │
├──────────────────────────────────────────────┤
│  📊 Metric: Stablecoin Supply                │
│  📈 Movement: +22.50% (7D)                   │
│  💰 Current Value: $~320.0M                  │
│  🏆 Status: SIGNIFICANT UPWARD MOVE          │
│  📡 Source: DefiLlama                        │
│  ⏰ Detected: March 15, 2026 - 08:00 SGT    │
│  ✍️ Suggested Draft Copy: [AI placeholder]   │
│  ⚡ Action Required: ...                     │
└──────────────────────────────────────────────┘
```

### 8.4 下跌告警

```
┌──────────────────────────────────────────────┐
│  🔴 MANTLE METRICS ALERT          [red]      │
├──────────────────────────────────────────────┤
│  📊 Metric: Daily Active Users (7D Rolling   │
│     Average)                                 │
│  📉 Movement: -25.30% (7D)                   │
│  💰 Current Value: ~74.7K                    │
│  🏆 Status: SHARP DECLINE                    │
│  📡 Source: Dune                             │
│  ⏰ Detected: March 12, 2026 - 11:15 SGT    │
│  ✍️ Suggested Draft Copy: [AI placeholder]   │
│  ⚡ Action Required: ...                     │
└──────────────────────────────────────────────┘
```

### 8.5 Multi-Signal 联合告警

```
┌──────────────────────────────────────────────┐
│  🟢 MANTLE METRICS ALERT          [green]    │
├──────────────────────────────────────────────┤
│  📊 Metric: Multi Signal                    │
│  📈 Movement: N/A (COMBINED)                 │
│  💰 Current Value: (主指标值)                 │
│  🏆 Status: MULTI SIGNAL:DEX_VOLUME, TVL     │
│  📡 Source: Unknown                          │
│  ⏰ Detected: March 16, 2026 - 16:30 SGT    │
│  ✍️ Suggested Draft Copy: [AI placeholder]   │
│  ⚡ Action Required: ...                     │
└──────────────────────────────────────────────┘
```

---

## 9. 告警完整生命周期

```
                    ┌─────────────────┐
                    │  Scheduler 触发  │
                    │ 数据采集任务      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Ingestion 层    │
                    │ 拉取各平台数据    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Snapshot 存储   │
                    │ 写入 metric_     │
                    │ snapshots 表     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Rule Engine     │
                    │  evaluate()      │
                    ├──────────────────┤
                    │ 1. Threshold     │ ← 7D / MTD 窗口变动百分比
                    │ 2. ATH           │ ← 与历史最大值比较
                    │ 3. Milestone     │ ← 是否跨越里程碑
                    │ 4. Decline       │ ← 7D / MTD 下跌 > 20%
                    │ 5. Multi-Signal  │ ← 合并同 entity 高级告警
                    │ 6. Cooldown      │ ← 过滤冷却期内的重复
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  写入 alert_     │
                    │  events 表       │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
     │ Internal Feed │ │ Lark     │ │ AI Enrich   │
     │ (Phase 1)     │ │ (Phase 2)│ │ (Phase 2+)  │
     │ /api/alerts   │ │ Webhook  │ │ Claude API  │
     └───────────────┘ └──────────┘ └─────────────┘
```

---

## 10. 告警触发场景完整对照表

| # | 场景 | 触发条件 | Severity | trigger_reason | 时间窗口 | 特殊标记 |
|---|------|---------|----------|----------------|---------|---------|
| 1 | 小幅增长 | 指标 7D/MTD 变动 ≥ 10% | `minor` | `threshold_{pct}pct_{window}` | 7d / mtd | - |
| 2 | 中等增长 | 指标 7D/MTD 变动 ≥ 15% | `moderate` | `threshold_{pct}pct_{window}` | 7d / mtd | - |
| 3 | 显著增长 | 指标 7D/MTD 变动 ≥ 20% | `high` | `threshold_{pct}pct_{window}` | 7d / mtd | - |
| 4 | 爆发增长 | 指标 7D/MTD 变动 ≥ 30% | `critical` | `threshold_{pct}pct_{window}` | 7d / mtd | - |
| 5 | 历史新高 | 当前值 > 所有历史最大值 | `critical` | `new_ath` | all_time | `is_ath=true` |
| 6 | 里程碑突破 | 跨越预定义里程碑数值 | `high` | `milestone_{label}` | milestone | `is_milestone=true` |
| 7 | 显著下跌 | 指标 7D/MTD 下跌 ≥ 20% | `critical` | `decline_{pct}pct_{window}` | 7d / mtd | - |
| 8 | 多信号联动 | 同实体 ≥ 2 个 high/critical | `critical` | `multi_signal:{metrics}` | combined | - |

---

## 11. Lark 频道路由

| 频道类型 | 用途 | 环境 |
|----------|------|------|
| Alert Chat (Dev) | 开发测试告警 | `lark_environment = "dev"` |
| Alert Chat (Prod) | 正式告警推送 | `lark_environment = "prod"` |
| Summary Chat (Dev) | 开发环境每日摘要 | `lark_environment = "dev"` |
| Summary Chat (Prod) | 正式每日摘要 | `lark_environment = "prod"` |

---

## 12. Phase 2+ AI 集成扩展

当 AI 集成上线后，告警卡片中的 "Suggested Draft Copy" 将由 Claude AI 实时生成。

**AI 生成内容包括：**

- `reason`: 为什么这个信号值得关注
- `signal_strength`: 信号强度评估
- `draft_copy`: 建议的社交媒体文案
- `visual_suggestion`: 建议的配图方向
- `combine_recommendation`: 是否建议与其他信号合并发布

**AI 约束：**

- 不得提及 $MNT 价格
- 遵循 Mantle 品牌语调
- 输出为结构化 JSON
- 温度参数 0.7（创意与一致性平衡）
- 最大 token 数 800

---

## Appendix A: Metric Label 映射表

| 内部标识 | 展示名称 |
|---------|---------|
| `tvl` | TVL (Total Value Locked) |
| `daily_active_users` | Daily Active Users (7D Rolling Average) |
| `active_addresses` | Active Addresses |
| `chain_transactions` | Chain Transactions |
| `dex_volume` | DEX Volume |
| `stablecoin_supply` | Stablecoin Supply |
| `stablecoin_mcap` | Stablecoin Market Cap |
| `stablecoin_transfer_volume` | Stablecoin Transfer Volume |
| `stablecoin_transfer_tx_count` | Stablecoin Transfer Transaction Count |
| `mnt_market_cap` | MNT Market Cap |
| `mnt_volume` | MNT Volume |
| `tvs` | TVS (Total Value Secured) |
| `supply` | Supply |
| `borrowed` | Borrowed |
| `utilization` | Utilization |
| `volume` | Volume |
| `users` | Users |

## Appendix B: Source Label 映射表

| 内部标识 | 展示名称 |
|---------|---------|
| `defillama` | DefiLlama |
| `l2beat` | L2BEAT |
| `growthepie` | growthepie |
| `coingecko` | CoinGecko |
| `dune` | Dune |

# Mantle Onchain Metrics Monitor and Alerting System

## 1. Overview

This document defines the approved design for an internal monitoring and alerting system for Mantle's onchain and ecosystem metrics.

The system is intended for internal BD, Social, and Design teams. Its primary purpose is to replace manual dashboard checking with a structured, automated monitoring pipeline that:

- collects Mantle chain-level metrics on a schedule
- monitors selected Mantle ecosystem protocols
- detects meaningful movements using deterministic rules
- stores alerts in an internal database-backed alert feed during Phase 1
- adds AI-generated explanations and draft copy in later phases
- integrates with Lark only after the monitoring and alert logic is stable

The design follows a hybrid model:

- deterministic rules decide whether an alert should exist
- AI improves interpretation, copy generation, and multi-signal packaging

This is intentionally more stable and auditable than an AI-first alerting design.

## 2. Confirmed Design Decisions

- The project uses the Hybrid approach, not an AI-first approach.
- Rule-based detection is the source of truth for alert generation.
- AI is used for explanation, signal packaging, draft copy, and visual suggestions.
- Phase 1 does not integrate with Lark.
- Phase 1 focuses on complete data coverage, snapshot storage, threshold evaluation, and an internal alert feed.
- The internal alert feed is backed by a simple database and exposed through the backend.
- Aave is treated as a special ecosystem protocol with its own metric logic.
- The ecosystem sub-dashboard uses a hybrid watchlist:
  - Aave is permanently pinned.
  - The remaining slots are filled dynamically from Mantle ecosystem protocols on DefiLlama.
- For non-Aave ecosystem protocols:
  - DEX protocols are monitored mainly through TVL and volume.
  - Non-DEX protocols are monitored mainly through TVL.
- Price-related monitoring is explicitly excluded.

## 3. Product Goals

The system should:

- automatically collect key Mantle metrics from multiple data sources
- maintain a historical snapshot store for change calculations
- evaluate changes across fixed time windows
- identify ATHs, milestone crossings, strong growth, and strong declines
- provide an internal alert feed that can be reviewed by stakeholders
- support social-content workflows without requiring manual dashboard checks

In later phases, the system should also:

- generate AI-supported alert explanations
- generate AI draft social copy
- suggest when multiple signals should be combined into a single narrative
- deliver structured alert cards to Lark

## 4. High-Level System Architecture

The system is organized into six layers:

1. Scheduler
   - triggers metric collection jobs on fixed cadences

2. Ingestion Layer
   - pulls data from APIs or approved fallbacks
   - normalizes source responses into internal metric records

3. Snapshot Storage Layer
   - stores timestamped metric snapshots
   - supports historical comparisons across alert windows

4. Rule Evaluation Layer
   - calculates changes
   - detects thresholds, ATHs, milestone crossings, and declines
   - generates deterministic alert candidates

5. AI Enrichment Layer
   - optional in Phase 1
   - generates reason strings, signal strength, draft copy, visual suggestions, and combine recommendations

6. Delivery Layer
   - Phase 1: internal alert feed backed by the backend database
   - Phase 2: Lark delivery

## 5. Monitoring Scope

### 5.1 Core Monitor

The core Mantle monitor includes the following chain-level or Mantle-wide metrics:

1. TVL
2. Total Value Secured
3. Daily Active Users
4. Active Addresses
5. Stablecoin Supply
6. Stablecoin Market Cap
7. Mantle Chain Transactions
8. Stablecoin Transfer Volume
9. DEX Volume
10. $MNT Volume
11. $MNT Market Cap

### 5.2 Explicit Exclusions

The following are excluded from monitoring, alerting, and AI copy:

- $MNT token price
- price change percentages
- price comparisons
- price predictions

## 6. Data Sources

The PRD names six source platforms:

- Dune Analytics
- Artemis
- DefiLlama
- Growthepie
- Nansen
- L2Beat

Source strategy:

- DefiLlama is the preferred primary source for TVL and many DeFi metrics.
- Other platforms are used for cross-checking or metrics that DefiLlama does not provide directly.
- API-based access is preferred.
- Scraping is fallback-only and should be used only where acceptable and reliable.

## 7. Ecosystem Sub-Dashboard

### 7.1 Purpose

The ecosystem sub-dashboard exists because chain-level metrics alone do not explain where usage, liquidity, and narrative momentum are coming from.

It is intended to answer questions such as:

- which ecosystem protocols are driving Mantle growth
- whether growth is broad-based or concentrated
- whether a single protocol deserves a protocol-specific alert or social angle

### 7.2 Watchlist Strategy

The ecosystem watchlist uses a hybrid model:

- Aave is always included.
- Remaining slots are filled dynamically from current DefiLlama Mantle ecosystem protocols.
- Candidate protocols are filtered by relevance and narrative value.

The watchlist should prioritize:

- Lending
- DEX
- RWA
- Yield / Index products
- Mantle-native or ecosystem-representative protocols

The watchlist should de-prioritize or exclude:

- CEX entities
- pure bridge entries with weak BD/Social storytelling value
- low-signal protocols with unreliable or noisy data

### 7.3 Current Candidate Pool

Based on currently accessible DefiLlama Mantle data, the candidate pool can include protocols such as:

- Aave V3
- CIAN Yield Layer
- Mantle Index Four Fund
- Merchant Moe Liquidity Book
- Treehouse Protocol
- Ondo Yield Assets
- Agni Finance
- Compound V3
- INIT Capital
- Lendle Pooled Markets
- Fluxion Network
- Merchant Moe DEX

This list is not a hard-coded final list except for Aave. The dynamic portion of the watchlist may change as the Mantle ecosystem changes.

## 8. Aave Special Handling

Aave should not be treated like a generic ecosystem protocol.

For Aave, TVL alone is insufficient. The monitor should track:

- Supply / Deposits
  - approximated by Mantle Aave TVL when using DefiLlama's protocol data

- Borrowed
  - available from DefiLlama's Mantle-borrowed fields

- Utilization
  - derived from borrowed divided by supply

- 7D and MTD change
  - for both supply and borrowed

- ATH and milestone events
  - for supply
  - for borrowed
  - optionally for utilization thresholds

Recommended Aave-specific alert conditions:

- significant supply growth in 7D or MTD
- significant borrowed growth in 7D or MTD
- borrowed reaches a new ATH
- supply reaches a new ATH
- supply and borrowed hit major milestones at the same time
- utilization crosses a meaningful threshold

The reason for this exception is simple: Aave gives a better signal of capital usage depth, not just parked liquidity.

## 9. Rules for Other Ecosystem Protocols

### 9.1 DEX Protocols

For DEX protocols, the default monitoring set is:

- TVL
- volume
- 7D change
- MTD change
- ATH
- milestone crossings

Examples include:

- Merchant Moe
- Agni Finance
- Fluxion Network

### 9.2 Non-DEX Protocols

For non-DEX ecosystem protocols, the default monitoring set is:

- TVL
- 7D change
- MTD change
- ATH
- milestone crossings

Examples include:

- Ondo Yield Assets
- Treehouse Protocol
- Mantle Index Four Fund
- CIAN Yield Layer

### 9.3 Secondary Lending Protocols

Protocols such as Compound, INIT, and Lendle can enter the watchlist in Phase 1, but they do not need Aave-level specialization yet.

Phase 1 recommendation:

- include them in the ecosystem watchlist
- monitor TVL first
- defer deeper borrow/supply decomposition unless they become strategically important

## 10. Alert Design

### 10.1 Alert Philosophy

The alert engine should be deterministic, auditable, and quiet enough to be trusted.

The system should prefer:

- clear threshold-based logic
- explainable triggers
- suppression of redundant signals
- consistent historical comparisons

It should avoid:

- overly subjective alert generation
- AI-only gating
- noisy alerts for ordinary daily variance

### 10.2 Threshold Levels

- Around 10%
  - minor signal
  - store internally only

- Around 15%
  - moderate signal
  - include in internal alert feed

- Around 20%
  - strong signal
  - high-priority internal alert

- Around 30% or more
  - major signal
  - highest internal priority

- New ATH
  - always priority override

### 10.3 Time Windows

The system should evaluate changes across:

- 7D
- MTD
- 1M
- 3M
- 6M
- YTD
- 1Y
- All Time

Priority guidance:

- 7D and MTD are the primary alert windows
- All Time is primarily for ATH detection
- longer windows are mainly for narrative context and monthly or strategic reviews

### 10.4 Special Alert Conditions

The following should trigger an alert even when normal percentage movement is not the main reason:

- new ATH
- round-number milestone crossing
- more than 20% decline
- two or more important metrics hitting significant thresholds at the same time

### 10.5 Suppression and Cooldown

The design should include suppression logic to prevent alert spam.

Recommended behavior:

- repeated alerts for the same metric enter cooldown
- multi-metric signals should be eligible for combination into one alert
- if a combined alert is emitted, lower-value individual alerts can be suppressed

## 11. Phase 1 Internal Alert Feed

Phase 1 does not deliver alerts to Lark.

Instead, alerts should be stored in a simple relational database and surfaced through the backend as an internal alert feed.

This feed is the primary review surface for Phase 1.

Each alert record should include at least:

- monitor scope
  - core or ecosystem

- entity name
  - for example Mantle, Aave, Merchant Moe

- metric name

- current value

- formatted value

- time window

- change percentage

- severity

- trigger reason

- source platform

- source reference link if available

- detected timestamp

- ATH flag

- milestone flag

- cooldown status

- reviewed status

- optional AI eligibility flag

### 11.1 Database Approach

A simple relational database is sufficient for Phase 1.

Recommended default:

- PostgreSQL for the shared backend environment

Acceptable local prototype:

- SQLite if only used for an initial local proof of concept

Core storage tables can be:

- `metric_snapshots`
- `alert_events`
- `watchlist_protocols`
- `source_runs`

## 12. AI Design

### 12.1 Role of AI

AI should improve signal presentation, not replace deterministic signal detection in Phase 1.

AI responsibilities in later phases:

- explain why the signal matters
- rate signal strength
- suggest whether multiple signals should be combined
- generate draft social copy
- generate visual suggestions

AI should not be the sole authority for:

- first-layer threshold decisions
- first-layer ATH detection
- first-layer milestone detection
- cooldown enforcement

### 12.2 Phase 1 AI Policy

Phase 1 can either:

- disable AI entirely, or
- run AI only on selected high-priority internal alerts for offline evaluation

The main goal in Phase 1 is to validate:

- source data stability
- metric-definition consistency
- alert quality
- alert noise levels

### 12.3 Phase 2 AI Outputs

When AI is introduced into the production flow, the structured output can include:

- reason
- signal strength
- signal rating
- recommended action
- combine recommendation
- draft copy
- visual suggestion

## 13. Delivery Strategy by Phase

### Phase 1: Data Foundation

Goals:

- collect all core metrics
- build the ecosystem sub-dashboard
- build snapshot storage
- implement the rule-based alert engine
- expose a backend-driven internal alert feed
- do not integrate with Lark yet

Scope:

- all core metrics ingested
- Aave special monitor included
- hybrid ecosystem watchlist included
- TVL, volume, borrow, and supply computations where applicable
- 7D, MTD, ATH, milestone, and decline detection

Success criteria:

- metrics are collected reliably
- metric definitions are understood and stable
- alert noise is acceptable
- stakeholders can review internal alerts without manual dashboard hunting

### Phase 2: AI and Lark Delivery

Goals:

- add AI explanations and draft copy
- add structured Lark delivery

Scope:

- AI signal explanation
- AI copy generation
- visual suggestion generation
- Lark webhook or bot integration

### Phase 3: Optimization

Goals:

- improve multi-metric packaging
- refine suppression and cooldown behavior
- support weekly and monthly digests
- improve ecosystem watchlist tuning

## 14. Operational Notes

The system should be built to support:

- scheduled execution
- source-level retries and backoff
- source freshness checks
- snapshot integrity checks
- source-by-source observability

Because this is an internal monitoring system, reliability and explainability are more important than aggressive automation at the beginning.

## 15. Recommended Implementation Posture

The recommended implementation posture is:

- one shared snapshot and alert framework for both core and ecosystem monitoring
- protocol-specific adapters only where justified
- Aave as the first special adapter
- generic protocol templates for the remaining ecosystem watchlist
- deterministic alert creation first
- AI language layer second

This keeps the first version stable while leaving a clear path for richer automation later.

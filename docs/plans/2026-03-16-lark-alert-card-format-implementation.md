# Lark Alert Card Format Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild Lark alert cards into the approved fixed PRD format with readable fields, directional header colors, and placeholder sections for draft copy and actions.

**Architecture:** Keep the existing alert delivery flow intact and concentrate the change in the alert serialization layer plus the pure Lark card builder. Extend serialized alert payloads with the metadata needed for presentation, then render a deterministic card layout from those fields. Cover the behavior with focused regression tests before changing production code.

**Tech Stack:** Python 3.13, pytest, FastAPI service modules, pure dict-based Lark card builders

---

### Task 1: Extend alert card regression tests

**Files:**
- Modify: `tests/test_integrations/test_lark_cards.py`

**Step 1: Write the failing tests**

Add tests for:

- upward threshold alert cards showing a green header, readable metric label, movement string, source text, Shanghai detected time, placeholder draft copy, and placeholder action block
- downward alert cards showing a red header
- ATH alert cards showing a neutral header and `NEW ALL-TIME HIGH` status

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_integrations/test_lark_cards.py -v`
Expected: FAIL because the current card builder does not render the new structure.

**Step 3: Commit**

```bash
git add tests/test_integrations/test_lark_cards.py
git commit -m "test: define lark alert card format expectations"
```

### Task 2: Extend serialized alert payload tests

**Files:**
- Modify: `tests/test_services/test_notifications.py`

**Step 1: Write the failing test**

Add assertions that the serialized alert payload handed to the Lark card builder includes:

- `change_pct`
- `detected_at`
- `is_ath`
- `is_milestone`
- `milestone_label`
- `source_platform`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_notifications.py -v`
Expected: FAIL because the serializer currently omits these fields.

**Step 3: Commit**

```bash
git add tests/test_services/test_notifications.py
git commit -m "test: cover lark alert serialization fields"
```

### Task 3: Implement the alert card format

**Files:**
- Modify: `src/integrations/lark/cards.py`
- Modify: `src/services/notifications.py`

**Step 1: Write the minimal implementation**

Update `build_alert_card` to:

- map metric keys to readable labels
- map movement direction to header template color
- render the fixed body order
- derive readable status strings
- render Shanghai-localized detected times
- insert placeholder `Suggested Draft Copy` and `Action Required` sections

Update alert serialization so the builder receives the fields listed in Task 2.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_integrations/test_lark_cards.py tests/test_services/test_notifications.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/integrations/lark/cards.py src/services/notifications.py tests/test_integrations/test_lark_cards.py tests/test_services/test_notifications.py
git commit -m "fix: rebuild lark alert cards into readable format"
```

### Task 4: Run broader regression verification

**Files:**
- No code changes expected

**Step 1: Run broader verification**

Run: `pytest tests/test_integrations/test_lark_cards.py tests/test_services/test_notifications.py tests/test_api/test_lark_integration.py tests/test_services/test_daily_summary.py tests/test_services/test_bot_query.py -v`
Expected: PASS

**Step 2: Commit if any verification-driven fixes were needed**

```bash
git add <only files changed by verification fixes>
git commit -m "test: verify lark card regressions"
```

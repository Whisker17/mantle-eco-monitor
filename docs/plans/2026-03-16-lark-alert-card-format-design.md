# Lark Alert Card Format Design

**Date:** 2026-03-16
**Status:** Approved in discussion on 2026-03-16.

## Goal

Make Lark alert cards readable at a glance by replacing the current free-form markdown list with a fixed format that matches the approved PRD example.

## Current Problem

The existing alert card builder renders a short list of generic markdown blocks:

- metric
- value
- window
- severity
- reason
- optional source URL

This structure exposes raw internal fields instead of presenting a clear alert summary. It also lacks the visual cues from the approved PRD format, including a consistent title, movement-oriented header color, and predictable field order.

## Approved Design

### Card Layout

All alert cards will use a fixed layout:

1. Header title: `MANTLE METRICS ALERT`
2. Body fields in this exact order:
   - `Metric`
   - `Movement`
   - `Current Value`
   - `Status`
   - `Source`
   - `Detected`
   - `Suggested Draft Copy`
   - `Action Required`

`Suggested Draft Copy` and `Action Required` will be placeholder sections in this iteration so the card shape matches the PRD without waiting on copy-generation logic.

### Presentation Rules

- Upward movement alerts use a green header template.
- Downward movement alerts use a red header template.
- ATH and other non-directional alerts use a neutral highlighted header template.
- `metric_name` is converted into a readable display label such as `TVL (Total Value Locked)`.
- `change_pct` and `time_window` are rendered as a human-readable movement string such as `+25% (7D)`.
- `formatted_value` is preferred for `Current Value`; raw numeric value is a fallback.
- `Status` is derived from alert semantics:
  - ATH alerts become `NEW ALL-TIME HIGH`
  - milestone alerts become a readable milestone label
  - threshold and decline alerts fall back to a readable version of the trigger reason
- `Source` shows a readable platform label and includes the reference URL when present.
- `Detected` is rendered in Shanghai time to match the product example.

## Data Changes

The current notification serializer does not pass all fields needed for the redesigned card. It will be extended to include:

- `change_pct`
- `detected_at`
- `is_ath`
- `is_milestone`
- `milestone_label`
- `source_platform`

The alert delivery pipeline will otherwise remain unchanged.

## Testing

Regression coverage will be added for:

- upward threshold alert rendering
- downward alert rendering and red header mapping
- ATH alert rendering and ATH status text
- notification serialization passing the new fields into the card builder

## Non-Goals

- generating real AI draft copy
- generating dynamic action recommendations
- changing daily summary or bot reply card layouts
- changing delivery persistence or Lark transport behavior

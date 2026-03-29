# Phase 2 Banner Multi-Analytics Policy

Date: 2026-03-29

This document defines deterministic behavior when multiple analytics compete for limited banner space.

## 1. Display Precedence

Final card visibility order is enforced as:

1. License eligibility
2. Manual selection (if mode is `manual`)
3. Auto layout selection (fallback/order)

Notes:

- Unlicensed cards are removed even if manually selected.
- If all manually selected cards are unlicensed, fallback uses licensed auto-layout cards.

## 2. Slot Conflict Merge Rules

When multiple cards target the same semantic slot, use deterministic winner selection:

1. Higher severity wins (`card_severity`)
2. If severity ties, higher priority wins (`card_priority`)
3. If still tied, lexical order acts as deterministic tie-break

Input shape expected by renderer policy helpers:

```json
{
  "slot_conflicts": {
    "temperature": ["temp_primary", "temp_secondary"]
  },
  "card_severity": {
    "temp_primary": 2,
    "temp_secondary": 3
  },
  "card_priority": {
    "temp_primary": 10,
    "temp_secondary": 2
  }
}
```

## 3. Overflow Summary

When not all cards can be rendered, show a summary indicator:

- `+N active analytics`

This is now rendered in both fire and PPE overlay paths.

## 4. Example Scenarios

### Scenario A: Manual selection with one unlicensed card

- Mode: `manual`
- Selected cards: `["gas", "flame"]`
- License: `gas=unlicensed`, `flame=licensed`
- Result: `flame` only

### Scenario B: Manual selection fully unlicensed

- Mode: `manual`
- Selected cards: `["gas"]`
- License: `gas=unlicensed`, auto candidates include `global`, `thermal` as licensed
- Result: fallback to `["global", "thermal"]`

### Scenario C: Same-slot conflict

- Selected cards: `["temp_primary", "temp_secondary", "gas"]`
- Slot conflict: `temperature=[temp_primary,temp_secondary]`
- Severity: `temp_secondary` higher
- Result: `["temp_secondary", "gas"]`

## 5. Test Coverage

Covered in:

- `tests/test_fusionbanner_category.py`

Specifically includes checks for:

- Auto vs manual selection behavior
- License override behavior
- Manual fallback behavior
- Slot merge determinism

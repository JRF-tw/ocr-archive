# qa_log.jsonl

Append-only QA log. One line per correction or flag, written by the QA teammate (Step 2.5). Shared across all chunks of a PDF run — located at `<work_dir>/qa_log.jsonl`.

## Correction entry (known rule applied)

```jsonl
{"chunk": "chunk_246-250", "page": 249, "type": "correction", "original": "劉藝正", "corrected": "劉馨正", "rule_pattern": "劉藝正", "confidence": "high"}
```

## Flag entry (new unknown error, not auto-corrected)

```jsonl
{"chunk": "chunk_246-250", "page": 250, "type": "flag", "original": "蔡美燕所有之國泰世[?]銀行", "corrected": null, "confidence": "low", "note": "銀行名稱中間一字模糊，疑為「華」"}
```

## Field notes

| Field | Values | Notes |
|-------|--------|-------|
| `type` | `correction` / `flag` | `correction` = rule applied; `flag` = needs human review |
| `original` | string | Exact text as it appeared in `ocr.md` |
| `corrected` | string / null | Corrected text (`null` for flags) |
| `rule_pattern` | string / null | The `pattern` field from `correction_rules.yaml` that matched; `null` for flags |
| `confidence` | `high` / `low` | `high` for rule-based corrections; `low` for flags |

## Workflow for flag review

1. Read `qa_log.jsonl` and filter `"type": "flag"`
2. Manually verify each flagged text against the PDF image
3. For confirmed errors: add a new rule to `tools/correction_rules.yaml`
4. Re-run QA on the chunk (Step 2.5) to apply the new rule

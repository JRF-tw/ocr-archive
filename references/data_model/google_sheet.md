# Google Sheet — Archive Schema

One row per PDF file (not per document). Multi-document PDFs have their
fields merged into a single row.

## Columns

| 欄 | 欄位 | 型別 | 來源 | 說明 |
|----|------|------|------|------|
| A | 案號 | string | `case_no` 正規化，或檔名 | `N005896`、`106上訴3315` |
| B | 收件日期 | date / null | 信封文件日期，或首個非空日期 | ISO 格式 `2022-06-17` |
| C | 文件日期 | string | 所有文件日期以 `；` 合併（去重） | `2022-06-17；2023-01-01` |
| D | 文件類型 | string | 所有 `doc_type` 以 `、` 合併（去重） | `信封、手寫書信` |
| E | 寄件人 | string | `defendants` + `others` 去重合併 | `陳文雄` |
| F | 收件人 | string | 留空（schema 目前無此欄位） | — |
| G | 摘要 | string | 各文件 `summary` 以換行合併 | — |
| H | 疑似罪名 | string | 各文件 `charge` 以 `；` 合併（去重）| `貪污治罪條例` |
| I | Drive連結 | url | 原始 PDF 的 Google Drive 連結（自動回填）| — |
| J | 備註 | string | 各文件 `notes` 以換行合併 | OCR 品質說明等 |

## 來源對應

`tagged.json` documents array → 單一 Google Sheet row：

```
case_no (首個非空)           → 案號
envelope date / first date   → 收件日期
all dates joined "；"        → 文件日期
all doc_types joined "、"    → 文件類型
defendants + others joined  → 寄件人
(empty)                     → 收件人
all summaries joined "\n"   → 摘要
all charges joined "；"     → 疑似罪名
(back-filled by pipeline)   → Drive連結
all notes joined "\n"       → 備註
```

## 設計原則

- **一列一個 PDF**：無論 PDF 內有幾份文件，Archive 只佔一列
- **多文件欄位合併**：摘要與備註以換行分隔，日期/類型/罪名以中文標點分隔
- **Drive連結欄**：由 `drive_pipeline upload` 自動回填，不需手動填入
- **收件人留空**：現有 tagged.json schema 未明確區分寄件人/收件人，可日後補充

## 自動化流程

1. `tools/export_sheet.py <tagged.json>` → 產生 `<stem>_sheet.csv`（一列，Drive連結空白）
2. `tools/drive_pipeline upload <work_dir>` → 上傳 CSV 並回填 Drive連結（欄 I）

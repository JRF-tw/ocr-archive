# Google Sheet — Archive Schema

One row per document (corresponds to one entry in `tagged.json`).

## Columns

| 欄位 | 型別 | 來源 | 說明 |
|------|------|------|------|
| 案號 | string | 手動 / `case_no` 正規化 | `106上訴3315` |
| 卷別 | string / null | 手動 | `卷2`；若文件非來自特定卷則留空 |
| 卷內序號 | int / null | `tagged.json id` | 在該卷中的流水號 |
| 文件類型 | string | `doc_type` | `刑事準備一狀` |
| 摘要 | string | `summary` | ≤50字一句話描述 |
| 日期 | date / null | `date` | ISO 格式 `2018-03-21` |
| 罪名 | string / null | `charge` | `貪污治罪條例` |
| 被告 | string | `defendants` 逗號合併 | `李孝君` |
| 辯護人 | string / null | `lawyers` 逗號合併 | `黃英哲,許樹依,王晟睿` |
| 法官 | string / null | `judges` 逗號合併 | `林孟皇` |
| 其他關係人 | string / null | `others` 逗號合併 | `郭金章,蔡美燕` |
| 起始頁 | int | `start_page` | PDF 全域頁碼 |
| 結束頁 | int | `end_page` | PDF 全域頁碼 |
| 原始 PDF | url | 手動 | Google Drive 連結，指向原始 PDF |
| OCR Google Doc | url | 自動產生 | 此份文件 OCR 內容轉出的 Google Doc |
| 標注 PDF | url | 自動產生 | Google Drive 連結，帶書籤的 PDF |
| 備註 | string / null | `notes` + 手動 | 自由文字 |

## 來源對應

`tagged.json` document → Google Sheet row 的欄位對應：

```
doc_type      → 文件類型
summary       → 摘要
date          → 日期
charge        → 罪名
defendants    → 被告（join with ","）
lawyers       → 辯護人（join with ","）
judges        → 法官（join with ","）
others        → 其他關係人（join with ","）
start_page    → 起始頁
end_page      → 結束頁
notes         → 備註（可附加手動補充）
```

案號、卷別、原始 PDF、OCR Google Doc、標注 PDF 由人工或自動化腳本填入。

## 設計原則

- **一行一份文件**：對應 `tagged.json` 的一個 document entry
- **卷別可為空**：文件若來自獨立 PDF 而非某卷則留空
- **人名以逗號分隔**：保留在單一儲存格以利人工閱讀；若需程式查詢可另建 sheet
- **OCR Google Doc 粒度**：每份文件的頁段（`start_page` 到 `end_page`）獨立轉成一個 Google Doc

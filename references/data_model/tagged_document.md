# tagged.json / merged_tagged.json

Structured metadata per document. One file per chunk (`tagged.json`); merged into `merged_tagged.json` for multi-chunk PDFs.

```json
{
  "source": "高院刑事_106上訴3315卷2_P1-544_OCR_1_54.pdf",
  "documents": [
    {
      "id": 8,
      "start_page": 9,
      "end_page": 36,
      "doc_type": "刑事準備一狀",
      "court": "臺灣高等法院",
      "case_no": "106年度上訴字第3315號",
      "date": "2018-03-21",
      "defendants": ["李孝君"],
      "lawyers": ["黃英哲", "許樹依", "王晟睿"],
      "judges": ["林孟皇"],
      "others": ["郭金章", "蔡美燕"],
      "charge": "貪污治罪條例",
      "tags": ["刑事準備書狀", "證據能力", "傳聞法則"],
      "summary": "被告李孝君辯護人就各項證據能力提出準備一狀，針對調詢筆錄、帳冊逐一表示意見。",
      "notes": null
    }
  ]
}
```

## Field notes

| Field | Type | Notes |
|-------|------|-------|
| `doc_type` | string | 標準化類型：卷宗封面、起訴書、判決書、不起訴處分書、偵查筆錄、警詢筆錄、審判筆錄、搜索票、扣押物品目錄、刑事準備書狀、聲請書、裁定書、函文、收據、送達證書、閱卷聲請書、空白頁、其他 |
| `court` | string / null | 發文法院或機關全稱 |
| `case_no` | string / null | 年度字號，如 `106年度上訴字第3315號` |
| `date` | ISO date / null | 文件日期；chunk 中段無法確認時為 null |
| `sender` | string / null | 寄件人或發文機關；信封取寄件人，函文取發文機關，無法判斷則 null |
| `recipient` | string / null | 收件人或受文機關；信封取收件人，函文取受文者，無法判斷則 null |
| `defendants` | string[] | 明確標示為「被告」者 |
| `lawyers` | string[] | 選任辯護人、公設辯護人（姓名，不含「律師」稱謂） |
| `judges` | string[] | 審判長、受命法官、陪席法官（姓名，不含職稱） |
| `others` | string[] | 檢察官、證人、告訴人、被害人、鑑定人、書記官等 |
| `charge` | string / null | 罪名或法條，如 `貪污治罪條例` |
| `tags` | string[2..5] | 自由關鍵詞，2–5 個 |
| `summary` | string | 一句話摘要，≤50字 |
| `notes` | string / null | 辨識備註，如 chunk 中段、文字模糊等 |

## Mapping to Google Sheet

See `references/data_model/google_sheet.md` for how these fields map to archive columns.

# segments.json

Document boundary detection output. One file per chunk, produced by the segment_docs.py prompt workflow.

```json
{
  "source": "高院刑事_106上訴3315卷2_P1-544_OCR_1_54.pdf",
  "page_offset": 1,
  "segments": [
    {
      "id": 1,
      "start_page": 1,
      "end_page": 1,
      "doc_type_hint": "卷宗封面",
      "boundary_confidence": "high",
      "boundary_note": null
    },
    {
      "id": 8,
      "start_page": 9,
      "end_page": 36,
      "doc_type_hint": "刑事準備一狀（被告李孝君）",
      "boundary_confidence": "high",
      "boundary_note": null,
      "continues": false
    }
  ]
}
```

## Field notes

| Field | Type | Notes |
|-------|------|-------|
| `page_offset` | int | Global page number of the first page in this chunk |
| `segments[].start_page` | int | Global page number (not local to chunk) |
| `segments[].end_page` | int | Global page number (inclusive) |
| `segments[].doc_type_hint` | string | Informal label for the LLM; becomes `doc_type` after tagging |
| `segments[].boundary_confidence` | `high` / `medium` / `low` | Confidence in the boundary detection |
| `segments[].boundary_note` | string / null | Required when confidence is not `high` |
| `segments[].continues` | bool | `true` if document continues into the next chunk; omit or `false` otherwise |

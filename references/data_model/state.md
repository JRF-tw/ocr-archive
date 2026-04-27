# state.json

Pipeline progress tracker. Created at Step 0, updated after each chunk completes.

```json
{
  "pdf": "<pdf_stem>.pdf",
  "pdf_path": "/absolute/path/to/<pdf_stem>.pdf",
  "total_pages": 544,
  "chunk_size": 50,
  "chunks": [
    {"id": "chunk_001-050", "start": 1,   "end": 50,  "status": "done"},
    {"id": "chunk_051-100", "start": 51,  "end": 100, "status": "in_progress"},
    {"id": "chunk_101-150", "start": 101, "end": 150, "status": "pending"}
  ],
  "pipeline_step": "ocr"
}
```

## Field notes

| Field | Values | Notes |
|-------|--------|-------|
| `chunks[].status` | `pending` / `in_progress` / `done` | Update to `done` only after tagged.json is written |
| `pipeline_step` | `images` / `ocr` / `qa` / `segment` / `tag` / `complete` | Current active step across all chunks |

## Resume logic

Read state.json first. Skip chunks where `status == "done"`. For each incomplete chunk, check existing files:

- `tagged.json` exists → mark done
- `segments.json` exists → resume from Step 4
- `ocr_corrected.md` exists → resume from Step 3
- `ocr.md` exists (all pages present) → resume from Step 2.5 (QA)
- `ocr.md` exists (partial) → resume OCR from next missing page
- `pages/` exists → resume from Step 2
- Nothing → resume from Step 1

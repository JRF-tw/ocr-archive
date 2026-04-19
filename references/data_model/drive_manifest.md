# drive_manifest.json

Drive upload state tracker. Created by `drive_pipeline.py run`, updated by `drive_pipeline.py upload`. One per work directory.

```json
{
  "_schema_version": "1",
  "input": {
    "file_id": "1a2b3c4d5e...",
    "file_name": "高院刑事_106上訴3315_卷2.pdf",
    "folder_id": "0B1234...",
    "downloaded_at": "2026-04-10T08:23:00Z",
    "local_pdf_path": "/Users/user/work/高院刑事_106上訴3315_卷2/高院刑事_106上訴3315_卷2.pdf",
    "md5_checksum": "d41d8cd98f00b204e9800998ecf8427e"
  },
  "output_folder_id": "0B5678...",
  "pipeline_status": "complete",
  "uploads": {
    "bookmarked_pdf": {
      "status": "uploaded",
      "local_path": "/Users/user/work/.../高院刑事_106上訴3315_卷2_bookmarked.pdf",
      "drive_file_id": "1x2y3z...",
      "drive_url": "https://drive.google.com/file/d/1x2y3z.../view",
      "uploaded_at": "2026-04-10T09:15:00Z",
      "error": null
    },
    "ocr_markdown": {
      "status": "uploaded",
      "local_path": "/Users/user/work/.../merged_ocr.md",
      "drive_file_id": "4a5b6c...",
      "drive_url": "https://drive.google.com/file/d/4a5b6c.../view",
      "uploaded_at": "2026-04-10T09:16:00Z",
      "error": null
    },
    "sheet_rows": {
      "status": "appended",
      "local_csv_path": "/Users/user/work/.../高院刑事_106上訴3315_卷2_sheet.csv",
      "spreadsheet_id": "1AbCdEf...",
      "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1AbCdEf.../edit",
      "tab_name": "Archive",
      "rows_appended": 42,
      "appended_at": "2026-04-10T09:17:00Z",
      "error": null
    }
  },
  "created_at": "2026-04-10T08:22:00Z",
  "updated_at": "2026-04-10T09:17:00Z"
}
```

## Field reference

| Field | Type | Notes |
|-------|------|-------|
| `_schema_version` | `"1"` | For future migrations |
| `input.file_id` | string | Google Drive file ID |
| `input.file_name` | string | Original filename from Drive |
| `input.folder_id` | string \| null | Drive folder containing the file |
| `input.downloaded_at` | ISO 8601 \| null | When download completed |
| `input.local_pdf_path` | string \| null | Absolute local path to PDF |
| `input.md5_checksum` | string \| null | MD5 from Drive metadata |
| `output_folder_id` | string \| null | Drive folder ID where outputs are uploaded |
| `pipeline_status` | `null` / `"complete"` | Set to `"complete"` after all uploads succeed |
| `uploads.bookmarked_pdf.status` | `"pending"` / `"uploaded"` / `"failed"` | File upload status |
| `uploads.ocr_markdown.status` | `"pending"` / `"uploaded"` / `"failed"` | File upload status |
| `uploads.sheet_rows.status` | `"pending"` / `"appended"` / `"failed"` | Note: uses `"appended"`, not `"uploaded"` |
| `created_at` | ISO 8601 | Set once on creation |
| `updated_at` | ISO 8601 | Updated on every `save()` call |

## Status enum values

| Status | Used by | Meaning |
|--------|---------|---------|
| `pending` | all three entries | Not yet attempted |
| `uploaded` | `bookmarked_pdf`, `ocr_markdown` | Successfully uploaded to Drive |
| `appended` | `sheet_rows` | CSV rows appended to Archive sheet |
| `failed` | all three entries | Operation failed — see `error` field |

## Resume logic

`drive_pipeline.py upload` reads the manifest and skips entries based on status:

- `bookmarked_pdf` / `ocr_markdown`: skip if `status == "uploaded"`
- `sheet_rows`: skip if `status == "appended"`
- `status == "pending"` or `"failed"`: retry the operation
- `--force` flag: bypass all skip logic, re-upload everything

## Atomicity

`save()` writes to `drive_manifest.json.tmp` first, then calls `os.replace()` to atomically move to the final path. This prevents corruption if the process is interrupted mid-write.

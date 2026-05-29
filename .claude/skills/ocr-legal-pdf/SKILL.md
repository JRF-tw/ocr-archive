---
name: ocr-legal-pdf
description: Use when given a Taiwan court case PDF (法院卷宗) and asked to OCR it, extract documents, or tag its contents. Input is a PDF path; output is OCR Markdown, segments JSON, tagged JSON, bookmarked PDF, and (optionally) Drive uploads.
---

# OCR Legal PDF Pipeline

Seven-step pipeline for Taiwan court case files (法院卷宗). No API key required — uses Claude Code's built-in vision via Max Plan.

## Pipeline Overview

```
PDF → working folder → images (50-page chunks) → OCR Markdown → QA/correction → segments JSON → tagged JSON → bookmarked PDF → Drive upload
```

All tools are in `tools/`. Prompts are in `tools/prompts/` (YAML, edit freely).

---

## CRITICAL: Plan First, Then Execute with Subagents

**Never read many images in one session.** Each image consumes context. Reading 54 pages in one session fills the context window and forces a long, expensive write at the end.

### CRITICAL: One chunk per session

**Process exactly ONE chunk per session, then exit with success.**

- Read `state.json` to find the first chunk where `status != "done"`
- Process only that chunk (Steps 1 → 2 → 2.5 → 3 → 4)
- Update `state.json` to mark that chunk as `"done"`
- If all chunks are done, proceed to Steps 4b → 5 → 6 → 7, then exit
- Exit cleanly — the pipeline will be re-invoked for the next chunk

This prevents context overflow on large PDFs.

### Required workflow when this skill is triggered:

1. **Enter plan mode immediately** — create `TaskCreate` entries for every batch before touching any files.
2. **Dispatch one subagent per 3-page batch** — each subagent reads 3 pages, appends OCR to the chunk's `ocr.md`, then exits.
3. **Main agent coordinates** — waits for each subagent, then dispatches next.

---

## Step 0 — Setup Working Folder

Before any processing, create a working folder named after the PDF stem **in the same directory as the PDF**:

```bash
# Example: for high_court_case.pdf
mkdir -p <pdf_dir>/<pdf_stem>/
```

All intermediate files go **inside** this folder. The original PDF is never moved.

### Working folder structure

```
<pdf_stem>/
  state.json              # progress tracker — update after each chunk
  chunk_001-050/
    pages/                # PNG images for pages 1–50
    ocr.md                # OCR output for pages 1–50
    segments.json         # segments for this chunk
    tagged.json           # tagged metadata for this chunk
  chunk_051-100/
    ...
  merged_ocr.md           # all chunks concatenated (created in Step 4 merge)
  merged_tagged.json      # all documents combined (created in Step 4 merge)
  <pdf_stem>_bookmarked.pdf   # final output (created in Step 5)
```

### state.json schema

See `references/data_model/state.md` for full schema and field notes.

Create this file immediately and update `status` after each chunk completes. **Resuming across sessions**: read `state.json` first. Skip chunks where `status == "done"`. Resume from the first `"pending"` or `"in_progress"` chunk.

---

## Step 1 — Convert PDF to Images (per chunk)

Run once per chunk, pointing `--out-dir` into the working folder:

```bash
.venv/bin/python tools/pdf_to_images.py <pdf_path> \
  --dpi 200 \
  --pages <start>-<end> \
  --out-dir <work_dir>/<chunk_id>/pages/
```

Example for chunk 051–100:
```bash
.venv/bin/python tools/pdf_to_images.py case.pdf \
  --pages 51-100 \
  --out-dir case/chunk_051-100/pages/
```

Check the output path printed by the script before proceeding.

### Chunk size

| PDF size | Chunk size |
|----------|-----------|
| ≤ 50 pages | No chunking needed — process as single chunk |
| 51–500 pages | 50 pages per chunk |
| 500+ pages | 50 pages per chunk |

---

## Step 2 — OCR via Subagents (3 pages per subagent)

### 2a. Create tasks first

Before reading any images, use `TaskCreate` to register every batch across all chunks. For a 2-chunk PDF (pages 1–100):

- Task: OCR pages 1–3 → append to `<work_dir>/chunk_001-050/ocr.md`
- Task: OCR pages 4–6 → append to `<work_dir>/chunk_001-050/ocr.md`
- ... (all batches for chunk 1)
- Task: OCR pages 51–53 → append to `<work_dir>/chunk_051-100/ocr.md`
- ... (all batches for chunk 2)
- Task: Run segment_docs.py for each chunk
- Task: Run tag_docs.py for each chunk
- Task: Merge chunks and run tag_pdf.py

### 2b. Subagent prompt template

Dispatch each batch as a subagent with this prompt:

```
You are OCR-ing pages {START}–{END} of a Taiwan court case PDF.

Images are at:
  {IMAGE_DIR}/page-{START_PADDED}.png
  {IMAGE_DIR}/page-{(START+1)_PADDED}.png
  {IMAGE_DIR}/page-{(START+2)_PADDED}.png
  (only include pages that exist)

For each page, read the image and transcribe the full text.

## Output format

For each page output:

## 第 N 頁

<transcribed content>

Use the GLOBAL page number N (not the local page number within the chunk images).
Global page = local image index + chunk start - 1.
Example: if chunk starts at page 51, the first image (page-001.png) → ## 第 51 頁

Rules:
- Tables → Markdown `| col |` format
- Unclear text → `[?]`
- Ignore 李之聖 watermarks
- Stamps/seals → transcribe text inside 【】
- Blank pages → write （空白頁）

## After transcribing all pages

**Append** the Markdown to: `{OCR_MD_PATH}`
(Read current file content if it exists, append new pages, write combined content back.)

If the file does not exist yet, create it. If it exists, append to the end.
```

### 2c. Append pattern

Each subagent:
1. Reads current file content (if exists)
2. Appends new pages' Markdown
3. Writes combined content back

### 2d. Batch size

Use **3 pages per subagent** (safe for all PDF types).

---

## Step 2.5 — QA (per chunk)

After **all** OCR batches for a chunk complete, dispatch one QA teammate. This is a single sequential step — not parallel with OCR.

**Inputs:**
- `<work_dir>/<chunk_id>/ocr.md` — raw OCR output from Step 2
- `tools/correction_rules.yaml` — global correction rule list (grows across runs)

**QA teammate prompt template:** `tools/prompts/qa_ocr.yaml`

Variables to fill when dispatching:

| Variable | Value |
|----------|-------|
| `{source}` | PDF filename |
| `{chunk_id}` | e.g. `chunk_246-250` |
| `{start_page}` | chunk start page |
| `{end_page}` | chunk end page |
| `{corrected_path}` | `<work_dir>/<chunk_id>/ocr_corrected.md` |
| `{qa_log_path}` | `<work_dir>/qa_log.jsonl` |
| `{correction_rules}` | full contents of `tools/correction_rules.yaml` |
| `{legal_terms}` | full contents of `tools/legal_terms.txt` |
| `{ocr_content}` | full contents of `ocr.md` |

**Outputs:**
- `<work_dir>/<chunk_id>/ocr_corrected.md` — corrected OCR; **all downstream steps use this file**
- `<work_dir>/qa_log.jsonl` — append-only log of corrections and flags across all chunks

**Adding new rules:** When QA flags a new error with `type=flag`, add it to `tools/correction_rules.yaml` with `confidence: high` only after human review. Longer patterns must come before shorter overlapping patterns in the rules list.

---

## Step 3 — Segment Documents (per chunk)

After QA completes, use `ocr_corrected.md` (not `ocr.md`):

```bash
.venv/bin/python tools/segment_docs.py \
  <work_dir>/<chunk_id>/ocr_corrected.md \
  --chunk-size 50
```

This prints a prompt. Paste into Claude Code → get JSON → save as `<work_dir>/<chunk_id>/segments.json`.

The `page_offset` field in the output JSON will reflect the global page numbers (from the `## 第 N 頁` headers in the OCR md).

---

## Step 4 — Tag Documents (per chunk)

```bash
.venv/bin/python tools/tag_docs.py \
  <work_dir>/<chunk_id>/segments.json \
  <work_dir>/<chunk_id>/ocr_corrected.md \
  --batch-size 10
```

Paste prompt → get JSON → save as `<work_dir>/<chunk_id>/tagged.json`.

### Step 4b — Merge chunks (multi-chunk PDFs only)

After all chunks are tagged, merge into a single file:

1. **Merge OCR**: Concatenate all `ocr_corrected.md` files in page order → `<work_dir>/merged_ocr.md`
2. **Merge tagged**: Combine all `documents` arrays from each `tagged.json` → `<work_dir>/merged_tagged.json`

See `references/data_model/tagged_document.md` for the full document schema.

For a single-chunk PDF, skip this step — the chunk's `tagged.json` is already the final output.

---

## Step 5 — Generate Bookmarked PDF

```bash
.venv/bin/python tools/tag_pdf.py \
  <pdf_path> \
  <work_dir>/merged_tagged.json \
  --output <work_dir>/<pdf_stem>_bookmarked.pdf
```

For a single-chunk PDF, use the chunk's `tagged.json` directly:
```bash
.venv/bin/python tools/tag_pdf.py \
  <pdf_path> \
  <work_dir>/<chunk_id>/tagged.json \
  --output <work_dir>/<pdf_stem>_bookmarked.pdf
```

The bookmarked PDF has a hierarchical bookmark tree:
```
行政文件
  └── 卷宗封面｜劉馨正 等4人｜2017-12-25  → p.1
  └── 辦理事項表                           → p.5
訴訟書狀
  └── 刑事準備一狀｜李孝君｜2018-03-21    → p.9
程序文件
  └── 送達證書｜劉馨正                    → p.37
  └── 閱卷聲請書｜吳炳煌｜2018-03-22     → p.39
```

---

## Step 6 — Export to Google Sheets CSV

```bash
.venv/bin/python tools/export_sheet.py \
  <work_dir>/merged_tagged.json \
  --volume "卷2" \
  --output <work_dir>/<pdf_stem>_sheet.csv
```

For a single-chunk PDF, use the chunk's `tagged.json`:
```bash
.venv/bin/python tools/export_sheet.py \
  <work_dir>/<chunk_id>/tagged.json \
  --volume "卷2" \
  --output <work_dir>/<pdf_stem>_sheet.csv
```

Options:
- `--case-no TEXT` — 案號 short form (e.g. `106上訴3315`). If omitted, auto-derived from the first non-null `case_no` field in the JSON.
- `--volume TEXT` — 卷別 (e.g. `卷2`). Leave blank if the PDF is not from a specific volume.
- `--output PATH` — defaults to `<tagged_json_stem>_sheet.csv` in the same directory.

The CSV has 17 columns matching the archive schema in `references/data_model/google_sheet.md`. URL columns (原始 PDF, OCR Google Doc, 標注 PDF) are left empty — they are auto-filled by Step 7 if using Drive integration.

---

## Step 7 — Upload to Google Drive (optional)

If the PDF was downloaded via `drive_pipeline.py run` (i.e. a `drive_manifest.json` exists in the work directory), upload outputs back to Drive:

```bash
.venv/bin/python -m tools.drive_pipeline upload <work_dir>
```

This uploads three outputs in sequence:
1. `<pdf_stem>_bookmarked.pdf` → Drive output folder (nested under `<case_no>/<volume>_<pdf_stem>/`)
2. `merged_ocr.md` (or single-chunk `ocr_corrected.md`) → same Drive subfolder
3. `<pdf_stem>_sheet.csv` → appended to the Archive tab of the Google Sheet

After appending, the URL columns (原始 PDF, OCR Google Doc, 標注 PDF) are back-filled automatically for the newly appended rows.

### Resume after failure

If any upload fails, re-run the same command — it skips entries already marked `uploaded` or `appended`:

```bash
.venv/bin/python -m tools.drive_pipeline upload <work_dir>
```

Use `--force` to re-upload everything regardless of status:

```bash
.venv/bin/python -m tools.drive_pipeline upload <work_dir> --force
```

### Check upload status

```bash
.venv/bin/python -m tools.drive_pipeline status <work_dir>
```

Prints a table showing: input file info, pipeline status, and each upload entry with its status, Drive URL, and any errors.

### Prerequisites

- `~/.jrf/credentials.json` — OAuth2 client credentials (from Google Cloud Console)
- `~/.jrf/token.json` — auto-created on first run (browser OAuth flow)
- `~/.jrf/drive_config.json` — copy from `drive_config.template.json` and fill in folder/spreadsheet IDs
- Install Drive dependencies: `pip install -r requirements-drive.txt`

See `references/data_model/drive_manifest.md` for the full manifest schema.

---

## Output Files

| File | Content |
|------|---------|
| `<work_dir>/state.json` | Progress tracker — read on resume |
| `<work_dir>/<chunk_id>/pages/page-NNN.png` | Per-page images |
| `<work_dir>/<chunk_id>/ocr.md` | Raw OCR Markdown — do not use downstream |
| `<work_dir>/<chunk_id>/ocr_corrected.md` | QA-corrected OCR — **use this for all downstream steps** |
| `<work_dir>/qa_log.jsonl` | Append-only log of all corrections and flags across chunks |
| `<work_dir>/<chunk_id>/segments.json` | Document boundary detection for chunk |
| `<work_dir>/<chunk_id>/tagged.json` | Structured metadata for chunk |
| `<work_dir>/merged_ocr.md` | Full corrected OCR (multi-chunk PDFs only) |
| `<work_dir>/merged_tagged.json` | All documents combined (multi-chunk PDFs only) |
| `<work_dir>/<pdf_stem>_bookmarked.pdf` | Final bookmarked PDF for lawyer browsing |
| `<work_dir>/<pdf_stem>_sheet.csv` | Google Sheets import CSV |
| `<work_dir>/drive_manifest.json` | Drive upload state tracker (Step 7) |

### Data model references

All schemas are in `references/data_model/`:

| File | Describes |
|------|-----------|
| `state.md` | `state.json` — pipeline progress tracker |
| `segments.md` | `segments.json` — document boundary detection output |
| `tagged_document.md` | `tagged.json` / `merged_tagged.json` — structured metadata per document |
| `qa_log.md` | `qa_log.jsonl` — QA corrections and flags |
| `google_sheet.md` | Google Sheet archive schema and mapping from `tagged.json` |
| `drive_manifest.md` | `drive_manifest.json` — Drive upload state tracker |

---

## Resuming an interrupted run

1. Read `<work_dir>/state.json`
2. Find chunks where `status != "done"`
3. For each incomplete chunk: check which files already exist in `<chunk_id>/`
   - If `tagged.json` exists → mark chunk done
   - If `segments.json` exists → resume from Step 4
   - If `ocr_corrected.md` exists → resume from Step 3
   - If `ocr.md` exists → check how many `## 第 N 頁` headers are present; if all pages present, resume from Step 2.5 (QA); otherwise resume OCR from the next missing page
   - If `pages/` exists → resume from Step 2
   - Otherwise → resume from Step 1
4. Continue from where processing stopped

---

## Editing Prompts

All prompts are YAML files in `tools/prompts/`. Supported template variables:

| File | Variables |
|------|-----------|
| `qa_ocr.yaml` | `{source}`, `{chunk_id}`, `{start_page}`, `{end_page}`, `{corrected_path}`, `{qa_log_path}`, `{correction_rules}`, `{ocr_content}`, `{legal_terms}` |
| `segment_docs.yaml` | `{source}`, `{n_pages}`, `{page_offset}`, `{content}` |
| `tag_docs.yaml` | `{source}`, `{content}`, `{segments}` |

Global correction rules (not a prompt): `tools/correction_rules.yaml` — add new rules here after human review of `qa_log.jsonl` flags.

# How-to: Google Drive 整合 OCR 管線

> 本文件適用對象：已完成 SETUP.md 環境建置、想透過 Google Drive 進行案件 PDF 處理的操作者。  
> 環境設定尚未完成者請先閱讀 [SETUP.md](SETUP.md)。

---

## 如何處理單一 PDF（從 Drive 下載到上傳回 Drive）

### 前置條件

- `~/.jrf/credentials.json` 與 `~/.jrf/drive_config.json` 已設定完成
- PDF 已上傳至 Google Drive 輸入資料夾
- 已取得該 PDF 的 Google Drive **File ID**（網址列 `/file/d/` 後的字串）

### 步驟

**1. 下載 PDF 並建立工作目錄**

```bash
python -m tools.drive_pipeline run <FILE_ID>
```

成功時輸出工作目錄的絕對路徑，例如：

```
/Users/you/jrf-work/高院刑事_106上訴3315_卷2
```

同時 Google Sheet Queue 頁籤狀態更新為 `running`。

**2. 在 Claude Code 中啟動 OCR**

在 Claude Code 對話中輸入：

```
/ocr-legal-pdf
```

接著提供 PDF 路徑（工作目錄內的 PDF，即步驟 1 輸出路徑下的 `<檔名>.pdf`）。  
Claude 會自動執行 Steps 1–6：圖片轉換 → OCR → QA 校正 → 分段 → 標記 → 書籤 PDF → CSV。

**3. 上傳結果回 Drive**

```bash
python -m tools.drive_pipeline upload <工作目錄路徑>
```

上傳完成後：

- 書籤 PDF 出現在 Drive 輸出資料夾的 `<案號>/<卷別_PDF名稱>/` 子目錄
- OCR Markdown 出現在同一子目錄
- CSV 附加到 Google Sheet Archive 頁籤，並自動填入三欄 URL

Queue 頁籤狀態更新為 `done`。

---

## 如何批次處理佇列中的所有 PDF

### 前置條件

- Google Apps Script 觸發器已設定（參見 SETUP.md §5）
  > **Script Properties 必填：** `FOLDER_ID`（輸入資料夾 ID）及 `SPREADSHEET_ID`（試算表 ID）。  
  > 在 Apps Script 編輯器中點選「專案設定」→「指令碼屬性」新增這兩個鍵值。
- 要處理的 PDF 已上傳至輸入資料夾，Apps Script 已將它們加入 Queue 頁籤

### 步驟

**處理一次所有 pending 工作後結束：**

```bash
python -m tools.drive_pipeline watch --once
```

**持續輪詢（每 60 秒）：**

```bash
python -m tools.drive_pipeline watch
```

`watch` 會自動對每筆 Queue 記錄依序執行完整三步驟：
1. **[1/3] 下載**：從 Drive 下載 PDF，建立工作目錄
2. **[2/3] OCR**：以 `claude --dangerously-skip-permissions` 自動執行 `/ocr-legal-pdf` 管線（無需手動操作）
3. **[3/3] 上傳**：將書籤 PDF、OCR Markdown 上傳至 Drive，CSV 附加至 Archive 頁籤

---

## 如何查看某個工作目錄的上傳狀態

```bash
python -m tools.drive_pipeline status <工作目錄路徑>
```

輸出範例：

```
=== Drive Pipeline Status ===
  Work dir:        /Users/you/jrf-work/高院刑事_106上訴3315_卷2
  File name:       高院刑事_106上訴3315_卷2.pdf
  File ID:         1aBcDeFgHiJkLmNoPqRsTuVwXyZ
  Downloaded at:   2026-05-12T08:23:00Z
  Pipeline status: complete

=== Upload Status ===
  bookmarked_pdf:
    Status:     uploaded
    Drive URL:  https://drive.google.com/file/d/1x2y3z.../view
  ocr_markdown:
    Status:     uploaded
    Drive URL:  https://drive.google.com/file/d/4a5b6c.../view
  sheet_rows:
    Status:     appended
    Spreadsheet: https://docs.google.com/spreadsheets/d/...
```

---

## 如何在上傳失敗後恢復

上傳中斷或失敗後，重新執行同一指令即可——已成功的部分不會重複執行：

```bash
python -m tools.drive_pipeline upload <工作目錄路徑>
```

管線會跳過 `status == "uploaded"` 或 `"appended"` 的項目，只重試失敗的部分。

---

## 如何強制重新上傳全部輸出

已上傳但需要覆蓋（例如重跑 OCR 後輸出有更新）：

```bash
python -m tools.drive_pipeline upload <工作目錄路徑> --force
```

`--force` 會忽略所有 `status` 欄位，重新上傳三個輸出並重新附加 CSV。

---

## 如何在 OCR 管線中斷後繼續（不重新下載）

如果 OCR 過程中斷但工作目錄已存在，**不需要重新執行 `drive_pipeline run`**。  
直接在 Claude Code 中提供現有工作目錄內的 PDF 路徑：

```
/ocr-legal-pdf
```

輸入 PDF 路徑後，Claude 會讀取 `state.json` 判斷進度，從斷點繼續。

---

## 排解常見問題

**`ERROR: Missing required config keys`**  
`~/.jrf/drive_config.json` 中有欄位未填。執行 `python -m tools.check_env` 確認哪一欄缺少值。

**`ERROR: Authentication failed`**  
`~/.jrf/token.json` 可能過期或不存在。刪除 `~/.jrf/token.json` 後重新執行，系統會開啟瀏覽器要求重新授權。

**`ERROR: No *_bookmarked.pdf found in work directory`**  
OCR 管線尚未完成（Steps 1–6 未跑完）。先完成 OCR，再執行 `upload`。

**`WARNING: Failed to back-fill URLs`**  
CSV 已附加至 Archive，但 URL 欄未填入。可忽略——URL 欄空白不影響資料完整性；若需填入，執行 `upload --force` 重試。

**Queue 頁籤狀態卡在 `running`**  
上一次 `run` 中途失敗。確認工作目錄下是否有 PDF 存在；若有，直接進行 OCR 管線再 `upload`；若無，重新執行 `drive_pipeline run <FILE_ID>`。

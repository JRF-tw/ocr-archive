# 環境建置指南

本文件說明如何在 macOS 上完整設定 JRF OCR 案件處理系統。  
完成後，您只需將 PDF 丟入 Google Drive 指定資料夾，系統會自動排隊並由 AI 進行 OCR 辨識。

---

## 目錄

1. [安裝必要工具](#1-安裝必要工具)
2. [取得程式碼](#2-取得程式碼)
3. [設定 Google OAuth 憑證](#3-設定-google-oauth-憑證)
4. [設定 Google Drive 設定檔](#4-設定-google-drive-設定檔)
5. [安裝 Google Apps Script 自動排程](#5-安裝-google-apps-script-自動排程)
6. [驗證環境](#6-驗證環境)
7. [日常操作流程](#7-日常操作流程)

---

## 1. 安裝必要工具

### 1-1. 安裝 Homebrew（macOS 套件管理工具）

打開「終端機」（Terminal），貼上以下指令後按 Enter：

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

依照畫面提示操作（可能需要輸入電腦密碼）。

### 1-2. 安裝 poppler（PDF 轉圖片工具）

```
brew install poppler
```

### 1-3. 安裝 uv（Python 執行環境管理工具）

```
brew install uv
```

### 1-4. 安裝 Claude Code（AI 助理 CLI）

```
npm install -g @anthropic-ai/claude-code
```

> 若您尚未安裝 Node.js，請先執行 `brew install node`。

---

## 2. 取得程式碼

在終端機執行：

```
git clone https://github.com/Judicial-Reform-Foundation/ocr-archive.git
cd ocr-archive
uv sync
```

`uv sync` 會自動安裝所有 Python 套件，完成後顯示 `All packages installed` 即可。

---

## 3. 設定 Google OAuth 憑證

這步驟讓程式取得存取您的 Google Drive 與 Google Sheets 的授權。

### 3-1. 建立 Google Cloud 專案

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 點選畫面左上角的專案選單 → **「新增專案」**
3. 專案名稱填入 `JRF-OCR`，點選 **「建立」**

### 3-2. 啟用 API

在左側選單點選 **「API 和服務」→「程式庫」**，分別搜尋並啟用：

- `Google Drive API` → 點選 **「啟用」**
- `Google Sheets API` → 點選 **「啟用」**

### 3-3. 建立 OAuth 憑證

1. 左側選單點選 **「憑證」→「建立憑證」→「OAuth 用戶端 ID」**
2. 若系統要求設定「同意畫面」，請先依步驟填寫（應用程式名稱填 `JRF-OCR`，其餘可留預設值）
3. 應用程式類型選 **「桌面應用程式」**
4. 名稱填 `JRF-OCR-desktop`，點選 **「建立」**
5. 在彈出視窗中點選 **「下載 JSON」**

### 3-4. 放置憑證檔案

在終端機執行：

```
mkdir -p ~/.jrf
```

將剛才下載的 JSON 檔（通常名稱類似 `client_secret_xxxx.json`）**移動並重新命名**為：

```
~/.jrf/credentials.json
```

可以在 Finder 中操作：將檔案移至使用者家目錄下的 `.jrf` 資料夾，並改名為 `credentials.json`。

> `.jrf` 資料夾因名稱開頭是點（`.`），在 Finder 中預設隱藏。  
> 按 **Cmd + Shift + .** 可切換顯示隱藏資料夾。

---

## 4. 設定 Google Drive 設定檔

### 4-1. 建立設定檔

```
cp drive_config.template.json ~/.jrf/drive_config.json
```

### 4-2. 取得必要 ID

**Google Drive 資料夾 ID**

在瀏覽器開啟 Google Drive，進入您的輸入資料夾（INPUT）。  
網址列會顯示類似：

```
https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ
```

最後那一串英數字（`1aBcDeFgHiJkLmNoPqRsTuVwXyZ`）就是資料夾 ID。  
輸出資料夾（OUTPUT）同樣方式取得。

**Google Sheets ID**

開啟您的 Google Sheets 試算表，網址格式為：

```
https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ/edit
```

`/d/` 後面、`/edit` 前面的部分就是 Spreadsheet ID。

### 4-3. 編輯設定檔

用文字編輯器（例如 TextEdit）開啟 `~/.jrf/drive_config.json`，將 `FILL_IN` 替換為實際的 ID：

```json
{
  "work_root": "~/jrf-work",
  "input_folder_id": "（輸入資料夾 ID）",
  "output_folder_id": "（輸出資料夾 ID）",
  "spreadsheet_id": "（試算表 ID）",
  "queue_tab": "Queue",
  "archive_tab": "Archive",
  "volume": "",
  "poll_interval_seconds": 60
}
```

> `work_root` 是本機暫存資料夾，`~/jrf-work` 表示放在家目錄下的 `jrf-work` 資料夾，可依需求修改。

---

## 5. 安裝 Google Apps Script 自動排程

這個步驟讓 Google Drive 在偵測到新 PDF 時，自動將它加入處理佇列。

1. 開啟您的 Google Sheets 試算表
2. 點選上方選單 **「擴充功能」→「Apps Script」**
3. 刪除編輯器中的預設內容，將 `gas/on_pdf_upload.gs` 的全部內容貼上
4. 點選 **「儲存」**（Ctrl+S 或 Cmd+S）

### 設定 Script Properties

在 Apps Script 編輯器中：

1. 點選左側 **「專案設定」**（齒輪圖示）
2. 捲到最底部「指令碼屬性」區塊，點選 **「新增指令碼屬性」**
3. 新增以下屬性：

| 屬性名稱 | 值 |
|---|---|
| `INPUT_FOLDER_ID` | 您的輸入資料夾 ID |

### 設定時間觸發器

1. 點選左側 **「觸發器」**（時鐘圖示）
2. 點選右下角 **「新增觸發器」**
3. 設定如下：
   - 執行哪個函式：`checkForNewPdfs`
   - 選取事件來源：`時間驅動`
   - 選取時間型觸發器類型：`分鐘計時器`
   - 選取分鐘間隔：`每 5 分鐘`
4. 點選 **「儲存」**

首次儲存時系統會要求 Google 帳戶授權，請點選允許。

---

## 6. 驗證環境

在終端機的 `ocr-archive` 資料夾中執行：

```
uv run python -m tools.check_env
```

正常輸出範例：

```
[1] CLI tools
  ✓  pdftoppm found

[2] OAuth credentials  (~/.jrf/credentials.json)
  ✓  File present  (type=installed, client_id=…xxxxxxxx)

[3] Drive config  (~/.jrf/drive_config.json)
  ✓  File present
  ✓  work_root = ~/jrf-work
  ✓  input_folder_id = 1aBcDeFg…
  ✓  output_folder_id = 2xYzWvUt…
  ✓  spreadsheet_id = 3mNoPqRs…
  ✓  queue_tab = Queue
  ✓  archive_tab = Archive

  → Opening browser for Google OAuth…   ← 首次執行會開啟瀏覽器授權

[4] Google Drive API
  ✓  input folder accessible: 'INPUT'
  ✓  output folder accessible: 'OUTPUT'

[5] Google Sheets API
  ✓  Spreadsheet accessible: 'JRF Case Queue'
  ✓  Tab 'Queue' exists
  ✓  Tab 'Archive' exists

✓  All checks passed — environment is ready.
```

若看到 `✗`，請依照錯誤訊息指示修正，再重新執行。

**首次授權**：第一次執行時瀏覽器會跳出 Google 授權頁面，登入您的 Google 帳戶並點選「允許」，授權資訊會自動儲存至 `~/.jrf/token.json`，之後不需再手動授權。

---

## 7. 日常操作流程

環境建置完成後，日常使用方式如下：

### 上傳 PDF

將案件 PDF 上傳至 Google Drive **輸入資料夾（INPUT）**。  
Google Apps Script 每 5 分鐘自動偵測，偵測到新檔案後會在試算表的 `Queue` 頁籤新增一筆待處理記錄。

### 執行 OCR 管線

在終端機執行：

```
uv run python -m tools.drive_pipeline
```

管線會：
1. 從 Google Sheets 讀取待處理佇列
2. 下載 PDF 到本機暫存資料夾
3. 轉換為圖片，交由 Claude 逐頁 OCR
4. 將 OCR 結果 Markdown 上傳至輸出資料夾
5. 更新 Sheets 狀態為 `done`

### 搭配 AI 助理

如您使用 Claude Code，可直接在對話中說：  
「請幫我跑 OCR 管線」，AI 助理會自動執行上述步驟。

---

## 常見問題

**Q: `pdftoppm not found` 錯誤？**  
A: 執行 `brew install poppler` 後重試。

**Q: `credentials.json` 找不到？**  
A: 確認檔案路徑為 `~/.jrf/credentials.json`（注意 `.jrf` 開頭有點）。

**Q: Google 授權頁面顯示「這個應用程式未經驗證」？**  
A: 這是正常情況，因為這是內部工具。點選「進階」→「前往 JRF-OCR（不安全）」→「允許」即可。

**Q: 試算表沒有 Queue 或 Archive 頁籤？**  
A: `check_env.py` 會自動建立缺少的頁籤，重新執行一次即可。

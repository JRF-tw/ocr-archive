# JRF OCR 案件處理系統

將法院 PDF 案卷上傳至 Google Drive，由 AI 自動進行 OCR 辨識並輸出 Markdown 文字稿、書籤 PDF 與試算表歸檔。

## 文件

| 文件 | 用途 |
|------|------|
| [SETUP.md](SETUP.md) | 首次環境建置（安裝工具、設定 OAuth、Drive 設定檔） |
| [HOW-TO-DRIVE.md](HOW-TO-DRIVE.md) | 日常操作：從 Drive 下載 PDF、執行 OCR、上傳結果 |

## 環境驗證

```
uv run python -m tools.check_env
```

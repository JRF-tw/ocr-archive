/**
 * Google Apps Script — Enqueue newly uploaded PDFs to the Queue sheet.
 *
 * Setup:
 *   1. Open the Google Sheet → Extensions → Apps Script.
 *   2. Paste this file's contents.
 *   3. Set the script properties (Project Settings → Script Properties):
 *        INPUT_FOLDER_ID   — Drive folder ID to watch for new PDFs
 *        SPREADSHEET_ID    — target spreadsheet ID (required)
 *        QUEUE_TAB_NAME    — (optional) defaults to "Queue"
 *   4. Create a time-driven trigger:
 *        Triggers → Add Trigger → checkForNewPdfs → Time-driven → Every 5 minutes.
 *
 * Queue tab columns (A–H):
 *   file_id | file_name | status | enqueued_at | started_at | completed_at | work_dir | error
 *
 * Duplicate detection: if a file_id already exists in column A, the row is skipped.
 * Incremental scanning: uses LAST_CHECKED_TIMESTAMP to only check recently modified files.
 */

// ---------------------------------------------------------------------------
// Main entry point — bound to a time-based trigger (every 5 min)
// ---------------------------------------------------------------------------

/**
 * Check for new PDFs in the INPUT folder and enqueue any that are not
 * already in the Queue tab. Uses LAST_CHECKED_TIMESTAMP to only scan
 * files modified since the last check.
 */
function checkForNewPdfs() {
  var props = PropertiesService.getScriptProperties();
  var folderId = props.getProperty("INPUT_FOLDER_ID");
  if (!folderId) {
    Logger.log("ERROR: INPUT_FOLDER_ID script property not set.");
    return;
  }

  var sheet = getQueueSheet();
  var folder = DriveApp.getFolderById(folderId);

  // Use LAST_CHECKED_TIMESTAMP for incremental scanning
  var lastChecked = props.getProperty("LAST_CHECKED_TIMESTAMP");
  var searchStart = new Date();

  // Sanitize: old values may have been stored as ISO with milliseconds (.000Z).
  // Drive query requires RFC 3339 without milliseconds (e.g. 2024-01-15T10:30:00Z).
  if (lastChecked) {
    lastChecked = toRfc3339(new Date(lastChecked));
  }

  var files;
  if (lastChecked) {
    // Use createdDate (not modifiedDate): files synced via Drive for Desktop
    // carry the local OS modifiedDate which may pre-date LAST_CHECKED_TIMESTAMP,
    // causing them to be missed. createdDate reflects when the file first
    // appeared in Drive, regardless of local file age.
    var query = "mimeType = 'application/pdf' and createdDate >= '" + lastChecked + "'";
    files = folder.searchFiles(query);
  } else {
    // First run — scan all PDFs in folder
    files = folder.getFilesByType(MimeType.PDF);
  }

  var enqueued = 0;
  while (files.hasNext()) {
    var file = files.next();

    if (isAlreadyQueued(sheet, file.getId())) {
      continue;
    }

    enqueueFile(sheet, file);
    enqueued++;
  }

  // Update last-checked timestamp in RFC 3339 format (no milliseconds)
  props.setProperty("LAST_CHECKED_TIMESTAMP", toRfc3339(searchStart));
  Logger.log("Enqueued " + enqueued + " new PDF(s).");
}

// ---------------------------------------------------------------------------
// Helper functions
// ---------------------------------------------------------------------------

/**
 * Get or create the Queue tab from the configured spreadsheet.
 * Creates the tab with a header row if it doesn't exist.
 * @returns {GoogleAppsScript.Spreadsheet.Sheet}
 */
function getQueueSheet() {
  var props = PropertiesService.getScriptProperties();
  var spreadsheetId = props.getProperty("SPREADSHEET_ID");
  if (!spreadsheetId) {
    throw new Error("SPREADSHEET_ID script property not set.");
  }

  var ss = SpreadsheetApp.openById(spreadsheetId);
  var tabName = props.getProperty("QUEUE_TAB_NAME") || "Queue";
  var sheet = ss.getSheetByName(tabName);

  if (!sheet) {
    sheet = ss.insertSheet(tabName);
    sheet.appendRow([
      "file_id", "file_name", "status",
      "enqueued_at", "started_at", "completed_at",
      "work_dir", "error",
    ]);
  }

  return sheet;
}

/**
 * Check whether a file_id already exists in column A of the Queue sheet.
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet
 * @param {string} fileId
 * @returns {boolean}
 */
function isAlreadyQueued(sheet, fileId) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    return false; // only header row or empty
  }

  var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (ids[i][0] === fileId) {
      return true;
    }
  }
  return false;
}

/**
 * Format a Date as RFC 3339 UTC string without milliseconds,
 * e.g. "2024-01-15T10:30:00Z". Drive query strings require this format;
 * toISOString() produces milliseconds (.000Z) which Drive rejects.
 * Uses string manipulation instead of Utilities.formatDate to avoid
 * single-quote literal handling quirks in the Apps Script runtime.
 * @param {Date} date
 * @returns {string}
 */
function toRfc3339(date) {
  // "2026-05-24T10:30:00.000Z" → "2026-05-24T10:30:00Z"
  return date.toISOString().replace(/\.\d+Z$/, 'Z');
}

/**
 * One-time utility: delete LAST_CHECKED_TIMESTAMP from Script Properties.
 * Run this once from the Apps Script editor after deploying updated code
 * if the stored value is in the old Python ISO format (e.g. 2026-05-23T15:07:52.533937+00:00).
 * After running, the next checkForNewPdfs execution will scan all PDFs from scratch.
 */
function clearLastCheckedTimestamp() {
  PropertiesService.getScriptProperties().deleteProperty("LAST_CHECKED_TIMESTAMP");
  Logger.log("LAST_CHECKED_TIMESTAMP cleared. Next run will scan all PDFs.");
}

/**
 * Append a pending row to the Queue sheet for a new PDF file.
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet
 * @param {GoogleAppsScript.Drive.File} file
 */
function enqueueFile(sheet, file) {
  var now = new Date().toISOString();
  sheet.appendRow([
    file.getId(),
    file.getName(),
    "pending",
    now,    // enqueued_at
    "",     // started_at
    "",     // completed_at
    "",     // work_dir
    "",     // error
  ]);
}

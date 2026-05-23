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
    // Search for PDFs modified after last check
    var query = "mimeType = 'application/pdf' and modifiedDate >= '" + lastChecked + "'";
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
 * @param {Date} date
 * @returns {string}
 */
function toRfc3339(date) {
  return Utilities.formatDate(date, 'UTC', "yyyy-MM-dd'T'HH:mm:ss'Z'");
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

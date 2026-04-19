// Court Case Extraction Output Schema
// Dates: YYYY-MM-DD format

interface CaseOutput {
  metadata: {
    編號: string;           // Case ID (required)
    卷宗名稱: string;        // Case file name (required)
    當事人名稱: string[];    // Parties involved, min 1 (required)
    證據名稱?: string[];     // Evidence names
    起始頁數: number;        // Starting page >= 1 (required)
    終結頁數: number;        // Ending page >= 1 (required)
  };
  extracted_content: {
    raw_text: string;       // Full OCR text (required)
    structured_fields: {
      verdict?: string;     // 判決內容
      charges?: string[];   // 罪名
      facts?: string;       // 事實摘要
      key_dates?: {
        filed_date?: string;   // 提起日期
        verdict_date?: string; // 判決日期
        [key: string]: string | undefined;
      };
      evidence?: string[];  // 證據清單
    };
  };
}

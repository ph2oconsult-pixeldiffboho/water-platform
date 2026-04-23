/**
 * WaterPoint Concept Study Template — shared docx helpers
 * 
 * This file defines the reusable document primitives used across all
 * ph2o Consulting concept studies. Import these helpers at the top of
 * any project-specific report script.
 * 
 * Derived from Canungra STP Rev 20 (April 2026).
 * Template version: v1.0
 */

const docx = require("docx");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, PageBreak, ImageRun, ShadingType
} = docx;
const fs = require("fs");

// ============================================================================
// DESIGN SYSTEM — colours
// ============================================================================
const COLOUR_PRIMARY   = "2E75B6";   // Primary blue — main headings, accents
const COLOUR_ACCENT    = "1F4E79";   // Dark blue — H1 text
const COLOUR_TEXT      = "1F1F1F";   // Body text
const COLOUR_GREY      = "595959";   // Italic captions, sub-text
const COLOUR_WARN      = "BF6E00";   // Amber — risks, warnings
const COLOUR_WARN_BG   = "FFF2CC";   // Amber background — risk callouts
const COLOUR_INFO_BG   = "DEEBF7";   // Light blue background — info callouts
const COLOUR_SUCCESS   = "548235";   // Green — positive findings
const COLOUR_SUCCESS_BG = "E2F0D9";  // Green background — positive callouts
const COLOUR_DANGER    = "C00000";   // Red — critical issues
const COLOUR_DANGER_BG = "FBE5D6";   // Salmon background — critical callouts
const COLOUR_NEUTRAL_BG = "F2F2F2";  // Grey background — neutral content

// ============================================================================
// PARAGRAPH FACTORIES
// ============================================================================

/**
 * Standard paragraph with optional formatting.
 * opts: { bold, italics, size, color, before, after, alignment }
 */
function makePara(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({
      text: text,
      bold: opts.bold || false,
      italics: opts.italics || false,
      size: opts.size || 22,   // half-points, so 22 = 11pt
      color: opts.color || COLOUR_TEXT,
    })],
    spacing: {
      before: opts.before !== undefined ? opts.before : 60,
      after: opts.after !== undefined ? opts.after : 60,
    },
    alignment: opts.alignment || AlignmentType.LEFT,
  });
}

/**
 * Heading (levels 1-3). H1 = chapter, H2 = section, H3 = sub-section.
 */
function makeHeading(text, level = 1) {
  const sizes = { 1: 36, 2: 28, 3: 24 };  // half-points
  const colors = { 1: COLOUR_ACCENT, 2: COLOUR_PRIMARY, 3: COLOUR_PRIMARY };
  const beforeSpacing = { 1: 400, 2: 280, 3: 200 };
  const afterSpacing = { 1: 200, 2: 160, 3: 120 };
  
  return new Paragraph({
    children: [new TextRun({
      text: text,
      bold: true,
      size: sizes[level] || 22,
      color: colors[level] || COLOUR_TEXT,
    })],
    spacing: {
      before: beforeSpacing[level] || 120,
      after: afterSpacing[level] || 60,
    },
    heading: level === 1 ? HeadingLevel.HEADING_1 :
             level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
  });
}

/**
 * Bullet point.
 */
function bullet(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({
      text: text,
      size: opts.size || 22,
      color: opts.color || COLOUR_TEXT,
      italics: opts.italics || false,
      bold: opts.bold || false,
    })],
    bullet: { level: 0 },
    spacing: { before: 40, after: 40 },
  });
}

// ============================================================================
// TABLES
// ============================================================================

/**
 * Table cell with optional formatting.
 * cellContent can be:
 *   - string: plain text cell
 *   - {text, bold, italics, shade, color}: formatted cell
 */
function cell(cellContent, widthTwip) {
  let text, bold = false, italics = false, shade = null, color = COLOUR_TEXT;
  
  if (typeof cellContent === "string") {
    text = cellContent;
  } else {
    text = cellContent.text;
    bold = cellContent.bold || false;
    italics = cellContent.italics || false;
    shade = cellContent.shade || null;
    color = cellContent.color || COLOUR_TEXT;
  }
  
  const cellProps = {
    children: [new Paragraph({
      children: [new TextRun({
        text: text,
        bold: bold,
        italics: italics,
        size: 20,
        color: color,
      })],
      spacing: { before: 40, after: 40 },
    })],
    width: { size: widthTwip, type: WidthType.DXA },
  };
  
  if (shade) {
    cellProps.shading = {
      type: ShadingType.SOLID,
      color: shade,
    };
  }
  
  return new TableCell(cellProps);
}

/**
 * Table with header row and body rows.
 * headers: array of strings
 * rows: array of rows (each row is array of cells — string or {text,bold,shade})
 * widths: array of twip widths matching column count
 */
function makeTable(headers, rows, widths) {
  const headerRow = new TableRow({
    children: headers.map((h, i) => cell({
      text: h,
      bold: true,
      shade: COLOUR_PRIMARY,
      color: "FFFFFF",
    }, widths[i])),
    tableHeader: true,
  });
  
  const bodyRows = rows.map(row => new TableRow({
    children: row.map((c, i) => cell(c, widths[i])),
  }));
  
  return new Table({
    rows: [headerRow, ...bodyRows],
    width: { size: 100, type: WidthType.PERCENTAGE },
  });
}

// ============================================================================
// CALLOUT BOX
// ============================================================================

/**
 * Callout box: title + body with coloured background.
 * Commonly used colour combinations:
 *   - Risk/warning: COLOUR_WARN_BG + COLOUR_WARN
 *   - Positive:     COLOUR_SUCCESS_BG + COLOUR_SUCCESS
 *   - Info:         COLOUR_INFO_BG + COLOUR_PRIMARY
 *   - Critical:     COLOUR_DANGER_BG + COLOUR_DANGER
 */
function calloutBox(title, body, bgColor, accentColor) {
  const titlePara = new Paragraph({
    children: [new TextRun({
      text: title,
      bold: true,
      size: 24,
      color: accentColor,
    })],
    spacing: { before: 120, after: 60 },
    shading: { type: ShadingType.SOLID, color: bgColor },
  });
  
  // Split body on \n for multi-line paragraphs
  const bodyParas = body.split("\n").map(line =>
    new Paragraph({
      children: [new TextRun({
        text: line,
        size: 22,
        color: COLOUR_TEXT,
      })],
      spacing: { before: 40, after: 40 },
      shading: { type: ShadingType.SOLID, color: bgColor },
    })
  );
  
  return [titlePara, ...bodyParas];
}

// ============================================================================
// CHART / IMAGE EMBEDDING
// ============================================================================

/**
 * Embed a chart image with caption.
 * Returns an array of paragraphs (image + caption).
 */
function embedChart(imagePath, caption, widthInches = 6.5) {
  const imageBuffer = fs.readFileSync(imagePath);
  const imagePara = new Paragraph({
    children: [new ImageRun({
      data: imageBuffer,
      transformation: {
        width: widthInches * 72,
        height: widthInches * 72 * 0.6,  // approximate aspect
      },
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
  });
  
  const captionPara = new Paragraph({
    children: [new TextRun({
      text: caption,
      italics: true,
      size: 20,
      color: COLOUR_GREY,
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 240 },
  });
  
  return [imagePara, captionPara];
}

// ============================================================================
// PAGE BREAK
// ============================================================================
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ============================================================================
// EXPORTS
// ============================================================================
module.exports = {
  // Colours
  COLOUR_PRIMARY, COLOUR_ACCENT, COLOUR_TEXT, COLOUR_GREY,
  COLOUR_WARN, COLOUR_WARN_BG,
  COLOUR_INFO_BG,
  COLOUR_SUCCESS, COLOUR_SUCCESS_BG,
  COLOUR_DANGER, COLOUR_DANGER_BG,
  COLOUR_NEUTRAL_BG,
  
  // Factories
  makePara, makeHeading, bullet,
  cell, makeTable,
  calloutBox,
  embedChart,
  pageBreak,
  
  // Re-exports (so project scripts can use directly)
  Document, Packer, Paragraph, TextRun,
  Table, TableRow, TableCell,
  PageBreak, ImageRun,
  AlignmentType, HeadingLevel,
};

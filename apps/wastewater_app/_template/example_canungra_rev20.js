const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  BorderStyle, WidthType, ShadingType, PageBreak,
  PageNumber, ImageRun,
} = require('docx');

const COLOUR_PRIMARY = "2E75B6";
const COLOUR_ACCENT = "1F4E79";
const COLOUR_GREY = "595959";
const COLOUR_WARN = "BF6E00";
const COLOUR_WARN_BG = "FFF2CC";
const COLOUR_INFO_BG = "DEEBF7";
const COLOUR_CAUTION_BG = "FBE5D6";
const FONT = "Arial";

function makePara(text, opts = {}) {
  return new Paragraph({
    spacing: { before: opts.before ?? 0, after: opts.after ?? 120 },
    alignment: opts.alignment ?? AlignmentType.LEFT,
    indent: opts.indent,
    shading: opts.shading,
    border: opts.border,
    children: [new TextRun({
      text,
      font: FONT,
      size: opts.size ?? 22,
      bold: opts.bold ?? false,
      italics: opts.italics ?? false,
      color: opts.color ?? "000000",
    })],
  });
}

function makeHeading(text, level) {
  const sizeMap = { 1: 32, 2: 28, 3: 24 };
  const colorMap = { 1: COLOUR_ACCENT, 2: COLOUR_ACCENT, 3: COLOUR_PRIMARY };
  return new Paragraph({
    heading: ["HEADING_1", "HEADING_2", "HEADING_3"][level-1],
    spacing: { before: level === 1 ? 360 : 240, after: level === 1 ? 180 : 120 },
    children: [new TextRun({
      text, font: FONT, bold: true,
      size: sizeMap[level],
      color: colorMap[level],
    })],
  });
}

function cell(text, opts = {}) {
  const width = opts.width ?? 1500;
  const isHeader = opts.header ?? false;
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
    },
    shading: isHeader
      ? { fill: COLOUR_PRIMARY, type: ShadingType.CLEAR }
      : (opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined),
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({
      alignment: opts.alignment ?? AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text),
        font: FONT,
        size: opts.size ?? 20,
        bold: isHeader || (opts.bold ?? false),
        color: isHeader ? "FFFFFF" : (opts.color ?? "000000"),
      })],
    })],
  });
}

function makeTable(headerRow, dataRows, columnWidths) {
  const totalWidth = columnWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headerRow.map((text, i) =>
          cell(text, { width: columnWidths[i], header: true, alignment: AlignmentType.CENTER })
        ),
      }),
      ...dataRows.map((row, rowIdx) =>
        new TableRow({
          children: row.map((text, i) => {
            const opts = { width: columnWidths[i] };
            if (rowIdx % 2 === 1) opts.shade = "F2F2F2";
            if (typeof text === 'object' && text !== null) {
              Object.assign(opts, text);
              return cell(text.text, opts);
            }
            return cell(text, opts);
          }),
        })
      ),
    ],
  });
}

function bullet(text, opts = {}) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 80 },
    children: [new TextRun({ text, font: FONT, size: 22, ...opts })],
  });
}

// Callout box — single-cell table with coloured background and thick accent border
// Shading applied at both cell and paragraph level for robust rendering across
// Word / LibreOffice / Google Docs
function calloutBox(title, text, bgColor, accentColor) {
  const titlePara = new Paragraph({
    spacing: { after: 120 },
    shading: { fill: bgColor, type: ShadingType.CLEAR },
    children: [new TextRun({ 
      text: title, font: FONT, bold: true, size: 24, color: accentColor 
    })],
  });
  
  const bodyParas = text.split('\n').map(line =>
    new Paragraph({
      spacing: { after: 80 },
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      children: [new TextRun({ text: line, font: FONT, size: 22 })],
    })
  );
  
  return new Table({
    width: { size: 9200, type: WidthType.DXA },
    columnWidths: [9200],
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: 9200, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        margins: { top: 200, bottom: 200, left: 240, right: 240 },
        borders: {
          top: { style: BorderStyle.SINGLE, size: 18, color: accentColor },
          bottom: { style: BorderStyle.SINGLE, size: 18, color: accentColor },
          left: { style: BorderStyle.SINGLE, size: 18, color: accentColor },
          right: { style: BorderStyle.SINGLE, size: 18, color: accentColor },
        },
        children: [titlePara, ...bodyParas],
      })],
    })],
  });
}


// Embed a chart image with caption
function embedChart(imagePath, captionText, width = 550, height = 310) {
  const imageBuffer = fs.readFileSync(imagePath);
  return [
    new Paragraph({
      spacing: { before: 120, after: 60 },
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({
        data: imageBuffer,
        transformation: { width, height },
      })],
    }),
    new Paragraph({
      spacing: { before: 0, after: 240 },
      alignment: AlignmentType.CENTER,
      children: [new TextRun({
        text: captionText,
        font: FONT, italics: true, size: 20, color: COLOUR_GREY,
      })],
    }),
  ];
}

const content = [];

// ============== TITLE PAGE ==============
content.push(
  new Paragraph({
    spacing: { before: 1800, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "CANUNGRA STP INTENSIFICATION",
      font: FONT, bold: true, size: 44, color: COLOUR_ACCENT,
    })],
  }),
  new Paragraph({
    spacing: { before: 120, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "CONCEPT OPTIONS STUDY",
      font: FONT, bold: true, size: 36, color: COLOUR_ACCENT,
    })],
  }),
  new Paragraph({
    spacing: { before: 240, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "5-Stage Bardenpho MBR — Screening-Level Assessment",
      font: FONT, italics: true, size: 28, color: COLOUR_GREY,
    })],
  }),
  new Paragraph({
    spacing: { before: 120, after: 0 },
    alignment: AlignmentType.CENTER,
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: COLOUR_PRIMARY, space: 8 } },
    children: [new TextRun({ text: "", font: FONT, size: 20 })],
  }),
);

// Status callout on title page
content.push(
  new Paragraph({ spacing: { before: 800, after: 0 }, children: [new TextRun({ text: "" })] })
);
content.push(calloutBox(
  "Document status",
  "This is a SCREENING-LEVEL concept study. It identifies a credible intensification pathway and defines the verification workstream required before capital commitment.\n\nIt is NOT a decision-grade capital basis. The concept requires completion of seven verification work packages (RFC-01 to RFC-07, Section 7) before QUU should proceed to funded design.",
  COLOUR_WARN_BG, COLOUR_WARN
));

content.push(
  new Paragraph({
    spacing: { before: 1200, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Prepared for:", font: FONT, size: 22, color: COLOUR_GREY })],
  }),
  new Paragraph({
    spacing: { before: 60, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "Queensland Urban Utilities",
      font: FONT, bold: true, size: 28, color: COLOUR_ACCENT,
    })],
  }),
  new Paragraph({
    spacing: { before: 600, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Prepared by:", font: FONT, size: 22, color: COLOUR_GREY })],
  }),
  new Paragraph({
    spacing: { before: 60, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "ph2o Consulting",
      font: FONT, bold: true, size: 28, color: COLOUR_ACCENT,
    })],
  }),
  new Paragraph({
    spacing: { before: 1200, after: 0 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: "Revision 20 ·  April 2026  ·  S2-E aerobic-shifted variant added",
      font: FONT, italics: true, size: 22, color: COLOUR_GREY,
    })],
  }),
  // Force a hard page break onto page 2 for Document status and scope
  new Paragraph({ 
    pageBreakBefore: true,
    spacing: { before: 0, after: 0 },
    children: [new TextRun({ text: "" })],
  }),
);

// ============== DOCUMENT STATUS AND SCOPE ==============
// Force new page for Document status and scope section
content.push(new Paragraph({
  pageBreakBefore: true,
  spacing: { before: 0, after: 0 },
  children: [new TextRun({ text: "" })],
}));
content.push(makeHeading("Document status and scope", 1));

content.push(makePara(
  "This Rev 20 document has been issued following an independent red-team review of Rev 4. The review correctly identified that the earlier document read as more decision-ready than the underlying evidence supports. Rev 5 repositioned the document as a screening-level Concept Study that identifies a credible intensification pathway and defines the verification package required before capital commitment. Rev 6 added a first-principles alkalinity balance; Rev 7 corrected the framing of that analysis following independent review, identifying alkalinity sufficiency as a major unresolved assumption (F8). Rev 8 re-examines the IFAS component following further independent review. The S1B (IFAS) feasibility case has been strengthened with three specific risks now flagged (F2 updated, F9 new) and is repositioned from \"no-regret immediate action\" to \"pre-feasibility verification required\" alongside S2.",
  { after: 120 }
));

content.push(makeHeading("Confidence level of this study", 2));
content.push(bullet("Screening-level process modelling. Kinetics are regional preliminary values, not site-calibrated."));
content.push(bullet("Capex estimates are indicative and based on comparable projects. They will require vendor-specific refinement at pre-feasibility stage."));
content.push(bullet("Membrane system footprint and cost are concept-level. Vendor layouts are required for decision-grade numbers."));
content.push(bullet("The following disciplines are out of scope and require separate assessment: hydraulic (inlet works, flow splitting), aeration (blower capacity, oxygen transfer, alpha-factor), solids handling (WAS production, dewatering, biosolids), outlet works, UV disinfection, structural, and electrical capacity."));

content.push(makeHeading("What this document establishes", 2));
content.push(bullet("A process-viable concept pathway to substantial capacity intensification within the existing site footprint, subject to resolution of the licence mass load basis (RFC-10, Stage 0 gateway) and verification of excluded disciplines (aeration, hydraulics, solids, structural, electrical, phosphorus)"));
content.push(bullet("A staged implementation sequence starting with no-regret operational upgrades"));
content.push(bullet("A defined verification workstream (seven work packages) that must complete before capital commitment on major intensification"));
content.push(bullet("Screening-level capex bands sufficient for strategic planning, not tender"));

content.push(makeHeading("What this document does NOT establish", 2));
content.push(bullet("That the intensified configuration will achieve the modelled capacity in practice — this requires site kinetic calibration and dynamic verification"));
content.push(bullet("That the excluded disciplines (aeration, hydraulics, structural, solids) will not bind capacity before the licence mass load — these require confirmation in Phase 2"));
content.push(bullet("That the TN-optimised intensification path will not create a TP compliance or chemical dosing problem that materially alters the operability or cost case. TP remains out of scope at this screening level — see RFC-06. This is a genuine open question, not a formality."));
content.push(bullet("Firm capex numbers — vendor and structural engagement is required"));
content.push(bullet("That methanol is the optimal external carbon source — alternative carbons (ethanol, glycerol, acetate) should be assessed in Phase 2"));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== EXECUTIVE SUMMARY ==============
content.push(makeHeading("Executive summary", 1));

content.push(makePara(
  "Canungra STP is a 5-stage Bardenpho MBR licensed for 1,500 EP. The plant discharges to limits including TN 5/10/15 mg/L (median/80%ile/max) and an annual mass load of 607 kg TN/yr. Queensland Urban Utilities has identified a need to assess options for intensification to support catchment growth."
));

content.push(makePara(
  "This Concept Study evaluates three scenarios and finds a potentially high-value intensification pathway centred on repurposing the existing MBR tank volume as post-anoxic biology, with membranes relocating to a compact new hollow-fibre installation. The concept is technically credible and merits progression to a verification phase."
));

content.push(makeHeading("Key findings", 2));

content.push(bullet("The existing MBR bay (118 kL, two 59 kL cells separated by an internal wall) can potentially be converted to post-anoxic duty by removing the internal wall. Combined with the existing 38 kL post-anoxic, this yields a conceptual 156 kL post-anoxic volume — a 4.1× increase over the Rev B configuration. Structural feasibility of wall removal is a critical hold point."));
content.push(bullet("Process modelling indicates that at this expanded post-anoxic volume, with appropriate recycle optimisation and methanol supplementation, under the adopted Interpretation B basis, the biology does not impose a capacity constraint below approximately 6,000 EP. Peak TN under MML loading approaches the 15 mg/L limit at this point and becomes the governing constraint at that point, subject to confirmation of aeration, hydraulic, solids, structural, and electrical capacity."));
content.push(bullet("Scenario S1A (controls and operational upgrades only: flow-paced recycles, VSD upgrades, instrumentation) is identified as a low-regret immediate action. Estimated capex AUD 280k. Captures most of the no-capex diurnal-peak benefit identified in the study."));
content.push(bullet("Scenario S1B (S1A plus IFAS aerobic carriers) is repositioned in Rev 8 from \"conditional next step\" to \"pre-feasibility verification required\". Three IFAS-specific risks are now flagged: aeration/oxygen transfer with carriers installed (F2), alkalinity sufficiency (F8), and carrier retention/MBR protection (F9 new). S1B capex revised upward to reflect realistic retention screen scope. Estimated capex AUD ~900k total including S1A."));
content.push(bullet("Scenario S2 has been resolved into five physically distinct configurations spanning a capacity range of 4,500–6,000 EP and a capex range of AUD 3.30–3.62M. Two preferred concepts for pre-feasibility development sit alongside each other: S2-C3 (series-then-parallel post-anoxic, modelled capacity ceiling 5,500 EP, capex AUD 3.56M) and S2-E (aerobic-shifted with flow balancing, modelled capacity 5,500-6,000 EP depending on flow balance sizing, capex AUD 3.5-3.8M). S2-E offers simpler process flow but depends on flow balancing performance that requires dynamic simulation to confirm (RFC-12) without wall removal, providing the best balance of capacity, capex, operability, and risk profile. See Section 4.6 for the full S2 variant analysis."));

content.push(bullet("Increased annual TN discharge. Growth from 1,500 EP to 5,500 EP at S2-C3 approximately doubles annual TN discharge to the receiving waterway (from 578 to 1,171 kg/yr). This is within the scaled licence limit under Interpretation B. Treatment efficiency (% TN removal) actually improves from 91% at S0 to 95% at S2-C3 — the higher total discharge reflects serving more people, not degraded treatment. See Section 5.4."));

content.push(bullet("CRITICAL OPEN QUESTION — licence mass load interpretation. The 607 kg TN/yr limit is derived from the 1,500 EP design (Rev B Table 2.1 footnote 1) and may or may not scale with re-licensed EP. Rev 18 tests Interpretation B as the strategic planning basis (mass limit scales with design EP per the Rev B derivation formula), under which the process model indicates S2 could potentially remain concentration-compliant up to approximately 6,000 EP. The actual relicensing basis remains unresolved. Under Interpretation A (hard 607 kg/yr cap), S2 capacity reverts to 4,000 EP. RFC-10 is the Stage 0 gateway — regulator consultation should precede any capital commitment. See Section 2.3."));
content.push(bullet("The capacity estimate is most sensitive to the K3 MeOH-acclimated denitrification rate, which is currently a regional assumption rather than site-calibrated. Sensitivity across the full literature range (0.05 to 0.15 gN/gVSS/d at 20°C, Table 3.2) shows a three-regime structure: at K3 ≤ 0.07 capacity falls by 22–37% to 2,500–3,100 EP; at K3 = 0.08–0.09 capacity falls by 10–15% to 3,400–3,600 EP; at K3 ≥ 0.11 capacity is mass-load-bound at 4,000 EP. Bench testing (RFC-01) would locate Canungra biomass within this range."));
content.push(bullet("Alkalinity sufficiency for nitrification at 4,000 EP is a major unresolved assumption. If Canungra influent alkalinity is at the lower end of regional estimates (~250 mg CaCO3/L), the plant is alkalinity-deficient at peak load and existing NaOH dosing capacity may be inadequate. Plant composite sampling for influent alkalinity is a Phase 1 priority."));
content.push(bullet("IFAS carrier retention upstream of the MBR is a previously under-scoped mechanical integration requirement. Any carrier escape would damage HF membranes. Retention screen design, headloss under peak flow, maintenance access, and failure containment must be established before S1B can be endorsed. See F9."));

content.push(makeHeading("Recommended path forward", 2));

content.push(makePara(
  "Immediate action: implement S1A (controls and operational upgrades) as a low-regret upgrade providing current compliance margin and compatible with any subsequent pathway.",
  { bold: true, after: 120 }
));

content.push(makePara(
  "Before any capital commitment on S1B or S2: complete the seven-package verification workstream defined in Section 7 (RFC-01 through RFC-07).",
  { bold: true, after: 120 }
));

content.push(makePara(
  "Decision gate: proceed to S2 detailed design only if (i) K3 methanol kinetics are confirmed by bench testing on Canungra biomass, (ii) aeration capacity is confirmed adequate, (iii) membrane vendor concept layouts confirm capex and footprint, and (iv) structural engineering confirms MBR wall removal is viable.",
  { before: 120, after: 120 }
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 1. INTRODUCTION ==============
content.push(makeHeading("1. Introduction", 1));

content.push(makeHeading("1.1 Background", 2));
content.push(makePara(
  "Canungra STP serves a small catchment in the Scenic Rim region of South East Queensland, operating under Queensland Urban Utilities. The plant was upgraded in 2012–2013 from an extended-aeration oxidation ditch to a 5-stage Bardenpho MBR configuration, designed by Tyr Group and constructed by Aquatec-Maxcon to meet revised effluent licence limits."
));
content.push(makePara(
  "The 2012 upgrade retained the existing oxidation ditch tankage (reconfigured as anaerobic and primary anoxic zones) and added new aerobic, de-aeration, post-anoxic and Kubota flat-sheet MBR tanks. The plant was sized for 1,500 EP at average annual load (AAL)."
));
content.push(makePara(
  "As-built civil drawings (Aquatec-Maxcon 8720Y-050, 8720E-001) confirm the MBR bay consists of two 59 kL cells of 4,100 mm × 5,200 mm × 2,780 mm water depth, separated by an internal dividing wall. The hypothesis tested in this Concept Study is that this dividing wall is non-structural and removable, enabling conversion of the combined 118 kL envelope to post-anoxic service. Structural confirmation is a required verification item."
));

content.push(makeHeading("1.2 Scope boundaries", 2));
content.push(makePara("Explicitly in scope:", { after: 60 }));
content.push(bullet("Biological process modelling (5-stage Bardenpho with MBR)"));
content.push(bullet("Membrane hydraulic feasibility (concept-level footprint)"));
content.push(bullet("Recycle design and control strategy"));
content.push(bullet("Screening-level capex estimates"));

content.push(makePara("Explicitly out of scope (requires separate assessment):", { after: 60, before: 120 }));
content.push(bullet("Inlet hydraulics, screening, grit removal, flow splitting"));
content.push(bullet("Aeration blower capacity, diffuser turn-up, oxygen transfer and alpha-factor validation"));
content.push(bullet("Solids handling, sludge dewatering, biosolids disposal"));
content.push(bullet("Civil structural review including MBR wall removal feasibility"));
content.push(bullet("Outlet works, UV disinfection, discharge modelling"));
content.push(bullet("Electrical and instrumentation capacity (other than concept-level pump and VSD costs)"));
content.push(bullet("Phosphorus compliance under intensified configuration (flagged as Phase 2 verification item)"));

content.push(makeHeading("1.3 Approach", 2));
content.push(makePara(
  "A Bardenpho steady-state mass balance model was constructed, treating the primary anoxic and post-anoxic zones as two sequential denitrification stages with independent kinetic, substrate, and delivery constraints. The model couples to a diurnal simulator applying the Rev B Figure 3.1 load profile at 30-minute resolution, with first-order MBR tank buffering."
));
content.push(makePara(
  "Scenarios were evaluated across 1,500 to 5,500 EP at 17°C winter design temperature under both AAL and maximum monthly load (MML) influent conditions. Compliance was tested against concentration-based licence limits (median, 80%ile, max) and the annual mass load of 607 kg TN/yr."
));
content.push(makePara(
  "The model has been verified against the Rev B BioWIN predictions at 1,500 EP design and passes a suite of seven regression tests. However, model predictions beyond the Rev B operating envelope (at intensified configurations and higher loads) rest on regional kinetic assumptions that have not been calibrated on Canungra biomass. Verification of these assumptions is required before capital decisions (see Section 7)."
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 2. PLANT BACKGROUND ==============
content.push(makeHeading("2. Plant background and baseline", 1));

content.push(makeHeading("2.1 As-built process configuration", 2));
content.push(makeTable(
  ["Zone", "Volume (kL)", "Function"],
  [
    ["Anaerobic", "68.8", "Biological P release (in repurposed oxidation ditch)"],
    ["Primary anoxic", "120.0", "Denitrification on influent RBCOD via A-recycle"],
    ["Aerobic", "117.0", "Nitrification, BOD oxidation, PAO P uptake"],
    ["De-aeration", "21.8", "DO stripping before post-anoxic"],
    ["Post-anoxic", "38.0", "Endogenous + sugar-dosed denitrification"],
    ["MBR Tank 1", "59.0", "Membrane separation (Kubota flat-sheet)"],
    ["MBR Tank 2", "59.0", "Membrane separation (Kubota flat-sheet)"],
    [{ text: "Total reactor", bold: true }, { text: "483.6", bold: true }, ""],
  ],
  [2400, 1400, 5560]
));
content.push(makePara("Table 2.1: Rev B as-built reactor zone configuration (drawings 8720Y-050, 8720E-001)", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("2.2 Licence limits", 2));
content.push(makeTable(
  ["Parameter", "Median", "80%ile", "Max", "Annual mass"],
  [
    [{ text: "TN", bold: true }, "5 mg/L", "10 mg/L", "15 mg/L", "607 kg/yr"],
    [{ text: "TP", bold: true }, "1 mg/L", "2 mg/L", "3 mg/L", "122 kg/yr"],
    [{ text: "NH3-N", bold: true }, "—", "2 mg/L", "4 mg/L", "—"],
    [{ text: "BOD5", bold: true }, "—", "15 mg/L", "20 mg/L", "—"],
    [{ text: "TSS", bold: true }, "—", "23 mg/L", "30 mg/L", "—"],
  ],
  [2000, 1600, 1600, 1600, 2560]
));
content.push(makePara("Table 2.2: Effluent licence limits (source: Rev B Section 2)", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("2.3 Mass load basis — two interpretations", 2));
content.push(makePara(
  "The 607 kg TN/yr annual mass load limit is a derived quantity, not an independent environmental cap. Per Rev B Table 2.1 footnote 1, the formula is:",
  { after: 60 }
));

content.push(makePara(
  "    Annual Mass Load = (Annual Median Concentration) × (Annual Mean Daily Flow) × 365 days × 1.10",
  { italics: true, before: 60, after: 60 }
));

content.push(makePara(
  "At the 1,500 EP design population:",
  { after: 60 }
));

content.push(bullet("Annual median TN concentration = 5 mg/L (licence limit)"));
content.push(bullet("Annual mean daily flow = 1,500 × 0.2 L/EP/d = 300 kL/d = 0.3 ML/d (ADWF)"));
content.push(bullet("Days in year = 365"));
content.push(bullet("Wet weather allowance = +10%"));
content.push(bullet("→ 5 × 0.3 × 365 × 1.10 ≈ 603 kg/yr, rounded to 607 kg/yr"));

content.push(makePara(
  "This creates an ambiguity for the intensification case. When the plant is re-licensed at 2,500 or 4,000 EP, the interpretation of the mass load limit is critical:",
  { after: 180 }
));

content.push(calloutBox(
  "Interpretation A — Hard environmental cap (conservative)",
  "607 kg/yr is a fixed environmental limit that does not scale with plant capacity. At higher EP, effluent concentrations must decrease to stay within the cap. At 4,000 EP, this forces effluent TN to approximately 2 mg/L to keep annual mass below 607 kg/yr. This is the assumption used in Revs 1–14 of this study.\n\nApplies when: the receiving waterway has limited nutrient assimilative capacity, catchment-wide nutrient caps apply, or the licence condition is explicitly written as 'not to exceed 607 kg/yr regardless of plant capacity'.",
  COLOUR_WARN_BG, COLOUR_WARN
));

content.push(calloutBox(
  "Interpretation B — Derived limit, re-scaled with design EP",
  "607 kg/yr was calculated at the 1,500 EP design point. When the plant is re-licensed at higher EP, the same formula is applied with the new design flow: the concentration limits (5/10/15 mg/L median/80%ile/peak) remain fixed, and the mass limit is recalculated proportionally. At 2,500 EP: ~1,012 kg/yr. At 4,000 EP: ~1,619 kg/yr.\n\nApplies when: concentration limits are the fundamental environmental standard; the mass load is a derived reporting metric; the regulator's policy supports re-scaling of mass limits at re-licensing.",
  COLOUR_INFO_BG, COLOUR_PRIMARY
));

content.push(makePara(
  "Neither interpretation is unambiguously correct without regulator consultation. See Section 7.4 and RFC-10 for the Phase 2 action to resolve this with Queensland Urban Utilities and the Department of Environment and Science.",
  { after: 120 }
));

embedChart('/home/claude/report_charts/chart3_mass_load.png',
  'Figure 2.1: Annual TN mass discharge versus EP under both interpretations. The two envelopes coincide at 1,500 EP (the derivation point) and diverge at higher EP. Under Interpretation A, S2 is mass-bound at 4,000 EP. Under Interpretation B, S2 is concentration-bound at approximately 6,000 EP.').forEach(p => content.push(p));

content.push(makeHeading("Why this matters", 3));
content.push(makePara(
  "The distinction between Interpretation A and Interpretation B materially changes the S2 business case:",
  { after: 60 }
));

content.push(makeTable(
  ["Question", "Under Interpretation A", "Under Interpretation B"],
  [
    ["S2 maximum EP", "4,000 (mass-bound)", "~6,000 (concentration-bound on peak TN)"],
    ["S2 capex vs value", "AUD 3.36M for 4,500 EP of new capacity", "AUD 3.36M for 4,500 EP of new capacity"],
    ["DN filter polishing value", "Required for growth beyond ~6,000 EP (new territory for DN filter case)", "Required for growth beyond ~6,000 EP (new territory for DN filter case)"],
    ["Long-term catchment horizon", "S2 is a 20-year solution at most", "S2 is a 30-40 year solution"],
    ["K3 MeOH sensitivity urgency", "High (binds at 4,000 EP mass cap)", "Lower (concentration limits bind first)"],
  ],
  [2000, 2500, 3100]
));
content.push(makePara("Table 2.3: Impact of licence interpretation on S2 business case", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "Rev 18 tests Interpretation B as the strategic planning basis for the capacity numbers, decision trees, and preferred concepts that follow. This is not the adopted design basis — the actual relicensing basis remains unresolved and must be confirmed through RFC-10 before any capital commitment. Where Interpretation A applies, the capacity envelope reverts to ≤4,000 EP and the variant ranking changes accordingly. The S2 business case under Interpretation B is substantially stronger than under Interpretation A — if Interpretation B is confirmed at relicensing, the AUD 3.36M capex at S2-A/B could deliver up to 4,500 EP of new capacity (growth from 1,500 to 6,000 EP) rather than 2,500 EP (growth from 1,500 to 4,000 EP). However, if the regulator subsequently applies Interpretation A at re-licensing, the capacity numbers in Rev 16 revert to those shown in Revs 11–15.",
  { after: 120 }
));

content.push(new Paragraph({ children: [new PageBreak()] }));


content.push(makeHeading("2.5 Process flow diagram — Rev B baseline", 2));
content.push(makePara(
  "The existing 5-stage Bardenpho MBR configuration is shown in PFD 1 below. This is the starting point for all intensification scenarios. The two 59 kL MBR cells are separated by an internal dividing wall, retained throughout all S1 and S2-B/C3/D configurations.",
  { after: 120 }
));

embedChart('/home/claude/pfds_v2/pfd_S0_alternative.png',
  'Figure 2.2: PFD 2 — S0 Rev B Alternative Dry Weather Operation (the design intent). Existing 1,500 EP plant.').forEach(p => content.push(p));

content.push(makeHeading("2.6 Rev B alternating Phase 1 / Phase 2 dry weather operation", 2));
content.push(makePara(
  "An important context for understanding the S2 intensification scenarios is that the Rev B as-built plant already operates with one MBR tank functioning as additional post-anoxic mass. Per Rev B Section 7.1, the design intent is for the membrane aeration, permeate withdrawal, and S-Recycle intake to alternate between the two MBR tanks every 30 minutes during dry weather operation."
));

content.push(makeHeading("Conventional vs Alternative dry weather operation", 3));
content.push(makePara(
  "Rev B describes two operating modes for the alternating cycle:"
));
content.push(bullet("Conventional mode: the off-line MBR tank has no flow or aeration during its off-line period. Some endogenous denitrification occurs but the off-line tank is largely lost as active bioreactor tankage."));
content.push(bullet("Alternative mode (the chosen design): mixed liquor flows from the post-anoxic zone through the off-line MBR tank to the operating MBR tank. The off-line tank effectively extends the post-anoxic mass fraction. Per Rev B, this reduces effluent TN by approximately 1 mg/L vs conventional mode."));

content.push(makePara(
  "PFD 1 (Figure 2.3 below) shows the conventional mode for reference. PFD 2 (Figure 2.2 above) shows the Alternative mode that represents the actual design intent for the Canungra plant."
));

embedChart('/home/claude/pfds_v2/pfd_S0_conventional.png',
  'Figure 2.3: PFD 1 — S0 Rev B Conventional Dry Weather Operation (Phase 1 with MBR-2 off-line). Off-line tank is dark grey.').forEach(p => content.push(p));

content.push(makeHeading("Implications for S2 intensification", 3));
content.push(makePara(
  "The Alternative mode demonstrates that Rev B already designed for one MBR tank to function as post-anoxic. The S2 intensification scenarios extend this concept by making the post-anoxic role of the former MBR tank (or tanks) permanent rather than alternating, while relocating membrane duty to a new compact HF MBR. This is an evolution of an existing design intent rather than a radical reconfiguration of the plant."
));

content.push(makePara(
  "Per Rev B Section 5.1.2, the cross-connection between MBR tanks already includes baffle plates 'to limit short-circuiting when the un-aerated MBR tank is used as additional post-anoxic mass fraction during dry weather flows'. This existing infrastructure can be leveraged in the S2 variants — particularly S2-B and S2-C3 which retain the wall and operate the former MBR cells as parallel post-anoxic chambers."
));

content.push(makeHeading("2.3 Diurnal loading profile", 2));
content.push(makePara("Rev B Figure 3.1 provides the design diurnal profile, digitised at 30-minute resolution:", { after: 60 }));
content.push(bullet("Peak flow 2.26 × ADWF at 08:30"));
content.push(bullet("Peak TKN concentration 1.30 × daily mean at 10:00"));
content.push(bullet("Peak combined mass load (flow × TKN) reaches 2.66 × daily mean"));
content.push(makePara(
  "The Rev B design uses a fixed absolute A-recycle flow setpoint. During the diurnal flow peak, this setpoint translates to an instantaneous ratio of only 6.2 × Q — well below the 14 × ADWF nominal ratio. Converting the A-recycle control to flow-paced (ratio of instantaneous Q) is identified as a central intervention in Scenarios S1A, S1B, and S2 (Section 4).",
  { before: 60 }
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 3. MODELLING APPROACH ==============
content.push(makeHeading("3. Modelling approach and limitations", 1));

content.push(makeHeading("3.1 Bardenpho two-zone denitrification", 2));
content.push(makePara(
  "The model treats the primary anoxic and post-anoxic zones as two sequential denitrification stages with independent kinetic, substrate, and delivery constraints:"
));
content.push(bullet("Primary anoxic zone (fed by A-recycle): removes nitrate using readily-biodegradable COD from the influent. Kinetically fast but bounded by COD delivery and recycle flow."));
content.push(bullet("Post-anoxic zone (receives forward flow only): uses endogenous respiration and supplemented methanol for nitrate removal. Slower kinetics but polishes to very low residual NO3."));
content.push(makePara(
  "The model solves the full mass balance across both anoxic zones with recycle iteration. This approach captures the two-zone nature of the 5-stage Bardenpho; the conclusions of this study are not derivable from single-anoxic effluent formulas."
));

content.push(makeHeading("3.2 Kinetic parameters — regional preliminary values", 2));

content.push(calloutBox(
  "Caveat on kinetic confidence",
  "The kinetic parameters used in this study are regional preliminary values drawn from typical South East Queensland municipal wastewater behaviour. They have NOT been calibrated on Canungra biomass.\n\nThe K3 methanol-acclimated rate (0.12 gN/gVSS/d at 20°C) is the single most sensitive assumption in the study and governs the intensified-scenario capacity. Bench testing on Canungra biomass is required before capital commitment on Scenario S2.",
  COLOUR_WARN_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(makeTable(
  ["Parameter", "Value (20°C)", "Description", "Confidence"],
  [
    ["K2 primary anoxic", "0.11 gN/gVSS/d", "RBCOD-driven denit", "Reasonable regional starting value"],
    ["K3 endogenous", "0.05 gN/gVSS/d", "Endogenous-only denit post-anoxic", "Reasonable order-of-magnitude"],
    [
      { text: "K3 MeOH-acclimated", bold: true },
      { text: "0.12 gN/gVSS/d", bold: true },
      "Methylotroph denit on dosed methanol",
      { text: "Weakest assumption — test required", bold: true, color: COLOUR_WARN }
    ],
    ["θ K2", "1.08", "Temperature correction denit", "Standard"],
    ["θ endogenous", "1.10", "Temperature correction endogenous", "Standard"],
    ["Kn ammonia half-sat", "0.3 mgN/L", "Rev B explicit deviation from BioWin 0.7", "From Rev B report"],
  ],
  [2700, 1700, 2700, 2100]
));
content.push(makePara("Table 3.1: Kinetic parameter set with confidence flags", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "Note on nomenclature: K2 and K3 as used here are project-defined labels. K2 refers to primary anoxic denitrification on readily-biodegradable influent COD; K3 refers to post-anoxic denitrification rates (subdivided between endogenous and methanol-acclimated pathways). Readers familiar with other BNR nomenclature conventions should be aware that these labels are not universally standard.",
  { italics: true, color: COLOUR_GREY, size: 20 }
));

content.push(makeHeading("3.3 K3 MeOH sensitivity", 2));
content.push(makePara(
  "Because the K3 MeOH-acclimated rate is the dominant assumption driving S2 capacity, the study tested its sensitivity across the realistic literature range. Results at 17°C winter, AAL + MML diurnal compliance:",
  { after: 120 }
));

content.push(makeTable(
  ["K3 (20°C) gN/gVSS/d", "vs baseline", "S2 max EP", "Δ EP", "% change", "MeOH at max (L/d AAL)"],
  [
    [{ text: "0.05", shade: "FBE5D6" }, { text: "0.42×", shade: "FBE5D6" }, { text: "2,500", shade: "FBE5D6" }, { text: "−1,500", shade: "FBE5D6" }, { text: "−37.5%", shade: "FBE5D6" }, { text: "0", shade: "FBE5D6" }],
    [{ text: "0.06", shade: "FBE5D6" }, { text: "0.50×", shade: "FBE5D6" }, { text: "2,800", shade: "FBE5D6" }, { text: "−1,200", shade: "FBE5D6" }, { text: "−30.0%", shade: "FBE5D6" }, { text: "0", shade: "FBE5D6" }],
    [{ text: "0.07", shade: "FBE5D6" }, { text: "0.58×", shade: "FBE5D6" }, { text: "3,100", shade: "FBE5D6" }, { text: "−900", shade: "FBE5D6" }, { text: "−22.5%", shade: "FBE5D6" }, { text: "28", shade: "FBE5D6" }],
    [{ text: "0.08", shade: "FFF2CC" }, { text: "0.67×", shade: "FFF2CC" }, { text: "3,400", shade: "FFF2CC" }, { text: "−600", shade: "FFF2CC" }, { text: "−15.0%", shade: "FFF2CC" }, { text: "56", shade: "FFF2CC" }],
    [{ text: "0.09", shade: "FFF2CC" }, { text: "0.75×", shade: "FFF2CC" }, { text: "3,600", shade: "FFF2CC" }, { text: "−400", shade: "FFF2CC" }, { text: "−10.0%", shade: "FFF2CC" }, { text: "80", shade: "FFF2CC" }],
    ["0.10", "0.83×", "3,900", "−100", "−2.5%", "108"],
    ["0.11", "0.92×", "4,000", "0", "0%", "120"],
    [{ text: "0.12 (baseline)", bold: true, shade: COLOUR_INFO_BG }, { text: "1.00×", bold: true, shade: COLOUR_INFO_BG }, { text: "4,000", bold: true, shade: COLOUR_INFO_BG }, { text: "—", bold: true, shade: COLOUR_INFO_BG }, { text: "—", bold: true, shade: COLOUR_INFO_BG }, { text: "120", bold: true, shade: COLOUR_INFO_BG }],
    [{ text: "0.13", shade: "E2F0D9" }, { text: "1.08×", shade: "E2F0D9" }, { text: "4,000", shade: "E2F0D9" }, { text: "0", shade: "E2F0D9" }, { text: "0% (mass-bound)", shade: "E2F0D9" }, { text: "120", shade: "E2F0D9" }],
    [{ text: "0.14", shade: "E2F0D9" }, { text: "1.17×", shade: "E2F0D9" }, { text: "4,000", shade: "E2F0D9" }, { text: "0", shade: "E2F0D9" }, { text: "0% (mass-bound)", shade: "E2F0D9" }, { text: "120", shade: "E2F0D9" }],
    [{ text: "0.15", shade: "E2F0D9" }, { text: "1.25×", shade: "E2F0D9" }, { text: "4,000", shade: "E2F0D9" }, { text: "0", shade: "E2F0D9" }, { text: "0% (mass-bound)", shade: "E2F0D9" }, { text: "120", shade: "E2F0D9" }],
  ],
  [1700, 1300, 1500, 1300, 1700, 1700]
));
content.push(makePara("Table 3.2: S2 capacity sensitivity to K3 MeOH-acclimated rate, full literature range", { italics: true, before: 120, after: 120, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "The sensitivity has three distinct regimes:"
));
content.push(bullet("RED zone (K3 ≤ 0.07): capacity penalty 22–37%. Deliverable EP drops to 2,500–3,100. S2 capex business case degrades significantly — at K3 = 0.05, the plant is capacity-limited well below the intended target and a methanol dose is barely required (biology cannot use more). Literature values this low are typical of unacclimated systems or non-methanol carbon sources."));
content.push(bullet("AMBER zone (K3 = 0.08–0.09): capacity penalty 10–15%. Deliverable EP 3,400–3,600. S2 still delivers meaningful intensification but below the 4,000 EP target. Methanol dose is moderate (56–80 L/d AAL)."));
content.push(bullet("GREEN zone (K3 ≥ 0.11): the 607 kg/yr licence mass load becomes the binding constraint at 4,000 EP. Additional kinetic capacity is not useful (methanol dose remains at ~120 L/d AAL). Further capacity requires mass-load reallocation or effluent polishing, not better kinetics."));

content.push(makePara(
  "The baseline value of 0.12 gN/gVSS/d is drawn from published values for methanol-acclimated methylotrophs at 20°C but has not been measured on Canungra biomass. The bench testing proposed in RFC-01 would locate Canungra within one of the three regimes above. The cost of that test (AUD 15–25k) is trivial against the capex uncertainty it resolves — at K3 = 0.07, the S2 capex of AUD 2.5–3.5M delivers only 3,100 EP rather than 4,000 EP, changing the investment case materially."
));

embedChart('/home/claude/report_charts/chart1_k3_sensitivity.png',
  'Figure 3.1: K3 MeOH sensitivity — three-regime capacity structure. Baseline assumption (K3 = 0.12) falls in the green mass-bound plateau. The RED zone (K3 ≤ 0.07) would materially degrade the S2 business case.').forEach(p => content.push(p));

content.push(makeHeading("3.4 Other model limitations", 2));
content.push(bullet("Steady-state solver with first-order MBR tank buffering. Not a full dynamic simulation. Sub-30-minute transient behaviour is not resolved."));
content.push(bullet("MBR tank buffering treats the membrane zone as a single CSTR. Real multi-train MBRs with train sequencing may behave differently."));
content.push(bullet("Post-anoxic mixing is assumed ideal. Short-circuiting, dead zones, and uneven methanol distribution in the combined 156 kL basin are not captured — see Section 6 red-flag discussion."));
content.push(bullet("Aeration demand is computed but not validated against blower capacity. This is an excluded discipline."));

content.push(makeHeading("3.5 Alkalinity balance for nitrification", 2));
content.push(makePara(
  "A first-principles alkalinity balance was performed across the EP range using standard nitrification/denitrification stoichiometry (7.14 mg CaCO3 destroyed per mg NH4-N nitrified; 3.57 mg CaCO3 recovered per mg NO3-N denitrified) and a 75 mg CaCO3/L minimum residual as the nitrification-supporting floor."
));
content.push(makePara(
  "The result is sensitive to the assumed influent alkalinity, which has not been measured for Canungra in this study. Screening-level analysis gives a net average demand of approximately 214–246 mg CaCO3/L and a net peak demand of approximately 281–322 mg CaCO3/L. Against these demands, an influent alkalinity of 250 mg CaCO3/L is inadequate at peak load; 300 mg/L is workable with essential dosing; 350 mg/L provides material margin. Site measurement is required. See Section 6 F8 for full details.",
  { italics: true, color: COLOUR_GREY }
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 4. SCENARIOS ==============
content.push(makeHeading("3.6 IFAS nitrification flux sensitivity", 2));
content.push(makePara(
  "The IFAS biofilm nitrification flux at 17°C is the second-most-sensitive kinetic parameter in the study (after K3 MeOH). The base case used in the model is 0.7 g NH4-N/m²·d at 17°C, drawn from typical published values for K5 media at moderate fill fractions in BNR systems. The recommended sensitivity test envelope is 0.5–1.1 g NH4-N/m²·d, with 0.5 as the conservative bound, 0.7 as the base case, 0.9 as the optimistic bound, and 1.0–1.1 as a stretch sensitivity only.",
  { after: 120 }
));

content.push(makeTable(
  ["Case", "Flux at 17°C (g NH4-N/m²·d)", "Use"],
  [
    [{ text: "Conservative", shade: "FBE5D6" }, { text: "0.5", shade: "FBE5D6" }, { text: "Cautious screening", shade: "FBE5D6" }],
    [{ text: "Base case ★", bold: true, shade: COLOUR_INFO_BG }, { text: "0.7", bold: true, shade: COLOUR_INFO_BG }, { text: "Best starting point", bold: true, shade: COLOUR_INFO_BG }],
    [{ text: "Optimistic", shade: "E2F0D9" }, { text: "0.9", shade: "E2F0D9" }, { text: "Favourable but credible", shade: "E2F0D9" }],
    [{ text: "Stretch", shade: "F2F2F2" }, { text: "1.0–1.1", shade: "F2F2F2" }, { text: "Sensitivity only, not primary basis", shade: "F2F2F2" }],
  ],
  [1800, 2700, 3500]
));
content.push(makePara("Table 3.3: Recommended IFAS nitrification flux test envelope at 17°C", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("Why this range", 3));
content.push(bullet("Published full-scale IFAS-EBPR data (Broomfield, US) shows efficient nitrification at 11–15°C with mixed-liquor SRT of 3.5–4 days and >75% of nitrification activity associated with carrier media — supporting the 0.7 g/m²·d base case at 17°C as conservative for SE QLD subtropical conditions."));
content.push(bullet("EPA IFAS guidance supports the broader logic: IFAS is used to increase biomass and treatment capacity in existing BNR systems, with most nitrification capability potentially residing on attached biomass."));
content.push(bullet("Practical IFAS performance depends on media type, protected SSA, DO in the aerobic zone, temperature, alkalinity/pH, ammonia concentration, biofilm thickness, fouling/overgrowth, and mixing/media motion. No single 'correct' rate applies universally; site verification is the only way to close the range."));

content.push(makeHeading("Required IFAS media surface area at design points", 3));
content.push(makePara(
  "The biofilm provides supplementary nitrification above the suspended-growth baseline. Assuming the suspended biomass carries the existing 1,500 EP licensed load (Rev B baseline), the biofilm must handle the incremental NH3 load at higher EP. Using a peak-load safety factor of 1.5 to cover diurnal peaks and temperature buffer:",
  { after: 120 }
));

content.push(makeTable(
  ["Flux (g/m²·d)", "Area for 1,700 EP", "Area for 2,500 EP", "Area for 4,000 EP", "Adequacy of existing 37,440 m²"],
  [
    [{ text: "0.5 (conservative)", shade: "FBE5D6" }, { text: "10,080 m²", shade: "FBE5D6" }, { text: "50,400 m²", shade: "FBE5D6" }, { text: "126,000 m²", shade: "FBE5D6" }, { text: "1,700 ✓ | 2,500 ✗ | 4,000 ✗", shade: "FBE5D6" }],
    [{ text: "0.7 (base) ★", bold: true, shade: COLOUR_INFO_BG }, { text: "7,200 m²", bold: true, shade: COLOUR_INFO_BG }, { text: "36,000 m²", bold: true, shade: COLOUR_INFO_BG }, { text: "90,000 m²", bold: true, shade: COLOUR_INFO_BG }, { text: "1,700 ✓ | 2,500 ✓ | 4,000 ✗", bold: true, shade: COLOUR_INFO_BG }],
    [{ text: "0.9 (optimistic)", shade: "E2F0D9" }, { text: "5,600 m²", shade: "E2F0D9" }, { text: "28,000 m²", shade: "E2F0D9" }, { text: "70,000 m²", shade: "E2F0D9" }, { text: "1,700 ✓ | 2,500 ✓ | 4,000 ✗", shade: "E2F0D9" }],
    ["1.1 (stretch)", "4,580 m²", "22,910 m²", "57,270 m²", "1,700 ✓ | 2,500 ✓ | 4,000 ✗"],
  ],
  [1400, 1500, 1500, 1500, 2400]
));
content.push(makePara("Table 3.4: Required IFAS media area at design points (incremental NH3 load above 1,500 EP base, MML loading, safety factor 1.5)", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("Aerobic zone fill-fraction limit", 3));
content.push(makePara(
  "Reading the area requirements against the existing aerobic zone (117 kL with K5 media at 800 m²/m³) gives the following fill fractions required to deliver the EP target via biofilm nitrification:",
  { after: 120 }
));
content.push(bullet("1,700 EP: 8% fill (very comfortable, well within 55% practical max)"));
content.push(bullet("2,500 EP: 39% fill (comfortable, within practical limits)"));
content.push(bullet("3,000 EP: 58% fill (at practical maximum — vendor-dependent)"));
content.push(bullet("3,500 EP: 77% fill (impractical — exceeds 55–60% vendor maximum)"));
content.push(bullet("4,000 EP: 96% fill (not feasible)"));

content.push(makePara(
  "This means that at the S2 4,000 EP target, IFAS in the existing aerobic zone alone CANNOT supply enough nitrification capacity at the base-case flux assumption. Practical alternatives are: (a) higher-SSA media (still insufficient at 4,000 EP), (b) carrier in additional zones (beyond aerobic), (c) build new aerobic tank (capex >> intensification benefit), or (d) rely on suspended-growth nitrification only at long MBR-enabled SRT.",
  { after: 120 }
));

content.push(calloutBox(
  "S2 + IFAS: practical conclusion",
  "The S2 configuration achieves 4,000 EP via post-anoxic biological intensification, NOT via aerobic nitrification intensification. The new HF MBR enables operation at SRT 30–40 days, which provides ample suspended-growth nitrification at 4,000 EP without needing IFAS in the aerobic zone.\n\nIFAS therefore has a role ONLY as an optional interim bridge at the S1B intermediate scenario (1,700–2,100 EP) where suspended-growth nitrification is approaching its limit and the long-SRT HF MBR is not yet built. IFAS is NOT part of the preferred long-term S2 configuration. If QUU proceeds directly from S1A to S2 (skipping S1B), IFAS is not required at any point in the pathway.",
  COLOUR_INFO_BG, COLOUR_PRIMARY
));

content.push(new Paragraph({ children: [new PageBreak()] }));

content.push(makeHeading("4. Intensification scenarios", 1));

content.push(makePara(
  "Three scenarios plus a staged breakdown are evaluated. S0 is the Rev B baseline. S1 is split into S1A (controls only) and S1B (S1A plus IFAS). S2 is the full reconfiguration.",
  { after: 180 }
));

content.push(makeTable(
  ["Scenario", "Key moves", "Conceptual EP", "Capex (AUD, screening)"],
  [
    [{ text: "S0 — Rev B baseline", bold: true }, "None", "1,500 (licensed)", "—"],
    [
      { text: "S1A — Controls only", bold: true, shade: "E2F0D9" },
      { text: "Flow-paced recycles, VSD upgrades, instrumentation, operating optimisation", shade: "E2F0D9" },
      { text: "1,500+", shade: "E2F0D9" },
      { text: "~280k", bold: true, shade: "E2F0D9" },
    ],
    [
      { text: "S1B — S1A + IFAS", bold: true, shade: COLOUR_WARN_BG },
      { text: "S1A plus IFAS aerobic carriers (pre-feasibility required: RFC-02, 08, 09)", shade: COLOUR_WARN_BG },
      { text: "~1,700 (subject to verification)", shade: COLOUR_WARN_BG },
      { text: "~900k total (revised)", shade: COLOUR_WARN_BG },
    ],
    [
      { text: "S2 — Full reconfiguration", bold: true, shade: COLOUR_INFO_BG },
      { text: "Remove MBR wall, combined 156 kL post-anoxic, HF MBR in new tank, methanol dosing", shade: COLOUR_INFO_BG },
      { text: "~4,000 (pending verification)", bold: true, shade: COLOUR_INFO_BG },
      { text: "2.5M – 3.5M band", bold: true, shade: COLOUR_INFO_BG },
    ],
  ],
  [2600, 3200, 1800, 2000]
));
content.push(makePara("Table 4.1: Scenario summary with screening-level capex", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

embedChart('/home/claude/report_charts/chart5_capex_ladder.png',
  'Figure 4.1: Scenario capex ladder under Interpretation B basis. All six intensification pathways shown with their capacities and capex bands. S1A is the no-regret immediate action. S1B and all S2 variants require Phase 2 verification before capital commitment.').forEach(p => content.push(p));

content.push(makeHeading("4.1 S1A — controls and operational upgrades", 2));
content.push(makePara(
  "S1A captures the highest-value no-regret work: converting the three recycle streams to flow-paced control, upgrading variable-speed drives, refreshing instrumentation, and optimising operating setpoints (SRT, DO)."
));
content.push(makePara("The Rev B plant uses fixed absolute flow setpoints for the A-recycle (14 × ADWF). Under the diurnal flow peak (2.26× ADWF), the effective ratio drops to 6.2× — a substantial loss of nitrate delivery to the primary anoxic. Converting to flow-paced (instantaneous Q) control restores the ratio through peaks and measurably improves compliance margin."));
content.push(bullet("Upgrade A, S, R recycle pumps with VSD and flow instrumentation"));
content.push(bullet("Implement flow-paced control logic in SCADA"));
content.push(bullet("Instrumentation audit: DO, NH3, NO3 online sensors"));
content.push(bullet("Operating point re-optimisation based on current load profile"));
content.push(bullet("Operator training on flow-paced control implications"));
content.push(makePara(
  "Estimated capex AUD 280k. Compatible with all subsequent pathways. Described as a no-regret action because the underlying control problem exists regardless of future expansion plans."
));
content.push(makePara(
  "Note: while S1A is described as a low-cost operational upgrade, it is not strictly zero-capex. The scope includes VSD upgrades, instrumentation, and control system modifications. 'Low capex subject to instrumentation audit' is a more accurate characterisation than 'zero capex'.",
  { italics: true, color: COLOUR_GREY }
));

embedChart('/home/claude/pfds_v2/pfd_S1A.png',
  'Figure 4.1A: PFD 3 — Scenario S1A. Recycles converted to flow-paced control (red labels). Same Alternative Dry Weather mode as Rev B.').forEach(p => content.push(p));

content.push(makeHeading("4.2 S1B — S1A plus IFAS", 2));
content.push(makePara(
  "S1B adds IFAS aerobic carriers (K5 type, 40% fill) to the aerobic zone on top of S1A. The rationale is to build nitrification margin against future load or temperature stress. Incremental capex over S1A is approximately AUD 620k (revised upward from Rev 5 to include realistic retention screen system scope)."
));
content.push(makePara(
  "Rev 8 note: Rev 5 characterised S1B as \"no tank modifications, no membrane work\". This is not accurate. Installing mobile IFAS carriers in an aerobic zone upstream of an MBR requires retention screens, mounting structure, headloss management, maintenance access, and membrane protection design. S1B is therefore a process-mechanical integration project, not a pure operational upgrade.",
  { italics: true, color: COLOUR_GREY, after: 120 }
));
content.push(makePara(
  "IFAS is directionally consistent with EPA Nutrient Control Design Manual guidance: media retrofits in existing BNR systems can increase biomass and nitrification capacity without raising suspended solids. However, the Canungra-specific feasibility depends on three verification items (RFC-02, RFC-08, RFC-09) that have not yet been closed. S1B should be progressed through pre-feasibility verification before capital commitment, not implemented immediately.",
  { after: 120 }
));
content.push(makePara(
  "At 1,500 EP with SRT 34 days and Kn 0.3 mgN/L, the Rev B plant has comfortable nitrification margin. IFAS becomes clearly justified if (i) catchment growth requires nitrification capacity beyond what the baseline plant supports, (ii) a specific aeration constraint favours biofilm-assisted nitrification, or (iii) S1B is selected as an interim step while S2 is verified.",
  { color: COLOUR_GREY, italics: true }
));

content.push(makeHeading("4.3 S2 — intensification pathway and four configuration variants", 2));
content.push(makePara(
  "Scenario S2 is the intensification pathway that exploits the existing MBR tank volume to provide substantially more post-anoxic biological capacity. Rev 11 resolves S2 into four physically distinct configurations that differ in how the MBR tank volume is converted, how flow is distributed through the post-anoxic zones, and where methanol is dosed. All four variants share the same upstream (anaerobic, primary anoxic, aerobic, de-aeration) configuration and the same downstream HF MBR replacement."
));

content.push(makePara(
  "The four variants are summarised below and detailed in Sections 4.4 to 4.7. The preferred concept for pre-feasibility development is S2-C3 (Section 4.6) — under Interpretation B its modelled capacity ceiling is approximately 5,500 EP at AUD ~3.56M capex band without wall removal and with the simplest of the multi-cell methanol dosing arrangements.",
  { after: 120 }
));

content.push(makeTable(
  ["Variant", "Configuration", "Wall removal", "MeOH dose points", "Max EP", "Capex (AUD)"],
  [
    [
      { text: "S2-A", bold: true },
      "Combined 156 kL post-anoxic (38+118)",
      { text: "REQUIRED", bold: true, shade: "FBE5D6" },
      "1 (single point)",
      { text: "6,000", bold: true },
      "~3.36M"
    ],
    [
      { text: "S2-B", bold: true },
      "Parallel 38+59+59 with proportional flow split",
      "Not required",
      "3 (proportional split)",
      { text: "6,000", bold: true },
      "~3.62M"
    ],
    [
      { text: "S2-C3", bold: true, shade: "E2F0D9" },
      { text: "Series 38 → parallel 59+59, MeOH only in 59 kL cells", shade: "E2F0D9" },
      { text: "Not required", shade: "E2F0D9" },
      { text: "2 (50:50 symmetric)", shade: "E2F0D9" },
      { text: "5,500 ★", bold: true, shade: "E2F0D9" },
      { text: "~3.56M ★", bold: true, shade: "E2F0D9" }
    ],
    [
      { text: "S2-D", bold: true },
      "Parallel 59+59 only, 38 kL decommissioned",
      "Not required",
      "2 (50:50 symmetric)",
      "4,500",
      "~3.30M"
    ],
    [
      { text: "S2-E", bold: true, shade: "FFF2CC" },
      { text: "Existing post-anox → aerobic. Former MBR → post-anoxic. Flow balancing in new MBR tank.", shade: "FFF2CC" },
      { text: "Not required", shade: "FFF2CC" },
      { text: "1 (single point)", shade: "FFF2CC" },
      { text: "5,500-6,000 (depends on flow balancing)", shade: "FFF2CC" },
      { text: "~3.5-3.8M", shade: "FFF2CC" }
    ],
  ],
  [800, 2700, 1400, 1500, 1200, 1100]
));
content.push(makePara("Table 4.4: S2 configuration variants. ★ recommended", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("4.4 S2-A: Combined post-anoxic (wall removed)", 2));
content.push(makePara(
  "S2-A removes the internal wall between the two 59 kL MBR cells, creating a combined 118 kL bay. Combined with the existing 38 kL post-anoxic, total post-anoxic volume becomes 156 kL operating as a single CSTR. Methanol is dosed at a single upstream point. This is the simplest configuration to operate but requires structural confirmation of wall removal feasibility (RFC-05). Maximum capacity 6,000 EP under Interpretation B, bound by peak TN at MML loading."
));
content.push(makePara("See PFD 4 (Figure 4.2) for the configuration diagram.", { italics: true, color: COLOUR_GREY }));

embedChart('/home/claude/pfds_v2/pfd_S2A.png',
  'Figure 4.2: PFD 5 — Scenario S2-A. Combined 156 kL post-anoxic (wall removed), single MeOH dosing point, new HF MBR.').forEach(p => content.push(p));

content.push(makeHeading("4.5 S2-B: Parallel post-anoxic (wall retained)", 2));
content.push(makePara(
  "S2-B retains the internal MBR wall and converts the two 59 kL MBR cells to post-anoxic chambers, operating in parallel with the existing 38 kL chamber. A flow distribution chamber upstream splits the (Q + S-recycle) forward flow proportionally to volume (24:38:38). Three outflows recombine in a downstream chamber before the new HF MBR feed. Methanol is dosed at three points proportional to flow."
));
content.push(makePara(
  "Mathematical equivalence: for first-order or capacity-limited denitrification kinetics, parallel CSTRs with proportionally-split flow give identical effluent quality to a single combined CSTR of the same total volume. The model confirms identical biological output to S2-A at all EP/load combinations tested, including 6,000 EP under Interpretation B. The +AUD 263k capex over S2-A buys the elimination of structural risk associated with wall removal."
));

embedChart('/home/claude/pfds_v2/pfd_S2B.png',
  'Figure 4.3: PFD 6 — Scenario S2-B. Three parallel post-anoxic chambers (38+59+59), wall retained, 3-point asymmetric MeOH dosing.').forEach(p => content.push(p));

content.push(makeHeading("4.6 S2-C3: Series-then-parallel with simplified dosing — preferred concept", 2));
content.push(makePara(
  "S2-C3 routes the full forward flow through the existing 38 kL post-anoxic chamber first (running on endogenous denitrification only, no methanol dosing), then splits 50:50 between the two converted 59 kL cells operating in parallel with methanol dosing. The 38 kL chamber acts as an endogenous pre-stage that reduces the NO3 load reaching the methanol-dosed polishing cells.",
  { after: 120 }
));

content.push(makePara(
  "Capacity at 5,500 EP under Interpretation B — 500 EP below S2-A/B but 1,000 EP above S2-D. The 38 kL endogenous pre-stage provides ~4.8 kg N/d denitrification capacity (vs ~12.2 kg N/d if methanol were also added there), so it captures roughly 60% of the kinetic value of the 38 kL chamber. The remaining 40% of value would require adding a third methanol dosing point (Configuration S2-B), which may not be worth the operational complexity for an additional 200 EP.",
  { after: 120 }
));

content.push(makeHeading("Why S2-C3 is the preferred concept for pre-feasibility development", 3));
content.push(bullet("No wall removal — eliminates structural risk (F5 closed)"));
content.push(bullet("Symmetric 50:50 methanol dosing — simpler to set up, balance, and operate than asymmetric 24:38:38 proportional dosing in S2-B"));
content.push(bullet("Built-in safety against methanol overdose — the 38 kL endogenous pre-stage absorbs upstream upsets before they reach the dosed cells"));
content.push(bullet("Built-in safety against methanol underdose — endogenous denitrification continues even if methanol dosing fails, providing partial capacity while operators respond"));
content.push(bullet("Lower capex than S2-B (~AUD 60k less due to simpler dosing infrastructure)"));
content.push(bullet("Capacity ceiling (5,500 EP) substantially exceeds realistic SE Queensland small-town growth horizons within a 30-year planning window, providing meaningful headroom beyond the 4,000 EP target"));

content.push(makePara(
  "The S2-C3 recommendation rests on hydraulic assumptions — flow split behaviour, methanol distribution, post-anoxic mixing, residence-time distribution, and absence of dead zones in converted former MBR cells — that are credible at screening level but have not been verified at the site. RFC-04 (post-anoxic hydraulics and mixing, including dye tracing) is the corresponding Phase 2 workstream. S2-C3 should be treated as the preferred concept for pre-feasibility development, not as a decision-grade selection at the current level of analysis.",
  { italics: true, color: COLOUR_GREY, after: 120 }
));

embedChart('/home/claude/pfds_v2/pfd_S2C3.png',
  'Figure 4.4: PFD 7 — Scenario S2-C3 ★ RECOMMENDED. 38 kL serial endogenous pre-stage, 50:50 split, 2 parallel polishing cells with simple 50:50 MeOH dosing.').forEach(p => content.push(p));

content.push(makeHeading("4.7 S2-D: Parallel-only (38 kL decommissioned)", 2));
content.push(makePara(
  "S2-D decommissions the existing 38 kL post-anoxic chamber and routes flow directly to the two parallel 59 kL converted cells. Total post-anoxic volume reduces to 118 kL — a 24% reduction from the S2-A/B baseline. Maximum capacity under Interpretation B is 4,500 EP (bound by peak TN). This is a 25% reduction from S2-A/B's 6,000 EP, reflecting the proportional reduction in post-anoxic kinetic capacity."
));
content.push(makePara(
  "S2-D is the lowest-capex S2 variant (~AUD 3.30M vs S2-A's 3.36M and S2-B's 3.62M). The decommissioned 38 kL chamber can be repurposed (RAS holding, methanol storage building, switchgear room, or future expansion shell). The configuration is operationally the simplest — symmetric 50:50 flow split, two methanol dosing points, no need for asymmetric proportional dosing."
));

embedChart('/home/claude/pfds_v2/pfd_S2D.png',
  'Figure 4.5: PFD 8 — Scenario S2-D. 38 kL decommissioned (cross-out, repurpose), bypass to 2 parallel cells, simple 50:50 MeOH dosing.').forEach(p => content.push(p));

content.push(makeHeading("4.8 S2-E: Aerobic-shifted with flow balancing", 2));

content.push(makePara(
  "S2-E is a fifth configuration variant identified during concept review. It takes a different approach to the post-anoxic intensification challenge. Rather than leaving the existing 38 kL post-anoxic tank downstream of the de-aeration zone, S2-E converts it to additional aerobic duty and uses flow balancing in the new MBR structure to compensate for the reduced post-anoxic volume.",
  { after: 120 }
));

content.push(makeHeading("Configuration", 3));
content.push(bullet("Existing 38 kL post-anoxic tank CONVERTED to aerobic (aeration retrofit — diffusers, piping, blower scope)"));
content.push(bullet("Aerobic zone expands from 117 kL to 155 kL (+32%)"));
content.push(bullet("Former MBR bay (2×59 kL = 118 kL) becomes the single post-anoxic zone (wall retained between cells)"));
content.push(bullet("New MBR structure incorporates flow balancing — approximately 30 kL total (10 kL balance zone + 20 kL membrane zone)"));
content.push(bullet("Single MeOH dosing point to the post-anoxic (simpler than S2-B or S2-C3)"));
content.push(bullet("No wall removal required (RFC-05 structural review not needed)"));

content.push(makeHeading("The flow balancing premise", 3));
content.push(makePara(
  "S2-E trades 38 kL of post-anoxic volume for 38 kL of aerobic volume plus flow balancing capacity. The post-anoxic volume reduction alone would drop capacity to approximately 4,500 EP (matching S2-D). Flow balancing recovers the capacity by dampening the MML peak-to-AAL flow ratio from approximately 1.4× down to 1.10-1.20×, which directly reduces peak NO3 loading to the post-anoxic zone.",
  { after: 120 }
));

content.push(makeTable(
  ["Flow balance retention", "Effective peak:AAL ratio", "S2-E capacity estimate"],
  [
    ["None (no balance tank)", "1.40×", "~4,500 EP (matches S2-D)"],
    ["1 hour", "~1.20×", "~5,300 EP"],
    ["2-4 hours", "~1.10×", "~5,700 EP"],
    ["4-6 hours (+ future IFAS option)", "<1.10×", "~6,000-6,500 EP"],
  ],
  [2200, 2200, 3400]
));
content.push(makePara("Table 4.7: S2-E capacity as a function of flow balancing retention (screening-level estimate)", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

embedChart('/home/claude/pfds_v2/pfd_S2E.png',
  'Figure 4.9: PFD 9 — Scenario S2-E. Aerobic zone expanded to 155 kL (existing 117 plus converted 38 kL). Former MBR bay serves as single post-anoxic. New combined MBR structure includes flow balancing zone upstream of membrane compartment.').forEach(p => content.push(p));

content.push(makeHeading("Advantages over other S2 variants", 3));
content.push(bullet("SIMPLEST PROCESS FLOW — single aerobic zone, single post-anoxic zone, single MeOH dosing point. Cleaner hydraulic profile end-to-end than S2-B (parallel with 3-point dosing) or S2-C3 (series-then-parallel)."));
content.push(bullet("NO WALL REMOVAL — existing internal MBR wall is retained, structural hold point (RFC-05) is not in the critical path. Lower project delivery risk."));
content.push(bullet("EXPANDED AEROBIC ZONE — 32% more aerobic volume provides better DO distribution at peak load, margin for temperature or BOD shock, and room for future IFAS at low fill fraction with minimal alpha-factor penalty."));
content.push(bullet("FLOW BALANCING VALUE — beyond TN capacity alone, flow balancing dampens wet-weather stress on MBR membranes, smooths diurnal permeate flux, and extends membrane life. This is operational value that none of the other S2 variants provide."));
content.push(bullet("FUTURE INTENSIFICATION HEADROOM — 155 kL aerobic zone can accommodate IFAS at 25-30% fill for future capacity increase (to approximately 6,500 EP) with minimal additional alpha-factor penalty. Keeps pathway open."));

content.push(makeHeading("Risks and unknowns", 3));
content.push(bullet("FLOW BALANCING IS LOAD-BEARING — in other S2 variants, peak load buffering relies on the post-anoxic volume itself. In S2-E, flow balancing IS the peak load management strategy. Undersizing, short-circuiting, or control failure in the balance tank reverts capacity to approximately 4,500 EP (S2-D equivalent)."));
content.push(bullet("BALANCE TANK DESIGN DETAILS ARE CRITICAL — tank location (integrated with MBR vs separate), aerobic vs anoxic hold, mixing, level control, and release rate control all materially affect the capacity recovery. This is not a screening-level question — it requires dynamic simulation (RFC-12)."));
content.push(bullet("AERATION RETROFIT OF EXISTING POST-ANOXIC — the 38 kL tank was designed for anoxic mixing (submersible mixers, no diffuser grid). Conversion requires diffuser installation, air piping, and additional blower capacity. Engineering is straightforward but adds capex (AUD 200-400k)."));
content.push(bullet("EXPANDED AEROBIC INCREASES O2 DEMAND — 155 kL vs 117 kL aerobic volume means larger blower capacity upgrade. Net effect on capex is partially offset by not needing wall removal, but the aeration package is larger."));
content.push(bullet("TANK CLEANOUT BEFORE COMMISSIONING — the 38 kL tank has operated as anoxic for 14+ years. Biofilm/sludge accumulation on mixers and corners requires cleanout before aerobic commissioning."));

content.push(makeHeading("Capex estimate", 3));
content.push(bullet("New MBR structure with flow balancing: AUD 1.8-2.2M (vs 1.6-1.8M for standard new MBR in S2-A/B)"));
content.push(bullet("Aeration retrofit of existing 38 kL tank: +AUD 200-400k"));
content.push(bullet("Former MBR bay conversion to post-anoxic: AUD 200-300k (simpler than S2-A — no wall removal)"));
content.push(bullet("Methanol dosing (single point): AUD 150-200k"));
content.push(bullet("Recycle pump upgrades, controls, commissioning: AUD 400-500k"));
content.push(bullet("Blower upgrade (larger than S2-A/B due to 32% more aerobic volume): AUD 300-400k"));
content.push(bullet("Total S2-E capex band: AUD 3.5-3.8M (comparable to S2-A/B at 3.36-3.62M)"));

content.push(new Paragraph({ children: [new PageBreak()] }));

content.push(makeHeading("4.9 Decision tree for S2 variant selection", 2));
content.push(makePara(
  "Selection between S2 variants depends on three factors: catchment growth horizon, outcome of structural review (RFC-05), and operator preference for dosing complexity. The recommended decision logic (Interpretation B basis) is:",
  { after: 120 }
));

content.push(makeTable(
  ["Catchment growth horizon", "Wall removal viable?", "Preferred concept"],
  [
    ["≤ 4,000 EP", "Either", "S2-D (lowest cost, 4,500 EP capacity)"],
    ["4,000 – 5,500 EP", "Either", { text: "S2-C3 ★ or S2-E ★ (parallel preferred concepts)", bold: true, shade: "E2F0D9" }],
    ["5,500 – 6,000 EP", "No (RFC-05 returns concern)", { text: "S2-E ★ (flow balancing) or S2-B (parallel wall retained)", bold: true, shade: "FFF2CC" }],
    ["5,500 – 6,000 EP", "Yes (RFC-05 confirms safe)", "S2-A (combined, demolish wall), or S2-E"],
    ["> 6,000 EP", "Either", "S2 exceeded — external post-anoxic extension or new aerobic zone"],
  ],
  [2400, 2400, 4400]
));
content.push(makePara("Table 4.5: S2 variant selection logic", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "RFC-05 (structural review of MBR wall) becomes a value-of-information exercise: AUD 30–50k spent on structural review either confirms the AUD 263k saving available with S2-A vs S2-B, or routes the project to a wall-retention variant. For growth horizons up to 5,500 EP, two preferred concepts are viable — S2-C3 (series-then-parallel post-anoxic) and S2-E (aerobic-shifted with flow balancing). The choice between them depends on the outcome of RFC-12 (flow balancing dynamic simulation) and the relative weight QUU places on process simplicity (S2-E) versus conservative post-anoxic sizing (S2-C3). At 5,500–6,000 EP, S2-E becomes attractive because it matches S2-A/B capacity without the wall removal structural risk. Above 6,000 EP, all S2 variants approach their peak TN ceiling and further capacity requires external post-anoxic extension or new aerobic tank construction."
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// Original Section 4.3 description was here — keep the recycle table material as Section 4.9
content.push(makeHeading("4.9 Recycle optimisation (applies to all S2 variants)", 2));
content.push(makePara(
  "All four S2 variants share the same recycle optimisation strategy:",
  { after: 120 }
));
// 4.9 was added above
content.push(makePara(
  "The reconfigured plant enables meaningful optimisation of all three recycle streams. The combined 156 kL post-anoxic changes where denitrification occurs, and HF MBR tank has different MLSS operating characteristics than the original Kubota. All three recycles are converted to flow-paced control.",
  { after: 120 }
));

content.push(makeTable(
  ["Recycle", "Rev B", "S2 proposed", "Rationale"],
  [
    [
      { text: "A-recycle", bold: true },
      "14× ADWF, fixed",
      { text: "10× Q, flow-paced", bold: true },
      "Primary anoxic becomes COD-limited; 10× captures ~91% of theoretical efficiency. Saves ~28% pumping energy."
    ],
    [
      { text: "S-recycle", bold: true },
      "6× ADWF, fixed",
      { text: "5× Q, flow-paced", bold: true },
      "HF operating window 5,000–10,000 mg/L MLSS. S=5 gives comfortable margin below ceiling."
    ],
    [
      { text: "R-recycle", bold: true },
      "1× influent from de-aeration",
      { text: "1× Q flow-paced from post-anoxic", bold: true },
      "Redirecting source improves bio-P performance via reduced NO3 carry to anaerobic zone. Expected alum benefit, but magnitude requires TP mass balance (Phase 2)."
    ],
  ],
  [1400, 2200, 2400, 3200]
));
content.push(makePara("Table 4.2: Recycle optimisation for S2", { italics: true, before: 120, after: 120, color: COLOUR_GREY, size: 20 }));

content.push(makeHeading("4.10 S2 capex band — screening level only", 2));
content.push(makePara(
  "Screening-level S2 capex is presented as a band of AUD 2.5M – 3.5M rather than a point estimate, reflecting the significant scope items that remain vendor-dependent or that require structural confirmation.",
  { after: 120 }
));

content.push(makeTable(
  ["Line item", "Screening estimate (AUD)"],
  [
    ["Instrumentation, VSDs, control upgrades (S1A basis)", "~280k"],
    ["IFAS aerobic carriers + retention screens (if required)", "~620k"],
    ["HF MBR equipment (modules, pumps, air scour, CEB, N+1)", "~700k"],
    ["HF MBR new tank civil (with access, freeboard, drainage)", "~250k"],
    ["HF interconnect — pipework, valves, MCC/PLC, electrical", "~200k"],
    ["Remove MBR internal wall + structural confirmation", "~60k"],
    ["Convert former MBR bay to post-anoxic (mixers, piping)", "~120k"],
    ["Existing Kubota decommissioning and disposal", "~40k"],
    ["Recycle pump upsizing (A, S)", "~150k"],
    ["R-recycle source repiping", "~25k"],
    ["Methanol storage and dosing (hazardous area)", "~180k"],
    ["Installation, commissioning", "~100k"],
    ["Engineering and design (20–30%)", "~500k–750k"],
    [{ text: "Indicative band", bold: true, shade: COLOUR_WARN_BG }, { text: "AUD 2.5M – 3.5M", bold: true, shade: COLOUR_WARN_BG }],
  ],
  [6000, 2600]
));
content.push(makePara("Table 4.3: S2 screening-level capex breakdown. Not a tender-ready number.", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 5. RESULTS ==============
content.push(makeHeading("5. Modelled process results", 1));

content.push(makeHeading("5.1 Capacity and binding constraints", 2));
content.push(makeTable(
  ["Scenario", "Conceptual EP", "Apparent binding constraint (within scope)"],
  [
    ["S0 Rev B baseline", "1,500 (design)", "Diurnal compliance margin"],
    [
      { text: "S1A Controls only", shade: "E2F0D9" },
      { text: "1,500+ (improved margin)", shade: "E2F0D9" },
      { text: "Approaching MML mass load", shade: "E2F0D9" },
    ],
    ["S1B S1A + IFAS", "1,700", "MML mass load"],
    [
      { text: "S2 Full reconfiguration", bold: true, shade: COLOUR_INFO_BG },
      { text: "4,000 (subject to verification)", bold: true, shade: COLOUR_INFO_BG },
      { text: "Annual TN mass load (within modelled scope)", shade: COLOUR_INFO_BG },
    ],
  ],
  [2400, 2400, 4800]
));
content.push(makePara("Table 5.1: Modelled capacity at 17°C winter, AAL + MML compliance (concentration limits plus annual mass)", { italics: true, before: 120, after: 120, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "Important caveat: the process model does not identify a biological or process-hydraulic constraint below approximately 6,000 EP for the S2 configuration. However, the excluded disciplines (aeration, inlet hydraulics, solids handling, structural, electrical) may impose constraints that become binding at lower EP. The honest conclusion is that process modelling does not rule out 6,000 EP as a modelled possibility under Interpretation B, subject to full verification of the excluded constraints (aeration, hydraulics, solids, structural, electrical, phosphorus) and of the kinetic assumptions.",
  { italics: true, color: COLOUR_GREY }
));

content.push(makeHeading("5.2 Annual mass load framing", 2));
content.push(makePara(
  "At 4,000 EP × 200 L/EP/d × 2.0 mg/L TN × 365 days = 584 kg/yr, approaching the 607 kg/yr annual licence mass. The MML condition produces higher mass flux, with peaks approaching the limit. The simple arithmetic suggests that the licence mass load will become the governing process constraint at approximately 4,000 EP, but true annual mass compliance depends on:"
));
content.push(bullet("Seasonal hydraulic patterns (wet vs dry season, infiltration/inflow)"));
content.push(bullet("Seasonal TKN variations (tourism, industrial discharges)"));
content.push(bullet("Year-to-year climate variability"));
content.push(bullet("Actual distribution between AAL and MML conditions throughout the year"));
content.push(makePara(
  "The simple calculation is a reasonable first-order indicator but not a rigorous annual compliance assessment. A dynamic simulation with representative annual flow and load data is required to confirm.",
  { italics: true, color: COLOUR_GREY }
));

content.push(makeHeading("5.3 Effluent quality response to loading", 2));
content.push(makePara(
  "S2 effluent TN response to EP and methanol dose at AAL/17°C illustrates the trade-off:",
  { after: 120 }
));

content.push(makeTable(
  ["EP", "MeOH = 0", "MeOH = 40", "MeOH = 80", "MeOH = 120"],
  [
    ["1,500", "< 2.0", "< 1.9", "< 1.9", "< 1.9"],
    ["2,500", { text: "< 1.9 (no MeOH needed)", bold: true }, "—", "—", "—"],
    ["3,000", "2.1", "1.9", "1.9", "1.9"],
    ["3,500", "2.5", "2.0", "1.9", "1.9"],
    [{ text: "4,000 (conceptual)", bold: true }, { text: "3.0", bold: true }, { text: "2.2", bold: true }, { text: "1.9", bold: true }, { text: "1.9", bold: true }],
  ],
  [2200, 1760, 1760, 1760, 1820]
));
content.push(makePara("Table 5.2: S2 flow-weighted mean TN (mg/L) vs EP and methanol dose (L/d) at AAL 17°C", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "Notable finding: at 2,500 EP in the S2 configuration, the model predicts compliance with no external methanol dosing. The enlarged 156 kL post-anoxic provides sufficient endogenous denitrification capacity. This result is plausible but requires bench-test confirmation of endogenous kinetics on Canungra biomass before being relied upon."
));

embedChart('/home/claude/report_charts/chart2_tn_vs_ep.png',
  'Figure 5.1: Effluent TN vs EP for each scenario (AAL 17°C). S0 baseline (fixed A-recycle) exceeds the 5 mg/L median licence limit at low EP. S1A and S1B track together — IFAS adds minimal TN benefit over controls alone. S2 maintains ~2 mg/L TN across the full EP range by leveraging the enlarged 156 kL post-anoxic.').forEach(p => content.push(p));

embedChart('/home/claude/report_charts/chart6_s2_capacity_envelope.png',
  'Figure 5.2: S2 effluent TN across EP range at AAL and MML loading. Under the adopted Interpretation B basis, S2-A/B could potentially remain concentration-compliant up to approximately 6,000 EP under Interpretation B, subject to verification of excluded constraints and confirmation of relicensing treatment of mass load, bound by the MML peak TN approaching the 15 mg/L licence limit. Peak TN is the first constraint to bind; mass load remains well below the scaled limit throughout.').forEach(p => content.push(p));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 6. RED FLAGS ==============
content.push(makeHeading("5.4 Increased annual discharge load — environmental context", 2));
content.push(makePara(
  "The intensification scenarios deliver more EP capacity but at higher total annual TN discharge to the receiving waterway. The Rev B baseline discharges approximately 578 kg TN/yr at 1,500 EP. The recommended S2-C3 configuration at its 5,500 EP ceiling discharges approximately 1,171 kg TN/yr — a 2.0× increase. The S2-A/B configuration at 6,000 EP discharges 1,338 kg/yr (2.3× increase). This is a material environmental change that must be considered alongside the treatment performance metrics."
));

content.push(makeTable(
  ["Scenario", "Design EP", "TN discharge kg/yr", "× vs S0 baseline", "% licence utilisation"],
  [
    [{ text: "S0 Rev B baseline", bold: true }, "1,500", "578", "1.00×", "95% of 607"],
    ["S1A Controls only", "1,900", "587", "1.02×", "76% of 769"],
    ["S1B S1A + IFAS", "2,100", "583", "1.01×", "69% of 850"],
    ["S2-D Parallel-only", "4,500", "744", "1.29×", "41% of 1,821"],
    [{ text: "S2-C3 Recommended ★", bold: true, shade: "E2F0D9" }, { text: "5,500", bold: true, shade: "E2F0D9" }, { text: "1,171", bold: true, shade: "E2F0D9" }, { text: "2.03×", bold: true, shade: "E2F0D9" }, { text: "53% of 2,226", bold: true, shade: "E2F0D9" }],
    ["S2-A/B Full 156 kL", "6,000", "1,338", "2.31×", "55% of 2,428"],
  ],
  [1800, 800, 1400, 1400, 1600]
));
content.push(makePara("Table 5.2: Annual TN discharge at each scenario design capacity (Interpretation B scaled limit)", { italics: true, before: 120, after: 240, color: COLOUR_GREY, size: 20 }));

embedChart('/home/claude/report_charts/chart7_discharge_scale.png',
  'Figure 5.3: Annual TN discharge at each scenario design capacity, compared to the scaled Interpretation B licence limit. S1A and S1B achieve higher EP without increasing total discharge above the Rev B baseline because improved concentrations offset increased flow. S2 variants approximately double or triple the total annual TN discharge to the receiving waterway.').forEach(p => content.push(p));

content.push(makeHeading("Engineering observations for QUU's environmental engagement", 3));
content.push(makePara(
  "Three engineering-relevant facts are worth putting in front of QUU's environmental team:",
  { after: 60 }
));

content.push(bullet("S1A and S1B deliver incremental capacity (to 1,900 and 2,100 EP respectively) without meaningfully changing the total annual discharge. The recycle control improvements and IFAS enhancements lower effluent concentrations, which offsets the higher flow. These scenarios have the same receiving-water impact as Rev B."));

content.push(bullet("S2 variants carry a step-change in total discharge. Growth from 1,500 to 5,500 EP at S2-C3 adds approximately 593 kg TN/yr to the receiving waterway. This is within the scaled Interpretation B licence limit (2,226 kg/yr) but is a real environmental increase that catchment authorities may scrutinise."));

content.push(bullet("Treatment efficiency (percentage TN removed) is actually HIGHER at S2 than at S0 — 95% removal at S2-C3 vs 91% at S0 — because the process is more thoroughly designed. The higher total mass discharge comes from serving more people, not from degraded treatment."));

content.push(makeHeading("Nitrogen load context", 3));
content.push(makePara(
  "To give engineering-relevant scale:"
));
content.push(bullet("Typical domestic influent TN load is approximately 11.5 g N/EP/d, giving an influent flow of approximately 6,300 kg N/yr at 1,500 EP and 23,100 kg N/yr at 5,500 EP."));
content.push(bullet("The Canungra plant's current biological removal rate is about 91% (578 kg discharged ÷ 6,300 kg influent). Under S2-C3 at 5,500 EP, removal rate would be 95% (1,171 kg discharged ÷ 23,086 kg influent) — a substantial process efficiency improvement even as absolute mass discharge roughly doubles."));
content.push(bullet("For catchment context, 1,171 kg TN/yr equates to approximately 3.2 kg/day. Whether this is environmentally significant depends on the receiving water's assimilative capacity, catchment-wide nitrogen budget, and seasonal flow regime — all matters requiring specific assessment outside this screening study's scope."));

content.push(makePara(
  "Our engineering role in this study is to quantify and minimise the intensification discharge load within process constraints. The receiving water assessment and regulator engagement are QUU's workstream. The numbers in Table 5.2 and Figure 5.3 provide the input QUU needs for that engagement.",
  { italics: true, color: COLOUR_GREY, after: 180 }
));

content.push(new Paragraph({ children: [new PageBreak()] }));

content.push(makeHeading("6. What could break Scenario S2", 1));

content.push(makePara(
  "This section lists the risk factors that could invalidate or materially reduce the Scenario S2 capacity estimate. Each is subject to verification in the Phase 2 workstream (Section 7).",
  { after: 180 }
));

content.push(calloutBox(
  "F1 — K3 methanol kinetics not site-calibrated",
  "The most sensitive assumption in the study. Extended sensitivity across K3 = 0.05–0.15 gN/gVSS/d (see Table 3.2) shows capacity ranges from 2,500 EP (worst case, K3 = 0.05) to 4,000 EP (mass-load bound under Interpretation A, K3 ≥ 0.11). Under the Rev 16 Interpretation B basis, the mass cap is not binding and the K3 sensitivity would instead affect peak TN rather than capacity. The three-regime structure is retained as a verification rationale. The middle of the literature range (K3 = 0.08–0.09) gives 3,400–3,600 EP — still meaningful intensification but 10–15% below the 4,000 EP target.\n\nCanungra biomass has not been bench-tested for methanol-acclimated denitrification. Without site-specific data, S2 could deliver anywhere from 2,500 to 4,000 EP — a capacity uncertainty of 1,500 EP that directly affects the value of the AUD 2.5–3.5M capex.\n\nMitigation: Bench testing (AUD 15–25k) before capital commitment. Approximately 2–3 weeks including acclimation. This was the single highest-value verification item under Interpretation A. Under Interpretation B (Rev 16 basis), K3 sensitivity matters less because capacity is bound by peak TN rather than annual mass. Bench testing remains valuable for operational confidence but is no longer the blocking constraint it was under Interpretation A.",
  COLOUR_WARN_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F2 — Aeration and oxygen transfer capacity not assessed",
  "At ~4,000 EP, oxygen demand from nitrification + carbon oxidation may exceed existing blower capacity or diffuser turn-up range. The issue is more acute for S1B than for S2 at equivalent EP because adding IFAS carriers changes alpha-factor, mixing energy requirements, and bulk DO distribution in the aerobic zone.\n\nEPA Nutrient Control Design Manual notes nitrification rates decline below 3 mg/L bulk DO. If the existing blowers and diffuser grid cannot maintain adequate bulk DO after IFAS media installation, the attached-growth nitrification benefit will not be realised and S1B's nitrification reserve claim is overstated.\n\nMitigation: Full oxygen balance at S1B and S2 design points. Alpha-factor validation at the carrier-loaded aerobic zone condition. Blower curve vs demand assessment including turn-down for diurnal minimum flow. Diffuser retrofit assessment if required.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F3 — HF MBR footprint and capex estimate",
  "The AUD ~700k HF equipment and ~250k new tank civil estimates are directionally plausible but vendor-dependent. Full installed cost including redundancy, access, pipework, air scour modifications, chemical cleaning systems, controls, and temporary works could be higher.\n\nMitigation: Concept layouts and capex from at least two HF vendors during pre-feasibility.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F4 — Post-anoxic hydraulics unverified",
  "The 156 kL combined basin is assumed to function as an effective mixing zone. Short-circuiting, dead zones from former MBR structural features, and uneven methanol distribution could reduce effective volume significantly. Lumped-parameter modelling cannot capture these effects.\n\nMitigation: Hydraulic residence time analysis (tracer study or CFD). Mixer sizing with spatial distribution assessment. Methanol dosing distribution design.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F5 — MBR internal wall removal feasibility",
  "The concept depends on removing the internal dividing wall between the two 59 kL MBR cells. The wall is assumed to be non-structural based on as-built drawings showing similar construction to removable baffles, but this requires confirmation.\n\nMitigation: Structural engineering assessment of the wall (mandatory hold point). If wall is load-bearing, alternative reconfigurations must be considered.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F6 — Phosphorus compliance not demonstrated",
  "Rev 5 does not include a phosphorus mass balance for S2. The plant has a 122 kg TP/yr annual mass limit that must also be complied with. The proposed R-recycle source change should improve bio-P (directionally), but the net effect on TP compliance under intensified loads is unquantified.\n\nMitigation: Phosphorus mass balance modelling in Phase 2. Assessment of alum demand under S2 including seasonal variation. Bio-P stability review.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F7 — Solids handling at higher EP",
  "WAS production scales with EP. At 4,000 EP, sludge handling (waste pumps, storage, dewatering capacity, polymer demand, biosolids haulage) may require upgrade. This is out of scope for Rev 5.\n\nMitigation: WAS production assessment at S2 design point. Sludge handling capacity review.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F8 — Alkalinity sufficiency depends on unmeasured influent concentration",
  "Nitrification destroys 7.14 mg CaCO3/mg NH4-N. Denitrification recovers only 3.57 mg CaCO3/mg NO3-N. Net demand is approximately 214–246 mg CaCO3/L average load and 281–322 mg CaCO3/L at peak. For a 75 mg CaCO3/L minimum nitrification residual, S2 at 4,000 EP peak load needs approximately 356–397 mg CaCO3/L of total available alkalinity. At 6,000 EP (Interpretation B ceiling), demand scales to approximately 536-597 mg CaCO3/L — this is a significant additional constraint that reinforces RFC-08 as a priority.\n\nCanungra influent alkalinity has NOT been measured in this study. At 250 mg/L (a commonly-cited SEQ regional value), the plant is alkalinity-deficient at peak load and requires continuous heavy NaOH dosing. At 300 mg/L the margin is thin. At 350 mg/L there is workable margin.\n\nMitigation: plant composite sampling for influent alkalinity as a Phase 2 priority before capital commitment on S2. If influent is confirmed to be 250 mg/L or below, the existing NaOH dosing capacity (installed for Rev B at 1,500 EP) may prove inadequate at 4,000 EP and a larger caustic storage/dosing system would be required.",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 120 }));

content.push(calloutBox(
  "F9 — Carrier retention and MBR protection (applies to S1B)",
  "Mobile K5 IFAS carriers must be retained in the aerobic zone by screened baffles, wedge-wire screens, or equivalent mechanical devices. Carrier escape downstream into the MBR is not tolerable — K5 pieces would foul permeate channels, potentially damage hollow fibres, and is a plant-stopping failure mode.\n\nThe Rev 5 characterisation of S1B as \"no tank modifications\" is not accurate. Adding mobile IFAS media to an existing aerobic tank requires: retention screens designed for peak hydraulic load, headloss assessment, cleaning/maintenance access, carrier escape monitoring, and failure containment strategy. None of this was scoped in earlier revisions.\n\nMitigation: RFC-09 (new) requires retention screen design concept, headloss under peak flow calculation, pilot or reference-site operational data for similar K5-into-MBR retrofits, and membrane protection strategy. S1B capex revised upward to reflect realistic retention system scope (AUD ~210k additional vs Rev 5 estimate).",
  COLOUR_CAUTION_BG, COLOUR_WARN
));

content.push(makePara("", { before: 240 }));

content.push(makeHeading("6.1 Alkalinity balance detail", 2));

content.push(makePara(
  "The net alkalinity demand on influent is the alkalinity destroyed by nitrification minus the alkalinity recovered by denitrification. Both terms scale with the nitrogen load processed.",
  { after: 120 }
));

content.push(makeTable(
  ["Loading condition", "Net avg demand", "Net peak demand", "Required influent alk for 75 mg/L residual"],
  [
    ["Rev B at 1,500 EP", "200 mg/L", "239 mg/L", "275–314 mg/L"],
    ["S2 at 2,500 EP", "200 mg/L", "234 mg/L", "275–309 mg/L"],
    ["S2 at 3,000 EP", "199 mg/L", "233 mg/L", "274–308 mg/L"],
    [{ text: "S2 at 4,000 EP", bold: true }, { text: "198 mg/L", bold: true }, { text: "232 mg/L", bold: true }, { text: "273–307 mg/L", bold: true }],
  ],
  [2800, 1800, 1800, 2800]
));
content.push(makePara("Table 6.1: Net alkalinity demand (modelled using S2 denitrification kinetics). Note the modest variation across EP: S2 achieves deeper denitrification than Rev B, slightly reducing per-EP demand.", { italics: true, before: 120, after: 180, color: COLOUR_GREY, size: 20 }));

content.push(makePara(
  "The reviewer-framed screening range (214–246 average, 281–322 peak) is more conservative than the modelled values above and should be used for capital planning until site-specific measurement is completed.",
  { italics: true, color: COLOUR_GREY, after: 180 }
));

content.push(makeTable(
  ["Influent alkalinity", "Peak residual before dosing", "Average residual before dosing", "Status"],
  [
    [
      { text: "250 mg/L", shade: "FBE5D6" },
      { text: "-50 mg/L (deficit)", shade: "FBE5D6" },
      { text: "~20 mg/L", shade: "FBE5D6" },
      { text: "Peak-load alkalinity-deficient. Continuous heavy NaOH dosing required. Capacity of existing installed NaOH system (187 L/d peak at 1,500 EP) may be inadequate at 4,000 EP.", shade: "FBE5D6" }
    ],
    [
      "300 mg/L",
      "~0 mg/L (at floor)",
      "~70 mg/L",
      "Peak-load dosing essential. Marginal working state. NaOH capacity needs confirmation."
    ],
    [
      { text: "350 mg/L", shade: "E2F0D9" },
      { text: "~50 mg/L", shade: "E2F0D9" },
      { text: "~120 mg/L", shade: "E2F0D9" },
      { text: "Workable. Modest dosing at peak load only. Existing NaOH capacity likely adequate.", shade: "E2F0D9" }
    ],
  ],
  [1600, 1800, 2000, 3800]
));
content.push(makePara("Table 6.2: Alkalinity adequacy at S2 4,000 EP design point across plausible influent concentrations", { italics: true, before: 120, after: 180, color: COLOUR_GREY, size: 20 }));

embedChart('/home/claude/report_charts/chart4_alkalinity.png',
  'Figure 6.1: Alkalinity sufficiency at S2 4,000 EP. Available influent alkalinity (bars) vs demand envelopes (horizontal bands). At 250 mg/L influent the plant is alkalinity-deficient at peak load; 300 mg/L is marginal; 350 mg/L is workable with modest NaOH dosing. Canungra influent has not been measured.').forEach(p => content.push(p));

content.push(makePara(
  "Peak residual < 75 mg/L means the plant requires continuous NaOH dosing to sustain nitrification during peak-load periods. At 250 mg/L influent, the required caustic dose at peak load is substantially higher than the Rev B installed system can deliver if scaled up, indicating that a new or expanded caustic storage and dosing system may be needed as part of S2 — an item not previously captured in the capex band.",
  { after: 120 }
));

content.push(makePara(
  "Action: plant composite sampling for influent alkalinity should be elevated to a Phase 1 priority, not a Phase 2 item. The result is a pre-condition for finalising the S2 capex band.",
  { bold: true, after: 120 }
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 7. VERIFICATION PACKAGE ==============
content.push(makeHeading("7. Phase 2 verification package", 1));

content.push(makePara(
  "Seven work packages must complete before capital commitment on Scenario S2. These correspond to the requests for clarification (RFC-01 through RFC-07) identified in the independent red-team review of this study and endorsed in Rev 5.",
  { after: 180 }
));

content.push(makeHeading("RFC-01 — Denitrification kinetics", 2));
content.push(bullet("Basis and validation of K2 (primary anoxic) and K3 endogenous and MeOH-acclimated rates for Canungra biomass"));
content.push(bullet("Bench denitrification tests at representative temperature (17°C)"));
content.push(bullet("Sensitivity analysis ±30% around confirmed values"));
content.push(bullet("Indicative timeframe: 2–3 weeks acclimation + testing. Indicative cost AUD 15–25k"));

content.push(makeHeading("RFC-02 — Aeration capacity", 2));
content.push(bullet("Oxygen demand calculation at S2 design point (nitrification + carbon oxidation + endogenous)"));
content.push(bullet("Existing blower curve vs demand assessment"));
content.push(bullet("Alpha-factor validation at high MLSS and with IFAS (if included)"));
content.push(bullet("Turndown adequacy for diurnal minimum flow"));
content.push(bullet("Diffuser sizing and replacement assessment"));

content.push(makeHeading("RFC-03 — Membrane system design", 2));
content.push(bullet("Concept layouts from at least two HF membrane suppliers"));
content.push(bullet("Installed system volume including redundancy (N+1), access, freeboard"));
content.push(bullet("Capex breakdown: membrane modules, scour system, CEB, pumps, civil, interconnect, controls"));
content.push(bullet("Carbon source and chemical clean-in-place (CIP) requirements"));

content.push(makeHeading("RFC-04 — Post-anoxic hydraulics", 2));
content.push(bullet("Mixing design: power input (kW/m³), mixer layout and spacing"));
content.push(bullet("Hydraulic residence time distribution (computational or tracer-based)"));
content.push(bullet("Methanol dosing distribution concept"));
content.push(bullet("Dead zone risk from former MBR structural features"));
content.push(bullet("De-aeration adequacy before the enlarged post-anoxic"));

content.push(makeHeading("RFC-05 — Structural feasibility", 2));
content.push(bullet("Structural engineering confirmation of MBR internal wall removability"));
content.push(bullet("Load transfer analysis for the combined 118 kL basin"));
content.push(bullet("Crack control and waterproofing strategy"));
content.push(bullet("Alternative reconfiguration if wall is load-bearing"));

content.push(makeHeading("RFC-06 — Phosphorus performance", 2));
content.push(bullet("Phosphorus mass balance under S2 configuration"));
content.push(bullet("Impact of R-recycle source change on bio-P and alum demand"));
content.push(bullet("TP compliance against 122 kg/yr annual and concentration limits"));
content.push(bullet("Alum dosing range and seasonal variation"));

content.push(makeHeading("RFC-07 — Solids handling", 2));
content.push(bullet("WAS production at 4,000 EP in S2 configuration"));
content.push(bullet("Impact on existing sludge pumps, storage, dewatering, polymer systems"));
content.push(bullet("Biosolids haulage and disposal capacity"));
content.push(bullet("Required upgrades or expansions to solids handling"));

content.push(makeHeading("RFC-08 — Influent alkalinity", 2));
content.push(bullet("Plant composite sampling for influent alkalinity over a minimum 2-week period including wet and dry days"));
content.push(bullet("Net alkalinity demand confirmation against actual biomass nitrogen uptake"));
content.push(bullet("If influent confirmed below 300 mg CaCO3/L: caustic storage and dosing system sizing review"));
content.push(bullet("If influent confirmed below 250 mg CaCO3/L: alternative alkalinity source assessment (lime, magnesium hydroxide) and corresponding capex addition"));
content.push(bullet("Indicative cost: AUD 3–5k for composite sampling program; AUD 150–300k for expanded NaOH system if required"));

content.push(makeHeading("RFC-09 — Carrier retention and MBR protection (S1B)", 2));
content.push(bullet("Retention screen design concept: mesh size, layout area, wedge-wire vs perforated plate, mounting approach"));
content.push(bullet("Headloss calculation under peak hydraulic load with partial screen fouling"));
content.push(bullet("Cleaning and maintenance access design including differential pressure monitoring"));
content.push(bullet("Carrier escape monitoring approach (continuous or periodic inspection) and failure containment strategy"));
content.push(bullet("Membrane protection design including downstream screening if required"));
content.push(bullet("Pilot or reference-site operational data for K5 carriers retrofitted upstream of an MBR — ideally from a comparable SEQ or Australian installation"));
content.push(bullet("Indicative cost: AUD 20–40k for retention design and pilot data workstream"));

content.push(makeHeading("Additional verification", 2));
content.push(bullet("Full dynamic simulation (BioWin or equivalent) with site-calibrated kinetics and annual flow/load data"));
content.push(bullet("Methanol dosing system detailed design including alternative carbon source assessment (ethanol, glycerol, acetate)"));
content.push(bullet("Current licence conditions verification against Rev B documented limits"));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 8. RECOMMENDATIONS ==============
content.push(makeHeading("RFC-10 — Resolve licence mass load basis with regulator (HIGHEST PRIORITY)", 3));
content.push(makePara(
  "Scope: QUU to consult with the Department of Environment and Science (Queensland) and any relevant catchment authority to confirm how the 607 kg TN/yr mass load limit will be treated at re-licensing for the intensified plant."
));
content.push(bullet("Confirm whether the mass load limit is interpreted as a hard environmental cap (Interpretation A) or a derived quantity that re-scales with design EP (Interpretation B). See Section 2.3."));
content.push(bullet("If Interpretation A applies: confirm the regulatory basis (catchment-wide nutrient cap, receiving water assimilative capacity, or licence wording) and whether any offset mechanism could apply."));
content.push(bullet("If Interpretation B applies: confirm the re-scaling formula will follow Rev B Table 2.1 footnote 1 (same concentration limits, updated design flow, +10% wet weather allowance)."));
content.push(bullet("Document the resolution as a licence condition before Phase 2 pre-feasibility design proceeds."));
content.push(makePara(
  "Cost: minor (QUU staff time and regulator consultation fees, ~AUD 5-15k). Timeline: 4–8 weeks.",
  { italics: true, color: COLOUR_GREY }
));
content.push(makePara(
  "Impact on project: STAGE 0 GATEWAY. RFC-10 is not a parallel verification item alongside RFC-01 to RFC-09 — it is the gateway question that determines whether the S2-C3 strategic narrative is defensible at all. Rev 18 tests Interpretation B as the strategic planning basis (modelled S2 capacity up to ~6,000 EP), but this does NOT constitute adoption. If the regulator confirms Interpretation A at relicensing, the capacity ceiling reverts to 4,000 EP and the variant ranking changes. QUU should resolve RFC-10 before emotional or organisational commitment to S2-C3 as a 5,500 EP strategy.",
  { color: COLOUR_WARN, italics: true }
));

content.push(makePara(
  "Note: the receiving water assessment and catchment engagement that will typically accompany any re-licensing application at higher EP sit outside the scope of this process engineering study. QUU's environmental team and/or specialist consultants own that workstream. The discharge load quantification in Section 5.4 provides the inputs needed for that engagement.",
  { italics: true, color: COLOUR_GREY, after: 180 }
));

content.push(makeHeading("RFC-12 — Flow balancing dynamic simulation (required for S2-E)", 3));
content.push(makePara(
  "Scope: if S2-E is selected as the preferred concept for pre-feasibility development, dynamic process simulation is required to confirm the flow balancing effect on peak post-anoxic loading and the resulting capacity uplift."
));
content.push(bullet("Build dynamic model (BioWIN or equivalent) of the S2-E configuration with site-specific diurnal flow profile (Rev B Fig 3.1 as baseline)"));
content.push(bullet("Parametrically test flow balance tank retention (1, 2, 4, 6 hours) vs post-anoxic peak NO3 loading"));
content.push(bullet("Confirm capacity uplift curve — identify minimum balance tank volume to reach target EP (5,500 or 6,000)"));
content.push(bullet("Test extreme conditions: wet weather flow events, temperature minimums, step loading"));
content.push(bullet("Output: balance tank sizing specification, capacity ceiling confirmation, peak TN modelling at design EP"));

content.push(makePara(
  "Cost: AUD 20-35k (dynamic simulation is the principal cost driver). Timeline: 4-6 weeks.",
  { italics: true, color: COLOUR_GREY }
));

content.push(makePara(
  "Priority: CONDITIONAL. RFC-12 is only required if S2-E is carried forward. If S2-C3 is selected on other grounds, RFC-12 is not in the critical path. However, S2-E cannot be committed to capital without RFC-12 closed.",
  { color: COLOUR_WARN, italics: true }
));

content.push(makeHeading("8. Recommendations", 1));

content.push(makeHeading("8.1 Immediate action — no regret", 2));
content.push(makePara(
  "Implement Scenario S1A (controls and operational upgrades only) as a low-regret action. Estimated capex AUD 280k. Captures the demonstrated benefit of flow-paced recycle control under diurnal load variation, refreshes instrumentation, and optimises operating setpoints. Compatible with all subsequent pathways.",
  { bold: true, after: 120 }
));

content.push(makeHeading("8.2 S1B — pre-feasibility verification required", 2));
content.push(makePara(
  "Scenario S1B (S1A plus IFAS) is repositioned in Rev 8 from \"conditional next step\" to a pathway requiring its own pre-feasibility verification. Three specific IFAS risks must be closed before S1B can be endorsed:",
  { after: 60 }
));
content.push(bullet("Aeration and oxygen transfer capacity with carriers installed (F2, RFC-02)"));
content.push(bullet("Alkalinity sufficiency for nitrification at IFAS-supported load (F8, RFC-08)"));
content.push(bullet("Carrier retention and MBR protection design (F9, RFC-09)"));
content.push(makePara(
  "S1B remains a potentially useful pathway to add nitrification reserve without the full cost of S2, but the Rev 5 \"no tank modifications, implement immediately\" framing was overstated. The IFAS retrofit is plausible in principle (consistent with EPA Nutrient Control Design Manual guidance) but has not been demonstrated for this specific plant. Decision on S1B should follow completion of RFC-02, RFC-08, and RFC-09.",
  { before: 120, after: 120 }
));

content.push(makeHeading("8.3 Intensification pathway — dependent on verification", 2));
content.push(makePara(
  "Scenario S2 (full reconfiguration) is identified as a potentially high-value intensification pathway with conceptual capacity to ~6,000 EP (Interpretation B basis; ~4,000 EP under Interpretation A). Two preferred concepts — S2-C3 and S2-E — sit alongside each other for pre-feasibility development. Choice between them depends on RFC-12 (flow balancing dynamic simulation). It should NOT be approved for capital on the basis of this screening study. Progress to pre-feasibility design is recommended, contingent on completion of the seven verification packages RFC-01 through RFC-07 (Section 7).",
  { after: 120 }
));

content.push(makeHeading("8.4 Decision gate for S2 capital commitment", 2));
content.push(makePara(
  "Proceed to funded S2 detailed design ONLY if all of the following are confirmed:",
  { after: 60 }
));
content.push(bullet("Licence mass load basis resolved with regulator (RFC-10) — STAGE 0 GATEWAY. Must close before committing to S2-C3 as the strategic pathway, not just before capital commitment."));

content.push(bullet("K3 methanol kinetics validated by bench testing on Canungra biomass (RFC-01)"));
content.push(bullet("Aeration capacity confirmed adequate at 4,000 EP with any IFAS or alpha-factor adjustments (RFC-02)"));
content.push(bullet("HF MBR vendor layouts confirm footprint and capex band (RFC-03)"));
content.push(bullet("Post-anoxic hydraulics and mixing demonstrate effective volume utilisation (RFC-04)"));
content.push(bullet("Flow balancing dynamic simulation complete if S2-E is carried forward (RFC-12)"));
content.push(bullet("Structural engineering confirms MBR wall removal viability (RFC-05)"));
content.push(bullet("Phosphorus compliance demonstrated under intensified configuration (RFC-06)"));
content.push(bullet("Solids handling capacity adequate or identified upgrades scoped (RFC-07)"));
content.push(bullet("Influent alkalinity measured and confirmed adequate for S2 at design peak load, or expanded caustic system scoped and costed (RFC-08)"));
content.push(bullet("For S1B specifically: carrier retention design confirmed, headloss acceptable, and MBR protection strategy verified (RFC-09)"));

content.push(makeHeading("8.5 Regulatory parallel track", 2));
content.push(makePara(
  "If catchment projections indicate demand beyond 4,000 EP within the planning horizon, commence engagement with the Department of Environment and Science on potential mass-load reallocation. S2 delivers effluent TN approximately 3× better per capita than Rev B configuration. This is a defensible basis for requesting a mass-load uplift."
));

content.push(new Paragraph({ children: [new PageBreak()] }));

// ============== 9. CAVEATS ==============
content.push(makeHeading("9. Caveats and limitations (comprehensive)", 1));

content.push(makePara(
  "This section consolidates the study's explicit caveats. It should be read in conjunction with the red-flag discussion (Section 6) and the verification package (Section 7)."
));

content.push(makeHeading("9.1 Model limitations", 2));
content.push(bullet("Steady-state solver with first-order MBR tank buffering — not a full dynamic simulation"));
content.push(bullet("Kinetic parameters are regional preliminary values, not calibrated to Canungra biomass"));
content.push(bullet("K3 MeOH-acclimated rate is the single most sensitive assumption and has not been site-tested"));
content.push(bullet("Post-anoxic is modelled as an ideal mixed tank; short-circuiting, dead zones, and methanol distribution effects are not captured"));
content.push(bullet("Sub-30-minute dynamics, wet weather events, and process upset responses are not resolved"));

content.push(makeHeading("9.2 Scope exclusions", 2));
content.push(bullet("Inlet hydraulics, screening, grit removal, flow splitting — separate assessment required"));
content.push(bullet("Aeration blower capacity, diffuser turn-up, oxygen transfer — separate assessment required"));
content.push(bullet("Solids handling, sludge dewatering, biosolids disposal — separate assessment required"));
content.push(bullet("Civil structural review including MBR wall removal — separate assessment required"));
content.push(bullet("Outlet works, UV disinfection, discharge modelling — separate assessment required"));
content.push(bullet("Electrical and instrumentation capacity beyond concept-level pump and VSD costs"));
content.push(bullet("Phosphorus compliance under intensified configuration"));

content.push(makeHeading("9.3 Commercial and planning caveats", 2));
content.push(bullet("Capex estimates are indicative 2024 Australian rates. Not a tender basis."));
content.push(bullet("Membrane packing density and sustainable flux values are representative of modern HF vendor products but subject to vendor-specific confirmation"));
content.push(bullet("HF MBR equipment capex of ~AUD 700k excludes any extended warranty or performance bond arrangements"));
content.push(bullet("Methanol is assumed as the external carbon source; alternative carbons should be assessed in Phase 2"));
content.push(bullet("Current licence conditions should be verified against the active licence document before any regulatory engagement"));
content.push(bullet("Population growth projections driving the capacity horizon should be confirmed with QUU planning"));

content.push(makeHeading("9.4 Status of key statements in this report", 2));
content.push(bullet("\"S2 can deliver approximately 4,000 EP\" — conceptual modelling result subject to verification"));
content.push(bullet("\"Biology does not impose a capacity constraint below 4,000 EP\" — within the modelled scope; excluded disciplines may impose binding constraints at lower EP"));
content.push(bullet("\"Annual mass load becomes the governing constraint\" — within the modelled scope; this is the apparent limit absent other constraints"));
content.push(bullet("\"S2 capex is approximately AUD 2.5M – 3.5M\" — screening band, subject to vendor and structural engagement"));
content.push(bullet("\"Flow-paced recycle control adds 200–500 EP capacity\" — modelled result; depends on existing pump turndown and instrumentation"));

// ============== DOCUMENT ==============
const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONT, color: COLOUR_ACCENT },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: FONT, color: COLOUR_ACCENT },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: FONT, color: COLOUR_PRIMARY },
        paragraph: { spacing: { before: 180, after: 120 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } },
                   run: { font: FONT, size: 22 } } }],
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOUR_PRIMARY, space: 4 } },
            children: [
              new TextRun({ text: "Canungra STP Intensification Concept Study", font: FONT, size: 18, color: COLOUR_GREY }),
              new TextRun({ text: "\t\t", font: FONT, size: 18 }),
              new TextRun({ text: "ph2o Consulting", font: FONT, size: 18, color: COLOUR_GREY, italics: true }),
            ],
          }),
        ],
      }),
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            alignment: AlignmentType.CENTER,
            border: { top: { style: BorderStyle.SINGLE, size: 6, color: COLOUR_PRIMARY, space: 4 } },
            children: [
              new TextRun({ text: "Page ", font: FONT, size: 18, color: COLOUR_GREY }),
              new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18, color: COLOUR_GREY }),
              new TextRun({ text: " of ", font: FONT, size: 18, color: COLOUR_GREY }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: 18, color: COLOUR_GREY }),
              new TextRun({ text: "  ·  Rev 20 April 2026 — Screening-level Concept Study", font: FONT, size: 18, color: COLOUR_GREY }),
            ],
          }),
        ],
      }),
    },
    children: content,
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/home/claude/canungra_final_report_rev20.docx", buffer);
  console.log("Rev 5 report created. Size:", buffer.length, "bytes");
});

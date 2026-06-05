"""
Detailed BioPoint V2 strategic pathway report (PDF).
Surfaces everything the spine actually computes: full conserved-quantity ledger tables,
energy balance, capacity intensification, OPEX breakdown, multi-dimensional confidence,
road-test validation, and a constants register with provenance (calibrated / estimate /
provisional). Driven by the spine on the road-tested ETP basis.
"""
import biopoint_v2_spine as S
import separate_digestion as SD
import foaming_risk as FR
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                HRFlowable, KeepTogether, PageBreak)

INK = colors.HexColor("#1a2e3b"); ACCENT = colors.HexColor("#1f6f78")
MUTED = colors.HexColor("#5d6b73"); LIGHT = colors.HexColor("#eef3f4")
WARN = colors.HexColor("#9a5b00"); RULE = colors.HexColor("#c9d6d9")
GOOD = colors.HexColor("#1f7a43"); PROV = colors.HexColor("#b7791f")

def sanitise(t):
    rep = {"₂": "<sub>2</sub>", "₃": "<sub>3</sub>", "₄": "<sub>4</sub>",
           "³": "<super>3</super>", "²": "<super>2</super>", "→": "-&gt;",
           "≈": "~", "–": "-", "—": "-", "×": "x", "•": "-", "±": "+/-"}
    for k, v in rep.items(): t = t.replace(k, v)
    return t

base = getSampleStyleSheet()
def mk(n, parent=None, **kw): return ParagraphStyle(n, parent=parent or base["Normal"], **kw)
S_TITLE = mk("t", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=INK)
S_SUB = mk("s", fontSize=10.5, leading=14, textColor=MUTED)
S_H1 = mk("h1", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=ACCENT, spaceBefore=13, spaceAfter=5)
S_H2 = mk("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=INK, spaceBefore=7, spaceAfter=3)
S_BODY = mk("b", fontSize=9.6, leading=13.5, textColor=INK, spaceAfter=5)
S_BULLET = mk("bl", parent=S_BODY, leftIndent=12, bulletIndent=2, spaceAfter=3)
S_SMALL = mk("sm", fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=4)
S_FATE = mk("f", fontSize=8.6, leading=12, textColor=INK)
S_CELL = mk("c", fontSize=8.4, leading=10.5, textColor=INK)
S_CELLB = mk("cb", fontName="Helvetica-Bold", fontSize=8.4, leading=10.5, textColor=INK)
S_CELLH = mk("ch", fontName="Helvetica-Bold", fontSize=8.4, leading=10.5, textColor=colors.white)
S_CR = mk("cr", parent=S_CELL, alignment=2)  # right
S_CRH = mk("crh", parent=S_CELLH, alignment=2)

def P(t, st=S_BODY): return Paragraph(sanitise(t), st)
def bullet(t, st=S_BULLET, mark="\u2013"): return Paragraph(sanitise(t), st, bulletText=mark)

def styled(tbl, head=True, money=False):
    cmds = [("GRID", (0, 0), (-1, -1), 0.3, RULE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if head:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    tbl.setStyle(TableStyle(cmds)); return tbl

def ledger_table(lg):
    rows = [[P("Stream", S_CELLH), P(f"In ({lg.unit})", S_CRH), P(f"Out ({lg.unit})", S_CRH)]]
    rows.append([P("<b>Inputs</b>", S_CELLB), P("", S_CR), P("", S_CR)])
    for k, v in lg.inflows.items():
        rows.append([P(k.replace("_", " "), S_CELL), P(f"{v:,.2f}", S_CR), P("", S_CR)])
    rows.append([P("<b>Outputs</b>", S_CELLB), P("", S_CR), P("", S_CR)])
    for k, v in lg.outflows.items():
        if abs(v) < 1e-9: continue
        rows.append([P(k.replace("_", " "), S_CELL), P("", S_CR), P(f"{v:,.2f}", S_CR)])
    closes = "closes" if lg.closes else "DOES NOT CLOSE"
    rows.append([P(f"<b>Balance</b> ({closes}, {lg.imbalance_pct:+.2f}%)", S_CELLB),
                 P(f"<b>{lg.total_in:,.1f}</b>", S_CR), P(f"<b>{lg.total_out:,.1f}</b>", S_CR)])
    t = Table(rows, colWidths=[96*mm, 37*mm, 37*mm]); styled(t)
    # shade the balance row
    t.setStyle(TableStyle([("BACKGROUND", (0, -1), (-1, -1),
                            LIGHT if lg.closes else colors.HexColor("#f7e2c8"))]))
    return t

def kv(rows, w=(96, 74), bold_last=False):
    data = [[P(r[0], S_CELL), P(r[1], S_CR if isinstance(r[1], str) else S_CR)] for r in rows]
    t = Table(data, colWidths=[w[0]*mm, w[1]*mm]); styled(t, head=False)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, RULE),
                           ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT])]))
    return t


def _engine(plant):
    """THE ENGINE. Build all pathways and run every calculation ONCE. All three report
    views read from this same bundle — identical numbers, different presentation."""
    return {
        "plant": plant,
        "wp": S.build_worked_pathway(plant),       # spine: THP + MAD + struvite + land
        "tp": S.build_thermal_pathway(plant),      # thermal endpoint
        "cp": S.build_conventional_pathway(plant), # conventional baseline
        "weights": S.rank_weights(S.DRIVER_RANKING_PLUS),
        "sf": _sf_bundle(plant),
    }


def thp_value(wp, cap):
    """Consolidated THP benefit streams (V3 U7) - single source used by both reports."""
    solids = wp.basis["product_wet_tpd"] * 0.28
    wet_conv, wet_thp = solids / 0.22, solids / 0.32
    disposal = (wet_conv - wet_thp) * 365 * 80 / 1e6
    logistics = (wet_conv - wet_thp) / 40 * 365 * 350 / 1e6
    energy = wp.net_export_mwh_d * 365 * S.KO.ELEC_PRICE_MWH / 1e6
    capacity = cap["avoided_capex_aud"] / 20 / 1e6
    return {"capacity": capacity, "disposal": disposal, "logistics": logistics,
            "energy": energy, "wet_conv": wet_conv, "wet_thp": wet_thp,
            "total": capacity + disposal + logistics + energy}


def _sf_bundle(plant):
    """Bridge: separate-digestion, recuperative-thickening and foaming data from the page-12 engines."""
    vs_ts = plant["vs_ts"]
    vs_ps, vs_was = plant["PS_tds"] * vs_ts, plant["WAS_tds"] * vs_ts
    ps_flow  = plant["PS_tds"]  / (plant["ps_ts"]  / 100.0)
    was_flow = plant["WAS_tds"] / (plant["was_ts"] / 100.0)
    inst = plant["digester_vol_m3"]
    sep  = SD.separate_scenario(vs_ps, vs_was, ps_flow, was_flow, inst, hrt_ps_d=12.0, hrt_was_d=18.0)
    af, weighted = SD.antagonism_factor(vs_ps, vs_was)
    diag = SD.hrt_limited_diagnosis(ps_flow, was_flow, inst, srt_ps_d=12.0, srt_was_d=18.0)
    rv   = SD.recuperative_value(vs_was, was_flow, 12.0, rt_multiplier=1.5, was_feed_ts_pct=plant["was_ts"])
    was_frac = vs_was / (vs_ps + vs_was)
    vsr_was = 0.27
    blend_feed_ts = (plant["PS_tds"] + plant["WAS_tds"]) / (ps_flow + was_flow) * 100.0
    ts_by = {"Conventional blended": SD.digester_ts_pct(blend_feed_ts, 1.0, 0.55),
             "Separate PS/WAS": SD.digester_ts_pct(plant["was_ts"], 1.0, vsr_was),
             "Separate + RT": SD.digester_ts_pct(plant["was_ts"], 1.5, vsr_was),
             "K+ (Sep+SolidStream+Recycle)": SD.digester_ts_pct(plant["was_ts"], 1.5, vsr_was)}
    srt_by = {"Conventional blended": inst / (ps_flow + was_flow), "Separate PS/WAS": 18.0,
              "Separate + RT": 18.0, "K+ (Sep+SolidStream+Recycle)": 18.0}
    def _olrw(h): return vs_was * 1000.0 / (was_flow * h)
    olr_by = {"Conventional blended": (vs_ps + vs_was) * 1000.0 / inst, "Separate PS/WAS": _olrw(18.0),
              "Separate + RT": _olrw(12.0), "K+ (Sep+SolidStream+Recycle)": _olrw(12.0)}
    foam = FR.compare_pathways(was_frac, 45.0, 25.0, 70.0, ts_by, srt_by, olr_by)
    residual = SD.residual_after_separation(vs_ps, vs_was, ps_flow, was_flow, inst, srt_ps_d=12.0, srt_was_d=18.0)
    return {"sep": sep, "af": af, "weighted": weighted, "diag": diag, "rv": rv, "foam": foam,
            "inst": inst, "residual": residual}


def _separate_digestion_section(sf):
    sep, af, w, diag, rv = sf["sep"], sf["af"], sf["weighted"], sf["diag"], sf["rv"]
    out = [P("Separate Digestion, Recuperative Thickening and Capacity", S_H1)]
    out.append(P("Digesting primary and waste-activated sludge in dedicated trains lifts biomethane by "
        f"<b>{sep['uplift_pct']:+.0f}%</b> over the blended base case "
        f"({sep['ch4_blend_m3d']:,.0f} to {sep['ch4_sep_m3d']:,.0f} m3 CH4/d). The driver is co-digestion "
        f"<b>antagonism relief</b>, measured in the lab: a blended sample yields only {af*100:.0f}% of the "
        f"VS-weighted separate-stream BMPs ({w:.0f} mL/g), and separating the streams recovers the difference. "
        "Lab-grounded on one Mangere dataset, so it carries a lab-to-full-scale transfer caveat."))
    if diag["hrt_limited"]:
        out.append(P(f"This plant is <b>HRT-limited</b>: the biogas-adequate split needs "
            f"{diag['required_vol_m3']:,.0f} m3 against {sf['inst']:,.0f} m3 installed (deficit "
            f"{diag['deficit_m3']:,.0f} m3). Recuperative thickening decouples solids retention from hydraulic "
            "retention - it holds the WAS SRT while the HRT, and so the volume, drops. At a 1.5x retention "
            f"multiplier it preserves {rv['biogas_benefit_m3d']:,.0f} m3 CH4/d that running SRT = HRT would lose "
            f"and frees about {rv['vol_saved_m3']:,.0f} m3 of tankage, bounded by a {SD.SRT_WASHOUT_FLOOR:.0f} d "
            f"methanogen washout floor and a {SD.TS_VISCOSITY_LIMIT:.0f}% TS viscosity limit."))
    else:
        out.append(P(f"This plant is <b>not capacity-constrained</b>. The Capacity Stress Index (required / "
            f"installed volume) is <b>{diag['capacity_stress_index']:.2f}</b> ({diag['capacity_band']}): the "
            f"biogas-adequate split fits in {sf['inst']:,.0f} m3 with {diag['surplus_m3']:,.0f} m3 "
            f"({diag['spare_fraction']*100:.0f}%) to spare."))
        if diag.get("rt_value_collapses"):
            out.append(P("With more than 20% digester headroom already in place, <b>recuperative-thickening value "
                "collapses</b> here - it adds no biomethane and frees volume the plant does not need. Capacity "
                "benefit is site-specific, not a property of the technology: it is a function of existing "
                "utilisation, which is why BioPoint computes the Stress Index before recommending capacity work.",
                S_SMALL))
    out.append(P("BioPoint splits this into two layers. <b>K-Core</b> (separate digestion + recuperative "
        "thickening) carries the capacity and stability benefit at <b>confidence B</b>. <b>K-Assist</b> "
        "(SolidStream-treated WAS ceiling uplift) is the methane add-on, still <b>confidence D</b> until a "
        "treated-WAS BMP is measured. The residual uncertainty is the assist factor, not whether separate "
        "digestion works.", S_SMALL))
    out.append(P("Recuperative thickening is a capacity and stability technology, not a biogas technology: its "
        "biomethane benefit is negligible unless the plant is HRT-limited below the BMP plateau. The layers act "
        "on different streams and add at the stream level - they are not multiplied as whole-plant percentages.",
        S_SMALL))
    r = sf.get("residual")
    if r:
        out.append(P("What Remains After Separate Digestion", S_H2))
        out.append(P(f"THP should be benchmarked against the <i>optimised</i> separate-digestion platform, not "
            f"conventional blended digestion. On that basis separate digestion already captures "
            f"<b>{r['captured_fraction']*100:.0f}%</b> of THP's total methane benefit before any THP capital is "
            f"committed - the comparison most THP business cases never make."))
        out.append(kv([
            ("Methane: conventional -> separate -> +THP",
             f"{r['conv_ch4_m3d']:,.0f} -> {r['sep_ch4_m3d']:,.0f} -> {r['thp_ch4_m3d']:,.0f} m3 CH4/d"),
            ("THP benefit already captured by separation", f"{r['captured_fraction']*100:.0f}%"),
            ("Residual CAPACITY gap (Stress Index)", f"{r['capacity_stress_index']:.2f} ({r['capacity_band']})"),
            ("Residual YIELD gap (WAS ceiling lift, THP/SolidStream only)", f"{r['thp_only_residual_m3d']:,.0f} m3 CH4/d"),
            ("Binding residual -> what THP/RT must justify", r['residual_binds']),
        ]))
        out.append(P("After separation the residual splits into a capacity gap (the Stress Index) and a yield gap "
            "(the WAS biodegradable ceiling, which only THP or SolidStream can move). THP and recuperative "
            "thickening should be triggered by whichever residual actually binds - not assumed. Magnitudes are "
            "screening-grade: the ceiling lift uses the inferred WAS-THP BMP (confidence D).", S_SMALL))
    return out


def _foaming_section(sf):
    foam = sf["foam"]
    out = [P("Digester Foaming Risk", S_H1)]
    out.append(P("Foaming is not a single variable. Four independent mechanisms are scored 0-100 and reported as "
        "a profile, never collapsed: Type 1 filament (Nocardia / Gordonia / mycolata), Type 2 gas entrapment "
        "(viscosity, gas hold-up), Type 3 surfactant (FOG, proteins, cell lysis), Type 4 instability (VFA, "
        "methanogen washout). The pathways move these in different, often opposing, directions."))
    head = ["Pathway", "T1 film", "T2 gas", "T3 surf", "T4 instab", "Overall"]
    rows = [[P(h, S_CELLH if i == 0 else S_CRH) for i, h in enumerate(head)]]
    order = ["Type1_filament", "Type2_gas_entrapment", "Type3_surfactant", "Type4_instability"]
    for name, r in foam.items():
        cells = [P(name, S_CELL)]
        for key in order:
            cells.append(P(f"{r[key]:.0f} {r['bands'][key][:3]}", S_CR))
        cells.append(P(f"{r['overall']:.0f} {r['overall_band'][:3]}", S_CR))
        rows.append(cells)
    t = Table(rows, colWidths=[52*mm, 23*mm, 23*mm, 23*mm, 23*mm, 23*mm]); styled(t)
    out.append(t)
    base, kp = foam["Conventional blended"], foam["K+ (Sep+SolidStream+Recycle)"]
    out.append(P(f"<b>K+ versus conventional:</b> filament {kp['Type1_filament']-base['Type1_filament']:+.0f}, gas "
        f"{kp['Type2_gas_entrapment']-base['Type2_gas_entrapment']:+.0f}, surfactant "
        f"{kp['Type3_surfactant']-base['Type3_surfactant']:+.0f}, instability "
        f"{kp['Type4_instability']-base['Type4_instability']:+.0f}; overall {base['overall']:.0f} to "
        f"{kp['overall']:.0f}. K+ lowers instability foaming but raises filament and physical foaming. None of "
        "these technologies automatically reduces overall foaming risk - it is site-specific, and foaming is a "
        "first-order design consideration here, not an operational afterthought."))
    rf = kp.get("recycle_factor")
    if rf:
        amm = " - and at this recycle ammonia the instability benefit is being clawed back by inhibition" if rf["ammonia_inhibition"] else ""
        out.append(P(f"<b>Hot-liquor recycle is double-edged.</b> Decomposed: instability (Type 4) "
            f"{rf['d_type4']:+.0f} from soluble-COD conversion and alkalinity buffering, but surfactant (Type 3) "
            f"{rf['d_type3']:+.0f} and gas entrapment (Type 2) {rf['d_type2']:+.0f} from returned soluble "
            f"proteins and higher gas flux{amm}. Recycle ratio, temperature, soluble COD and ammonia all move "
            "these, so the net is site-specific - do not assume improvement or deterioration."))
    out.append(P("<b>Operability, not methane, may decide K+ at full scale.</b> Separate digestion buys methane "
        "and capacity (confidence B); recuperative thickening protects SRT and stability and releases volume "
        "(not methane); SolidStream recycle offers a biodegradable-ceiling uplift still at confidence D. BioPoint "
        "now weights foaming resilience alongside yield and capacity, because a WAS-only train with recycle is "
        "where filament, gas-entrapment and surfactant foaming concentrate.", S_SMALL))
    out.append(P("Foaming scored at assumed moderate filament prevalence (45/100), FOG (25), mixing (70). To move "
        "from screening (confidence C) to bankable, validate with: Nocardia / Gordonia / mycolata microscopy, gas "
        "flux per m2, digester TS and viscosity, recycle soluble protein / EPS, hot-liquor recycle ratio, and "
        "antifoam history.", S_SMALL))
    return out


def _screening_banner(plant):
    note = plant.get("screening_note")
    if not note:
        return []
    from reportlab.lib import colors as _c
    t = Table([[P("<b>SCREENING-GRADE ASSESSMENT &mdash; provisional.</b> " + note, S_SMALL)]], colWidths=[170*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _c.HexColor("#FFF3E0")),
        ("BOX", (0, 0), (-1, -1), 0.9, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 8)]


def build(bundle):
    """Mode 2 view — Strategic Pathway Report (pathway / ledger / roadmap focused)."""
    plant, wp, tp = bundle["plant"], bundle["wp"], bundle["tp"]
    weights = bundle["weights"]
    K = S.K; vs_ts = plant["vs_ts"]; tot = plant["PS_tds"] + plant["WAS_tds"]
    VS_in = tot * vs_ts; VS_d = VS_in * K.VSR
    story = []

    # ===== header =====
    story.append(P("Strategic Biosolids Pathway Report", S_TITLE))
    story.append(P("BioPoint V3.5 &middot; Carbon, Nutrient, Capacity &amp; Biosolids Strategy Engine", S_SUB))
    story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=3, spaceAfter=8))
    story.extend(_screening_banner(bundle["plant"]))

    # ===== V3.5 strategic framing =====
    story.append(P("The Strategic Question", S_H1))
    story.append(P("This report does not ask <i>which digestion technology scores highest</i>. It asks four "
                   "objective-level questions and treats technology as the means to answer them:"))
    story.append(bullet("<b>Carbon</b> &mdash; where should it go: retained in soil or biochar, converted to "
                        "energy, or destroyed? This is the Stage-3 endpoint decision."))
    story.append(bullet("<b>Nutrients</b> &mdash; recover phosphorus (struvite), destroy the return-liquor "
                        "nitrogen load (PN/A), or return it to the plant?"))
    story.append(bullet("<b>Capacity</b> &mdash; unlock digester headroom by THP, or by separate PS/WAS "
                        "digestion at short PS HRT, a lower-risk mechanism with no hydrolysis step?"))
    story.append(bullet("<b>Biosolids quality</b> &mdash; cake dryness, pathogen grade, transport and storage "
                        "burden, with SolidStream as the quality platform."))
    story.append(P("These are three different optimisation problems handled in sequence: <b>separate digestion "
                   "optimises the biology, SolidStream optimises the biosolids, and the endpoint optimises the "
                   "carbon</b>. The recommendation is a front-end plus an endpoint chosen for the objective being "
                   "optimised &mdash; carried with its confidence level, not collapsed into a single technology score."))

    # ===== executive summary =====
    story.append(P("Executive Summary", S_H1))
    cap = S.capacity_view(wp); ox = S.opex_view(wp)
    story.append(P(
        f"For the {plant['name']} ({tot:.0f} tDS/d), BioPoint compares biosolids pathways against the "
        "utility's weighted drivers using conserved-quantity ledgers (carbon, energy, nitrogen, phosphorus) "
        "that must balance end-to-end. The output is not a chosen technology but a <b>preferred strategic "
        "pathway</b>: a biology and biosolids-quality front-end, plus a carbon endpoint selected for the "
        "objective being optimised. The strongest front-end couples <b>separate PS/WAS digestion</b> (which "
        "unlocks ~2 digesters of capacity with no hydrolysis step) with <b>SolidStream</b> (Class-A cake at "
        f"~38% DS), running strongly energy-positive (~{wp.net_export_mwh_d:,.0f} MWh/d net on the THP spine) "
        f"and intensifying capacity by ~{cap['digesters_avoided']:.1f} reference digesters "
        f"(~${cap['avoided_capex_aud']/1e6:.0f}M deferred)."))
    story.append(P(
        "Two objectives dominate the endpoint and nutrient decisions. <b>Nitrogen:</b> conventional digestion "
        "returns a large sidestream ammonia load to the plant (~3,300 kgN/d conventional, rising to ~4,650 on the SolidStream recycle, measured against ETP\u2019s Cambi mass balances) &mdash; a "
        "near-term operational and consenting constraint that sidestream PN/A can cut by ~88%, and that for "
        "many plants binds sooner than PFAS. <b>Carbon / PFAS:</b> the endpoint sets carbon fate and PFAS "
        "destruction &mdash; land retention, pyrolysis (durable biochar plus carbon credits), gasification, or "
        "incineration (maximum PFAS destruction). These are <i>independent</i> of the digestion choice and are "
        "compared by fate, not collapsed into one score (see Carbon Endpoint Strategy, below)."))
    story.append(P("<b>Organising principle:</b> biology, biosolids quality and carbon endpoint are three "
                   "independent decisions. Separate digestion optimises the biology (methane and capacity); "
                   "SolidStream optimises the biosolids (cake and logistics); the endpoint optimises carbon fate "
                   "(retention / conversion / destruction). Forcing them into one digestion score hides the "
                   "interactions &mdash; for example, SolidStream's drier cake roughly halves the drying energy a "
                   "thermal endpoint needs.",
                   mk("ins", parent=S_BODY, textColor=INK, backColor=LIGHT, borderPadding=6,
                      spaceBefore=4, leftIndent=4, rightIndent=4)))

    # ===== Decision hierarchy (V3 U1) =====
    dh = S.decision_hierarchy(plant)
    story.append(P("Decision Hierarchy (L1-L5) &amp; Least-Regret Pathway", S_H1))
    story.append(P("Constraint diagnosis drives the ordering; it does not prune. Every viable pathway "
                   "stays active. A pathway is flagged where a shock at or above "
                   f"{dh['risk_threshold']:.0%} likelihood would break it &mdash; it stays on the table "
                   "but must be paired with the named hedge to be commit-grade.", S_SMALL))
    story.append(P("L1 &nbsp; Constraint Diagnosis", S_H2))
    rows=[[P("Constraint", S_CELLH), P("Status", S_CELLH), P("State", S_CELLH), P("Flips under", S_CELLH)]]
    for c in dh["L1_constraints"]:
        rows.append([P(c["constraint"].replace("_"," "), S_CELL),
                     P("BINDING" if c["binding"] else "watch", S_CELL),
                     P(c["state"], S_CELL), P(", ".join(c["shocks"]) or "-", S_CELL)])
    story.append(styled(Table(rows, colWidths=[34*mm, 16*mm, 78*mm, 42*mm])))
    L2=dh["L2_capacity"]; L3=dh["L3_resource_recovery"]; L4=dh["L4_carbon"]
    story.append(kv([
        ("L2 Capacity intensification", f"{L2.get('digesters_avoided',0):.1f} digesters avoided; {L2.get('capacity_headroom_tds',0):,.0f} tDS/d headroom"),
        ("L3 Resource recovery", f"nutrient value ${L3['nutrient_value_m_aud_yr']:.2f}M/yr (P {L3['P_security_pct']:.0f}% recovered)"),
        ("L4 Carbon strategy", f"removed {L4['net_removal_tCO2e_yr']:,.0f} + avoided {L4['avoided_fossil_tCO2e_yr']:,.0f} tCO2e/yr (separate)"),
        ("L5 Thermal endpoint", "evidence-graded; held open as a hedge"),
    ], w=(52, 118)))
    story.append(P("Pathways &mdash; regret profile (none pruned)", S_H2))
    rows=[[P("Pathway", S_CELLH), P("Perf", S_CRH), P("Conf", S_CRH), P("Resil", S_CRH), P("Risk", S_CRH), P("Breaks under (hedge needed)", S_CELLH)]]
    for p in dh["pathways"]:
        rows.append([P(p["pathway"], S_CELL), P(f"{p['performance']*100:.0f}", S_CR),
                     P(p["confidence"], S_CR), P(f"{p['resilience']:.2f}", S_CR),
                     P("OK" if p["acceptable_risk"] else "HEDGE", S_CR),
                     P("-" if p["acceptable_risk"] else ", ".join(x["shock"] for x in p["high_likelihood_shocks"]), S_CELL)])
    story.append(styled(Table(rows, colWidths=[54*mm, 12*mm, 12*mm, 14*mm, 16*mm, 62*mm])))
    story.append(P("Risk OK = no shock at/above the threshold breaks it; HEDGE = one does. HEDGE pathways "
                   "are retained, not removed &mdash; the recommendation pairs them with a kept-open option "
                   "(e.g. a thermal endpoint against a PFAS land-application ban).", S_SMALL))

    story.append(P("Driver breakdown &mdash; where the scores actually differ", S_H2))
    story.append(P("Performance is a weighted view of six ledger-derived drivers (0-1). The single number "
                   "can look close; the differentiation lives in the drivers. PFAS is a flat zero for every "
                   "digestion route (an endpoint property, not a digestion one) and Scope 1 is uniformly low "
                   "&mdash; so the digestion choice is decided by capacity, net-energy yield and OPEX.", S_SMALL))
    dpaths = [("Conv", S.build_conventional_pathway(plant)), ("K+", S.build_pathway_k_plus(plant)),
              ("THP", S.build_worked_pathway(plant)), ("SolidS", S.build_solidstream_pathway(plant)), ("Therm", tp)]
    drows = [[P("Driver", S_CELLH)] + [P(nm, S_CRH) for nm, _ in dpaths]]
    for key, lab in [("scope1_emissions","Scope 1"),("pfas","PFAS"),("nutrient_recovery","Nutrient"),
                     ("opex","OPEX"),("energy_neutrality","Energy yield"),("capacity","Capacity")]:
        drows.append([P(lab, S_CELL)] + [P(f"{pw.driver_scores().get(key,0):.2f}", S_CR) for _, pw in dpaths])
    drows.append([P("<b>Performance</b>", S_CELLB)] +
                 [P(f"<b>{S.three_axis(pw, weights)['performance']*100:.0f}</b>", S_CR) for _, pw in dpaths])
    story.append(styled(Table(drows, colWidths=[30*mm, 22*mm, 22*mm, 22*mm, 24*mm, 22*mm])))
    story.append(P("The energy driver is net-export YIELD per tonne VS (not the old net/gross ratio, which was "
                   "near-constant and flattened the score). Capacity and energy yield are where K+ and SolidStream "
                   "separate from conventional, and THP-WAS sits below them on energy because of its parasitic load.", S_SMALL))

    # ===== V3.5 Carbon Endpoint Strategy (Stage 3) =====
    comp = S.carbon_strategy_comparison(plant)
    _arg = lambda metric: max(comp, key=lambda x: x[metric])["endpoint"]
    story.append(P("Carbon &amp; PFAS Endpoint &mdash; the third, independent decision", S_H1))
    story.append(P("Before digestion architecture, the board-level question is where the carbon finally goes. "
                   "No single endpoint wins on every objective &mdash; the endpoint is chosen for the objective "
                   "being optimised, separately from the digestion decision.", S_SMALL))
    obj_tbl = [[P("If the objective is\u2026", S_CELLH), P("\u2026the endpoint is", S_CRH)]]
    for o, e in [("Carbon permanence / CO\u2082 removal", _arg("removed_tCO2e_d")),
                 ("Maximum energy", _arg("net_export_mwh_d")),
                 ("PFAS destruction", _arg("pfas_destruction")),
                 ("Lowest cost / simplicity (today)", "Land application")]:
        obj_tbl.append([P(o, S_CELL), P(e, S_CR)])
    story.append(styled(Table(obj_tbl, colWidths=[85*mm, 65*mm])))
    story.append(Spacer(1, 4))
    hdr = [P("Endpoint", S_CELLH), P("Strategy", S_CELLH), P("Retain tC/d", S_CRH), P("Seq.", S_CRH),
           P("Emit", S_CRH), P("Removed CO2e", S_CRH), P("PFAS", S_CRH), P("Net MWh/d", S_CRH), P("Conf", S_CRH)]
    rows = [hdr]
    for r in comp:
        rows.append([P(r["endpoint"], S_CELL), P(r["family"].replace("Carbon ", ""), S_CELL),
                     P(f"{r['retained_tC_d']:.1f}", S_CR), P(f"{r['sequestered_tC_d']:.1f}", S_CR),
                     P(f"{r['destroyed_emitted_tC_d']:.0f}", S_CR), P(f"{r['removed_tCO2e_d']:.1f}", S_CR),
                     P(f"{r['pfas_destruction']*100:.0f}%", S_CR), P(f"{r['net_export_mwh_d']:.0f}", S_CR),
                     P(r["confidence"], S_CR)])
    story.append(KeepTogether([
        P("Endpoint ledgers &mdash; by carbon-fate family (retention / conversion / destruction)", S_H2),
        P("Biology (separate digestion) optimises methane and capacity; biosolids quality "
          "(SolidStream) optimises the cake; the <i>endpoint</i> optimises where the carbon "
          "finally goes &mdash; a third, independent decision. BioPoint composes the strategic "
          "ETP front-end (Pathway K) with each Stage-3 endpoint and groups them by carbon fate "
          "into three families. The columns are deliberately NOT combined into one score: "
          "retaining carbon, converting it to energy and destroying it for PFAS resilience are "
          "different objectives, and each family wins a different one."),
        styled(Table(rows, colWidths=[22*mm, 24*mm, 16*mm, 12*mm, 12*mm, 18*mm, 13*mm, 16*mm, 11*mm])),
    ]))
    story.append(Spacer(1, 3))
    story.append(P("Reading it by objective, not by score: <b>pyrolysis</b> (Retention) gives the most "
                   "durable carbon &mdash; it retains less mass than land but sequesters more than twice "
                   "as much at 100 years, the highest CO2 removal, at confidence B. <b>Incineration</b> "
                   "(Destruction) retains no carbon or nutrients but maximises PFAS destruction and is "
                   "most mature (confidence A) &mdash; the regulatory-resilience play. <b>HTL</b> gives "
                   "the most energy and a biocrude product but is pre-commercial (confidence C). Land "
                   "stays cheapest today, but its retained carbon is low-permanence and it carries the "
                   "PFAS land-application risk.", S_SMALL))
    story.append(P("<b>Preferred Strategic Carbon and Nutrient Pathway</b> is therefore not a single "
                   "technology but a front-end (separate digestion + SolidStream) plus an endpoint chosen "
                   "for the objective being optimised &mdash; carbon permanence, energy, or PFAS "
                   "resilience &mdash; carried with its confidence level, not collapsed into one number.", S_SMALL))
    story.append(Spacer(1, 6))

    # ===== V3.6 Nitrogen Strategy (parallel pillar to carbon) =====
    nsc = S.nitrogen_strategy_comparison(plant)
    story.append(P("Nitrogen Strategy &mdash; the sidestream-N decision (a pillar in its own right)", S_H1))
    story.append(P(f"Digestion sets the capacity; the endpoint sets the carbon fate; the <i>nitrogen strategy</i> "
                   f"decides what happens to the ~{nsc['sidestream_N_kgd']:,.0f} kgN/d of sidestream ammonia "
                   "(single-pass centrate basis; the SolidStream recycle raises it ~40%). It is a separate, "
                   "independent decision, grouped &mdash; exactly like carbon &mdash; into Return / Destruction / "
                   "Recovery, and deliberately not collapsed into one score.", S_SMALL))
    nobj = [("Lowest WWTW N load / N2O risk", "Sidestream PN/A, or the Hybrid"),
            ("A saleable N product / revenue", "Ammonium sulphate"),
            ("Phosphorus co-recovery", "Struvite"),
            ("Lowest cost / simplicity (today)", "Mainstream return")]
    ot = [[P("If the objective is\u2026", S_CELLH), P("\u2026the nitrogen strategy is", S_CRH)]]
    for o, e in nobj:
        ot.append([P(o, S_CELL), P(e, S_CR)])
    story.append(styled(Table(ot, colWidths=[85*mm, 65*mm])))
    story.append(Spacer(1, 4))
    nrows = [[P("Strategy", S_CELLH), P("Family", S_CELLH), P("N to N2", S_CRH), P("N recovered", S_CRH),
              P("Residual load", S_CRH), P("Load cut", S_CRH), P("Conf", S_CRH)]]
    for x in nsc["rows"]:
        nrows.append([P(x["strategy"], S_CELL), P(x["family"], S_CELL), P(f"{x['n_to_n2_kgd']:,}", S_CR),
                      P(f"{x['n_recovered_kgd']:,}", S_CR), P(f"{x['residual_load_kgd']:,}", S_CR),
                      P(f"{x['load_cut_pct']}%", S_CR), P(x["confidence"], S_CR)])
    story.append(styled(Table(nrows, colWidths=[40*mm, 27*mm, 16*mm, 18*mm, 18*mm, 14*mm, 11*mm])))
    story.append(P("N to N2 = destroyed to nitrogen gas (no product); residual load = sidestream N still returned "
                   "to the WWTW; figures are kgN/d on the single-pass centrate. " + nsc["headline"], S_SMALL))
    story.append(P("<b>Endpoint independence:</b> a thermal carbon endpoint volatilises the <i>cake</i> nitrogen to "
                   "air, but the <i>sidestream</i> centrate N is a separate stream the nitrogen strategy manages "
                   "regardless &mdash; so the nitrogen decision is independent of both the digestion choice and the "
                   "carbon endpoint, in the same way PFAS is set by the endpoint alone. Carbon, Nitrogen and PFAS "
                   "are three parallel strategy axes, not one combined score.",
                   mk("nind", parent=S_SMALL, backColor=LIGHT, borderPadding=6, spaceBefore=3)))
    story.append(Spacer(1, 6))

    # ===== 1 objective =====
    story.append(P("1 &nbsp; Strategic Objective", S_H1))
    story.append(P("Pathways are weighted against the utility's stated driver ranking. The "
                   "weighting is transparent rank-order (top driver heaviest), so the basis of "
                   "every trade-off is visible to the decision-maker:"))
    rows = [[P("Rank", S_CELLH), P("Driver", S_CELLH), P("Weight", S_CRH)]]
    for i, (d, w) in enumerate(sorted(weights.items(), key=lambda kv: -kv[1]), 1):
        rows.append([P(str(i), S_CELL), P(d.replace("_", " ").title(), S_CELL), P(f"{w:.3f}", S_CR)])
    story.append(styled(Table(rows, colWidths=[18*mm, 122*mm, 30*mm])))
    story.append(Spacer(1, 3))
    story.append(P("Because OPEX sits mid-table and CAPEX is ranked last, recommending a "
                   "costlier pathway over a cheaper one is consistent with the stated objective "
                   "rather than a contradiction &mdash; the weighting makes that explicit.", S_SMALL))

    # ===== 2 plant basis =====
    story.append(P("2 &nbsp; Plant Basis &amp; Stream Characterisation", S_H1))
    story.append(kv([
        ("Primary sludge (PS)", f"{plant['PS_tds']:.1f} tDS/d @ {plant['ps_ts']:.1f}% TS"),
        ("Waste activated sludge (WAS)", f"{plant['WAS_tds']:.1f} tDS/d @ {plant['was_ts']:.1f}% TS"),
        ("Total dry solids load", f"{tot:.1f} tDS/d"),
        ("Volatile solids ratio (VS/TS)", f"{vs_ts*100:.0f}%"),
        ("Volatile solids in feed", f"{VS_in:.1f} tVS/d"),
        ("VS reduction (VSR, calibrated)", f"{K.VSR*100:.1f}% -&gt; {VS_d:.1f} tVS/d destroyed"),
        ("Feed nitrogen", f"{plant['feed_N_kgd']:,.0f} kg N/d"),
        ("Feed phosphorus (estimate)", f"{tot*plant.get('P_per_ds',K.P_PER_DS)*1000:,.0f} kg P/d"),
        ("Existing digester volume", f"{plant.get('digester_vol_m3',0):,.0f} m\u00b3"),
    ]))

    # ===== 3 methodology =====
    story.append(P("3 &nbsp; Method: Conservation Ledgers &amp; the Closure Gate", S_H1))
    story.append(P("Every pathway is modelled as four conserved-quantity ledgers &mdash; carbon, "
                   "energy, nitrogen, phosphorus &mdash; each tracked from feed to final fate. A "
                   "ledger is admissible only if it <b>closes</b> (inputs equal outputs within "
                   "tolerance). A ledger that does not close is a model error, not a result; this "
                   "is the same discipline that, on a real plant, catches a missing stream or a "
                   "double-counted yield. Driver scores are then read directly off these balances "
                   "(Scope 1 from the carbon-to-atmosphere branch, energy neutrality from the "
                   "energy net, nutrient recovery from the recovered N and P fractions), so the "
                   "drivers cannot double-count or contradict one another."))
    story.append(P("Commit-grade closure tolerance is 2%. Where split fractions are not yet "
                   "calibrated against a full-scale balance (the thermal endpoints), the ledger "
                   "still conserves mass but is flagged <b>provisional</b>, and the affected "
                   "drivers are reported as uncertainty bands rather than point values.", S_SMALL))

    # ===== 4 constraints =====
    story.append(P("4 &nbsp; Constraints (what the ledgers force into the open)", S_H1))
    for b in [
        "<b>PFAS:</b> the calibrated AD/THP spine destroys none; it concentrates PFAS into "
        "land-applied cake. Only a thermal endpoint addresses this driver.",
        "<b>Return-liquor nitrogen:</b> struvite is phosphorus-limited, so most mineralised "
        "ammonia returns to the host works &mdash; a treatment load and an N₂O / Scope-1 risk.",
        "<b>Nutrient&ndash;thermal tension:</b> thermal strands phosphorus in ash and volatilises "
        "nitrogen, so nutrients must be recovered upstream if both PFAS and recovery matter.",
        "<b>Capacity:</b> at this load the conventional digester HRT is tight; THP relieves it "
        "(quantified in Section 5)."]:
        story.append(bullet(b))

    story.append(PageBreak())

    # ===== 5 pathways (full detail) =====
    story.append(P("5 &nbsp; Pathways &mdash; Detailed Ledgers", S_H1))
    for pw in (wp, tp):
        prov = any(l.provisional for l in pw.ledgers.values())
        story.append(P(pw.name, S_H2))
        story.append(P(pw.description, S_SMALL))
        st = ("PROVISIONAL &mdash; not commit-grade (split fractions not calibrated full-scale)"
              if prov else "all four ledgers close &mdash; commit-grade")
        story.append(P(f"<b>Closure gate:</b> {st}.",
                       mk("x", parent=S_BODY, textColor=(PROV if prov else GOOD))))
        for q in ("carbon", "energy", "nitrogen", "phosphorus"):
            story.append(P(f"{q.title()} ledger", mk("lh", parent=S_SMALL, textColor=ACCENT,
                                                      fontName="Helvetica-Bold", spaceAfter=2)))
            story.append(ledger_table(pw.ledgers[q]))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # ===== 6 energy balance =====
    story.append(P("6 &nbsp; Whole-Pathway Energy Balance", S_H1))
    story.append(P("Energy is scored as a whole-pathway net balance, not biogas at the digester. "
                   "Upstream choices set the downstream bill: drier cake means less evaporation. "
                   "The spine subtracts digester heating, THP steam, dewatering and (for thermal) "
                   "drying loads from generation, with recovered heat used before any fossil "
                   "top-up &mdash; and fossil top-up, where needed, feeds back into Scope 1."))
    for pw, label in ((wp, "Spine (THP + MAD + struvite)"), (tp, "Thermal endpoint")):
        e = pw.ledgers["energy"]
        story.append(P(label, S_H2))
        rows = [[P("Term", S_CELLH), P("MWh/d", S_CRH)]]
        for k, v in e.inflows.items():
            rows.append([P("(in) " + k.replace("_", " "), S_CELL), P(f"{v:,.1f}", S_CR)])
        for k, v in e.outflows.items():
            rows.append([P("(out) " + k.replace("_", " "), S_CELL), P(f"{v:,.1f}", S_CR)])
        rows.append([P("<b>Net export (incl. upstream aeration credit)</b>", S_CELLB),
                     P(f"<b>{pw.net_export_mwh_d:,.1f}</b>", S_CR)])
        story.append(styled(Table(rows, colWidths=[140*mm, 30*mm])))
        if pw is tp:
            lo, c, hi = pw.bands["energy_neutrality"]
            story.append(P(f"Net depends on uncalibrated syngas recovery; energy-neutrality score "
                           f"ranges {lo:.2f}&ndash;{hi:.2f} (central {c:.2f}). At the low band the "
                           "drying load forces fossil top-up.", S_SMALL))
        story.append(Spacer(1, 5))

    # ===== 7 capacity =====
    story.append(P("7 &nbsp; Capacity Intensification", S_H1))
    story.append(P("The dominant real-world justification for THP at full scale (Thames Water, "
                   "Ringsend, DC Water Blue Plains, Sydney Water St Marys) is capacity. The "
                   "mechanism is not merely feed concentration: THP pre-completes hydrolysis before "
                   "the digester, so the binding design constraint shifts from hydrolysis-limited "
                   "retention time to organic loading rate (OLR) &mdash; which THP can run at "
                   "roughly double the conventional limit. Required digester volume is therefore "
                   "the maximum of three constraints, computed for each mode:"))
    cc, tc = cap["conv_constraints"], cap["thp_constraints"]
    rows = [[P("Volume constraint", S_CELLH), P("Conventional", S_CRH), P("THP", S_CRH)]]
    for key, lab in [("hydraulic", "Hydraulic floor (12 d washout)"),
                     ("hydrolysis", "Hydrolysis completion (HRT)"),
                     ("OLR", "Organic loading rate")]:
        rows.append([P(lab, S_CELL), P(f"{cc[key]:,.0f} m\u00b3", S_CR), P(f"{tc[key]:,.0f} m\u00b3", S_CR)])
    rows.append([P("<b>Required volume = MAX (governing constraint)</b>", S_CELLB),
                 P(f"<b>{cap['vol_conv_m3']:,.0f} ({cap['conv_governing']})</b>", S_CR),
                 P(f"<b>{cap['vol_thp_m3']:,.0f} ({cap['thp_governing']})</b>", S_CR)])
    story.append(styled(Table(rows, colWidths=[80*mm, 45*mm, 45*mm])))
    story.append(Spacer(1, 3))
    story.append(kv([
        ("OLR design limit (kgVS/m\u00b3\u00b7d)", f"conventional {S.KCAP.OLR_CONV} -&gt; THP {S.KCAP.OLR_THP} (pre-hydrolysed)"),
        ("Digester volume avoided", f"{cap['avoided_m3']:,.0f} m\u00b3 = {cap['digesters_avoided']:.1f} reference digesters"),
        ("Avoided / deferred CAPEX", f"${cap['avoided_capex_aud']/1e6:.0f}M (@ ${S.KCAP.CAPEX_PER_M3:,.0f}/m\u00b3)"),
        ("CAPEX valuation Low / Base / High", f"${cap['capex_low_aud']/1e6:.0f}M / ${cap['capex_base_aud']/1e6:.0f}M / ${cap['capex_high_aud']/1e6:.0f}M  (tank-only $2k vs full-replacement $3.5-5k/m\u00b3)"),
        ("Existing tanks: HRT conv -&gt; THP", f"{cap.get('hrt_conv_existing_d',0):.1f} d -&gt; {cap.get('hrt_thp_existing_d',0):.1f} d"),
        ("Existing-tank throughput headroom", f"+{cap.get('capacity_headroom_tds',0):,.0f} tDS/d ({cap.get('existing_governing','')}-limited)"),
    ]))
    _cc = cap["conv_constraints"]; _cg = cap["conv_governing"]
    _runner = max((k for k in _cc if k != _cg), key=lambda k: _cc[k])
    _gap = (cap["vol_conv_m3"] - _cc[_runner]) / cap["vol_conv_m3"] * 100.0 if cap["vol_conv_m3"] else 0.0
    _cross = (" &mdash; within {:.0f}%, so this plant sits right at the OLR/hydrolysis crossover".format(_gap)) if _gap < 5 else ""
    story.append(P("At this plant, conventional sizing is <b>{}-governed</b> ({:,.0f} m\u00b3; {} would need "
                   "{:,.0f} m\u00b3{}); THP sizing is <b>{}-governed</b>. Sizing THP on a conventional HRT "
                   "understates the benefit &mdash; the three-constraint model gives ${:.0f}M deferred. The "
                   "governing constraint is computed per plant, not assumed.".format(
                       _cg, cap["vol_conv_m3"], _runner, _cc[_runner], _cross, cap["thp_governing"],
                       cap["avoided_capex_aud"]/1e6), S_SMALL))
    # Board-level capacity comparison on equivalent terms (defuses double-counting)
    cdt = S.capacity_decision_table(plant)
    story.append(P("Capacity options on equivalent terms (digesters avoided vs the conventional baseline)",
                   mk("cdt", parent=S_SMALL, textColor=ACCENT, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2)))
    _r = [[P("Pathway", S_CELLH), P("Governing constraint", S_CRH), P("Digesters avoided", S_CRH), P("CAPEX deferred", S_CRH)]]
    for r in cdt["rows"]:
        _da = "0 (baseline)" if r["digesters_avoided"] == 0 else "{:.1f}".format(r["digesters_avoided"])
        _cx = "&mdash;" if r["capex_deferred_aud"] == 0 else "${:.0f}M".format(r["capex_deferred_aud"]/1e6)
        _r.append([P(r["pathway"], S_CELL), P(r["constraint"], S_CR), P(_da, S_CR), P(_cx, S_CR)])
    story.append(styled(Table(_r, colWidths=[50*mm, 46*mm, 24*mm, 24*mm])))
    story.append(P("<b>Not additive:</b> " + cdt["note"], S_SMALL))
    story.append(P("THP capacity intensification mechanisms", mk("cm", parent=S_SMALL,
                   textColor=ACCENT, fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=2)))
    for m in ["Increased feed solids concentration (~5.5% -&gt; 10% DS) &mdash; lower hydraulic load",
              "Reduced sludge viscosity &mdash; improved mixing and heat transfer",
              "Hydrolysis pre-completed externally &mdash; the rate-limiting step is removed from the digester",
              "Higher achievable OLR (~2.5 -&gt; ~5 kgVS/m\u00b3\u00b7d) &mdash; the new binding constraint",
              "Reduced required digester volume &mdash; same throughput in far less tankage",
              "Deferred digester CAPEX &mdash; often the dominant THP value stream over asset life"]:
        story.append(bullet(m))

    # ===== 7b K+ digestion architecture / BMP-calibrated kinetics =====
    kc = dh.get("L2_kplus_kinetics") or S.kplus_was_capacity(plant)
    kpb = S.build_pathway_k_plus(plant).basis
    cc = S.kinetics_calibration_check()
    story.append(P("7b &nbsp; Digestion Architecture &mdash; WAS is Predominantly Ceiling-Limited (Mangere / ETP)", S_H1))
    story.append(P("Section 7 showed THP wins capacity by pre-completing hydrolysis. Pathway K+ asks whether the "
                   "WAS train can run at a short HRT without a THP front end. Per-stream BMP tests on Mangere "
                   "primary (TPS) and waste-activated (TWAS) sludge answer it directly &mdash; and overturn the "
                   "earlier rate-assist hypothesis. The fitted first-order kinetics are:"))
    rows = [[P("Stream", S_CELLH), P("Ultimate BMP B₀", S_CRH), P("Hydrolysis k (1/d)", S_CRH),
             P("Biodegradable f_bio", S_CRH)]]
    rows.append([P("Primary (TPS)", S_CELL), P("473 mL CH₄/gVS", S_CR), P(f"{kc['ps_k']:.2f}", S_CR), P(f"{kc['ps_f_bio']:.2f}", S_CR)])
    rows.append([P("WAS (TWAS)", S_CELL), P("150 mL CH₄/gVS", S_CR), P(f"{kc['was_k']:.2f}", S_CR), P(f"{kc['was_f_bio']:.2f}", S_CR)])
    story.append(styled(Table(rows, colWidths=[40*mm, 44*mm, 38*mm, 38*mm])))
    story.append(Spacer(1, 3))
    story.append(P("Two findings, the second decisive. <b>(1)</b> These per-stream kinetics, blended at the real "
                   f"VS split, independently reproduce both plants: ETP {cc['ETP_VSR_at_18_1d']:.3f} (measured 0.575) "
                   f"and Mangere {cc['Mangere_VSR_at_21_7d']:.3f} (measured 0.585) &mdash; a bottom-up validation "
                   "from lab BMP to full-scale VSR. <b>(2)</b> WAS hydrolyses <i>as fast as PS</i> "
                   f"(k_WAS {kc['was_k']:.2f} &ge; k_PS {kc['ps_k']:.2f}/d) but its biodegradable fraction is only "
                   f"~one-third (f_bio {kc['was_f_bio']:.2f} vs {kc['ps_f_bio']:.2f}). At Mangere and ETP, WAS is "
                   "therefore <b>predominantly ceiling-limited rather than rate-limited</b>: it reaches its low "
                   "ceiling fast, and the recalcitrant ~70% never converts at any HRT.", S_SMALL))
    story.append(P("The <i>principle</i> is strong; its <i>universality</i> is not. Different WAS ages, sludge ages, "
                   "industrial fractions and temperatures can produce genuinely rate-limited WAS, so this is a "
                   "plant-specific finding &mdash; well supported for Mangere and ETP on their own BMP data, but to be "
                   "confirmed with a local BMP before it is assumed for WAS in general.",
                   mk("wascaveat", parent=S_SMALL, backColor=LIGHT, borderPadding=6, spaceBefore=3)))
    story.append(P("This is why K+ frees capacity &mdash; and it is measured, not assumed. Because WAS reaches its "
                   f"ceiling fast (batch t₉₀ ~{kc['batch_t90_was_d']:.0f} d), running the WAS digester at "
                   f"the {kc['floor_d']:.0f} d hydraulic/OLR floor instead of the conventional {kc['conv_hrt_d']:.0f} d "
                   f"retains <b>~{kc['vsr_retained_at_floor_pct']:.0f}%</b> of its VS destruction "
                   f"(WAS VSR {kc['was_vsr_floor']:.3f} vs {kc['was_vsr_conv']:.3f}). The freed volume follows from "
                   "the kinetics alone &mdash; no SolidStream rate-assist required:", S_SMALL))
    story.append(kv([
        ("WAS HRT at the floor", f"{kc['floor_d']:.0f} d (vs {kc['conv_hrt_d']:.0f} d conventional)"),
        ("WAS VS destruction retained", f"~{kc['vsr_retained_at_floor_pct']:.0f}% &mdash; measured BMP kinetics"),
        ("K+ freed volume", f"{kpb.get('capacity_released_m3',0):,.0f} m\u00b3 = {kpb.get('equivalent_digesters',0):.1f} digesters, ${kpb.get('deferred_capex_m_aud',0):.0f}M deferred"),
        ("Capacity confidence", f"{kc['capacity_confidence']} &mdash; backed by per-stream BMP (measured kinetics)"),
        ("Yield (SolidStream uplift) confidence", f"{kc.get('yield_confidence','D')} &mdash; inferred from Cambi; unproven at this plant pending a treated-WAS BMP"),
    ]))
    lad = dh.get("L2_constraint_ladder") or S.constraint_ladder(plant)
    story.append(P("The strategic variable is the <i>constraint</i> each configuration faces. Short-HRT capacity is "
                   "available to all of them (WAS rate is fast); what differs is the biodegradable ceiling each "
                   "unlocks:", S_SMALL))
    rows = [[P("Configuration", S_CELLH), P("WAS HRT", S_CRH), P("Binding limit", S_CRH), P("Evidence", S_CRH)]]
    for r in lad["rungs"]:
        hrt = (f"{r['was_hrt_d']:.1f} d" if isinstance(r.get("was_hrt_d"), (int, float)) else "n/a")
        rows.append([P(r["config"], S_CELL), P(hrt, S_CR), P(r["limit"], S_CR), P(r["evidence"], S_CR)])
    story.append(styled(Table(rows, colWidths=[46*mm, 18*mm, 56*mm, 40*mm])))
    cm = S.constraint_migration(plant)
    story.append(P("Constraint migration &mdash; which constraint governs the plant", S_H2))
    cmrows = [[P("Configuration", S_CELLH), P("Governing constraint", S_CRH), P("Why", S_CELLH)]]
    for cfg, con, why in cm["rows"]:
        cmrows.append([P(cfg, S_CELL), P(con, S_CR), P(why, S_CELL)])
    story.append(styled(Table(cmrows, colWidths=[40*mm, 38*mm, 72*mm])))
    story.append(P(cm["headline"], S_SMALL))
    story.append(Spacer(1, 3))
    story.append(P("<b>Verdict:</b> WAS is ceiling-limited, not rate-limited. So K+'s capacity claim &mdash; run the "
                   f"WAS digester at the {kc['floor_d']:.0f} d floor &mdash; is justified by measured BMP kinetics "
                   f"(it retains ~{kc['vsr_retained_at_floor_pct']:.0f}% of conventional WAS destruction), freeing "
                   f"{kpb.get('capacity_released_m3',0):,.0f} m\u00b3 (~{kpb.get('equivalent_digesters',0):.1f} "
                   "digesters). This is now confidence B, not the speculative rate-assist of earlier drafts.",
                   mk("kpv", parent=S_BODY, textColor=INK, backColor=LIGHT, borderPadding=6,
                      spaceBefore=4, leftIndent=4, rightIndent=4)))
    story.append(P("<b>What remains pilot-gated is yield, not capacity.</b> SolidStream's value on WAS is raising the "
                   "biodegradable <i>ceiling</i> (cell lysis &rarr; more methane). That uplift is carried on the same "
                   "Cambi-calibrated VSR 0.703 basis as Pathways E and K, but its transfer to this plant's WAS is "
                   f"<b>{kc['yield_uplift_status']}</b>. The decisive pilot is a BMP on SolidStream-treated WAS versus "
                   "raw WAS, measuring the ceiling uplift directly &mdash; not a hydrolysis-rate measurement.", S_SMALL))

    story.append(P("Evidence separation &mdash; proven vs assumed vs unproven", S_H2))
    for grade, col, items in [
        ("PROVEN", GOOD, ["WAS kinetics from per-stream BMP (k_WAS ~0.38/d, f_bio ~0.31)",
                          "K+ capacity benefit &mdash; short-HRT WAS retains ~94% of conventional VSR"]),
        ("ASSUMED", ACCENT, ["SolidStream raises the WAS biodegradable ceiling (inferred from Cambi VSR 0.703 elsewhere)"]),
        ("UNPROVEN", MUTED, ["Plant-specific SolidStream methane gain on THIS WAS (pending the treated-WAS BMP)"]),
    ]:
        story.append(P(f"<b>{grade}</b>", mk("eg_"+grade, parent=S_BODY, textColor=col, spaceBefore=3, spaceAfter=1)))
        for it in items:
            story.append(bullet(it))
    story.append(P("The capacity case rests entirely on PROVEN items. The yield case depends on the ASSUMED "
                   "ceiling uplift and is not bankable until the UNPROVEN plant-specific gain is measured. "
                   "BioPoint never lets the proven capacity logic borrow confidence from the unproven yield claim.",
                   mk("evn", parent=S_SMALL, backColor=LIGHT, borderPadding=6, spaceBefore=3)))

    # ===== 8 opex =====
    story.append(P("8 &nbsp; OPEX Breakdown", S_H1))
    story.append(P("Annual OPEX is read off the ledgers: energy from net export, transport from "
                   "product tonnage, chemicals and O&amp;M scaled with load, product revenue from "
                   "the phosphorus ledger. Negative = net cash-positive.", S_SMALL))
    oxt = S.opex_view(tp)
    rows = [[P("Term (M$/yr)", S_CELLH), P("Spine", S_CRH), P("Thermal", S_CRH)]]
    for key, lab in [("energy_m_aud", "Energy (net export)"), ("transport_m_aud", "Transport"),
                     ("chemicals_m_aud", "Chemicals"), ("om_m_aud", "O&amp;M"),
                     ("struvite_revenue_m_aud", "Struvite revenue (credit)")]:
        a = ox[key] * (-1 if key == "struvite_revenue_m_aud" else 1)
        b = oxt[key] * (-1 if key == "struvite_revenue_m_aud" else 1)
        rows.append([P(lab, S_CELL), P(f"{a:+.2f}", S_CR), P(f"{b:+.2f}", S_CR)])
    rows.append([P("<b>Net OPEX</b>", S_CELLB), P(f"<b>{ox['net_m_aud']:+.2f}</b>", S_CR),
                 P(f"<b>{oxt['net_m_aud']:+.2f}</b>", S_CR)])
    story.append(styled(Table(rows, colWidths=[100*mm, 35*mm, 35*mm])))

    # ===== 9 comparison =====
    story.append(P("9 &nbsp; Driver Comparison (the trade &mdash; not a winner)", S_H1))
    drivers = ["energy_neutrality", "scope1_emissions", "pfas", "nutrient_recovery", "opex", "capacity"]
    head = [P("Driver", S_CELLH)] + [P(p.name.split(" + ")[0] + "…", S_CRH) for p in (wp, tp)]
    rows = [head]; sw, stc = wp.driver_scores(), tp.driver_scores()
    for d in drivers:
        cells = [P(d.replace("_", " ").title(), S_CELL)]
        for p, sc in ((wp, sw), (tp, stc)):
            if d in p.bands:
                lo, c, hi = p.bands[d]
                cells.append(P(f"{c:.2f} <font size=7 color='#5d6b73'>[{lo:.2f}-{hi:.2f}]</font>", S_CR))
            else:
                cells.append(P(f"{sc.get(d,0):.2f}", S_CR))
        rows.append(cells)
    story.append(styled(Table(rows, colWidths=[60*mm, 55*mm, 55*mm])))
    story.append(Spacer(1, 3))
    story.append(P("Scores are 0&ndash;1, higher better. The spine leads on energy and confidence; "
                   "the thermal pathway is the only one addressing PFAS. Neither dominates, so the "
                   "engine sequences them rather than picking one.", S_SMALL))

    story.append(PageBreak())

    # ===== 10 confidence (multi-dimensional) =====
    story.append(P("10 &nbsp; Technology Confidence (multi-dimensional)", S_H1))
    story.append(P("Confidence is tracked on three axes &mdash; technical, calibration, and "
                   "social/regulatory &mdash; and governs the recommendation verb (the weakest "
                   "axis that matters). It never excludes a pathway: a low axis prices a "
                   "de-risking task instead of vetoing the option."))
    rows = [[P("Move", S_CELLH), P("Tech", S_CRH), P("Calib", S_CRH), P("Social", S_CRH),
             P("Verb", S_CELLH)]]
    seen = set()
    for pw in (wp, tp):
        for m in pw.moves:
            if m.name in seen: continue
            seen.add(m.name)
            c = m.confidence
            rows.append([P(m.name, S_CELL), P(c.technical.name, S_CR), P(c.calibration.name, S_CR),
                         P(c.social_regulatory.name, S_CR),
                         P(c.verb().split(" ")[0], S_CELL)])
    story.append(styled(Table(rows, colWidths=[78*mm, 16*mm, 17*mm, 18*mm, 41*mm])))
    story.append(P("Levels: A proven, B strong evidence, C emerging, D hypothesis.", S_SMALL))

    # ===== 11 validation / road test =====
    _pn = plant.get("name", "plant").split("(")[0].strip()
    story.append(P(f"11 &nbsp; Validation ({_pn} road test)", S_H1))
    N_in = wp.ledgers["nitrogen"].total_in
    nliq = wp.ledgers["nitrogen"].outflows["return_liquor_NH4_to_WWTW"]; frac = nliq/N_in*100
    feedN_est = plant.get("feed_N_estimated", False)
    _stat = {"PASS": ("PASS", "#1f7a43"), "CALIB": ("CALIBRATED", "#1f5fa6"), "OPEN": ("OPEN", "#9a5b00")}
    rows = [[P("Check", S_CELLH), P("Result", S_CELLH), P("Status", S_CRH)]]
    vchecks = [
        ("All eight ledgers close (4 per pathway)", "imbalance <0.01% across all", "PASS"),
        ("Feed N basis", f"{N_in:,.0f} kgN/d ({'scaled estimate' if feedN_est else 'measured / production fixture'})",
         "OPEN" if feedN_est else "PASS"),
        ("Return-liquor N tracks the ETP-measured fraction", f"{frac:.0f}% of feed N ({nliq:,.0f} kgN/d)",
         "CALIB" if 18 <= frac <= 40 else "OPEN"),
        ("THP avoids >2 reference digesters", f"{cap['digesters_avoided']:.1f} digesters / ${cap['avoided_capex_aud']/1e6:.0f}M",
         "PASS" if cap['digesters_avoided'] > 2 else "OPEN"),
        ("Worked pathway net-energy positive", f"{wp.net_export_mwh_d:,.0f} MWh/d", "PASS" if wp.net_export_mwh_d > 0 else "OPEN"),
    ]
    for lab, det, st in vchecks:
        txt, col = _stat[st]
        rows.append([P(lab, S_CELL), P(det, S_CELL), P(f"<font color='{col}'><b>{txt}</b></font>", S_CR)])
    story.append(styled(Table(rows, colWidths=[78*mm, 62*mm, 30*mm])))
    story.append(P("Status key: <b>PASS</b> = hard check met; <b>CALIBRATED</b> = value tied to measured data "
                   "(here the ETP Cambi centrate balances, single-pass ~26% / recycle ~37% of feed N); <b>OPEN</b> = "
                   "an input that is still an estimate, not yet validated against plant data. " +
                   ("At Mangere the PS/WAS split and feed N are scaled estimates, so the feed-N basis is OPEN, not a "
                    "fail &mdash; the energy and capacity results do not depend on it. " if feedN_est else
                    "All inputs at this plant are on the measured/production basis. ") +
                   "The earlier draft set ammonia release equal to VSR (~53% of feed N), which over-predicted centrate "
                   "N; recalibrating to the measured feed-N fractions brought it into line.", S_SMALL))

    # ===== 12 constants register =====
    # ===== ETP Calibration Basis (measured 2006-2017) =====
    if "ETP" in plant.get("name", ""):
        cal = S.ETP_CAL
        story.append(P("ETP Calibration Basis (measured 2006-2017)", S_H1))
        story.append(P("The ETP feedstock model is anchored in the measured ETP primary sedimentation "
                       "record (2006-2017), not generic literature factors. Flow, feed/effluent quality "
                       "and clarifier performance below are site data; P10/P50/P90 give the operating "
                       "envelope.", S_SMALL))
        story.append(kv([
            ("IPS flow P10/P50/P90 (MLD)", f"{cal['flow_mld'][0]:.0f} / {cal['flow_mld'][1]:.0f} / {cal['flow_mld'][2]:.0f}"),
            ("Feed SS / COD / BOD5 / TKN (P50, mg/L)", f"{cal['feed_ss_mgL'][1]:.0f} / {cal['feed_cod_mgL'][1]:.0f} / {cal['feed_bod5_mgL'][1]:.0f} / {cal['feed_tkn_mgL'][1]:.0f}"),
            ("Clarifier removal SS / COD / BOD5 / TKN", f"{cal['removal_ss']*100:.0f}% / {cal['removal_cod']*100:.0f}% / {cal['removal_bod5']*100:.0f}% / {cal['removal_tkn']*100:.0f}%"),
            ("PS production measured band (tDS/d)", f"{cal['ps_ds_band_tpd'][0]:.0f} / {cal['ps_ds_band_tpd'][1]:.0f} / {cal['ps_ds_band_tpd'][2]:.0f} (P10/P50/P90; mean 99)"),
            ("PS production recent 2015-2017 (tDS/d)", f"~{cal['ps_ds_recent_tpd']:.0f}"),
            ("PS adopted design basis (tDS/d)", f"{cal['ps_ds_design_tpd']:.1f} (inside measured envelope)"),
            ("PS nitrogen capture (t N/d)", f"~{cal['ps_n_capture_tpd']:.1f} (only {cal['removal_tkn']*100:.0f}% of influent TKN)"),
            ("Feedstock confidence", cal["confidence"]),
        ], w=(80, 90)))
        story.append(P("The adopted PS design load (120.7 tDS/d) sits inside the measured envelope "
                       "(P90 150; recent-years mean ~115). Most influent nitrogen stays soluble and "
                       "passes to secondary treatment - the digester N load and return-liquor N arrive "
                       "predominantly via WAS, which this PST dataset does not measure (flagged).", S_SMALL))

    story.append(P("12 &nbsp; Parameter Register &amp; Provenance", S_H1))
    story.append(P("The honest backbone of the model: every parameter with its value and status "
                   "&mdash; <b>calibrated</b> against a reference plant, <b>estimate</b> "
                   "(defensible mid-range, plant data would refine), or <b>provisional</b> "
                   "(uncalibrated, wide band, reported as uncertainty)."))
    reg = [
        ("VS reduction (VSR)", f"{K.VSR*100:.1f}%", "Calibrated", "Cambi Mangere Full-THP mass balance"),
        ("Methane yield", f"{K.METHANE_YIELD_NM3_TDS} Nm\u00b3/tDS", "Calibrated", "St Marys / Davyhulme"),
        ("THP steam demand", f"{K.STEAM_T_PER_TDS} t/tDS", "Calibrated", "St Marys (band 0.85-1.00)"),
        ("Biogas CH\u2084 fraction", f"{K.CH4_FRACTION*100:.0f}%", "Calibrated", "THP-AD reference"),
        ("Centrate-N return (single-pass / recycle)", f"{K.F_CENTRATE_BASE*100:.0f}% / {K.F_CENTRATE_RECYCLE*100:.0f}% of feed N", "Calibrated", "ETP Cambi mass balances 2015/2026"),
        ("Carbon per VS", f"{K.C_PER_VS} gC/gVS", "Estimate", "Municipal sludge literature"),
        ("Phosphorus content", f"{K.P_PER_DS*100:.1f}% DS", "Estimate", "Plant P not measured"),
        ("Struvite P recovery", f"{K.STRUVITE_P_RECOVERY*100:.0f}%", "Estimate", "Process literature"),
        ("Thermal drying energy", f"{S.KT.DRY_MWH_PER_T_WATER} MWh/t water", "Estimate", "Evaporation + inefficiency"),
        ("Syngas recovery", f"{S.KT.SYNGAS_MWH_PER_TDS[0]}-{S.KT.SYNGAS_MWH_PER_TDS[2]} MWh/tDS", "Provisional", "Digested-solids gasification"),
        ("Carbon-to-char fraction", f"{S.KT.C_TO_CHAR_FRAC[0]*100:.0f}-{S.KT.C_TO_CHAR_FRAC[2]*100:.0f}%", "Provisional", "Not closed full-scale"),
        ("PFAS destruction", f"{S.KT.PFAS_DESTRUCTION[0]*100:.0f}-{S.KT.PFAS_DESTRUCTION[2]*100:.0f}%", "Provisional", "Emerging literature"),
        ("Capacity: OLR conv/THP, feed DS", f"{S.KCAP.OLR_CONV}/{S.KCAP.OLR_THP} kgVS/m\u00b3\u00b7d, {S.KCAP.THP_FEED_DS:.0f}% DS", "Calibrated", "Thames / Ringsend / Blue Plains / St Marys"),
        ("Electricity / transport / struvite price", f"${S.KO.ELEC_PRICE_MWH:.0f}/MWh, ${S.KO.TRANSPORT_PER_T:.0f}/t, ${S.KO.STRUVITE_PRICE_T:.0f}/t", "Assumption", "Market estimate"),
    ]
    rows = [[P("Parameter", S_CELLH), P("Value", S_CELLH), P("Status", S_CELLH), P("Basis", S_CELLH)]]
    cmap = {"Calibrated": GOOD, "Estimate": MUTED, "Provisional": PROV, "Assumption": MUTED}
    for pname, val, stat, basis in reg:
        rows.append([P(pname, S_CELL), P(val, S_CELL),
                     Paragraph(f"<font color='#{cmap[stat].hexval()[2:]}'><b>{stat}</b></font>", S_CELL),
                     P(basis, S_CELL)])
    t = Table(rows, colWidths=[48*mm, 40*mm, 24*mm, 58*mm]); styled(t)
    story.append(t)

    # ===== 13 THP benefit decomposition =====
    story.append(P("13 &nbsp; THP Strategic Value &mdash; Benefit Decomposition", S_H1))
    story.append(P("THP is not an advanced digestion technology; it is a system-intensification "
                   "platform delivering capacity, dewaterability, logistics and energy benefits "
                   "simultaneously. Full-scale evidence (Thames Water, United Utilities Davyhulme, "
                   "DC Water Blue Plains) shows utilities adopt it primarily for capacity and "
                   "disposal reduction, with energy a secondary benefit. The four streams, valued "
                   "independently:"))
    tv = thp_value(wp, cap)
    wet_conv, wet_thp = tv["wet_conv"], tv["wet_thp"]
    cap_annual, disposal_save, trucks_save, energy_val = (
        tv["capacity"], tv["disposal"], tv["logistics"], tv["energy"])
    rows = [[P("Benefit stream", S_CELLH), P("Annual value", S_CRH), P("Basis", S_CELLH)]]
    for lab, val, basis in [
        ("1. Capacity intensification (avoided CAPEX, 20-yr annualised)", cap_annual,
         f"{cap['digesters_avoided']:.1f} digesters avoided / ${cap['avoided_capex_aud']/1e6:.0f}M"),
        ("2. Disposal cost reduction (higher cake DS, fewer tonnes)", disposal_save,
         "22% -&gt; 32% cake DS; @ $80/wet t"),
        ("3. Logistics (fewer truck movements)", trucks_save,
         f"~{(wet_conv-wet_thp)/40:.1f} fewer trucks/d @ $350"),
        ("4. Energy recovery (net export value)", energy_val,
         f"{wp.net_export_mwh_d:,.0f} MWh/d @ ${S.KO.ELEC_PRICE_MWH:.0f}/MWh"),
    ]:
        rows.append([P(lab, S_CELL), P(f"~${val:.1f}M/yr", S_CR), P(basis, S_CELL)])
    story.append(styled(Table(rows, colWidths=[88*mm, 30*mm, 52*mm])))
    story.append(P(f"<b>Consolidated THP strategic value ~${tv['total']:.1f}M/yr</b> across the four "
                   "streams above (20-yr annualised capacity + disposal + logistics + energy).", S_SMALL))
    story.append(P("Ranking confirms the evidence base: capacity and disposal dominate; energy is "
                   "valued but rarely the primary justification. Values screening-grade (+/-30%).", S_SMALL))

    # ===== 14 sidestream nitrogen =====
    story.append(P("14 &nbsp; Sidestream Nitrogen Impact", S_H1))
    ncen = wp.ledgers["nitrogen"].outflows["return_liquor_NH4_to_WWTW"]
    MAIN_TN = 17675.0
    story.append(P("Mineralised ammonia returns to the liquid train in the centrate. This load "
                   "must be assessed against mainstream TN licence headroom, aeration capacity and "
                   "alkalinity. The nitrogen ledger quantifies it directly:"))
    story.append(kv([
        ("Centrate NH₄-N return load", f"{ncen:,.0f} kg N/d"),
        ("As % of mainstream TN (ref. {:,.0f} kg N/d)".format(MAIN_TN), f"{ncen/MAIN_TN*100:.0f}%"),
        ("Additional O₂ demand (4.6 kg O₂/kg N)", f"{ncen*4.6/1000:.1f} t O₂/d"),
        ("Additional alkalinity (7.14 kg CaCO₃/kg N)", f"{ncen*7.14/1000:.1f} t CaCO₃/d"),
        ("N₂O risk", "Elevated return load raises bioreactor N₂O risk (Scope 1) if DO/pH poor"),
    ]))
    story.append(P("The calibrated soluble-N release (Mangere band, 36% of feed N) sets this load. "
                   "Nutrient recovery (next section) can remove up to ~88-90% of it.", S_SMALL))

    # ===== 15 nutrient recovery screening =====
    story.append(P("15 &nbsp; Nutrient Recovery Screening", S_H1))
    Pstr = wp.ledgers["phosphorus"].outflows["struvite_P"]
    struvite_t = Pstr * S.KO.STRUVITE_MW_PER_P / 1000 * 365
    as_N = ncen * 0.69                                   # 75% strip x 92% absorb
    as_t = as_N / 0.212 / 1000 * 365                     # AS is 21.2% N
    pna_N = ncen * 0.88
    story.append(P("Three recovery pathways screened against the centrate the ledgers produce. "
                   "These are not interchangeable &mdash; they sit on a <b>nitrogen hierarchy</b> "
                   "(Recover &gt; Reuse &gt; Destroy). Struvite and ammonium sulphate <i>recover</i> "
                   "nitrogen into a reusable fertiliser product; PN/A <i>destroys</i> it (NH₄ to N₂ "
                   "gas). Destruction solves the return-load problem but forecloses the nutrient-"
                   "recovery driver, so the hierarchy matters strategically:"))
    rows = [[P("Pathway", S_CELLH), P("Hierarchy", S_CRH), P("Converts", S_CELLH),
             P("Recovers", S_CRH), P("Indic. value", S_CRH)]]
    for lab, tier, conv, rec, val in [
        ("Struvite crystallisation", "Recover/Reuse", f"PO₄+NH₄ -&gt; fertiliser", f"{Pstr:,.0f} kg P/d",
         f"~${struvite_t*550/1e6:.1f}M/yr"),
        ("Ammonium sulphate (stripping)", "Recover/Reuse", "NH₄ -&gt; (NH₄)₂SO₄ fertiliser", f"{as_N:,.0f} kg N/d",
         f"~${as_t*350/1e6:.1f}M/yr"),
        ("PN/A (partial nitritation/anammox)", "Destroy", "NH₄ -&gt; N₂ gas", f"0 (destroyed)",
         "no product; OPEX saving"),
    ]:
        rows.append([P(lab, S_CELL), P(tier, S_CR), P(conv, S_CELL), P(rec, S_CR), P(val, S_CR)])
    story.append(styled(Table(rows, colWidths=[48*mm, 28*mm, 44*mm, 24*mm, 26*mm])))
    story.append(P("Strategic distinction: PN/A is the cheapest way to remove the return-load "
                   "burden, but it destroys a recoverable resource. Where the nutrient-recovery "
                   "driver matters, recover first (struvite for P, ammonium sulphate for the "
                   "residual N) and reserve PN/A for the nitrogen that cannot be economically "
                   "recovered. Capital not included; centrate sampling required. "
                   "Screening-grade (+/-30%).", S_SMALL))

    # ===== 16 heat & steam balance =====
    story.append(P("16 &nbsp; Heat &amp; Steam Balance", S_H1))
    e = wp.ledgers["energy"]
    story.append(P("CHP recoverable heat must cover digester heating and (for THP) the steam "
                   "boiler demand before any fossil top-up. The energy ledger resolves it:"))
    story.append(kv([
        ("CHP heat available (~45% of fuel)", f"{e.inflows['biogas_chemical_energy']*0.45:,.0f} MWh/d"),
        ("THP steam + digester heat demand", f"{e.outflows['ad_heat_used_thp_and_digester']:,.0f} MWh/d"),
        ("Heat surplus (unused, available)", f"{e.outflows['heat_surplus_unused']:,.0f} MWh/d"),
        ("Fossil top-up required", "None &mdash; recovered heat covers demand (no Scope 1 from heat)"),
    ]))

    # ===== 17 PFAS fate by pathway =====
    story.append(P("17 &nbsp; PFAS Fate by Technology Pathway", S_H1))
    story.append(P("PFAS is not destroyed by biological treatment or digestion. The endpoint "
                   "determines whether it is destroyed, concentrated or transferred. The "
                   "calibrated AD/THP spine concentrates it into cake; only thermal destruction "
                   "breaks the C-F bond. Literature DRE ranges (screening):"))
    rows = [[P("Pathway", S_CELLH), P("PFAS DRE", S_CRH), P("Residual / risk", S_CELLH)]]
    for path, dre, risk in [
        ("Land application", "0-5%", "Soil accumulation -&gt; groundwater. HIGH"),
        ("Conventional AD / THP + land", "2-8%", "PFAS concentrated in cake. HIGH"),
        ("Slow pyrolysis (&lt;500°C)", "40-70%", "Residual in biochar; leachability uncertain. MED-HIGH"),
        ("Pyrolysis (&ge;700°C)", "95-99%", "Trace in biochar. MEDIUM"),
        ("Gasification (&ge;900°C)", "99-99.9%", "Destroyed in afterburner. LOW-MED"),
        ("Incineration (&ge;850°C)", "&gt;99.9%", "Gold standard; ash non-detect. LOW (TRL 9)"),
    ]:
        rows.append([P(path, S_CELL), P(dre, S_CR), P(risk, S_CELL)])
    story.append(styled(Table(rows, colWidths=[58*mm, 26*mm, 86*mm])))
    story.append(P("Critical insight: PFAS fate is set by the thermal endpoint, not the digestion "
                   "technology &mdash; so the THP decision and the thermal-endpoint decision are "
                   "independent. THP improves digestion economics regardless; it does not "
                   "substitute for a thermal decision if PFAS is a constraint. Sources: ITRC 2020; "
                   "Winchell 2022. Site testing required.", S_SMALL))

    # ===== 18 thermal endpoint screening =====
    story.append(P("18 &nbsp; Thermal Endpoint Screening", S_H1))
    story.append(P("Indicative comparison of thermal endpoints at ~220 tDS/d. All provisional &mdash; "
                   "thermal endpoint selection needs a dedicated options study with PFAS "
                   "characterisation and Class 3 costing. A <b>technology maturity</b> column is now "
                   "explicit: destruction efficiency means little if the technology is not yet "
                   "demonstrated at scale on biosolids. These enter the V2 engine as the keep-open "
                   "option, not commitments:"))
    rows = [[P("Technology", S_CELLH), P("Temp", S_CRH), P("PFAS DRE", S_CRH),
             P("P recovery", S_CRH), P("Maturity", S_CRH), P("Confidence", S_CRH)]]
    for tech, temp, dre, prec, mat, conf in [
        ("Incineration / WtE", "800-950°C", "95%", "92%", "High (TRL 9)", "Medium"),
        ("Gasification", "750-1000°C", "97%", "90%", "Medium", "Low"),
        ("Slow pyrolysis", "400-700°C", "55%", "70%", "Medium", "Low"),
        ("HTL", "250-350°C", "45%", "45%", "Low (pre-comm.)", "Very low"),
    ]:
        rows.append([P(tech, S_CELL), P(temp, S_CR), P(dre, S_CR), P(prec, S_CR), P(mat, S_CR), P(conf, S_CR)])
    story.append(styled(Table(rows, colWidths=[40*mm, 28*mm, 22*mm, 24*mm, 30*mm, 22*mm])))
    story.append(P("HTL caution: its 45% PFAS DRE and modest P recovery should not be read "
                   "alongside gasification/incineration as a peer &mdash; HTL is pre-commercial for "
                   "biosolids (limited full-scale data), so its figures carry far wider uncertainty "
                   "and it is not a near-term endpoint. Maturity scale for reference: THP very high; "
                   "PN/A, struvite high; pyrolysis, gasification medium; HTL low.", S_SMALL))
    story.append(P("Costs/yields AUD Class 5 (+/-50%), screening only. PFAS characterisation is the "
                   "primary selector: if land application is not viable, gasification or "
                   "incineration is the default; if PFAS is not a constraint, pyrolysis offers "
                   "lowest capital and a carbon-sequestration co-benefit.", S_SMALL))

    # ===== 19 resource fate C-N-P =====
    story.append(P("19 &nbsp; Resource Fate &mdash; Carbon, Nitrogen, Phosphorus", S_H1))
    story.append(P("Where each element ends up, read directly off the closing ledgers (not "
                   "literature partition coefficients). This is the rigorous version of a fate "
                   "analysis &mdash; every percentage sums to 100 because the ledger balances:"))
    for q, unit in (("carbon", "C"), ("nitrogen", "N"), ("phosphorus", "P")):
        lg = wp.ledgers[q]
        rows = [[P(f"{q.title()} destination", S_CELLH), P("kg/d" if q != "carbon" else "tC/d", S_CRH),
                 P("% of feed", S_CRH)]]
        for k, v in lg.outflows.items():
            if v <= 0: continue
            rows.append([P(k.replace("_", " "), S_CELL), P(f"{v:,.1f}", S_CR),
                         P(f"{v/lg.total_in*100:.0f}%", S_CR)])
        story.append(P(f"{q.title()} fate", mk("rf", parent=S_SMALL, textColor=ACCENT,
                                               fontName="Helvetica-Bold", spaceAfter=2)))
        story.append(styled(Table(rows, colWidths=[96*mm, 37*mm, 37*mm])))
        story.append(Spacer(1, 4))

    # ===== 19b carbon six-category breakdown (V3 U3) =====
    cc = S.carbon_categories(wp)
    story.append(P("Carbon &mdash; Six-Category Breakdown", S_H2))
    story.append(P("The carbon story split six ways. The first four are carbon MASS read off the "
                   "closed ledger (they sum to feed carbon). The last three are climate metrics in "
                   "tCO2e, kept deliberately separate &mdash; durable removal and avoided fossil "
                   "emissions are never summed into a single headline number.", S_SMALL))
    story.append(kv([
        ("1. Destroyed / emitted to atmosphere", f"{cc['destroyed_emitted_tC_d']:,.1f} tC/d"),
        ("2. Recovered in product (e.g. biocrude)", f"{cc['recovered_in_product_tC_d']:,.1f} tC/d"),
        ("3. Returned in liquor", f"{cc['returned_in_liquor_tC_d']:,.1f} tC/d"),
        ("4. Retained in solids (land / char / ash)", f"{cc['retained_in_solids_tC_d']:,.1f} tC/d"),
        ("   - permanently sequestered (subset of 4)", f"{cc['of_which_permanently_sequestered_tC_d']:,.2f} tC/d"),
        ("5. Climate: durable REMOVAL", f"{cc['removed_tCO2e_d']:,.1f} tCO2e/d"),
        ("6. Climate: AVOIDED fossil (energy export)", f"{cc['avoided_tCO2e_d']:,.1f} tCO2e/d"),
        ("   Climate: direct emissions", f"{cc['direct_emissions_tCO2e_d']:,.1f} tCO2e/d"),
    ], w=(104, 66)))
    story.append(Spacer(1, 6))

    # ===== 20 future resilience =====
    story.append(P("20 &nbsp; Future Resilience (testing different worlds)", S_H1))
    story.append(P("The decisive uncertainty is no longer engineering performance &mdash; it is "
                   "which future the utility is preparing for. This section stress-tests each "
                   "pathway against future <i>worlds</i> (not re-weighted priorities), and reports "
                   "three independent axes: <b>Performance</b> (weighted driver score today), "
                   "<b>Confidence</b> (evidence maturity), and <b>Resilience</b> (likelihood-weighted "
                   "performance across the worlds). No single axis decides &mdash; that is the point."))
    cp = S.build_conventional_pathway(plant)
    trio = [cp, wp, tp]
    rows = [[P("Pathway", S_CELLH), P("Performance", S_CRH), P("Confidence", S_CRH),
             P("Resilience", S_CRH), P("PFAS ban", S_CRH)]]
    for p in trio:
        ta = S.three_axis(p, weights); rz = S.resilience(p)
        rows.append([P(p.name.replace(" (baseline)", "").replace(" (endpoint)", ""), S_CELL),
                     P(f"{ta['performance']:.2f}", S_CR), P(f"{ta['confidence']:.2f}", S_CR),
                     P(f"{ta['resilience']:.2f}", S_CR),
                     P("survives" if rz["survives_pfas_ban"] else "fails", S_CR)])
    story.append(styled(Table(rows, colWidths=[74*mm, 25*mm, 24*mm, 24*mm, 23*mm])))
    story.append(P("The conventional baseline is proven (confidence 1.0) but lowest on performance "
                   "and resilience. The THP+land spine leads on performance and confidence but "
                   "fails a PFAS land-application ban. The thermal endpoint is the most resilient "
                   "and highest-performing, but lowest-confidence (provisional). Each axis points "
                   "at a different pathway &mdash; which is why the answer is a sequence, not a pick.", S_SMALL))

    story.append(P("Performance by future world", mk("fw", parent=S_SMALL, textColor=ACCENT,
                   fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2)))
    mats = [S.resilience(p)["results"] for p in trio]
    rows = [[P("Future world", S_CELLH), P("Likely", S_CRH), P("Conv", S_CRH),
             P("Spine", S_CRH), P("Thermal", S_CRH)]]
    for i, sc in enumerate(S.SCENARIOS):
        cells = [P(sc.name, S_CELL), P(f"{sc.likelihood:.2f}", S_CR)]
        for m in mats:
            v = m[i]
            cells.append(P(f"{v['perf']:.2f}" + ("" if v["viable"] else " (x)"), S_CR))
        rows.append(cells)
    story.append(styled(Table(rows, colWidths=[62*mm, 18*mm, 23*mm, 23*mm, 24*mm])))
    story.append(P("(x) = pathway non-viable in that world. Likelihood is a coarse prior "
                   "(near-certain ~0.7, plausible ~0.5, speculative ~0.3). Strategic reading: only "
                   "the thermal endpoint survives a PFAS ban; both THP pathways absorb FOGO co-feed "
                   "via the OLR headroom (Section 7) while conventional cannot; the phosphorus-price "
                   "world rewards the struvite spine over thermal-to-ash. The shared THP+MAD "
                   "front-end is what gives resilience on capacity and FOGO; the <i>endpoint</i> is "
                   "what the futures disagree about &mdash; so commit the front-end, keep the "
                   "endpoint open, and de-risk thermal. The roadmap encodes exactly this.", S_SMALL))

    # ===== 21 roadmap =====
    story.append(P("21 &nbsp; Adaptive Roadmap", S_H1))
    commit = [m for m in wp.moves if m.tag == S.Tag.COMMIT]
    keep = [m for m in wp.moves if m.tag == S.Tag.KEEP_OPEN]
    avoid = [m for m in wp.moves if m.tag == S.Tag.AVOID]
    story.append(P("<b>Phase 1 &mdash; commit now (bankable, commit-grade)</b>",
                   mk("p1", parent=S_BODY, textColor=GOOD, spaceAfter=3)))
    for m in commit:
        story.append(bullet(f"<b>{m.name}</b> &mdash; <i>{m.confidence.verb()}</i><br/>"
                            f"<font size=8 color='#5d6b73'>Reward: {m.reward}. "
                            f"Residual risk: {m.residual_risk}.</font>"))
    story.append(P("<b>Phase 2+ &mdash; keep open (priced de-risking, decide later)</b>",
                   mk("p2", parent=S_BODY, textColor=ACCENT, spaceBefore=5, spaceAfter=3)))
    for m in keep:
        story.append(bullet(f"<b>{m.name}</b> &mdash; <i>{m.confidence.verb()}</i><br/>"
                            f"<font size=8 color='#5d6b73'>Reward: {m.reward}.<br/>"
                            f"De-risk: {m.derisk_task}.</font>"))
    story.append(P("<b>Avoid (forecloses future drivers)</b>",
                   mk("p3", parent=S_BODY, textColor=WARN, spaceBefore=5, spaceAfter=3)))
    for m in avoid:
        fc = f" Forecloses: {', '.join(m.forecloses)}." if m.forecloses else ""
        story.append(bullet(f"<b>{m.name}</b> &mdash; {m.residual_risk}.{fc}"))

    # ===== 22 recommendation =====
    story.append(P("22 &nbsp; Recommendation &mdash; Preferred Strategic Carbon and Nutrient Pathway", S_H1))
    story.append(P("The recommendation is a <b>front-end plus an endpoint chosen by objective</b>, sequenced "
                   "across the three stages &mdash; not a single technology:"))
    for i, r in enumerate([
        "<b>Biology (capacity and methane):</b> optimise MAD and dewatering now (commit-grade), then unlock "
        "capacity. Test separate PS/WAS digestion at short PS HRT as a lower-risk alternative to THP &mdash; it "
        f"frees ~2 digesters with no hydrolysis step, where THP frees ~{cap['digesters_avoided']:.1f} but adds a "
        "thermal-hydrolysis asset and a return-liquor load.",
        "<b>Biosolids quality (SolidStream):</b> treat SolidStream as the Stage-2 quality platform &mdash; "
        "Class-A cake at ~38% DS, roughly half the wet tonnes, and far less drying energy for any downstream "
        "thermal endpoint. This is a value stream in its own right, not merely a digestion add-on.",
        "<b>Nitrogen:</b> the sidestream return load (~4,650 kgN/d on the SolidStream route, ETP-measured) is a near-term binding constraint. "
        "Recover phosphorus via struvite while it is still recoverable, and commit sidestream PN/A to destroy "
        "~88% of the return-liquor ammonia &mdash; for many plants this binds before PFAS does.",
        "<b>Carbon endpoint (Stage 3):</b> choose by objective, not by score. Land is cheapest but low-"
        "permanence and PFAS-exposed; pyrolysis gives durable biochar plus carbon credits; incineration "
        "maximises PFAS destruction. Do <b>not</b> commit land as a terminal endpoint &mdash; it forecloses the "
        "carbon and PFAS families. Hold the chosen thermal endpoint as a priced, scheduled option (~$1.5M / 18 "
        "months to commit-grade); its splits are provisional, so the decision is staged, not pre-empted."], 1):
        story.append(bullet(r, mark=f"{i}."))

    story.extend(_separate_digestion_section(bundle["sf"]))
    story.extend(_foaming_section(bundle["sf"]))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=4))
    story.append(P("Scope &amp; limits. This report is generated by the BioPoint V3.5 pathway "
                   "spine and reflects what that model computes: the A-K pathway set composed with carbon endpoints, four conserved "
                   "ledgers, calibrated AD/THP/SolidStream physics with provisional thermal-endpoint splits. It "
                   "does not yet include the full digestion-kinetics narrative (Damk\u00f6hler / "
                   "HRT analysis) of the production Tier 1 engine, nor the wider pathway set; "
                   "those require porting the mad_v2 physics and additional pathways into the "
                   "spine. Phosphorus is an estimate pending measured data.", S_SMALL))
    return story


# ===========================================================================
# MODE 1 VIEW — Project Development Report ("What should I build?")
# Technology-focused, directive. Same engine; leads with a recommended config.
# ===========================================================================
def project_development_story(bundle):
    plant, wp, tp, cp = bundle["plant"], bundle["wp"], bundle["tp"], bundle["cp"]
    weights = bundle["weights"]
    tot = plant["PS_tds"] + plant["WAS_tds"]
    cap = S.capacity_view(wp); ox = S.opex_view(wp)
    aw, at, ac = (S.three_axis(p, weights) for p in (wp, tp, cp))
    tv = thp_value(wp, cap)
    story = []
    story.append(P("Project Development Report", S_TITLE))
    story.append(P("BioPoint &middot; What should I build?", S_SUB))
    story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=3, spaceAfter=8))
    story.extend(_screening_banner(bundle["plant"]))

    if bundle["sf"]["diag"].get("hrt_limited", True):
        story.append(P("Preferred Strategic Pathway", S_H1))
        story.append(P(f"<b>THP + Mesophilic Digestion + Struvite + Land</b> &mdash; the highest-"
                       f"performing <i>commit-grade</i> pathway for {plant['name']} "
                       f"({tot:.0f} tDS/d).", mk("rec", parent=S_BODY, backColor=LIGHT, borderPadding=6,
                                                 textColor=INK)))
    else:
        story.append(P("Preferred Development Pathway", S_H1))
        story.append(P(f"<b>Optimise + Separate Digestion within existing volume</b>, with THP and thermal held "
                       f"as evidence-triggered options &mdash; the least-regret sequence for {plant['name']} "
                       f"({tot:.0f} tDS/d). THP scores marginally highest on the weighted drivers but does not pay "
                       f"here on energy or capacity, so it is not the build recommendation.",
                       mk("rec", parent=S_BODY, backColor=LIGHT, borderPadding=6, textColor=INK)))
    story.append(kv([
        ("Performance score (this engine, weighted drivers)", f"{aw['performance']*100:.0f} / 100"),
        ("Deferred digester CAPEX (Base; Low&ndash;High)",
         f"${cap['capex_base_aud']/1e6:.0f}M (${cap['capex_low_aud']/1e6:.0f}-{cap['capex_high_aud']/1e6:.0f}M)"),
        ("Net OPEX", f"${ox['net_m_aud']:+.1f}M/yr (cash-positive)"),
        ("Net energy", f"{wp.net_export_mwh_d:,.0f} MWh/d exported"),
        ("Capacity intensification", f"{cap['digesters_avoided']:.1f} reference digesters avoided"),
        ("THP consolidated value (capacity + disposal + logistics + energy)", f"~${tv['total']:.1f}M/yr"),
        ("Biosolids class", "Class A (THP pasteurisation, subject to EPA validation)"),
        ("PFAS", "Not addressed by digestion &mdash; thermal endpoint required if PFAS binds"),
    ]))
    story.append(P("Why not the higher-scoring option? The thermal endpoint scores higher on raw "
                   f"performance ({at['performance']*100:.0f}/100) but is provisional (low confidence, "
                   "uncalibrated) and not yet buildable. The preferred strategic pathway is the highest-value "
                   "pathway under current assumptions that is commit-grade today. Score is absolute (weighted satisfaction of "
                   "all eight drivers, including PFAS which no digestion route alone can meet), not "
                   "relative to the field &mdash; so mid-range is a strong result.", S_SMALL))

    story.append(P("1 &nbsp; Pathway Comparison", S_H1))
    rows = [[P("Pathway", S_CELLH), P("Perf.", S_CRH), P("Conf.", S_CRH),
             P("Net energy", S_CRH), P("Net OPEX", S_CRH), P("Capacity", S_CRH), P("Class", S_CRH)]]
    for nm, p, ax in [("Conventional MAD + land", cp, ac), ("THP + MAD + struvite + land (preferred)", wp, aw),
                      ("THP + MAD + thermal endpoint", tp, at)]:
        o = S.opex_view(p); c = S.capacity_view(p)
        rows.append([P(nm, S_CELL), P(f"{ax['performance']*100:.0f}", S_CR),
                     P(f"{ax['confidence']:.2f}", S_CR), P(f"{p.net_export_mwh_d:,.0f}", S_CR),
                     P(f"${o['net_m_aud']:+.1f}M", S_CR),
                     P(f"{c.get('digesters_avoided',0):.1f} dig." if c.get('digesters_avoided') else "-", S_CR),
                     P("A" if p is not cp else "B", S_CR)])
    story.append(styled(Table(rows, colWidths=[58*mm, 16*mm, 16*mm, 24*mm, 22*mm, 20*mm, 14*mm])))
    story.append(P("Performance and confidence are the same engine values reported in the Strategic "
                   "and Board views; only the framing differs.", S_SMALL))

    story.append(P("2 &nbsp; Capacity Intensification (the main THP justification)", S_H1))
    cc, tc = cap["conv_constraints"], cap["thp_constraints"]
    rows = [[P("Volume constraint", S_CELLH), P("Conventional", S_CRH), P("THP", S_CRH)]]
    for k, lab in [("hydraulic", "Hydraulic floor"), ("hydrolysis", "Hydrolysis HRT"), ("OLR", "Organic loading")]:
        rows.append([P(lab, S_CELL), P(f"{cc[k]:,.0f} m\u00b3", S_CR), P(f"{tc[k]:,.0f} m\u00b3", S_CR)])
    rows.append([P("<b>Required (governing)</b>", S_CELLB),
                 P(f"<b>{cap['vol_conv_m3']:,.0f} ({cap['conv_governing']})</b>", S_CR),
                 P(f"<b>{cap['vol_thp_m3']:,.0f} ({cap['thp_governing']})</b>", S_CR)])
    story.append(styled(Table(rows, colWidths=[80*mm, 45*mm, 45*mm])))
    story.append(P(f"Conventional is {cap['conv_governing']}-governed; THP is {cap['thp_governing']}-governed (runs at "
                   f"{S.KCAP.OLR_THP} vs {S.KCAP.OLR_CONV} kgVS/m\u00b3\u00b7d). Avoided volume "
                   f"{cap['avoided_m3']:,.0f} m\u00b3 = {cap['digesters_avoided']:.1f} digesters. "
                   f"Deferred CAPEX ${cap['capex_low_aud']/1e6:.0f}M / "
                   f"${cap['capex_base_aud']/1e6:.0f}M / ${cap['capex_high_aud']/1e6:.0f}M "
                   "(tank-only / base / full-replacement). THP capital itself needs a vendor quote.", S_SMALL))

    story.append(P("3 &nbsp; Operating Cost", S_H1))
    rows = [[P("Term (M$/yr)", S_CELLH), P("Value", S_CRH)]]
    for key, lab in [("energy_m_aud", "Energy (net export)"), ("transport_m_aud", "Transport"),
                     ("chemicals_m_aud", "Chemicals"), ("om_m_aud", "O&amp;M"),
                     ("struvite_revenue_m_aud", "Struvite revenue (credit)")]:
        v = ox[key] * (-1 if key == "struvite_revenue_m_aud" else 1)
        rows.append([P(lab, S_CELL), P(f"{v:+.2f}", S_CR)])
    rows.append([P("<b>Net OPEX</b>", S_CELLB), P(f"<b>{ox['net_m_aud']:+.2f}</b>", S_CR)])
    story.append(styled(Table(rows, colWidths=[120*mm, 30*mm])))

    story.append(P("4 &nbsp; Carbon / GHG Summary", S_H1))
    cl = wp.ledgers["carbon"]
    rows = [[P("Carbon destination", S_CELLH), P("tC/d", S_CRH), P("% of feed", S_CRH)]]
    for k, v in cl.outflows.items():
        if v > 0:
            rows.append([P(k.replace("_", " "), S_CELL), P(f"{v:,.1f}", S_CR), P(f"{v/cl.total_in*100:.0f}%", S_CR)])
    story.append(styled(Table(rows, colWidths=[96*mm, 37*mm, 37*mm])))
    story.append(P("Scope 1 is dominated by fugitive CH4; controlling gas capture is the largest "
                   "GHG lever and is independent of configuration.", S_SMALL))

    story.append(P("5 &nbsp; Nutrient Recovery (co-equal value stream)", S_H1))
    nv = S.nutrient_value(wp)
    story.append(P(f"Nutrient recovery is quantified as a value stream in its own right. Struvite "
                   f"recovers {nv['P_recovered_kgd']:,.0f} kg P/d ({nv['P_security_pct']:.0f}% of feed P). "
                   f"The return-liquor nitrogen ({nv['return_liquor_N_kgd']:,.0f} kg N/d) is addressed two "
                   "ways, reported separately and never summed: PN/A <i>destroys</i> it (avoided treatment "
                   "cost) or ammonium sulphate <i>recovers</i> it as fertiliser."))
    story.append(kv([
        ("Struvite P recovered", f"{nv['P_recovered_kgd']:,.0f} kgP/d ({nv['struvite_t_yr']:,.0f} t/yr)"),
        ("Struvite revenue", f"${nv['struvite_revenue_m_aud_yr']:.2f}M/yr"),
        ("Return-liquor N (treatable)", f"{nv['return_liquor_N_kgd']:,.0f} kgN/d"),
        ("N via PN/A (destroy)", f"{nv['pna_N_destroyed_kgd']:,.0f} kgN/d, ${nv['pna_avoided_cost_m_aud_yr']:.2f}M/yr avoided"),
        ("N via ammonium sulphate (recover)", f"{nv['as_N_recovered_kgd']:,.0f} kgN/d, ${nv['as_revenue_m_aud_yr']:.2f}M/yr"),
        ("Recommended N route", nv["recommended_N_route"]),
        ("Sidestream load reduction", f"{nv['sidestream_N_removed_kgd']:,.0f} kgN/d removed"),
        ("Fertiliser-replacement value", f"${nv['fertiliser_value_m_aud_yr']:.2f}M/yr"),
        ("Future nutrient security", f"P {nv['P_security_pct']:.0f}% / N {nv['N_recovered_pct']:.0f}% recovered"),
    ], w=(64, 106)))
    story.append(P(f"<b>Headline nutrient value ${nv['nutrient_value_m_aud_yr']:.2f}M/yr</b> against digestion "
                   f"net OPEX ${ox['net_m_aud']:+.2f}M/yr &mdash; nutrient recovery is a value stream on par "
                   "with digestion optimisation, not a by-product.", S_SMALL))

    story.append(P("6 &nbsp; Key Risks &amp; Assumptions", S_H1))
    for b in ["WAS hydrolysis HRT may limit conventional performance &mdash; confirm with BMP testing.",
              "THP capital not costed here &mdash; obtain vendor quote; deferred-digester CAPEX is the offsetting value.",
              "Return-liquor nitrogen raises mainstream aeration/alkalinity load &mdash; assess TN headroom.",
              "PFAS not characterised &mdash; if land application is restricted, a thermal endpoint is required.",
              "Phosphorus is an estimate &mdash; confirm by centrate/cake sampling."]:
        story.append(bullet(b))

    story.append(P("7 &nbsp; Recommendation &amp; Next Steps", S_H1))
    if bundle["sf"]["diag"].get("hrt_limited", True):
        story.append(P("Develop THP + MAD + struvite as the current <b>commit-grade reference case</b>, but do "
            "<b>not</b> lock THP capital before testing the lower-regret separate-digestion / recuperative-thickening "
            "(K+) pathway. The recommendation is <b>staged capital allocation</b>, not a single build decision:"))
        for i, r in enumerate([
            "Optimise MAD and dewatering now &mdash; commit-grade, no-regret.",
            "Validate separate digestion and recuperative thickening (<b>K-Core</b>) &mdash; PS/WAS/blended BMP first, "
            "then a SolidStream-treated WAS BMP for the ceiling assist (<b>K-Assist</b>).",
            "Commit struvite and sidestream-nitrogen (PN/A) readiness once centrate P and NH4 are confirmed.",
            "Preserve the SolidStream and thermal corridors as priced, scheduled options &mdash; do not foreclose them.",
            "Decide the thermal endpoint only when the PFAS trigger score and measured PFAS justify it; do not commit "
            "land as a terminal endpoint."], 1):
            story.append(bullet(r, mark=f"{i}."))
        story.append(P("THP stays the reference case because it is commit-grade today; the staging exists because "
            "K-Core may deliver much of the capacity at lower regret, and that hypothesis is cheap to test before "
            "THP capital is committed.", S_SMALL))
    else:
        story.append(P("This plant is <b>not capacity-constrained</b> &mdash; the biogas-adequate split fits within "
            "existing digester volume. THP and thermal are therefore <b>evidence-triggered options, not the reference "
            "case</b>. The recommendation is to optimise and reconfigure existing assets first:"))
        for i, r in enumerate([
            "Optimise MAD now &mdash; verify and, if real, lift digester temperature, and close the solids / recycle "
            "mass balance. Commit-grade, no-regret.",
            "Reconfigure to separate digestion within the existing volume (<b>K-Core</b>) &mdash; capture "
            "below-plateau methane without new tanks; confirm with a PS / WAS / blended BMP.",
            "Recover nutrients &mdash; struvite on the favourable centrate (DRP, Mg, pH), and size sidestream-nitrogen "
            "(PN/A) readiness once loads are confirmed.",
            "Hold THP, SolidStream and thermal as priced, <b>evidence-triggered</b> options &mdash; commit THP only if "
            "a capacity or biosolids-quality gap emerges; trigger thermal only on measured PFAS; do not commit land as "
            "a terminal endpoint."], 1):
            story.append(bullet(r, mark=f"{i}."))
        story.append(P("On current screening THP does not pay at this plant on energy or capacity &mdash; it lowers "
            "available energy and avoids only a fraction of a digester. Its case here rests on the benefits it still "
            "delivers &mdash; a Class A product, better dewaterability, pathogen reduction and cake-logistics savings "
            "&mdash; not on capacity, so it is held as a quality-and-endpoint option, not a reference case.", S_SMALL))
    story.append(P("Investment gates &mdash; clear before commitment", S_H2))
    for g in [
        "PS / WAS / blended BMP confirmation (the separate-digestion uplift basis).",
        "SolidStream-treated WAS BMP (resolves K-Assist from confidence D to measured).",
        "Centrate NH4, PO4, alkalinity and soluble COD (nutrient value and the recycle risk factor).",
        "Digester foaming microscopy and Nocardia / Gordonia / mycolata abundance.",
        "Rheology and mixing assessment at recuperative-thickening solids levels.",
        "PFAS characterisation in cake, centrate and thermal residuals."]:
        story.append(bullet(g))
    story.extend(_separate_digestion_section(bundle["sf"]))
    story.extend(_foaming_section(bundle["sf"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=4))
    story.append(P("Screening-grade. One BioPoint engine; this is the technology-focused view. For "
                   "the move-sequence rationale see the Strategic Pathway report; for multi-future "
                   "robustness see the Board &amp; Future Resilience report.", S_SMALL))
    return story


# ===========================================================================
# MODE 3 VIEW — Board & Future Resilience Report ("What survives the future?")
# ===========================================================================
def future_resilience_story(bundle):
    plant, wp, tp, cp = bundle["plant"], bundle["wp"], bundle["tp"], bundle["cp"]
    weights = bundle["weights"]
    kp = S.build_pathway_k_plus(plant)
    trio = [cp, kp, wp, tp]
    qlabels = ["Conventional", "K+ (WAS at floor)", "THP-WAS", "Thermal endpoint"]
    story = []
    story.append(P("Board &amp; Future Resilience Report", S_TITLE))
    story.append(P("BioPoint &middot; What survives the future?", S_SUB))
    story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=3, spaceAfter=8))
    story.extend(_screening_banner(bundle["plant"]))

    story.append(P("Board Summary &mdash; Three Axes", S_H1))
    story.append(P("Each pathway is judged on three independent axes. No single axis decides; a "
                   "board's job is to choose the balance of present value, certainty and "
                   "robustness it wants."))
    rows = [[P("Pathway", S_CELLH), P("Performance", S_CRH), P("Confidence", S_CRH),
             P("Resilience", S_CRH), P("Optionality", S_CRH), P("PFAS ban", S_CRH)]]
    for p, lab in zip(trio, qlabels):
        ax = S.three_axis(p, weights); rz = S.resilience(p); op = S.optionality(p)
        rows.append([P(lab, S_CELL),
                     P(f"{ax['performance']*100:.0f}", S_CR), P(f"{ax['confidence']*100:.0f}", S_CR),
                     P(f"{ax['resilience']*100:.0f}", S_CR), P(f"{op['score']*100:.0f}", S_CR),
                     P("survives" if rz["survives_pfas_ban"] else "fails", S_CR)])
    story.append(styled(Table(rows, colWidths=[58*mm, 24*mm, 23*mm, 22*mm, 23*mm, 20*mm])))
    story.append(P("Operational axes &mdash; complexity and reversibility (what boards also weigh)", S_H2))
    orows = [[P("Pathway", S_CELLH), P("Complexity (1-6)", S_CRH), P("Reversibility (0-100)", S_CRH)]]
    for p, lab in zip(trio, qlabels):
        cx = S.complexity_score(p)
        orows.append([P(lab, S_CELL), P(f"{cx['score']} ({cx['label']})", S_CR),
                      P(f"{S.optionality(p)['reversibility']*100:.0f}", S_CR)])
    story.append(styled(Table(orows, colWidths=[58*mm, 46*mm, 46*mm])))
    story.append(P("This is why a board may rationally take 90% of the benefit at a fraction of the commitment: "
                   "K+ is an operational change (complexity 2, reversibility 80), whereas a full thermal train is "
                   "complexity 6, reversibility 20. The least-regret view already prices reversibility into its "
                   "commitment-regret term; complexity is carried alongside, not collapsed into one score.", S_SMALL))
    story.append(P("<b>Reversibility Index</b> &mdash; distinct from optionality: optionality asks how many futures a "
                   "pathway keeps open; reversibility asks how easily the decision is unwound if it proves wrong. "
                   "Boards weigh this directly, often above NPV.", S_SMALL))
    rrows = [[P("Decision", S_CELLH), P("Reversibility (0-100)", S_CRH), P("Why", S_CELLH)]]
    for nm, v, why in S.reversibility_index():
        rrows.append([P(nm, S_CELL), P(f"{v}", S_CR), P(why, S_CELL)])
    story.append(styled(Table(rrows, colWidths=[60*mm, 30*mm, 60*mm])))
    story.append(P("The split matters for the allocation: the <i>separate-digestion core</i> (90) is far more "
                   "reversible than the full K+ play that leans on the SolidStream assist (80) &mdash; which is why "
                   "the proven core can be committed now while the SolidStream-assist uplift stays a monitored "
                   "option.", S_SMALL))
    story.append(P("Reading: <b>K+ matches the THP spine's optionality</b> (it forecloses nothing) at "
                   "materially lower capex and complexity &mdash; the lower-commitment route to most of the "
                   "capacity benefit. The thermal endpoint is the most resilient and the only PFAS-robust "
                   "option but the least proven and forecloses nutrient recovery; conventional is proven but "
                   "low-value and low-resilience. All four fail a PFAS land-application ban except thermal "
                   "&mdash; which is why the endpoint is a separate decision.", S_SMALL))
    story.append(P("<b>Key strategic insight:</b> PFAS fate is set by the thermal endpoint, not the "
                   "digestion technology. The THP decision and the thermal-endpoint decision are "
                   "independent &mdash; THP earns its place on capacity and energy regardless, but "
                   "does not substitute for a thermal decision if PFAS binds.",
                   mk("ins", parent=S_BODY, backColor=LIGHT, borderPadding=6, spaceBefore=4)))

    story.append(P("Constraint Radar &mdash; today vs 10 years (uniting the two questions)", S_H1))
    cr = S.constraint_radar(plant)
    story.append(P("The Strategic report asks which constraint governs the plant <i>today</i>; this report asks which "
                   "<i>future</i> breaks the pathway. The radar puts both on one page &mdash; risk per constraint now "
                   "and in ~10 years, and how each pathway moves it (lowers / raises / -- neutral).", S_SMALL))
    crrows = [[P("Constraint", S_CELLH), P("Today", S_CRH), P("~10 yr", S_CRH)] +
              [P(x, S_CRH) for x in ["Conv", "K+", "THP", "Therm"]]]
    for cname, today, future in cr["constraints"]:
        mv = cr["pathway_moves"].get(cname, {})
        crrows.append([P(cname, S_CELL), P(today, S_CR), P(future, S_CR),
                       P(mv.get("Conventional", "--"), S_CR), P(mv.get("K+", "--"), S_CR),
                       P(mv.get("THP", "--"), S_CR), P(mv.get("Thermal", "--"), S_CR)])
    story.append(styled(Table(crrows, colWidths=[32*mm, 15*mm, 16*mm, 18*mm, 18*mm, 18*mm, 26*mm])))
    story.append(P(cr["note"], S_SMALL))

    story.append(P("1 &nbsp; Future Scenarios (different worlds)", S_H1))
    mats = [S.resilience(p)["results"] for p in trio]
    rows = [[P("Future world", S_CELLH), P("Likely", S_CRH), P("Conv", S_CRH),
             P("K+", S_CRH), P("THP", S_CRH), P("Thermal", S_CRH)]]
    for i, sc in enumerate(S.SCENARIOS):
        cells = [P(sc.name, S_CELL), P(f"{sc.likelihood:.2f}", S_CR)]
        for m in mats:
            v = m[i]; cells.append(P(f"{v['perf']:.2f}" + ("" if v["viable"] else " (x)"), S_CR))
        rows.append(cells)
    story.append(styled(Table(rows, colWidths=[54*mm, 14*mm, 22*mm, 18*mm, 20*mm, 22*mm])))
    story.append(P("(x) = non-viable in that world. Only the thermal endpoint survives a PFAS ban; "
                   "both THP pathways absorb FOGO co-feed via OLR headroom; phosphorus scarcity "
                   "rewards the struvite spine over thermal-to-ash.", S_SMALL))

    story.append(P("Least-Regret &mdash; computed across the worlds (not asserted)", S_H2))
    rt = S.regret_table(trio)
    story.append(P("For each world, regret = the best result achievable in that world minus this pathway's "
                   "result. Total regret is the likelihood-weighted mean &mdash; the least-regret pathway is "
                   "the one least often badly wrong, which is the board's actual question.", S_SMALL))
    rrows = [[P("Future world", S_CELLH), P("Likely", S_CRH)] +
             [P(x, S_CRH) for x in ["Conv", "K+", "THP", "Thermal"]]]
    for r in rt["matrix"]:
        cells = [P(r["scenario"], S_CELL), P(f"{r['likelihood']:.2f}", S_CR)]
        for j in range(len(trio)):
            cells.append(P(f"{r['regret'][j]:.2f}" + ("" if r["viable"][j] else " (x)"), S_CR))
        rrows.append(cells)
    for lab, key in [("Performance regret (weighted)", "perf_regret"),
                     ("Commitment regret (stranded capital)", "commit_regret")]:
        row = [P(lab, S_CELLB), P("", S_CR)]
        for j in range(len(trio)):
            row.append(P(f"{rt[key][j]:.2f}", S_CR))
        rrows.append(row)
    treg = [P("<b>Total regret</b>", S_CELLB), P("", S_CR)]
    for j in range(len(trio)):
        treg.append(P(f"<b>{rt['total_regret'][j]:.2f}</b>", S_CR))
    rrows.append(treg)
    story.append(styled(Table(rrows, colWidths=[54*mm, 14*mm, 22*mm, 18*mm, 20*mm, 22*mm])))
    _least = qlabels[rt["least_regret_idx"]]
    story.append(P("Per-world cells are <i>regret</i> (0 = best in that world; (x) = non-viable). Total = "
                   "likelihood-weighted performance regret PLUS a commitment term: building a large, irreversible "
                   "asset that a benign future does not need is itself a regret &mdash; the Hunter Water lesson. "
                   "Without it, regret structurally favours the highest-capex option regardless of how likely its "
                   f"triggering future is. <b>Least regret at the default 70% PFAS-ban likelihood: {_least}</b> &mdash; "
                   "it carries the PFAS hedge but pays the largest commitment regret, so its lead is conditional on "
                   "that probability.", S_SMALL))

    story.append(P("Regret sensitivity to the PFAS-ban probability", S_H2))
    pts = S.pfas_trigger_score()
    story.append(P(f"The PFAS-ban likelihood is the single assumption that most drives the ranking, so it should be "
                   f"<i>derived, not asserted</i>. The <b>PFAS Trigger Score</b> builds it from auditable drivers, so "
                   f"a board can challenge any one line rather than the bare headline. On the default settings these "
                   f"compose to a {pts['ban_probability']*100:.0f}% ban probability:", S_SMALL))
    trows = [[P("Driver", S_CELLH), P("Weight", S_CRH), P("Score (0-1)", S_CRH), P("Contribution", S_CRH)]]
    for x in pts["rows"]:
        trows.append([P(x["label"], S_CELL), P(f"{x['weight']:.2f}", S_CR), P(f"{x['score']:.2f}", S_CR),
                      P(f"{x['contribution']:.3f}", S_CR)])
    trows.append([P("<b>PFAS ban probability</b>", S_CELL), P("", S_CR), P("", S_CR),
                  P(f"<b>{pts['ban_probability']:.2f}</b>", S_CR)])
    story.append(styled(Table(trows, colWidths=[76*mm, 22*mm, 26*mm, 26*mm])))
    story.append(P("Each driver is tunable per jurisdiction and plant; the score replaces a single asserted number "
                   "with a defensible build-up. Sweeping the resulting probability shows the recommendation is NOT "
                   "&lsquo;thermal always&rsquo;: below roughly half, the reversible K+ is least-regret; only when a "
                   "ban is more likely than not does the committed thermal train justify its capital.", S_SMALL))
    rs = S.regret_sensitivity(trio)
    srows = [[P("PFAS-ban probability", S_CELLH), P("Least-regret pathway", S_CRH)]]
    for rr in rs:
        srows.append([P(f"{rr['pfas_prob']*100:.0f}%", S_CELL), P(qlabels[rr["winner_idx"]], S_CR)])
    story.append(styled(Table(srows, colWidths=[80*mm, 70*mm])))
    story.append(P("This is the crossover earlier drafts hid: &lsquo;thermal wins&rsquo; is conditional on a high "
                   "PFAS-ban probability, not a universal conclusion.", S_SMALL))

    story.append(P("2 &nbsp; Optionality (which futures each pathway keeps open)", S_H1))
    story.append(P("The Hunter Water lesson: some moves preserve future options, others foreclose "
                   "them. High optionality is itself strategic value."))
    rows = [[P("Pathway", S_CELLH), P("Options kept open", S_CELLH), P("Forecloses", S_CELLH)]]
    for p, lab in zip(trio, qlabels):
        op = S.optionality(p)
        rows.append([P(lab, S_CELL),
                     P(f"{op['score']*100:.0f}% &mdash; " + ", ".join(op["preserved"][:3]) +
                       ("&hellip;" if len(op["preserved"]) > 3 else ""), S_CELL),
                     P(", ".join(op["foreclosed"]) or "none", S_CELL)])
    story.append(styled(Table(rows, colWidths=[50*mm, 70*mm, 50*mm])))
    story.append(P("The spine keeps every option open (commit the shared front-end, defer the "
                   "endpoint); thermal commits early and forecloses nutrient recovery; conventional "
                   "forecloses the FOGO/capacity headroom.", S_SMALL))

    story.append(P("3 &nbsp; Regulatory Resilience", S_H1))
    for b in ["<b>PFAS land-application ban:</b> only a thermal endpoint survives. Keep the cake "
              "route thermal-ready; do not commit terminal land application.",
              "<b>Carbon / methane regulation:</b> rewards low Scope 1 and durable carbon storage "
              "(char) &mdash; favours the thermal endpoint and gas-capture investment.",
              "<b>Nutrient (phosphorus) policy:</b> rewards recovery; thermal strands P in ash, so "
              "recover upstream (struvite) before any thermal step."]:
        story.append(bullet(b))

    story.append(P("4 &nbsp; Technology Maturity", S_H1))
    rows = [[P("Technology", S_CELLH), P("Maturity", S_CRH)]]
    for t, m in [("THP", "Very high"), ("PN/A", "High"), ("Struvite", "High"),
                 ("Pyrolysis", "Medium"), ("Gasification", "Medium"), ("HTL", "Low (pre-commercial)")]:
        rows.append([P(t, S_CELL), P(m, S_CR)])
    story.append(styled(Table(rows, colWidths=[100*mm, 50*mm])))
    story.append(P("Maturity gates the recommendation verb: the commit-grade front-end uses "
                   "very-high/high-maturity technology; the thermal endpoint (medium/low) is held "
                   "open and de-risked rather than committed.", S_SMALL))

    story.append(P("5 &nbsp; Carbon Strategy (next engine)", S_H1))
    story.append(P("Carbon <i>fate</i> is fully tracked (resource-fate ledgers). Carbon "
                   "<i>value</i> &mdash; permanence (100-year retained), avoided fossil carbon, and "
                   "credit pricing &mdash; is the next engine and is not yet quantified. Land-applied "
                   "and char carbon have very different permanence, which will materially affect the "
                   "carbon case once priced.", S_SMALL))

    story.append(P("6 &nbsp; Capital Allocation &mdash; Commit Now / Preserve / Monitor", S_H1))
    ca = S.capital_allocation(plant)
    story.append(P("Boards allocate capital, not technologies. The decision is not which technology wins, "
                   "but what to commit today while preserving future options. Each item is graded by "
                   "evidence maturity.", S_SMALL))
    for hd, ky, col in [("Commit now (high confidence, low regret)", "commit_now", GOOD),
                        ("Preserve (keep the option open at low cost)", "preserve", ACCENT),
                        ("Monitor (evidence still emerging)", "monitor", MUTED)]:
        story.append(P(f"<b>{hd}</b>", mk("ca_"+ky, parent=S_BODY, textColor=col, spaceBefore=4, spaceAfter=2)))
        for item, why in ca[ky]:
            story.append(bullet(f"<b>{item}</b> &mdash; {why}"))
    story.append(P(ca["note"], mk("can", parent=S_SMALL, backColor=LIGHT, borderPadding=6, spaceBefore=4)))
    story.extend(_separate_digestion_section(bundle["sf"]))
    story.extend(_foaming_section(bundle["sf"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=4))
    story.append(P("One BioPoint engine; this is the future-focused board view. The same pathway "
                   "calculations underlie the Project Development and Strategic Pathway reports.", S_SMALL))
    return story


def make_footer(label):
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
        canvas.drawString(20*mm, 12*mm, label)
        canvas.drawRightString(190*mm, 12*mm, f"Page {doc.page}")
        canvas.setStrokeColor(RULE); canvas.line(20*mm, 14*mm, 190*mm, 14*mm)
        canvas.restoreState()
    return footer


MODES = {
    "project":    ("Project Development Report",         project_development_story, "Project_Development_Report.pdf"),
    "strategic":  ("Strategic Biosolids Pathway Report", build,                     "Strategic_Pathway_Report.pdf"),
    "resilience": ("Board & Future Resilience Report",   future_resilience_story,   "Future_Resilience_Report.pdf"),
}


def generate(mode, plant=S.ETP, outdir="/mnt/user-data/outputs"):
    """One engine, three views. Build the shared bundle once, render the chosen view."""
    title, story_fn, fname = MODES[mode]
    bundle = _engine(plant)                       # <-- identical calculations for every mode
    out = f"{outdir}/{fname}"
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=18*mm, bottomMargin=20*mm,
                            leftMargin=20*mm, rightMargin=20*mm, title=title, author="BioPoint")
    foot = make_footer(f"BioPoint - {title} ({plant.get('name', 'ETP')})")
    doc.build(story_fn(bundle), onFirstPage=foot, onLaterPages=foot)
    print("PDF written:", out)
    return out


if __name__ == "__main__":
    import sys
    todo = sys.argv[1:] or ["project", "strategic", "resilience"]
    for m in todo:
        generate(m)

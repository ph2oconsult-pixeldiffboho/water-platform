"""
apps/biosolids_app/engine/biopoint_v2_bridge.py

Bridges the V1 Tier-1 data object (Tier1ReportData) onto the V2 spine/report engine,
so the app can produce V2 strategic reports from the SAME plant inputs the user
entered for the V1 report.

V2's report writes a PDF file and returns its path; this module wraps it to return
bytes, matching how the page already handles the V1 PDF.
"""
import os as _os, sys as _sys, tempfile as _tempfile

# engine/ on path (append, not insert) so the bare sibling imports inside the V2
# modules resolve on Streamlit Cloud without shadowing stdlib (e.g. dataclasses.py).
_ED = _os.path.dirname(_os.path.abspath(__file__))
if _ED not in _sys.path:
    _sys.path.append(_ED)

import biopoint_v2_report as _V2R
import biopoint_v2_spine as _S

V2_MODES = ("project", "strategic", "resilience")
V2_MODE_LABELS = {
    "project":    "Project Development Report",
    "strategic":  "Strategic Biosolids Pathway Report",
    "resilience": "Board & Future Resilience Report",
}


def v1_data_to_v2_plant(d):
    """Map a V1 Tier1ReportData object onto the V2 spine plant dict.

    Direct:  PS/WAS dry solids (tDS/d) and feed TS% (V1 and V2 share the percent-number
             convention).
    Derived: V2 wants a single DS-weighted VS/TS fraction and a single total feed-N load;
             V1 stores both split by stream.
    Gap:     V1 captures no phosphorus input, so P_per_ds uses the spine default.
    """
    ps_tds  = float(d.ps_ds_tpd)
    was_tds = float(d.was_ds_tpd)
    total   = ps_tds + was_tds
    if total <= 0:
        raise ValueError("V1 data has zero total dry solids; cannot build a V2 plant.")
    vs_ts  = (ps_tds * float(d.ps_vs_pct) + was_tds * float(d.was_vs_pct)) / (total * 100.0)
    feed_N = (ps_tds * float(d.ps_n_pct)  + was_tds * float(d.was_n_pct)) / 100.0 * 1000.0
    return dict(
        name            = (getattr(d, "project_name", None) or "BioPoint Analysis"),
        PS_tds          = ps_tds,
        WAS_tds         = was_tds,
        ps_ts           = float(d.ps_ts_pct),
        was_ts          = float(d.was_ts_pct),
        vs_ts           = vs_ts,
        feed_N_kgd      = feed_N,
        P_per_ds        = _S.K.P_PER_DS,     # V1 has no P input; spine default (flagged)
        digester_vol_m3 = float(d.ps_volume_m3) + float(d.was_volume_m3),
    )


def generate_v2_report_bytes(mode, plant):
    """Run one V2 report view and return PDF bytes (V2 writes a file; we read it back)."""
    if mode not in V2_MODES:
        raise ValueError(f"unknown V2 mode {mode!r}; expected one of {V2_MODES}")
    tmp = _tempfile.mkdtemp(prefix="biopoint_v2_")
    path = _V2R.generate(mode, plant=plant, outdir=tmp)
    with open(path, "rb") as fh:
        return fh.read()

"""
streamlit_app.py — Streamlit Cloud entrypoint

Streamlit Cloud looks for this file at the repo root.
It simply re-runs the main application from apps/main_app.py.
"""
import sys
from pathlib import Path

# Ensure repo root is on the path so all imports resolve correctly
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Execute the main app
exec(open(ROOT / "apps" / "main_app.py").read())

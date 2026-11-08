"""Run once before class: finds or downloads har.csv and caches the UMAP lens in data/.
"""
from __future__ import annotations

import time

import numpy as np

from core.data import DATA_DIR, _emb_path, download_uci, find_csv, load_bundle

if __name__ == "__main__":
    path = find_csv() or download_uci(DATA_DIR / "har.csv")
    b = load_bundle(str(path), path.stat().st_mtime)
    print(f"{b.n} moments × {b.d} numbers · {len(set(b.subject.tolist()))} people · PCA 95% = {b.n95}")
    try:
        import umap
    except ImportError:
        raise SystemExit("pip install umap-learn  (needed for the UMAP lens)")
    t0 = time.time()
    u10 = umap.UMAP(n_components=10, random_state=42).fit_transform(b.X)
    DATA_DIR.mkdir(exist_ok=True)
    np.savez_compressed(_emb_path(b), umap10=u10)
    print(f"UMAP lens ready ({time.time() - t0:.0f}s). Start the game:  streamlit run app.py")

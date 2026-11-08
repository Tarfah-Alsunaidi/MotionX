"""Loads har.csv and runs the heavy shared computations (scaling, PCA, embeddings,
clustering), cached once for every screen.
"""
from __future__ import annotations

import io
import time
import zipfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

# --------------------------------------------------------------------------- #
# Settings and notebook results
# --------------------------------------------------------------------------- #
RANDOM_STATE = 42
APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
CSV_CANDIDATES = [APP_DIR / "har.csv", DATA_DIR / "har.csv", APP_DIR / "har.csv.gz", DATA_DIR / "har.csv.gz"]
_DOWNLOAD_LOCK = __import__("threading").Lock()
UCI_URL = ("https://archive.ics.uci.edu/static/public/240/"
           "human+activity+recognition+using+smartphones.zip")

ACTIVITIES = ["WALKING", "WALKING_UPSTAIRS", "WALKING_DOWNSTAIRS",
              "SITTING", "STANDING", "LAYING"]

NOTEBOOK = {
    ("kmeans", "raw"):    dict(ari=0.420, sil=0.110, time=1.75),
    ("kmeans", "pca95"):  dict(ari=0.419, sil=0.109, time=0.34),
    ("kmeans", "pca2"):   dict(ari=0.274, sil=0.096, time=0.04),
    ("kmeans", "umap10"): dict(ari=0.605, sil=0.076, time=0.05),
    ("dbscan", "raw"):    dict(ari=0.288, sil=0.313, time=1.31, noise=30.3, clusters=9, eps=14.0),
    ("dbscan", "pca2"):   dict(ari=0.321, sil=0.218, time=0.08, noise=5.1, clusters=6, eps=1.0),
}


# --------------------------------------------------------------------------- #
# Getting har.csv
# --------------------------------------------------------------------------- #
def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}.{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def download_uci(dest: Path) -> Path:
    raw = urllib.request.urlopen(UCI_URL, timeout=180).read()
    outer = zipfile.ZipFile(io.BytesIO(raw))
    inner = next((n for n in outer.namelist() if n.endswith("UCI HAR Dataset.zip")), None)
    z = zipfile.ZipFile(io.BytesIO(outer.read(inner))) if inner else outer

    def member(suffix: str) -> io.BytesIO:
        name = next(n for n in z.namelist()
                    if n.endswith(suffix) and "__MACOSX" not in n)
        return io.BytesIO(z.read(name))

    feats = pd.read_csv(member("features.txt"), sep=r"\s+", header=None)[1].tolist()
    labels = pd.read_csv(member("activity_labels.txt"), sep=r"\s+", header=None)
    label_map = dict(zip(labels[0], labels[1]))

    parts = []
    for split in ("train", "test"):
        X = pd.read_csv(member(f"{split}/X_{split}.txt"), sep=r"\s+", header=None)
        X.columns = _dedupe(feats)
        X["subject"] = pd.read_csv(member(f"{split}/subject_{split}.txt"), header=None)[0].values
        X["Activity"] = pd.read_csv(member(f"{split}/y_{split}.txt"), header=None)[0].map(label_map).values
        parts.append(X)
    df = pd.concat(parts, ignore_index=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False)
    return dest


def find_csv() -> Path | None:
    for p in CSV_CANDIDATES:
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------- #
# The bundle: everything derived from X that several chapters need
# --------------------------------------------------------------------------- #
@dataclass
class Bundle:
    key: str
    feature_names: list[str]
    X_raw: np.ndarray
    X: np.ndarray
    y: np.ndarray
    subject: np.ndarray
    Z: np.ndarray
    components: np.ndarray
    evr: np.ndarray
    eigvals: np.ndarray
    n95: int
    plot_idx: np.ndarray
    extra: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return self.X.shape[0]

    @property
    def d(self) -> int:
        return self.X.shape[1]


@st.cache_resource(show_spinner="Folding 561 dimensions… (one time only)")
def load_bundle(path_str: str, mtime: float) -> Bundle:
    df = pd.read_csv(path_str)
    if "Activity" not in df.columns:
        raise ValueError("har.csv needs an 'Activity' column")
    feat_cols = [c for c in df.columns if c not in ("subject", "Activity")]
    X_raw = df[feat_cols].to_numpy(np.float64)
    X = StandardScaler().fit_transform(X_raw)
    pca = PCA(svd_solver="full", random_state=RANDOM_STATE).fit(X)
    Z = pca.transform(X)
    cum = np.cumsum(pca.explained_variance_ratio_)
    n95 = int(np.argmax(cum >= 0.95) + 1)
    rng = np.random.default_rng(RANDOM_STATE)
    plot_idx = np.sort(rng.choice(len(X), size=min(3000, len(X)), replace=False))
    key = f"{X.shape[0]}x{X.shape[1]}_{float(np.abs(X_raw[:200]).sum()):.3f}"
    subject = df["subject"].to_numpy() if "subject" in df.columns else np.zeros(len(df), int)
    return Bundle(key=key, feature_names=feat_cols, X_raw=X_raw, X=X,
                  y=df["Activity"].astype(str).to_numpy(), subject=subject, Z=Z,
                  components=pca.components_, evr=pca.explained_variance_ratio_,
                  eigvals=pca.explained_variance_, n95=n95, plot_idx=plot_idx)


def get_bundle() -> Bundle:
    path = find_csv()
    if path is None and not st.session_state.get("_uci_failed"):
        with st.spinner("First start: downloading the dataset from UCI (about 1 minute)…"):
            with _DOWNLOAD_LOCK:
                path = find_csv()
                if path is None:
                    try:
                        path = download_uci(DATA_DIR / "har.csv")
                    except Exception as e:
                        st.session_state["_uci_failed"] = str(e)
    if path is None:
        if st.session_state.get("_uci_failed"):
            st.error(f"Automatic download failed: {st.session_state['_uci_failed']}")
        st.markdown("### 📂 Where is `har.csv`?")
        st.write("Put the notebook's `har.csv` next to `app.py` (or in `data/`), "
                 "download it straight from UCI, or upload it here.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬇️ Download from UCI (58 MB, ~1 min)", type="primary"):
                with st.spinner("Downloading and merging train + test…"):
                    try:
                        download_uci(DATA_DIR / "har.csv")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Download failed: {e}")
        with c2:
            up = st.file_uploader("…or upload har.csv", type="csv")
            if up is not None:
                DATA_DIR.mkdir(exist_ok=True)
                (DATA_DIR / "har.csv").write_bytes(up.getbuffer())
                st.rerun()
        st.stop()
    return load_bundle(str(path), path.stat().st_mtime)


# --------------------------------------------------------------------------- #
# Embeddings (t-SNE + UMAP) — slow, so cached on disk
# --------------------------------------------------------------------------- #
def _emb_path(b: Bundle) -> Path:
    return DATA_DIR / f"embeddings_{b.key.replace('.', '_')}.npz"


def umap_available() -> bool:
    try:
        import umap
        return True
    except Exception:
        return False


def load_embeddings(b: Bundle) -> dict | None:
    if "emb" in b.extra:
        return b.extra["emb"]
    p = _emb_path(b)
    if p.exists():
        with np.load(p) as f:
            b.extra["emb"] = {k: f[k] for k in f.files}
        return b.extra["emb"]
    return None


def compute_embeddings(b: Bundle, progress=None) -> dict:
    from sklearn.manifold import TSNE
    out = {}
    steps = [("tsne2", "t-SNE (2D)")]
    if umap_available():
        steps += [("umap2", "UMAP (2D)"), ("umap10", "UMAP (10D)")]
    for i, (k, label) in enumerate(steps):
        if progress:
            progress(i / len(steps), f"Computing {label}…")
        t0 = time.time()
        if k == "tsne2":
            out[k] = TSNE(n_components=2, random_state=RANDOM_STATE).fit_transform(b.X)
        else:
            import umap
            n = 2 if k == "umap2" else 10
            out[k] = umap.UMAP(n_components=n, random_state=RANDOM_STATE).fit_transform(b.X)
        out[f"{k}_seconds"] = np.array(time.time() - t0)
    DATA_DIR.mkdir(exist_ok=True)
    np.savez_compressed(_emb_path(b), **out)
    b.extra["emb"] = out
    if progress:
        progress(1.0, "Done")
    return out


# --------------------------------------------------------------------------- #
# Representations and clustering (same as the notebook's run_kmeans/run_dbscan)
# --------------------------------------------------------------------------- #
def rep_label(rep: str, b: Bundle) -> str:
    if rep == "raw":
        return f"All {b.d} features"
    if rep == "pca95":
        return f"PCA 95% ({b.n95} comps)"
    if rep == "umap10":
        return "UMAP (10D)"
    if rep.startswith("pca"):
        return f"PCA ({rep[3:]} comps)"
    return rep


def get_rep(b: Bundle, rep: str) -> np.ndarray:
    if rep == "raw":
        return b.X
    if rep == "pca95":
        return b.Z[:, :b.n95]
    if rep == "umap10":
        emb = load_embeddings(b)
        if emb is None or "umap10" not in emb:
            raise KeyError("UMAP not computed yet")
        return emb["umap10"]
    if rep.startswith("pca"):
        return b.Z[:, :int(rep[3:])]
    raise KeyError(rep)


def _silhouette(b: Bundle, labels: np.ndarray) -> float:
    mask = labels != -1
    if len(set(labels[mask])) < 2:
        return float("nan")
    return float(silhouette_score(b.X[mask], labels[mask],
                                  sample_size=min(3000, int(mask.sum())),
                                  random_state=RANDOM_STATE))


@st.cache_data(show_spinner=False, max_entries=128)
def run_clustering(_b: Bundle, bkey: str, rep: str, algo: str,
                   k: int = 6, eps: float = 1.0, min_samples: int = 10) -> dict:
    data = get_rep(_b, rep)
    t0 = time.time()
    if algo == "kmeans":
        labels = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit_predict(data)
    else:
        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(data)
    seconds = time.time() - t0
    mask = labels != -1
    return dict(labels=labels, seconds=seconds,
                ari=float(adjusted_rand_score(_b.y, labels)),
                sil=_silhouette(_b, labels),
                n_clusters=int(len(set(labels[mask]))),
                noise=float((~mask).mean() * 100))


@st.cache_data(show_spinner=False, max_entries=16)
def k_distance(_b: Bundle, bkey: str, rep: str, k: int = 10) -> np.ndarray:
    data = get_rep(_b, rep)
    d = NearestNeighbors(n_neighbors=k).fit(data).kneighbors(data)[0][:, -1]
    return np.sort(d)


@st.cache_resource(show_spinner=False)
def knn_index(_b: Bundle, bkey: str):
    return NearestNeighbors(n_neighbors=16).fit(_b.Z[:, :_b.n95])


def feature_family(name: str) -> str:
    return name.split("-")[0].split("(")[0].split(".")[0]


def find_feature(b: Bundle, *candidates: str) -> int | None:
    names = b.feature_names
    for c in candidates:
        if c in names:
            return names.index(c)
    for c in candidates:
        for i, n in enumerate(names):
            if c.lower() in n.lower():
                return i
    return None


_UMAP_LOCK = __import__("threading").Lock()


def ensure_umap(b: Bundle) -> bool:
    emb = load_embeddings(b)
    if emb is not None and "umap10" in emb:
        return True
    if not umap_available():
        return False
    with _UMAP_LOCK:
        emb = load_embeddings(b)
        if emb is not None and "umap10" in emb:
            return True
        import umap
        u10 = umap.UMAP(n_components=10, random_state=RANDOM_STATE).fit_transform(b.X)
        DATA_DIR.mkdir(exist_ok=True)
        out = dict(emb or {}, umap10=u10)
        np.savez_compressed(_emb_path(b), **out)
        b.extra["emb"] = out
    return True

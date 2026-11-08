"""Builds the game data from har.csv with the notebook's pipeline
(scaling, PCA / UMAP, K-Means / DBSCAN, ARI and Silhouette).
"""
from __future__ import annotations

import time

import numpy as np
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
ACTIVITIES = ["WALKING", "WALKING_UPSTAIRS", "WALKING_DOWNSTAIRS", "SITTING", "STANDING", "LAYING"]
NAMES = ["Noura", "Faisal", "Lama", "Omar", "Reem", "Saad", "Hessa", "Majed", "Dana", "Yousef",
         "Sara", "Khalid", "Maha", "Turki", "Joud", "Fahad", "Leen", "Nawaf", "Ruba", "Ziyad",
         "Hind", "Bader", "Amal", "Saud", "Ghada", "Rakan", "Jana", "Talal", "Wafa", "Hamad",
         "Mona", "Ali", "Rana", "Sami", "Dalia", "Nasser", "Lulu", "Hadi", "Rawan", "Zaid"]
NOTEBOOK_EPS = {"full": 14.0, "pca2": 1.0}


# --------------------------------------------------------------------------- #
# The machine: lens, sorter and scores
# --------------------------------------------------------------------------- #
def lenses(Z: np.ndarray, X: np.ndarray, n95: int, cum: np.ndarray, umap10: np.ndarray | None):
    out = {
        "full": dict(label="No lens · all 561 numbers", short="561 numbers", data=X, dims=X.shape[1],
                     kept=1.0, code="X"),
        "pca95": dict(label=f"PCA lens · {n95} numbers", short=f"PCA {n95}", data=Z[:, :n95], dims=n95,
                      kept=float(cum[n95 - 1]), code=f"PCA(n_components={n95}).fit_transform(X)"),
        "pca2": dict(label="Tiny PCA lens · 2 numbers", short="PCA 2", data=Z[:, :2], dims=2,
                     kept=float(cum[1]), code="PCA(n_components=2).fit_transform(X)"),
    }
    if umap10 is not None:
        out["umap"] = dict(label="UMAP lens · 10 numbers", short="UMAP 10", data=umap10, dims=10,
                           kept=None, code="umap.UMAP(n_components=10).fit_transform(X)")
    return out


def silhouette(X: np.ndarray, lab: np.ndarray) -> float | None:
    m = lab != -1
    if len(set(lab[m].tolist())) < 2:
        return None
    try:
        return float(silhouette_score(X[m], lab[m], sample_size=min(3000, int(m.sum())), random_state=42))
    except Exception:
        return None


def run_machine(data: np.ndarray, y_idx: np.ndarray, sorter: str, eps: float | None = None,
                X: np.ndarray | None = None) -> dict:
    t0 = time.time()
    if sorter == "kmeans":
        lab = KMeans(n_clusters=6, n_init=10, random_state=42).fit_predict(data)
    else:
        lab = DBSCAN(eps=eps, min_samples=10).fit_predict(data)
    sec = time.time() - t0
    piles, name_of = [], {}
    for c in sorted(set(lab.tolist()), key=lambda c: (c == -1, c)):
        m = lab == c
        counts = np.bincount(y_idx[m], minlength=6)
        name = -1 if c == -1 else int(counts.argmax())
        name_of[c] = name
        piles.append(dict(name=name, counts=counts.tolist(), size=int(m.sum())))
    pred = np.array([name_of[c] for c in lab])
    acc = float((pred == y_idx).mean())
    per_act = [float((pred[y_idx == a] == a).mean()) if (y_idx == a).any() else 0.0 for a in range(6)]
    n_clusters = len(set(lab.tolist()) - {-1})
    return dict(acc=acc, ari=float(adjusted_rand_score(y_idx, lab)), sec=sec, piles=piles,
                sil=silhouette(X, lab) if X is not None else None, clusters=n_clusters,
                perAct=per_act, unknown=float((pred == -1).mean()),
                pred="".join("x" if p == -1 else str(p) for p in pred))


# --------------------------------------------------------------------------- #
# Game data
# --------------------------------------------------------------------------- #
def build(X: np.ndarray, y: np.ndarray, subject: np.ndarray, Z: np.ndarray,
          evr: np.ndarray, n95: int, umap10: np.ndarray | None = None, progress=None) -> dict:
    y_idx = np.array([ACTIVITIES.index(a) for a in y])
    cum = np.cumsum(evr)
    L = lenses(Z, X, n95, cum, umap10)
    jobs = [(k, "kmeans") for k in L] + [(k, "dbscan") for k in ("full", "pca2")]
    machines = {}
    for i, (lens, sorter) in enumerate(jobs):
        if progress:
            progress(i / len(jobs), f"Running {L[lens]['short']} + {sorter}")
        r = run_machine(L[lens]["data"], y_idx, sorter, NOTEBOOK_EPS.get(lens), X=X)
        r.update(lens=lens, sorter=sorter)
        machines[f"{lens}|{sorter}"] = r

    sds = {k: v["data"].std(0) + 1e-9 for k, v in L.items() if k != "full"}

    def moment(r: int) -> dict:
        return dict(fp=np.round(np.clip(X[r], -3, 3), 1).tolist(),
                    lensVals={k: np.round(np.clip(L[k]["data"][r] / sd, -3, 3), 1).tolist()
                              for k, sd in sds.items()})

    subs = sorted(set(subject.tolist()))
    rng = np.random.default_rng(7)
    people = []
    for i, s in enumerate(subs):
        idx = np.where(subject == s)[0]
        rep = int(rng.choice(idx))
        people.append(dict(id=int(s), name=NAMES[i % len(NAMES)], idx=idx.tolist(), rep=rep, **moment(rep)))

    catalogue = {}
    for a in range(6):
        pool = np.where(y_idx == a)[0]
        picks = rng.choice(pool, size=min(10, len(pool)), replace=False)
        catalogue[a] = [dict(rec=int(r), **moment(int(r))) for r in picks]
    return dict(
        n=int(X.shape[0]), d=int(X.shape[1]), n95=int(n95), acts=ACTIVITIES,
        truth="".join(str(v) for v in y_idx),
        lenses={k: dict(label=v["label"], short=v["short"], dims=v["dims"], kept=v["kept"], code=v["code"])
                for k, v in L.items()},
        machines=machines, people=people, catalogue=catalogue,
        counts=np.bincount(y_idx, minlength=6).tolist(),
    )

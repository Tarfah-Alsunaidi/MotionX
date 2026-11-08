"""MotionX — the Streamlit app.

One link serves two screens: the big screen on the projector (the city game) and the
players' phones (/?join=1), which build a character and follow the story.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core.city import build
from core.classroom import LOOK_KEYS, get_room, join_url, qr_data_uri
from core.data import ensure_umap, get_bundle, load_embeddings, umap_available

# --------------------------------------------------------------------------- #
# Paths and page setup
# --------------------------------------------------------------------------- #
APP_DIR = Path(__file__).parent
WEB = APP_DIR / "web"
COMP_DIR = APP_DIR / ".component"
JOINING = "join" in st.query_params

st.set_page_config(page_title="MotionX", page_icon="❄️",
                   layout="centered" if JOINING else "wide", initial_sidebar_state="collapsed")


# --------------------------------------------------------------------------- #
# The game data: the notebook's pipeline, run once and cached
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="The MotionX market is training its machines on har.csv…")
def game(_b, bkey: str, has_umap: bool) -> tuple[dict, str]:
    emb = load_embeddings(_b) or {}
    data = build(_b.X, _b.y, _b.subject, _b.Z, _b.evr, _b.n95, umap10=emb.get("umap10"))
    return data, json.dumps(data, separators=(",", ":"))


def load_game():
    b = get_bundle()
    emb = load_embeddings(b) or {}
    if "umap10" not in emb and umap_available():
        with st.spinner("First start: polishing the store's UMAP lens (1–2 minutes, only once)…"):
            ensure_umap(b)
        emb = load_embeddings(b) or {}
    return game(b, b.key, "umap10" in emb)


# --------------------------------------------------------------------------- #
# Big screen
# --------------------------------------------------------------------------- #
def build_component(data_json: str) -> Path:
    COMP_DIR.mkdir(exist_ok=True)
    html = (WEB / "city.html").read_text(encoding="utf-8")
    html = html.replace("const D = __DATA__;", "const D = window.CITY_DATA;")
    html = html.replace("<script>", '<script src="data.js"></script>\n<script>', 1)
    assert 'src="data.js"' in html and "window.CITY_DATA" in html, "city.html layout changed: data.js not wired in"
    html = html.replace("</body>", '<script src="bridge.js"></script>\n</body>')
    music_dir, songs = WEB / "music", []
    if music_dir.is_dir():
        (COMP_DIR / "music").mkdir(exist_ok=True)
        for f in sorted(music_dir.iterdir()):
            if f.suffix.lower() in (".mp3", ".m4a", ".ogg", ".wav") and f.stat().st_size < 30_000_000:
                dest = COMP_DIR / "music" / f.name
                if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                    dest.write_bytes(f.read_bytes())
                songs.append("music/" + f.name)
    voice_dir, voices = WEB / "voices", {}
    if voice_dir.is_dir():
        (COMP_DIR / "voices").mkdir(exist_ok=True)
        for f in sorted(voice_dir.iterdir()):
            if f.suffix.lower() in (".mp3", ".m4a", ".ogg", ".wav") and f.stat().st_size < 10_000_000:
                dest = COMP_DIR / "voices" / f.name
                if not dest.exists() or dest.stat().st_size != f.stat().st_size:
                    dest.write_bytes(f.read_bytes())
                voices[f.stem] = "voices/" + f.name
    files = {"index.html": html,
             "data.js": "window.MUSIC_FILES=" + json.dumps(songs) + ";\nwindow.VOICE_FILES=" + json.dumps(voices)
                        + ";\nwindow.CITY_DATA=" + data_json + ";",
             "bridge.js": (WEB / "bridge.js").read_text(encoding="utf-8")}
    for name, text in files.items():
        p = COMP_DIR / name
        if not p.exists() or hashlib.md5(p.read_bytes()).hexdigest() != hashlib.md5(text.encode()).hexdigest():
            p.write_text(text, encoding="utf-8")
    return COMP_DIR


@st.fragment(run_every=1.5)
def live_city(city) -> None:
    room = get_room()
    url = room.url_override or join_url()
    ev = city(players=room.for_city(), answers=room.answer_summary(),
              join=dict(url=url, qr=qr_data_uri(url), count=len(room.players)),
              height=st.session_state.get("screen_h", 860), key="city", default=None)
    if st.session_state.get("presenter") and isinstance(ev, dict) and ev.get("t") != room.last_t:
        room.last_t = ev.get("t")
        room.set_act(ev.get("act", room.act), ev.get("machine"))


def presenter_pin() -> str:
    try:
        return str(st.secrets.get("PRESENTER_PIN", os.environ.get("PRESENTER_PIN", "561")))
    except Exception:
        return os.environ.get("PRESENTER_PIN", "561")


def big_screen() -> None:
    st.markdown("""<style>
header[data-testid="stHeader"], footer, [data-testid="stToolbar"], [data-testid="stSidebar"],
[data-testid="collapsedControl"] {display:none !important;}
.block-container {padding: 0 !important; max-width: 100% !important;}
iframe {display:block; border:0;}
div[data-testid="stExpander"] {margin: .4rem .8rem;}
</style>""", unsafe_allow_html=True)
    data, data_json = load_game()
    city = components.declare_component("storm_city", path=str(build_component(data_json)))
    room = get_room()

    live_city(city)

    with st.expander("Presenter settings"):
        st.slider("Game height (px), match your screen", 600, 1400, 860, 20, key="screen_h")
        if not st.session_state.get("presenter"):
            st.info("Enter the presenter PIN on the projector screen **before starting the story**: "
                    "only this screen controls what everyone's phones show.")
            pin = st.text_input("Presenter PIN", type="password")
            if pin and pin == presenter_pin():
                st.session_state["presenter"] = True
                st.rerun()
            elif pin:
                st.error("Wrong PIN")
            return
        room.url_override = st.text_input("Join link (only if the QR shows the wrong address)",
                                          room.url_override, placeholder=join_url())
        c3, c4 = st.columns(2)
        if c3.button("New game (remove everyone)"):
            room.wipe()
            st.rerun()
        page = (WEB / "city.html").read_text(encoding="utf-8").replace("__DATA__", data_json)
        c4.download_button("Standalone version (.html, no phones)", page, file_name="storm_city.html",
                           mime="text/html")
        st.caption(f"This screen controls the story · {len(room.players)} residents in the city · act {room.act}")
        if presenter_pin() == "561":
            st.warning("You're using the default PIN (561), which is written in the public code. "
                       "Set your own `PRESENTER_PIN` in the app's Secrets on Streamlit Cloud.")


# --------------------------------------------------------------------------- #
# Players' phones (Arabic by default, a small switch for English)
# --------------------------------------------------------------------------- #
def build_phone() -> Path:
    d = APP_DIR / ".phone"
    d.mkdir(exist_ok=True)
    html = (WEB / "phone.html").read_text(encoding="utf-8").replace("</body>", '<script src="bridge.js"></script>\n</body>')
    for name, text in {"index.html": html, "bridge.js": (WEB / "bridge.js").read_text(encoding="utf-8")}.items():
        p = d / name
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
    return d


def phone() -> None:
    st.markdown("""<style>
header[data-testid="stHeader"], footer, [data-testid="stToolbar"], [data-testid="stSidebar"] {display:none !important;}
html, body, [data-testid="stAppViewContainer"], .stApp {background:#1a1440 !important;}
.block-container {padding: 0 !important; max-width: 520px !important;}
iframe {display:block; border:0;}
</style>""", unsafe_allow_html=True)
    sid = st.session_state.get("sid") or st.query_params.get("me")
    if sid and sid in get_room().players:
        st.session_state["sid"] = sid
    comp = components.declare_component("motionx_phone", path=str(build_phone()))
    phone_live(comp)


@st.fragment(run_every=3)
def phone_live(comp) -> None:
    room = get_room()
    sid = st.session_state.get("sid")
    p = room.players.get(sid) if sid else None
    args = dict(joined=p is not None, act=room.act)
    if p:
        data, _ = load_game()
        args["me"] = dict(name=p["name"], act=p["act"], fixed=p.get("fixed"), confirmed=p.get("confirmed"),
                          look={k: p.get(k) for k in LOOK_KEYS})
        machine = data["machines"].get(room.machine) if room.machine else None
        if machine is None:
            args["pred"] = -2
        else:
            rec = data["catalogue"][p["act"]][p["k"] % len(data["catalogue"][p["act"]])]["rec"]
            ch = machine["pred"][rec]
            args["pred"] = -1 if ch == "x" else int(ch)
    if st.session_state.get("join_error"):
        args["error"] = st.session_state.pop("join_error")
    ev = comp(key="phone", default=None, **args)
    if not isinstance(ev, dict) or ev.get("n") == st.session_state.get("last_n"):
        return
    st.session_state["last_n"] = ev.get("n")
    kind = ev.get("type")
    if kind == "join" and not p:
        new_sid = room.add(str(ev.get("name", ""))[:16], ev.get("look") or {}, ev.get("act", 3))
        if new_sid is None:
            st.session_state["join_error"] = True
        else:
            st.session_state["sid"] = new_sid
            st.query_params["me"] = new_sid
    elif p and kind == "update" and room.act <= 1:
        look = ev.get("look") or {}
        room.update(sid, act=ev.get("act", p["act"]), **{k: look.get(k) for k in LOOK_KEYS if k in look})
    elif p and kind == "fix" and room.act in (2, 3, 4, 5):
        room.update(sid, fixed=bool(ev.get("fixed")))
    elif p and kind == "confirm" and room.act in (5, 6) and p.get("confirmed") is None:
        ok = bool(ev.get("ok"))
        room.update(sid, confirmed=ok, left=True)
        room.answer(sid, ok)
    try:
        st.rerun(scope="fragment")
    except Exception:
        pass


if JOINING:
    phone()
else:
    big_screen()

"""The shared room: everyone who joined from a phone, their character and place,
and which part of the story the big screen is on.
"""
from __future__ import annotations

import random
import re
import socket
import threading
import time
import uuid

import streamlit as st

# --------------------------------------------------------------------------- #
# Character options
# --------------------------------------------------------------------------- #
SKINS = {"1": "#FFDBAC", "2": "#F1C27D", "3": "#E0AC69", "4": "#C68642", "5": "#8D5524", "6": "#5C3A1E"}
STYLES = {"shmagh": ("شماغ", "Shmagh"), "hijab": ("حجاب", "Hijab"), "short": ("شعر قصير", "Short hair"),
          "long": ("شعر طويل", "Long hair")}
OUTFITS = {"thobe": ("ثوب", "Thobe"), "abaya": ("عباية", "Abaya"), "casual": ("كاجوال", "Casual")}
HAIRS = {"Black": "#1E1A17", "Brown": "#5A3A22", "Blonde": "#C9A15A", "Grey": "#9A9A9A",
         "Navy": "#2C3E70", "Beige": "#D8C3A5", "White": "#F7F3EE", "Red": "#C0392B"}
SHIRTS = {"Terracotta": "#C2410C", "Teal": "#2A9D8F", "Navy": "#355070", "Gold": "#D4A017",
          "Purple": "#6D3FA0", "Olive": "#6B705C", "Rose": "#B56576", "Sky": "#4EA8DE"}
COLOR_AR = {"Black": "أسود", "Brown": "بني", "Blonde": "أشقر", "Grey": "رمادي", "Navy": "كحلي", "Beige": "بيج",
            "White": "أبيض", "Red": "أحمر", "Terracotta": "طوبي", "Teal": "فيروزي", "Gold": "ذهبي", "Purple": "بنفسجي",
            "Olive": "زيتي", "Rose": "وردي", "Sky": "سماوي"}
# --------------------------------------------------------------------------- #
# Places in the city
# --------------------------------------------------------------------------- #
PLACES = {3: ("", ("MotionX coffee", "the café"), ("جالس", "sitting")),
          4: ("", ("طابور سوق النجوم", "the market queue"), ("واقف", "standing")),
          5: ("", ("حديقة الحي", "the park lawn"), ("منسدح", "lying down")),
          0: ("", ("الممشى", "the walkway"), ("تمشي", "walking")),
          1: ("", ("درج المجمع · طالع", "the mall stairs · up"), ("تطلع الدرج", "going upstairs")),
          2: ("", ("درج المجمع · نازل", "the mall stairs · down"), ("تنزل الدرج", "going downstairs"))}
WHITE = "#F4F1EA"
CLOTH = {"thobe": ("#F4F1EA", "#A3A7AD", "#7A5A3E", "#26232B"),
         "abaya": ("#1D1B22", "#2C3E70", "#5A3A2A", "#6B6F78", "#C9B79C", "#4A2B4F", "#F4F1EA", "#9B1B30", "#D98BA6"),
         "casual": tuple(SHIRTS.values()) + (WHITE,)}
TRIM_EXTRA = (WHITE, "#E9B44C")
OVERS = ("none", "sideri", "jacket", "farwa")
OVER_COLS = ("#2A2A33", "#5A3A22", "#355070", "#6B705C", "#7A1C26", "#C9B79C")
HATS = ("none", "cap", "beanie", "earmuffs")
HAT_COLS = (WHITE, "#1E1A17") + tuple(SHIRTS.values())
GLASSES = ("none", "sun", "med")
GEARS = ("none", "headset", "pad", "both")
GEAR_COLS = ("#8B5CF6", "#22D3EE", "#22C55E", "#EF4444", "#F4F1EA", "#1E1A17")
LOOK_KEYS = ("outfit", "style", "cloth", "hair", "skin", "shirt", "over", "overc", "scarf", "scarfc", "hat", "hatc", "glasses", "gear", "gearc")
ACT_NAMES = ["Walking", "Upstairs", "Downstairs", "Sitting", "Standing", "Lying down"]


# --------------------------------------------------------------------------- #
# The room
# --------------------------------------------------------------------------- #
class Classroom:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.players: dict[str, dict] = {}
        self.answers: dict[str, bool] = {}
        self.act = -1
        self.machine: str | None = None
        self.last_t = None
        self.url_override = ""

    MAX_PLAYERS = 80

    @staticmethod
    def clean_name(name: str) -> str:
        name = re.sub(r"[^\w\s\-.']", "", name, flags=re.UNICODE)
        return re.sub(r"\s+", " ", name).strip()[:16] or "Guest"

    @staticmethod
    def clean_look(look: dict) -> dict:
        look = look if isinstance(look, dict) else {}
        pick = lambda v, ok, d: v if v in ok else d
        out = pick(look.get("outfit"), OUTFITS, "casual")
        style = look.get("style")
        hat = pick(look.get("hat"), HATS, "none")
        if style == "cap":
            style = "short"
            hat = hat if look.get("hat") in HATS else "cap"
        heads = {"thobe": ("shmagh", "short"), "abaya": ("hijab",), "casual": ("short", "long")}[out]
        style = pick(style, heads, heads[0])
        if style in ("shmagh", "hijab") and hat in ("cap", "beanie"):
            hat = "none"
        gear = pick(look.get("gear"), GEARS, "none")
        if gear in ("headset", "both") and hat == "earmuffs":
            hat = "none"
        hair_ok = ("#F7F3EE", "#C0392B") if style == "shmagh" else tuple(HAIRS.values())
        trim_ok = tuple(SHIRTS.values()) + TRIM_EXTRA
        return dict(
            outfit=out, style=style,
            cloth=pick(look.get("cloth"), CLOTH[out], CLOTH[out][0]),
            hair=pick(look.get("hair"), hair_ok, hair_ok[0]),
            skin=pick(look.get("skin"), tuple(SKINS.values()), SKINS["3"]),
            shirt=pick(look.get("shirt"), trim_ok, SHIRTS["Terracotta"]),
            over=pick(look.get("over"), OVERS if out == "thobe" else ("none", "sideri", "jacket") if out == "casual" else ("none",), "none"),
            overc=pick(look.get("overc"), OVER_COLS, OVER_COLS[0]),
            scarf=look.get("scarf") is True if out == "casual" else False,
            scarfc=pick(look.get("scarfc"), trim_ok, "#C0392B"),
            hat=hat, hatc=pick(look.get("hatc"), HAT_COLS, HAT_COLS[0]),
            glasses=pick(look.get("glasses"), GLASSES, "none"),
            gear=gear, gearc=pick(look.get("gearc"), GEAR_COLS, GEAR_COLS[0]))

    def add(self, name: str, look: dict, act: int) -> str | None:
        sid = uuid.uuid4().hex[:10]
        look = self.clean_look(look)
        act = int(act) if str(act).lstrip("-").isdigit() and int(act) in PLACES else 3
        with self.lock:
            if len(self.players) >= self.MAX_PLAYERS:
                return None
            self.players[sid] = dict(name=self.clean_name(name), act=int(act), k=random.randrange(10),
                                     joined=time.time(), **look)
        return sid

    def update(self, sid: str, **fields) -> None:
        fields = {k: v for k, v in fields.items()
                  if k in ("act", "fixed", "left", "confirmed") + LOOK_KEYS}
        if any(k in fields for k in LOOK_KEYS):
            with self.lock:
                cur = dict(self.players.get(sid, {}))
            fields.update(self.clean_look({**cur, **{k: v for k, v in fields.items() if k in LOOK_KEYS}}))
        if "act" in fields and fields["act"] not in PLACES:
            fields.pop("act")
        with self.lock:
            if sid in self.players:
                if "act" in fields and fields["act"] != self.players[sid]["act"]:
                    fields["k"] = random.randrange(10)
                self.players[sid].update(fields)

    def answer(self, sid: str, ok: bool) -> None:
        with self.lock:
            self.answers[sid] = ok

    def for_city(self) -> list[dict]:
        return [dict(sid=s, name=p["name"], act=p["act"], k=p["k"], fixed=p.get("fixed") is True, left=bool(p.get("left")),
                     confirmed=p.get("confirmed"), **{k: p.get(k) for k in LOOK_KEYS})
                for s, p in list(self.players.items())]

    def set_act(self, act: int, machine: str | None) -> None:
        with self.lock:
            if act in (1, 2) and self.act != act:
                for p in self.players.values():
                    p.update(fixed=None, left=False, confirmed=None)
                self.answers.clear()
            self.act, self.machine = act, machine

    def answer_summary(self) -> dict:
        vals = list(self.answers.values())
        return dict(total=len(vals), yes=sum(vals), no=len(vals) - sum(vals))

    def wipe(self) -> None:
        with self.lock:
            self.players.clear(); self.answers.clear()
            self.act, self.machine, self.last_t = -1, None, None


# --------------------------------------------------------------------------- #
# Join link and QR code
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_room() -> Classroom:
    return Classroom()


def lan_url() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "localhost"
    port = st.get_option("server.port") or 8501
    return f"http://{ip}:{port}/?join=1"


def join_url() -> str:
    try:
        h = st.context.headers
        host = h.get("Host") or h.get("host") or ""
    except Exception:
        host = ""
    if host and host.split(":")[0] not in ("localhost", "127.0.0.1", "0.0.0.0"):
        proto = (h.get("X-Forwarded-Proto") or ("https" if ".streamlit.app" in host else "http")).split(",")[0].strip()
        return f"{proto}://{host}/?join=1"
    return lan_url()


def qr_data_uri(url: str) -> str | None:
    try:
        import base64
        import io

        import qrcode
        buf = io.BytesIO()
        qrcode.make(url, box_size=8, border=2).save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Character picture
# --------------------------------------------------------------------------- #
def avatar_svg(look: dict, size: int = 170) -> str:
    skin, hair, shirt, st_ = look["skin"], look["hair"], look["shirt"], look["style"]
    outfit = look.get("outfit", "casual")
    if st_ == "shmagh" and outfit != "thobe":
        st_ = "short"
    if st_ == "hijab" and outfit != "abaya":
        st_ = "long"
    cx, cy, r = 50, 44, 21
    back, front = "", ""
    if st_ == "hijab":
        back = (f"<ellipse cx='{cx}' cy='{cy}' rx='{r*1.2:.1f}' ry='{r*1.22:.1f}' fill='{hair}'/>"
                f"<path d='M{cx-r*1.1:.1f} {cy+r*0.3:.1f} Q{cx-r*1.35:.1f} {cy+r*1.25:.1f} {cx-r*0.9:.1f} {cy+r*1.45:.1f} L{cx+r*0.9:.1f} {cy+r*1.45:.1f} "
                f"Q{cx+r*1.35:.1f} {cy+r*1.25:.1f} {cx+r*1.1:.1f} {cy+r*0.3:.1f} Z' fill='{hair}'/>")
        face_c, face_r = (cx, cy + r * 0.1), r * 0.82
    elif st_ == "shmagh":
        cloth = "#FAF7F2"
        back = (f"<path d='M{cx-r*1.12:.1f} {cy+r*1.4:.1f} L{cx-r*1.15:.1f} {cy-r*0.2:.1f} Q{cx} {cy-r*1.55:.1f} {cx+r*1.15:.1f} {cy-r*0.2:.1f} "
                f"L{cx+r*1.12:.1f} {cy+r*1.4:.1f} Z' fill='{cloth}'/>")
        if hair == "#C0392B":
            cid = f"shm{abs(hash((skin, shirt, size))) % 99999}"
            back += (f"<clipPath id='{cid}'><path d='M{cx-r*1.12:.1f} {cy+r*1.4:.1f} L{cx-r*1.15:.1f} {cy-r*0.2:.1f} Q{cx} {cy-r*1.55:.1f} {cx+r*1.15:.1f} {cy-r*0.2:.1f} "
                     f"L{cx+r*1.12:.1f} {cy+r*1.4:.1f} Z'/></clipPath><g clip-path='url(#{cid})'>")
            back += "".join(f"<line x1='{cx-r*1.1+k*6:.1f}' y1='{cy-r*1.3:.1f}' x2='{cx-r*1.1+k*6:.1f}' y2='{cy+r*1.4:.1f}' stroke='#c82828' stroke-width='1.6' opacity='.8'/>" for k in range(8))
            back += "".join(f"<line x1='{cx-r*1.15:.1f}' y1='{cy-r*1.2+k*6:.1f}' x2='{cx+r*1.15:.1f}' y2='{cy-r*1.2+k*6:.1f}' stroke='#c82828' stroke-width='1.6' opacity='.8'/>" for k in range(10))
            back += "</g>"
        front = (f"<path d='M{cx-r*0.95:.1f} {cy:.1f} Q{cx} {cy-r*0.6:.1f} {cx+r*0.95:.1f} {cy:.1f} L{cx+r*0.95:.1f} {cy-r*0.5:.1f} Q{cx} {cy-r*1.2:.1f} {cx-r*0.95:.1f} {cy-r*0.5:.1f} Z' fill='{cloth}'/>"
                 f"<ellipse cx='{cx}' cy='{cy-r*0.72:.1f}' rx='{r*0.9:.1f}' ry='{r*0.2:.1f}' fill='none' stroke='#161616' stroke-width='3.4'/>")
        face_c, face_r = (cx, cy + r * 0.15), r * 0.84
    else:
        if st_ == "long":
            back = (f"<ellipse cx='{cx}' cy='{cy+r*0.05:.1f}' rx='{r*1.12:.1f}' ry='{r*1.1:.1f}' fill='{hair}'/>"
                    f"<rect x='{cx-r*1.12:.1f}' y='{cy-r*0.1:.1f}' width='{r*0.36:.1f}' height='{r*1.05:.1f}' rx='{r*0.18:.1f}' fill='{hair}'/>"
                    f"<rect x='{cx+r*0.76:.1f}' y='{cy-r*0.1:.1f}' width='{r*0.36:.1f}' height='{r*1.05:.1f}' rx='{r*0.18:.1f}' fill='{hair}'/>")
        front = f"<path d='M{cx-r*1.03:.1f} {cy-r*0.15:.1f} A{r*1.05:.1f} {r*1.05:.1f} 0 0 1 {cx+r*1.03:.1f} {cy-r*0.15:.1f} Q{cx} {cy-r*0.7:.1f} {cx-r*1.03:.1f} {cy-r*0.15:.1f} Z' fill='{hair}'/>"
        if st_ == "cap":
            front = (f"<path d='M{cx-r*1.06:.1f} {cy-r*0.15:.1f} A{r*1.06:.1f} {r*1.06:.1f} 0 0 1 {cx+r*1.06:.1f} {cy-r*0.15:.1f} Z' fill='{shirt}'/>"
                     f"<ellipse cx='{cx+r*0.45:.1f}' cy='{cy-r*0.17:.1f}' rx='{r*0.75:.1f}' ry='{r*0.16:.1f}' fill='{shirt}'/>")
        face_c, face_r = (cx, cy), r
    fx, fy = face_c
    ex, ey = face_r * 0.36, fy + face_r * 0.06
    face = (f"<ellipse cx='{fx}' cy='{fy:.1f}' rx='{face_r:.1f}' ry='{face_r*1.04:.1f}' fill='{skin}'/>"
            f"<ellipse cx='{fx-ex:.1f}' cy='{ey:.1f}' rx='{face_r*0.1:.1f}' ry='{face_r*0.14:.1f}' fill='#2b2622'/>"
            f"<ellipse cx='{fx+ex:.1f}' cy='{ey:.1f}' rx='{face_r*0.1:.1f}' ry='{face_r*0.14:.1f}' fill='#2b2622'/>"
            f"<circle cx='{fx-ex+0.8:.1f}' cy='{ey-1:.1f}' r='0.9' fill='#fff'/><circle cx='{fx+ex+0.8:.1f}' cy='{ey-1:.1f}' r='0.9' fill='#fff'/>"
            f"<ellipse cx='{fx-face_r*0.55:.1f}' cy='{fy+face_r*0.32:.1f}' rx='{face_r*0.15:.1f}' ry='{face_r*0.1:.1f}' fill='#ff7878' opacity='.35'/>"
            f"<ellipse cx='{fx+face_r*0.55:.1f}' cy='{fy+face_r*0.32:.1f}' rx='{face_r*0.15:.1f}' ry='{face_r*0.1:.1f}' fill='#ff7878' opacity='.35'/>"
            f"<path d='M{fx-face_r*0.2:.1f} {fy+face_r*0.32:.1f} Q{fx} {fy+face_r*0.5:.1f} {fx+face_r*0.2:.1f} {fy+face_r*0.32:.1f}' stroke='#2b2622' stroke-width='1.6' fill='none' stroke-linecap='round'/>")
    phone = "<rect x='65.5' y='86' width='7' height='11' rx='2' fill='#1d2b33'/><rect x='66.7' y='87.2' width='4.6' height='8.4' fill='#7CD7FF'/>"
    if outfit in ("thobe", "abaya"):
        cloth = "#F4F1EA" if outfit == "thobe" else "#1d1b22"
        line = (f"<line x1='50' y1='68' x2='50' y2='82' stroke='{shirt}' stroke-width='2'/>" if outfit == "thobe"
                else f"<line x1='50' y1='68' x2='50' y2='120' stroke='{shirt}' stroke-width='2.4'/>")
        body = (f"<path d='M38 70 Q50 64 62 70 L65 121 Q50 124 35 121 Z' fill='{cloth}'/>"
                f"<line x1='39' y1='73' x2='33' y2='96' stroke='{cloth}' stroke-width='6' stroke-linecap='round'/>"
                f"<line x1='61' y1='73' x2='68' y2='94' stroke='{cloth}' stroke-width='6' stroke-linecap='round'/>{line}"
                "<ellipse cx='42' cy='123' rx='6' ry='2.8' fill='#2a1d16'/><ellipse cx='58' cy='123' rx='6' ry='2.8' fill='#2a1d16'/>")
        if outfit == "thobe":
            body += ("<path d='M37 69 L46 69 L46 108 L35 108 Z' fill='#7a5230'/><path d='M54 69 L63 69 L65 108 L54 108 Z' fill='#7a5230'/>"
                     "<rect x='44.5' y='69' width='2' height='39' fill='#efe3cf'/><rect x='53.5' y='69' width='2' height='39' fill='#efe3cf'/>")
    else:
        body = ("<line x1='46' y1='100' x2='46' y2='121' stroke='#3a4252' stroke-width='6' stroke-linecap='round'/>"
                "<line x1='54' y1='100' x2='54' y2='121' stroke='#3a4252' stroke-width='6' stroke-linecap='round'/>"
                "<ellipse cx='43' cy='123' rx='6' ry='2.8' fill='#2a1d16'/><ellipse cx='57' cy='123' rx='6' ry='2.8' fill='#2a1d16'/>"
                f"<rect x='38' y='66' width='24' height='38' rx='10' fill='{shirt}'/>"
                f"<line x1='39' y1='72' x2='33' y2='96' stroke='{shirt}' stroke-width='5.5' stroke-linecap='round'/>"
                f"<line x1='61' y1='72' x2='68' y2='94' stroke='{shirt}' stroke-width='5.5' stroke-linecap='round'/>")
    if outfit == "casual" and st_ not in ("hijab",):
        body += f"<rect x='39' y='64' width='22' height='6' rx='3' fill='#c0392b'/><rect x='52' y='68' width='5' height='14' rx='2' fill='#c0392b'/>"
    hands = f"<circle cx='33' cy='97' r='3' fill='{skin}'/><circle cx='68' cy='95' r='3' fill='{skin}'/>"
    return f"""<svg viewBox='0 0 100 130' width='{size}' height='{size * 1.3:.0f}' style='display:block;margin:auto'>
<ellipse cx='50' cy='125' rx='22' ry='4.5' fill='rgba(0,0,0,.15)'/>
{body}{back}{face}{front}{hands}{phone}
</svg>"""

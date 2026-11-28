"""NA Developers - Wix Lead Bot (Windows app).

Build the .exe with BUILD_EXE.bat. Run from source with:  python gui.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, quote_plus

import ai
import audit as A
import calls as C
import outreach as O
import security as S
import updater as U
import website as WS
import wixbot as W

ASSETS = os.path.join(W.BUNDLED, "assets")
DB_PATH = os.path.join(W.HERE, "wixbot.sqlite")
CFG_PATH = os.path.join(W.HERE, "config.json")
OUT_DIR = os.path.join(W.HERE, "output")

NAVY, TEAL, RED = "#16212D", "#1E91A8", "#E8222B"
TEAL_DARK, RED_DARK = "#167487", "#C41A22"
GREEN, AMBER = "#1F9D55", "#F08C2E"
LEVEL_COLOR = {k: v[1] for k, v in W.LEVELS.items()}
THEMES = {
    "light": dict(BG="#F4F6F9", CARD="#FFFFFF", BORDER="#E3E8EF", MUTED="#6B7785", TEXT="#16212D",
                  SOFT="#F8FAFC", HOVER="#EEF6F8", ACTIVE="#E3F2F5", INFO="#F3FAFB", INFO_BORDER="#D5EBF0",
                  WARN_BG="#FDE7E8", TROUGH="#E9EEF3", TREE_HEAD="#F1F4F8", SEL="#CDEBF1", BTN="#EDF1F5",
                  BTN_HOVER="#E0E6ED", ACCENT_TXT=TEAL_DARK,
                  TINT={"super": "#FDECEC", "hot": "#FEF3E7", "normal": "#FFFFFF"}),
    "dark": dict(BG="#0E151D", CARD="#17212B", BORDER="#26323F", MUTED="#93A1B0", TEXT="#E6EDF3",
                 SOFT="#1C2733", HOVER="#1E2C38", ACTIVE="#123744", INFO="#152A33", INFO_BORDER="#1F4553",
                 WARN_BG="#3A1E22", TROUGH="#26323F", TREE_HEAD="#1C2733", SEL="#16495A", BTN="#24313E",
                 BTN_HOVER="#2E3D4C", ACCENT_TXT="#7FD3E6",
                 TINT={"super": "#3A1E23", "hot": "#382A1C", "normal": "#17212B"}),
}
THEME = "light"
BG = CARD = BORDER = MUTED = TEXT = SOFT = HOVER = ACTIVE = INFO = INFO_BORDER = ""
WARN_BG = TROUGH = TREE_HEAD = SEL = BTN = BTN_HOVER = ACCENT_TXT = ""
LEVEL_TINT: dict = {}


def apply_theme(name: str) -> None:
    global THEME, BG, CARD, BORDER, MUTED, TEXT, SOFT, HOVER, ACTIVE, INFO, INFO_BORDER
    global WARN_BG, TROUGH, TREE_HEAD, SEL, BTN, BTN_HOVER, ACCENT_TXT, LEVEL_TINT
    THEME = name if name in THEMES else "light"
    t = THEMES[THEME]
    (BG, CARD, BORDER, MUTED, TEXT, SOFT, HOVER, ACTIVE, INFO, INFO_BORDER, WARN_BG, TROUGH, TREE_HEAD,
     SEL, BTN, BTN_HOVER, ACCENT_TXT) = (t[k] for k in (
        "BG", "CARD", "BORDER", "MUTED", "TEXT", "SOFT", "HOVER", "ACTIVE", "INFO", "INFO_BORDER", "WARN_BG",
        "TROUGH", "TREE_HEAD", "SEL", "BTN", "BTN_HOVER", "ACCENT_TXT"))
    LEVEL_TINT = dict(t["TINT"])


apply_theme("light")
STATUS_COLOR = {"new": MUTED, "draft": "#7A5AF8", "emailed": TEAL, "replied": GREEN,
                "call_booked": GREEN, "proposal_sent": "#0E7490", "won": "#15803D",
                "lost": "#9CA3AF", "no_reply": "#9CA3AF", "later": AMBER, "unsubscribed": RED,
                "bounced": RED, "do_not_contact": RED}
FONT = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"

YP_TERMS = {
    "dentist": "dentists", "chiropractor_physio": "chiropractors",
    "medical_clinic_medspa": "medical spas", "hair_salon_barber": "hair salons",
    "beauty_nails_spa": "nail salons", "fitness_yoga": "yoga studios",
    "restaurant_cafe": "restaurants", "bakery_dessert": "bakeries",
    "home_services": "plumbers", "landscaping": "landscaping",
    "real_estate": "real estate agents", "lawyer": "attorneys", "accountant": "accountants",
    "insurance_finance": "insurance agents", "auto_services": "auto repair",
    "pet_services": "pet grooming", "photographer": "photographers",
    "events_wedding": "wedding planners", "church_nonprofit": "churches",
    "childcare_education": "child care", "boutique_retail": "boutiques",
    "hospitality": "bed and breakfast", "tattoo": "tattoo shops", "funeral": "funeral homes",
    "cleaning_movers": "house cleaning",
}


def F(size=10, weight="normal"):
    return (FONT, size, weight)


def open_url(url: str) -> None:
    if url:
        webbrowser.open(url if re.match(r"^https?://", url) else "http://" + url)


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------
def setup_style(root: tk.Tk) -> None:
    st = ttk.Style(root)
    st.theme_use("clam")
    import tkinter.font as tkfont
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT, size=10)
        except tk.TclError:
            pass
    root.configure(bg=BG)
    st.configure(".", background=BG, foreground=TEXT, font=F(10), bordercolor=BORDER,
                 lightcolor=BORDER, darkcolor=BORDER, troughcolor=TROUGH, focuscolor=TEAL)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=TEXT)
    st.configure("Card.TLabel", background=CARD, foreground=TEXT)
    st.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=F(9))
    st.configure("H1.TLabel", background=BG, foreground=TEXT, font=F(19, "bold"))
    st.configure("Sub.TLabel", background=BG, foreground=MUTED)
    st.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=F(11, "bold"))
    for w in ("TCheckbutton", "TRadiobutton"):
        st.configure(w, background=CARD, foreground=TEXT, indicatorbackground=CARD,
                     indicatorforeground=TEAL, upperbordercolor=BORDER, lowerbordercolor=BORDER)
        st.map(w, background=[("active", CARD)], indicatorbackground=[("selected", CARD)],
               indicatorforeground=[("selected", TEAL)])
    st.configure("TButton", padding=(12, 6), relief="flat", background=BTN, foreground=TEXT)
    st.map("TButton", background=[("active", BTN_HOVER)])
    st.configure("TMenubutton", background=BTN, foreground=TEXT, relief="flat", padding=(10, 6),
                 arrowcolor=MUTED)
    st.map("TMenubutton", background=[("active", BTN_HOVER)])
    st.configure("Treeview", rowheight=32, background=CARD, fieldbackground=CARD, foreground=TEXT,
                 bordercolor=BORDER, font=F(10), borderwidth=0)
    st.configure("Treeview.Heading", background=TREE_HEAD, font=F(9, "bold"), foreground=MUTED,
                 relief="flat", padding=(8, 7), bordercolor=BORDER)
    st.map("Treeview.Heading", background=[("active", TREE_HEAD)])
    st.map("Treeview", background=[("selected", SEL)], foreground=[("selected", TEXT)])
    for name, col in (("Teal", TEAL), ("Red", RED)):
        st.configure(f"{name}.Horizontal.TProgressbar", background=col, troughcolor="#2A3A4B",
                     bordercolor="#2A3A4B", lightcolor=col, darkcolor=col, thickness=8)
    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    # extra room on the right: on scaled Windows screens the text was cut off
    st.configure("TNotebook.Tab", padding=(14, 8, 24, 8), font=F(10), background=BG, foreground=MUTED,
                 bordercolor=BORDER)
    st.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])
    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=SOFT, foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                     darkcolor=BORDER, padding=6, insertcolor=TEXT, arrowcolor=MUTED, background=CARD)
        st.map(w, bordercolor=[("focus", TEAL)], lightcolor=[("focus", TEAL)],
               fieldbackground=[("readonly", SOFT)], foreground=[("readonly", TEXT)])
    for k, v in (("*Label.foreground", TEXT), ("*Text.background", SOFT), ("*Text.foreground", TEXT), ("*Text.insertBackground", TEXT),
                 ("*Text.selectBackground", SEL), ("*Text.selectForeground", TEXT),
                 ("*Listbox.background", CARD), ("*Listbox.foreground", TEXT),
                 ("*Menu.background", CARD), ("*Menu.foreground", TEXT),
                 ("*Menu.activeBackground", TEAL), ("*Menu.activeForeground", "#FFFFFF")):
        root.option_add(k, v)
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", TEAL)
    root.option_add("*TCombobox*Listbox.font", F(10))
    for sb in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        st.configure(sb, background=BTN, troughcolor=CARD, bordercolor=CARD, lightcolor=BTN,
                     darkcolor=BTN, arrowcolor=MUTED, gripcount=0, relief="flat")
        st.map(sb, background=[("active", BTN_HOVER)])
    st.configure("TPanedwindow", background=BG)
    st.configure("TSeparator", background=BORDER)


class Btn(tk.Canvas):
    """Rounded, modern button (drop-in for the simple ttk.Button uses in this app)."""
    KINDS = {"Primary.TButton": "primary", "Danger.TButton": "danger", "Dark.TButton": "dark",
             "Warn.TButton": "warn"}

    def __init__(self, parent, text="", command=None, style=None, state="normal", width=None, **kw):
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = BG
        super().__init__(parent, highlightthickness=0, bd=0, bg=pbg, cursor="hand2", height=34)
        import tkinter.font as tkfont
        self.kind = self.KINDS.get(style, "default")
        self.font = tkfont.Font(family=FONT, size=10, weight="normal" if self.kind == "default" else "bold")
        self._text, self._cmd, self._state, self._wchars, self._hover = text, command, state, width, False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Configure>", lambda e: self._draw(e.width))
        self._size()
        self._draw()

    def _colors(self):
        base = {"primary": (TEAL, TEAL_DARK, "#FFFFFF"), "danger": (RED, RED_DARK, "#FFFFFF"),
                "dark": (NAVY if THEME == "light" else "#2B3D50", "#24384C" if THEME == "light" else "#36506A", "#FFFFFF"),
                "warn": (AMBER, "#D9771F", "#FFFFFF"), "default": (BTN, BTN_HOVER, TEXT)}[self.kind]
        if self._state == "disabled":
            return (TROUGH, TROUGH, MUTED)
        return (base[1] if self._hover else base[0], None, base[2])

    def _size(self):
        w = self.font.measure(self._text) + 28
        if self._wchars:
            w = max(w, int(self._wchars * self.font.measure("0") + 24))
        super().configure(width=w)

    def _draw(self, width=None):
        self.delete("all")
        if width and width > 10:
            self._bw = width
        w = getattr(self, "_bw", 0) or (self.winfo_width() if self.winfo_width() > 10 else int(float(self.cget("width"))))
        h = max(34, self.winfo_height() if self.winfo_height() > 10 else 34)
        r = 8
        fill, _, fg = self._colors()
        pts = [r, 1, w - r, 1, w - 1, 1, w - 1, r, w - 1, h - r, w - 1, h - 1, w - r, h - 1, r, h - 1,
               1, h - 1, 1, h - r, 1, r, 1, 1]
        self.create_polygon(pts, smooth=True, fill=fill, outline=fill)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self.font)
        super().configure(cursor="arrow" if self._state == "disabled" else "hand2")

    def _set_hover(self, v):
        self._hover = v and self._state != "disabled"
        self._draw()

    def _click(self, e):
        if self._state != "disabled" and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    def invoke(self):
        if self._cmd and self._state != "disabled":
            return self._cmd()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        changed = False
        for key, attr in (("text", "_text"), ("state", "_state"), ("command", "_cmd")):
            if key in kw:
                setattr(self, attr, kw.pop(key))
                changed = True
        if "style" in kw:
            self.kind = self.KINDS.get(kw.pop("style"), "default")
            changed = True
        if kw:
            super().configure(**kw)
        if changed:
            self._size()
            self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)


def card(parent, title: str | None = None, sub: str | None = None, pad=14):
    outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=BORDER)
    inner = tk.Frame(outer, bg=CARD)
    inner.pack(fill="both", expand=True, padx=pad, pady=pad)
    if title:
        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w")
    if sub:
        ttk.Label(inner, text=sub, style="Muted.TLabel", wraplength=300,
                  justify="left").pack(anchor="w", pady=(2, 8))
    outer.inner = inner
    return outer


def badge(parent, text, color, bg=None):
    return tk.Label(parent, text=f" {text} ", bg=color, fg="white", font=F(9, "bold"),
                    padx=6, pady=1)


def link(parent, text, url, bg=None, size=10):
    lb = tk.Label(parent, text=text, fg=ACCENT_TXT, bg=bg or CARD, cursor="hand2", font=F(size, "underline"),
                  anchor="w", justify="left")
    lb.bind("<Button-1>", lambda e: open_url(url))
    return lb


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=None):
        bg = bg or CARD
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, bg=bg)
        self.win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


def make_tree(parent, cols: list[tuple[str, str, int]], height=12):
    frame = tk.Frame(parent, bg=CARD)
    tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings",
                        height=height, selectmode="extended")
    for key, label, width in cols:
        tree.heading(key, text=label, command=lambda k=key: sort_tree(tree, k))
        tree.column(key, width=width, anchor="w", stretch=key == cols[1][0])
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    for lvl, tint in LEVEL_TINT.items():
        tree.tag_configure(lvl, background=tint)
    return frame, tree


def sort_tree(tree, col):
    rows = [(tree.set(k, col), k) for k in tree.get_children("")]
    rev = getattr(tree, "_rev", {}).get(col, False)

    def key(v):
        s = v[0].replace(",", "")
        try:
            return (0, float(s))
        except ValueError:
            return (1, s.lower())
    rows.sort(key=key, reverse=rev)
    for i, (_, k) in enumerate(rows):
        tree.move(k, "", i)
    tree._rev = {**getattr(tree, "_rev", {}), col: not rev}


def short_label(label: str) -> str:
    return label.split(" (")[0]


def marketing_text(m) -> str:
    """Short badge text for what marketing a business already pays for."""
    items = [x.strip() for x in (m or "").split(";") if x.strip()]
    ads = [x.replace(" Pixel", "").replace("Google Ads", "Google") for x in items if x in W.ADS_LABELS]
    if ads:
        return "$ Ads: " + ", ".join(ads)
    if "Google Analytics" in items or "Tag Manager" in items:
        return "Analytics"
    return "—"


def level_text(level: str) -> str:
    return "● " + W.LEVELS[level][0]


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = S.Config(CFG_PATH)
        self.cats = W.load_categories()
        self.q: queue.Queue = queue.Queue()
        self.db: W.DB | None = None
        self.job: threading.Thread | None = None
        self.job_kind = ""
        self.inbox = None
        self.images = {}
        self.yp_proc = None
        self.session_captured = []
        root.title(f"NA Developers · Wix Lead Bot {W.VERSION}")
        apply_theme(self.cfg.get("theme", "light"))
        root.configure(bg=BG)
        root.geometry("1340x860")
        root.minsize(1180, 740)
        self._load_images()
        setup_style(root)
        self.login_frame = None
        self.main_frame = None
        self.show_login()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def toggle_theme(self):
        new = "dark" if THEME == "light" else "light"
        self.cfg.set("theme", new)
        self.cfg.save()
        apply_theme(new)
        current = self.current or "dashboard"
        self.main_frame.destroy()
        self.main_frame = None
        setup_style(self.root)
        self._load_images()
        self.build_main()
        self.show(current)

    def _load_images(self):
        suffix = "_dark" if THEME == "dark" else "_t"
        for name in ("logo_sidebar", "logo_login", "mark64"):
            img = None
            for cand in ((name + suffix) if name != "mark64" else name, name):
                try:
                    img = tk.PhotoImage(file=os.path.join(ASSETS, cand + ".png"))
                    break
                except tk.TclError:
                    continue
            self.images[name] = img
        if self.images.get("mark64"):
            self.root.iconphoto(True, self.images["mark64"])
        ico = os.path.join(ASSETS, "icon.ico")
        if sys.platform.startswith("win") and os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
            except tk.TclError:
                pass

    # ---------------- login / password ----------------
    def show_login(self):
        if self.main_frame:
            self.main_frame.pack_forget()
        f = self.login_frame = tk.Frame(self.root, bg=BG)
        f.pack(fill="both", expand=True)
        box = card(f, pad=34)
        box.place(relx=0.5, rely=0.47, anchor="center")
        b = box.inner
        if self.images.get("logo_login"):
            tk.Label(b, image=self.images["logo_login"], bg=CARD).pack(pady=(0, 18))
        first = not S.has_password(self.cfg)
        ttk.Label(b, text="Create your app password" if first else "Welcome back",
                  style="CardTitle.TLabel", font=F(15, "bold")).pack()
        ttk.Label(b, text=("This password locks the app and encrypts your saved email "
                           "password.\nThere's no way to recover it, so keep it safe."
                           if first else "Enter your password to unlock Wix Lead Bot."),
                  style="Muted.TLabel", justify="center").pack(pady=(4, 16))
        pw1, pw2 = tk.StringVar(), tk.StringVar()
        ttk.Label(b, text="Password", style="Card.TLabel").pack(anchor="w")
        e1 = ttk.Entry(b, textvariable=pw1, show="•", width=34, font=F(11))
        e1.pack(fill="x", pady=(2, 10))
        if first:
            ttk.Label(b, text="Type it again", style="Card.TLabel").pack(anchor="w")
            ttk.Entry(b, textvariable=pw2, show="•", width=34, font=F(11)).pack(fill="x", pady=(2, 10))
        msg = tk.Label(b, text="", fg=RED, bg=CARD, font=F(9))
        msg.pack()
        tries = {"n": 0, "until": 0.0}

        def go(_=None):
            if time.time() < tries["until"]:
                msg.config(text=f"Too many tries. Wait {int(tries['until'] - time.time())}s.")
                return
            if first:
                prob = S.password_problem(pw1.get())
                if prob:
                    return msg.config(text=prob)
                if pw1.get() != pw2.get():
                    return msg.config(text="The two passwords don't match.")
                S.set_password(self.cfg, pw1.get())
            elif not S.check_password(self.cfg, pw1.get()):
                tries["n"] += 1
                if tries["n"] >= 5:
                    tries["until"] = time.time() + 30 * (tries["n"] - 4)
                pw1.set("")
                return msg.config(text="Wrong password.")
            f.destroy()
            self.login_frame = None
            self.open_main()

        showv = tk.BooleanVar(value=False)
        opts = tk.Frame(b, bg=CARD)
        opts.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(opts, text="Show password", variable=showv,
                        command=lambda: e1.config(show="" if showv.get() else "•")).pack(side="left")
        caps = tk.Label(opts, text="", bg=CARD, fg=AMBER, font=F(9, "bold"))
        caps.pack(side="right")

        def caps_check(e):
            try:
                caps.config(text="⇪ Caps Lock is on" if e.state & 0x2 else "")
            except Exception:
                pass
        e1.bind("<KeyRelease>", caps_check, add="+")
        ub = Btn(b, text="Create password and start  →" if first else "🔓  Unlock",
                 style="Primary.TButton", command=go)
        ub.pack(fill="x", pady=(12, 0), ipady=4)
        f.bind_all("<Return>", go)
        f.bind("<Destroy>", lambda e: e.widget is f and self.root.unbind_all("<Return>"))
        e1.focus_set()
        self.root.after(200, lambda: e1.winfo_exists() and e1.focus_force())

    def lock(self):
        if self.job and self.job.is_alive():
            if not messagebox.askyesno("Lock", "A job is running. It will keep running while "
                                       "locked. Lock now?"):
                return
        S.lock()
        self.show_login()

    def open_main(self):
        if self.main_frame:
            self.main_frame.pack(fill="both", expand=True)
            self.refresh_page()
            return
        self.db = W.DB(DB_PATH)
        O.init(self.db)
        A.init(self.db)
        ai.init(self.db)
        try:
            O.backup(DB_PATH)
        except Exception:
            pass
        try:   # keep a current copy of the Chrome helper next to the app
            import shutil
            src = os.path.join(W.BUNDLED, "chrome-extension")
            if os.path.isdir(src) and os.path.abspath(src) != os.path.abspath(os.path.join(W.HERE, "chrome-helper")):
                shutil.copytree(src, os.path.join(W.HERE, "chrome-helper"), dirs_exist_ok=True)
        except Exception:
            pass
        W.LOG_HOOK = lambda m: self.q.put(("log", m))
        W.PROGRESS_HOOK = lambda d: self.q.put(("prog", d))
        self.inbox = W.start_inbox(DB_PATH, lambda new, total, items:
                                   self.q.put(("captured", new, total, items)))
        self.build_main()
        self.root.after(150, self.poll)
        self.root.after(1500, self.startup_tasks)

    def check_updates(self, manual=False):
        def go():
            try:
                self.q.put(("update", U.check(), manual))
            except Exception as e:
                self.q.put(("update", None, manual and str(e)))
        threading.Thread(target=go, daemon=True).start()

    def on_update(self, info, manual):
        if not info:
            if manual:
                messagebox.showinfo("Updates", manual if isinstance(manual, str) else
                                    ("You have the latest version." if U.enabled()
                                     else "Online updates are not set up yet."))
            return
        self.update_info = info
        self.update_bar.config(text=f"  ⬆  Update available: v{W.VERSION} → v{info['version']}   ")
        self.update_frame.pack(side="top", fill="x", before=self.pages_host)

    def install_update(self):
        info = getattr(self, "update_info", None)
        if not info:
            return
        if not U.can_self_update():
            webbrowser.open(f"https://github.com/{W.UPDATE_REPO}/releases/latest")
            return
        notes = info["notes"][:600]
        if not messagebox.askyesno("Update", f"Install v{info['version']} now? The app will "
                                   f"restart. Your leads and settings stay.\n\n{notes}"):
            return

        def fn():
            U.download_and_restart(info, lambda d, tot: W.progress(
                phase="update", done=d // 1048576, total=max(1, tot // 1048576),
                label="Downloading update (MB)"))
            return True
        self.run_job("Updating", fn, after=lambda ok: ok and self.root.after(300, self.quit_for_update))

    def quit_for_update(self):
        if self.inbox:
            self.inbox.shutdown()
        self.root.destroy()

    def startup_tasks(self):
        self.check_updates()
        out = dict(self.cfg.get("outreach", {}) or {})
        if not out.get("_send_anytime_v1"):          # you asked to email at any time
            out["business_hours_only"] = False
            out["_send_anytime_v1"] = True
            self.cfg.set("outreach", out)
            self.cfg.save()
        if not self.db.get_kv("netfail_fix_v1", ""):
            try:
                r = O.fix_network_failures(self.db)
                if r["to_draft"] or r["duplicates"]:
                    self.toast(f"{r['to_draft']} emails that failed because the internet dropped are back in "
                               f"'Waiting for approval'" + (f"; {r['duplicates']} duplicates removed" if r["duplicates"] else ""))
            except Exception:
                pass
            self.db.set_kv("netfail_fix_v1", "1")
        if not self.db.get_kv("campaigns_v1", ""):
            # emails written before campaigns existed: keep them visible as one campaign
            rows = self.db.q("SELECT id FROM messages WHERE campaign_id IS NULL")
            if rows:
                cid = O.new_campaign(self.db, "Earlier emails")
                O.tag_campaign(self.db, cid, [r[0] for r in rows])
            self.db.set_kv("campaigns_v1", "1")
        O.ON_WON = self._won_to_site
        self.root.after(4000, self.website_tick)
        self.root.after(90 * 1000, self.autopilot_tick)
        self.root.after(3000, self.badge_tick)
        self.root.after(2 * 60 * 1000, self.leftovers_tick)
        self.root.after(30 * 1000, self.marketing_tick)
        try:
            n = O.create_due_followups(self.db, self.cfg)
            if n:
                self.toast(f"{n} follow-up email{'s' if n > 1 else ''} ready for your approval")
        except Exception:
            pass

    def contact_dialog(self, domains=None):
        """One click: write, approve and send first emails, to the leads you picked
        (domains) or to all Super + Hot leads."""
        s = O.settings(self.cfg)
        picked, reasons = None, {}
        if domains:
            recs = {r["domain"]: r for r in self.db.lead_records()}
            picked = [d for d in domains if d in recs and not O.can_contact(self.db, recs[d])]
            for d in domains:
                why = O.can_contact(self.db, recs[d]) if d in recs else "not a lead"
                if why:
                    reasons[why] = reasons.get(why, 0) + 1
            waiting = len(picked)
        else:
            waiting = O.leads_to_contact(self.db)
        lim = O.daily_limit(self.db, self.cfg)
        room = max(0, lim - O.sent_today(self.db) - len(O.messages(self.db, "approved")))
        win = tk.Toplevel(self.root)
        title = (f"Email {len(domains)} selected lead{'s' if len(domains) != 1 else ''}" if domains
                 else "Contact Super + Hot leads")
        win.title(title)
        win.configure(bg=CARD)
        win.transient(self.root)
        win.grab_set()
        f = tk.Frame(win, bg=CARD)
        f.pack(padx=22, pady=18)
        tk.Label(f, text=title, bg=CARD, fg=TEXT, font=F(13, "bold")).pack(anchor="w")
        if domains:
            head = f"{waiting} of them can be emailed now." + "".join(
                f"\n  · {n} skipped: {why}" for why, n in reasons.items()) + "\n"
        else:
            head = f"{waiting} Super/Hot leads with an email haven't been contacted yet.\n"
        backlog = len(O.messages(self.db, "approved"))
        if backlog:
            head += f"{backlog} approved emails are already waiting to go out first.\n"
        tk.Label(f, text=(head +
                          f"Today you can send {room} more (today's limit {lim}{' while warming up to ' + str(s['daily_limit']) if lim < int(s['daily_limit']) else ''}). The rest go "
                          "on the next days."), bg=CARD, fg=MUTED, font=F(10),
                 justify="left").pack(anchor="w", pady=(4, 12))
        tk.Label(f, text="Who writes the emails?", bg=CARD, fg=TEXT, font=F(10, "bold")).pack(anchor="w")
        writer = tk.StringVar(value="ai" if ai.enabled(self.cfg) else "tpl")
        ttk.Radiobutton(f, text="Gemini: a personal email per business from its audit (about 1 min each)",
                        value="ai", variable=writer,
                        state="normal" if ai.enabled(self.cfg) else "disabled").pack(anchor="w")
        ttk.Radiobutton(f, text="Templates: instant, still filled with each business's own problems",
                        value="tpl", variable=writer).pack(anchor="w", pady=(0, 10))
        tk.Label(f, text="Campaign name", bg=CARD, fg=TEXT, font=F(10, "bold")).pack(anchor="w")
        regions = sorted({(r.get("region") or "") for r in self.db.lead_records()
                          if domains and r["domain"] in set(domains)} - {""})
        default = (", ".join(regions[:2]) + " · " if regions else ("Super + Hot · " if not domains else "")) \
            + dt.date.today().strftime("%d %b")
        cname = tk.StringVar(value=default)
        ttk.Entry(f, textvariable=cname, width=46).pack(anchor="w", pady=(2, 4))
        tk.Label(f, text="Next: the app writes the emails, shows them to you in one window, "
                         "and you click Send once.", bg=CARD, fg=MUTED, font=F(9)).pack(anchor="w")
        mode = tk.StringVar(value="check")
        auto = tk.BooleanVar(value=bool(s.get("autopilot")) and not domains)
        if not domains:
            ttk.Checkbutton(f, text="Autopilot: do this every day until everyone is contacted, and send their "
                            "follow-ups too (while the app is open)", variable=auto).pack(anchor="w", pady=(10, 0))
        bb = tk.Frame(f, bg=CARD)
        bb.pack(fill="x", pady=(16, 0))

        def start():
            use_ai = writer.get() == "ai"
            send = mode.get() == "send" or auto.get()
            on = bool(auto.get())
            if not domains:
                out = dict(self.cfg.get("outreach", {}) or {})
                out["autopilot"] = on
                out["autopilot_ai"] = use_ai
                self.cfg.set("outreach", out)
                self.cfg.save()
            win.destroy()
            if on:
                self.db.set_kv("autopilot_last", dt.date.today().isoformat())
            key = S.get_secret(self.cfg, "psi_key")

            cid = O.new_campaign(self.db, cname.get().strip() or default)

            def done(res):
                if not res:
                    return
                if not send:
                    if res.get("ids"):
                        self.review_batch(cid)
                    else:
                        self.toast("No emails were written (nothing left to contact).")
                    self.refresh_page()
                    return
                if send:
                    left = res.get("queued", 0)
                    self.toast(f"{res['sent']} sent." + (f" {left} more go out on your next send (daily limit)."
                                                         if left else "")
                               + (f" {res['later']} more will be written on the next days." if res.get("later")
                                  else "")
                               + (" Autopilot continues tomorrow." if on else ""), GREEN)
                    self.refresh_page()
                else:
                    self.toast(f"{res['drafted']} emails ready. Check them, click Approve all, then Send approved.")
                    self.show("outreach", view="draft")
            if domains:
                self.run_job("Contacting leads",
                             lambda: O.contact_leads(self.db, self.cfg, picked, use_ai, send, key, campaign_id=cid), after=done)
            else:
                self.run_job("Contacting leads", lambda: O.contact_today(self.db, self.cfg, use_ai, send, key, campaign_id=cid),
                             after=done)
        Btn(bb, text="Write emails  →", style="Primary.TButton", command=start).pack(side="right")
        Btn(bb, text="Cancel", command=win.destroy).pack(side="right", padx=8)
        if not waiting:
            tk.Label(f, text="Nothing to send: " + ("none of these can be emailed." if domains
                                                    else "find more leads first."), bg=CARD, fg=RED,
                     font=F(9, "bold")).pack(anchor="w")
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

    def review_batch(self, cid: int):
        """One window: every email of this campaign, tick/untick, edit, then ONE Send."""
        ms = [m for m in O.campaign_messages(self.db, cid) if m["status"] in ("draft", "approved", "failed")]
        if not ms:
            return self.toast("Nothing waiting in this campaign.")
        name = (self.db.q("SELECT name FROM campaigns WHERE id=?", (cid,)) or [("Campaign",)])[0][0]
        names = {r["domain"]: (r["name"] or r["domain"]) for r in self.db.lead_records()}
        win = tk.Toplevel(self.root)
        win.title(f"Review and send · {name}")
        win.configure(bg=BG)
        win.geometry("1100x680")
        win.transient(self.root)
        top = tk.Frame(win, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(top, text=name, bg=BG, fg=TEXT, font=F(14, "bold")).pack(anchor="w")
        info = tk.Label(top, bg=BG, fg=MUTED, font=F(10), anchor="w", justify="left")
        info.pack(anchor="w")
        mid = tk.Frame(win, bg=BG)
        mid.pack(fill="both", expand=True, padx=16)
        lc = card(mid, pad=8)
        lc.pack(side="left", fill="both", expand=True)
        fr, tree = make_tree(lc.inner, [("on", "Send", 50), ("biz", "Business", 210), ("to", "To", 220)],
                             height=20)
        fr.pack(fill="both", expand=True)
        rc = card(mid, pad=12)
        rc.pack(side="left", fill="both", expand=True, padx=(12, 0))
        to_v, subj_v = tk.StringVar(), tk.StringVar()
        for lab, var in (("To", to_v), ("Subject", subj_v)):
            r = tk.Frame(rc.inner, bg=CARD)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=lab, bg=CARD, fg=MUTED, width=8, anchor="w").pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True)
        body = tk.Text(rc.inner, wrap="word", font=F(10), relief="flat", padx=10, pady=8,
                       highlightthickness=1, highlightbackground=BORDER)
        body.pack(fill="both", expand=True, pady=(6, 0))
        on = {m["id"]: True for m in ms}
        byid = {m["id"]: m for m in ms}
        cur = [None]

        def save_cur():
            m = byid.get(cur[0])
            if not m:
                return
            m.update(to_addr=to_v.get().strip(), subject=subj_v.get().strip(), body=body.get("1.0", "end").rstrip())
            O.update_message(self.db, m["id"], to_addr=m["to_addr"], subject=m["subject"], body=m["body"])

        def update_info():
            n = sum(on.values())
            room = max(0, O.daily_limit(self.db, self.cfg) - O.sent_today(self.db))
            today = min(n, room)
            info.config(text=f"{len(ms)} emails written. {n} ticked to send.  "
                             f"{today} go out now (1–2 minutes apart)"
                             + (f", the other {n - today} go out by themselves on the next days "
                                "(daily limit), while the app is open." if n > today else "."))
            send_btn.config(text=f"📤  Send {n} email{'s' if n != 1 else ''}", state="normal" if n else "disabled")

        def load(e=None):
            i = tree.focus()
            if not i:
                return
            save_cur()
            m = byid[int(i)]
            cur[0] = m["id"]
            to_v.set(m["to_addr"]); subj_v.set(m["subject"])
            body.delete("1.0", "end"); body.insert("1.0", m["body"])

        def toggle(e):
            i = tree.identify_row(e.y)
            if i and tree.identify_column(e.x) == "#1":
                on[int(i)] = not on[int(i)]
                tree.set(i, "on", "☑" if on[int(i)] else "☐")
                update_info()

        for m in ms:
            tree.insert("", "end", iid=str(m["id"]), values=("☑", names.get(m["domain"], m["domain"]), m["to_addr"]))
        tree.bind("<<TreeviewSelect>>", load)
        tree.bind("<Button-1>", toggle, add="+")
        bb = tk.Frame(win, bg=BG)
        bb.pack(fill="x", padx=16, pady=12)

        def set_all(v):
            for k in on:
                on[k] = v
                tree.set(str(k), "on", "☑" if v else "☐")
            update_info()

        Btn(bb, text="Tick all", command=lambda: set_all(True)).pack(side="left")
        Btn(bb, text="Untick all", command=lambda: set_all(False)).pack(side="left", padx=6)
        Btn(bb, text="👁  Preview design", command=lambda: (save_cur(), cur[0] and self._preview_msg(cur[0]))).pack(side="left")

        def later():
            save_cur()
            win.destroy()
            self.toast("Saved. Open Outreach → Campaigns to send them later.")
            self.refresh_page()

        def send():
            save_cur()
            ids = [k for k, v in on.items() if v]
            bad = [byid[k]["to_addr"] for k in ids
                   if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", byid[k]["to_addr"] or "")]
            if bad:
                return messagebox.showwarning("Email", "These addresses don't look right:\n" + "\n".join(bad), parent=win)
            if not S.get_secret(self.cfg, "smtp_password"):
                return messagebox.showwarning("Email", "Connect your email first: Settings > Email account.", parent=win)
            win.destroy()
            self.run_job("Sending emails", lambda: O.send_now(self.db, self.cfg, ids),
                         after=lambda r: r and (self.toast(f"{name}: {r['sent']} sent" + (
                             f", {r['waiting']} go out on the next days." if r["waiting"] else "."), GREEN),
                             self.refresh_page()))
            self.toast(f"Sending {len(ids)} emails in the background. Watch them in Outreach → Campaigns.")

        send_btn = Btn(bb, text="📤  Send", style="Primary.TButton", command=send)
        send_btn.pack(side="right")
        Btn(bb, text="Save for later", command=later).pack(side="right", padx=8)
        kids = tree.get_children()
        if kids:
            tree.selection_set(kids[0]); tree.focus(kids[0]); load()
        update_info()

    def _preview_msg(self, mid):
        try:
            p = self.pages.get("outreach")
            if p:
                p.refresh(select=mid)
                p.preview()
        except Exception as e:
            self.toast(f"Preview failed: {e}")

    def leftovers_tick(self):
        """Emails you clicked Send on that didn't fit yesterday's limit go out today."""
        try:
            if (S.get_secret(self.cfg, "smtp_password") and "Sending emails" not in self.side_jobs
                    and self.db.q("SELECT 1 FROM messages WHERE status='approved' AND auto_send=1 LIMIT 1")
                    and O.daily_limit(self.db, self.cfg) - O.sent_today(self.db) > 0):
                self.run_job("Sending emails", lambda: O.send_leftovers(self.db, self.cfg),
                             after=lambda n: n and self.toast(f"{n} waiting campaign emails sent", GREEN))
        except Exception:
            pass
        self.root.after(30 * 60 * 1000, self.leftovers_tick)

    def badge_tick(self):
        """Little count bubbles in the sidebar: drafts waiting / approved to send, and new replies."""
        try:
            b = getattr(self, "nav_badges", {})
            d = self.db.q("SELECT COUNT(*) FROM messages WHERE status='draft'")[0][0]
            a = self.db.q("SELECT COUNT(*) FROM messages WHERE status='approved'")[0][0]
            r = self.db.q("SELECT COUNT(*) FROM replies WHERE kind NOT IN ('spam','inquiry') "
                          "AND COALESCE(handled,0)=0")[0][0]
            for key, n, col in (("outreach", d + a, TEAL), ("inbox", r, RED)):
                w = b.get(key)
                if not w:
                    continue
                if n:
                    w.config(text=str(n), bg=col)
                    w.pack(side="right", padx=(0, 10))
                else:
                    w.pack_forget()
        except Exception:
            pass
        self.root.after(15000, self.badge_tick)

    def autopilot_tick(self):
        """Once a day while the app is open, if you turned Autopilot on."""
        s = O.settings(self.cfg)
        today = dt.date.today().isoformat()
        if (s.get("autopilot") and self.db.get_kv("autopilot_last", "") != today
                and S.get_secret(self.cfg, "smtp_password")):
            self.db.set_kv("autopilot_last", today)
            key = S.get_secret(self.cfg, "psi_key")
            self.run_job("Autopilot", lambda: O.autopilot_day(self.db, self.cfg, key),
                         after=lambda r: r and self.toast(f"Autopilot: {r['sent']} emails sent today", GREEN))
        self.root.after(60 * 60 * 1000, self.autopilot_tick)

    def _won_to_site(self, domain):
        if WS.enabled(self.cfg) and WS.settings(self.cfg)["won_projects"]:
            def go():
                try:
                    WS.won_project(self.db, self.cfg, domain)
                    self.q.put(("toast", "Draft project added on your website (Projects > Drafts)"))
                except Exception as e:
                    self.q.put(("log", f"Couldn't add the project to your website: {e}"))
            threading.Thread(target=go, daemon=True).start()

    def marketing_tick(self):
        """Older leads were found before ads/pixel detection: check a few at a time in the background."""
        if not getattr(self, "_mk_running", False):
            rows = self.db.q("SELECT domain, final_url FROM sites WHERE is_wix=1 AND marketing IS NULL "
                             "AND final_url IS NOT NULL LIMIT 15")
            if rows:
                self._mk_running = True

                def go():
                    import requests
                    try:
                        for dom, url in rows:
                            try:
                                r = requests.get(url, timeout=15, headers={"User-Agent": W.USER_AGENT})
                                found = "; ".join(W.detect_marketing(r.text))
                            except Exception:
                                found = ""
                            self.db.x("UPDATE sites SET marketing=? WHERE domain=?", (found, dom))
                    finally:
                        self._mk_running = False
                threading.Thread(target=go, daemon=True).start()
        self.root.after(3 * 60 * 1000, self.marketing_tick)

    def website_tick(self):
        """Every 5 minutes: who opened their review, new website inquiries."""
        if WS.enabled(self.cfg) and not getattr(self, "_ws_busy", False):
            self._ws_busy = True

            def go():
                try:
                    res = WS.run_background(self.db, self.cfg)
                    names = {r["domain"]: (r["name"] or r["domain"]) for r in
                             self.db.lead_records("s.domain IN (%s)" % ",".join("?" * len(res["views"])),
                                                  [v["domain"] for v in res["views"]])} if res["views"] else {}
                    for v in res["views"][:3]:
                        self.q.put(("toast", f"🔥 {names.get(v['domain'], v['domain'])} is looking at their free "
                                             f"review ({v['views']} view{'s' if v['views'] != 1 else ''}). Follow up today.",
                                    RED))
                    if res["inquiries"]:
                        self.q.put(("toast", f"{res['inquiries']} new inquir{'y' if res['inquiries'] == 1 else 'ies'} "
                                             "from your website. See Outreach > Replies."))
                    if res.get("error"):
                        self.q.put(("log", "Website: " + res["error"]))
                finally:
                    self._ws_busy = False
            threading.Thread(target=go, daemon=True).start()
        self.root.after(5 * 60 * 1000, self.website_tick)

    # ---------------- main layout ----------------
    def build_main(self):
        self.current = None
        m = self.main_frame = tk.Frame(self.root, bg=BG)
        m.pack(fill="both", expand=True)
        side = tk.Frame(m, bg=CARD, width=236, highlightthickness=1, highlightbackground=BORDER)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        if self.images.get("logo_sidebar"):
            tk.Label(side, image=self.images["logo_sidebar"], bg=CARD).pack(pady=(22, 4), padx=12)
        tk.Label(side, text="WIX LEAD BOT", bg=CARD, fg=MUTED, font=F(8, "bold")).pack(pady=(0, 18))
        self.nav = {}
        items = [("dashboard", "⌂", "Dashboard"), ("find", "⌕", "Find leads"),
                 ("yp", "☰", "Yellow Pages"), ("leads", "★", "Leads"),
                 ("outreach", "✉", "Outreach"), ("calls", "☏", "Calls"), ("inbox", "⇩", "Inbox"),
                 ("pipeline", "▤", "Pipeline"),
                 ("coverage", "▦", "Coverage"), ("settings", "⚙", "Settings")]
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(0, 10))
        for key, icon, text in items:
            row = tk.Frame(side, bg=CARD, cursor="hand2")
            row.pack(fill="x", padx=12, pady=2)
            bar = tk.Frame(row, bg=CARD, width=4)
            bar.pack(side="left", fill="y")
            ic = tk.Label(row, text=icon, bg=CARD, fg=MUTED, font=F(13), width=2, cursor="hand2")
            ic.pack(side="left", padx=(12, 4), pady=8)
            lb = tk.Label(row, text=text, bg=CARD, fg=TEXT, font=F(11), anchor="w", cursor="hand2")
            lb.pack(side="left", fill="x", expand=True)
            badge = tk.Label(row, text="", bg=CARD, fg="white", font=F(8, "bold"), padx=6)
            if key in ("outreach", "inbox"):
                self.nav_badges = getattr(self, "nav_badges", {})
                self.nav_badges[key] = badge
            for w in (row, ic, lb):
                w.bind("<Button-1>", lambda e, k=key: self.show(k))
                w.bind("<Enter>", lambda e, k=key: self._nav_hover(k, True))
                w.bind("<Leave>", lambda e, k=key: self._nav_hover(k, False))
            self.nav[key] = (row, bar, ic, lb)
        bottom = tk.Frame(side, bg=CARD)
        bottom.pack(side="bottom", fill="x", pady=14, padx=16)
        self.inbox_lbl = tk.Label(bottom, bg=CARD, fg=MUTED, font=F(8), justify="left", anchor="w")
        self.inbox_lbl.pack(fill="x")
        self.inbox_lbl.config(text=("● Capture inbox on" if self.inbox else
                                    "● Capture inbox off (port busy)"),
                              fg=GREEN if self.inbox else RED)
        Btn(bottom, text="⬆  Check for updates",
            command=lambda: self.check_updates(True)).pack(fill="x", pady=(8, 0))
        rowb = tk.Frame(bottom, bg=CARD)
        rowb.pack(fill="x", pady=(6, 0))
        Btn(rowb, text="☀  Light" if THEME == "dark" else "☾  Dark", command=self.toggle_theme).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        Btn(rowb, text="🔒  Lock", command=self.lock).pack(side="left", fill="x", expand=True, padx=(3, 0))
        tk.Label(bottom, text=f"v{W.VERSION} · nadevelopers.com", bg=CARD, fg=MUTED,
                 font=F(8)).pack(pady=(8, 0))

        right = tk.Frame(m, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.build_jobbar(right)
        self.update_frame = tk.Frame(right, bg=TEAL)
        self.update_bar = tk.Label(self.update_frame, bg=TEAL, fg="white", font=F(10, "bold"), pady=8)
        self.update_bar.pack(side="left", padx=12)
        Btn(self.update_frame, text="Update now", style="Dark.TButton",
                   command=self.install_update).pack(side="left", pady=6)
        tk.Label(self.update_frame, text="Later", bg=TEAL, fg="white", cursor="hand2",
                 font=F(9, "underline")).pack(side="left", padx=12)
        self.update_frame.winfo_children()[-1].bind("<Button-1>", lambda e: self.update_frame.pack_forget())
        self.pages_host = tk.Frame(right, bg=BG)
        self.pages_host.pack(fill="both", expand=True, padx=22, pady=(16, 8))
        self.pages = {
            "dashboard": DashboardPage(self), "find": FindPage(self), "yp": YPPage(self),
            "leads": LeadsPage(self), "outreach": OutreachPage(self), "inbox": InboxPage(self),
            "calls": CallsPage(self),
            "pipeline": PipelinePage(self), "coverage": CoveragePage(self),
            "settings": SettingsPage(self),
        }
        self.current = None
        self.show("dashboard")

    def _nav_hover(self, key, on):
        if key == self.current:
            return
        row, bar, ic, lb = self.nav[key]
        for w in (row, ic, lb):
            w.config(bg=HOVER if on else CARD)
        bar.config(bg=HOVER if on else CARD)

    def show(self, key, **kw):
        for k, (row, bar, ic, lb) in self.nav.items():
            on = k == key
            for w in (row, ic, lb):
                w.config(bg=ACTIVE if on else CARD)
            bar.config(bg=TEAL if on else CARD)
            ic.config(fg=ACCENT_TXT if on else MUTED)
            lb.config(fg=ACCENT_TXT if on else TEXT, font=F(11, "bold") if on else F(11))
        for p in self.pages.values():
            p.frame.pack_forget()
        self.current = key
        page = self.pages[key]
        page.frame.pack(fill="both", expand=True)
        page.refresh(**kw)

    def refresh_page(self):
        if self.current:
            self.pages[self.current].refresh()

    def open_profile(self, domain):
        self.show("leads", select=domain)

    def toast(self, text, color=TEAL):
        t = tk.Label(self.root, text="  " + text + "  ", bg=color, fg="white", font=F(10, "bold"),
                     pady=8)
        t.place(relx=0.5, rely=0.02, anchor="n")
        self.root.after(3500, t.destroy)

    # ---------------- job bar (progress + pause/resume/stop) ----------------
    def build_jobbar(self, parent):
        bar = self.jobbar = tk.Frame(parent, bg=NAVY)
        bar.pack(side="bottom", fill="x")
        left = tk.Frame(bar, bg=NAVY)
        left.pack(side="left", fill="both", expand=True, padx=18, pady=10)
        self.job_title = tk.Label(left, text="Ready", bg=NAVY, fg="white", font=F(10, "bold"),
                                  anchor="w")
        self.job_title.pack(fill="x")
        row = tk.Frame(left, bg=NAVY)
        row.pack(fill="x", pady=(5, 0))
        self.pb_all = ttk.Progressbar(row, style="Teal.Horizontal.TProgressbar", maximum=100)
        self.pb_all.pack(side="left", fill="x", expand=True)
        self.job_pct = tk.Label(row, text="", bg=NAVY, fg="white", font=F(9, "bold"), width=6)
        self.job_pct.pack(side="left")
        self.job_detail = tk.Label(left, text="Pick what to search on the Find leads page.",
                                   bg=NAVY, fg="#AFC0CF", font=F(9), anchor="w")
        self.job_detail.pack(fill="x", pady=(4, 0))
        srow = tk.Frame(left, bg=NAVY)
        srow.pack(fill="x")
        self.job_side = tk.Label(srow, text="", bg=NAVY, fg="#7FD3E6", font=F(9), anchor="w")
        self.job_side.pack(side="left")
        self.side_stop = tk.Label(srow, text="", bg=NAVY, fg="#FFB4B7", font=F(9, "underline"), cursor="hand2")
        self.side_stop.pack(side="left", padx=10)
        self.side_stop.bind("<Button-1>", lambda e: self.stop_sending())
        self.side_jobs = []
        btns = tk.Frame(bar, bg=NAVY)
        btns.pack(side="right", padx=18)
        self.btn_pause = Btn(btns, text="⏸  Pause", style="Warn.TButton",
                                    command=self.toggle_pause, state="disabled", width=11)
        self.btn_pause.pack(side="left", padx=4)
        self.btn_stop = Btn(btns, text="■  Stop", style="Danger.TButton",
                                   command=self.stop_job, state="disabled", width=9)
        self.btn_stop.pack(side="left", padx=4)
        self.prog = {}

    SEARCH_JOBS = ("Finding leads", "wixsite.com hunt", "Checking your list", "Checking Yellow Pages websites")

    BACKGROUND_JOBS = ("Sending emails", "Contacting leads", "Autopilot")

    def run_job(self, kind: str, fn, after=None):
        if kind in self.BACKGROUND_JOBS:
            W.SEND_STOP.clear()
            return self.run_side(kind, fn, after)     # sending waits for US hours: keep the bar for searches
        if self.job and self.job.is_alive():
            if kind in self.SEARCH_JOBS and self.job_kind in self.SEARCH_JOBS:
                messagebox.showinfo("Busy", "A search is already running. You can keep using the rest of the "
                                    "app; start the next search when this one finishes.")
                return False
            return self.run_side(kind, fn, after)
        W.STOP.clear()
        W.PAUSE.clear()
        self.job_kind = kind
        self.prog = {"t0": time.time(), "phase_t0": time.time(), "phase": None}
        self.job_title.config(text=f"{kind}…")
        self.job_detail.config(text="Starting…")
        self.pb_all.config(mode="determinate", value=0)
        self.job_pct.config(text="0%")
        self.btn_pause.config(state="normal", text="⏸  Pause")
        self.btn_stop.config(state="normal")
        self.job_after = after

        def target():
            try:
                res = fn()
                self.q.put(("done", kind, res, None))
            except Exception as e:  # report any failure in the UI
                self.q.put(("done", kind, None, e))
        self.job = threading.Thread(target=target, daemon=True)
        self.job.start()
        return True

    def run_side(self, kind: str, fn, after=None):
        """Run a task next to the search: the search keeps going, the app stays usable."""
        self.side_jobs.append(kind)
        self._side_label()

        def target():
            W.SIDE.on = True
            try:
                res, err = fn(), None
            except Exception as e:
                res, err = None, e
            self.q.put(("side_done", kind, res, err, after))
        threading.Thread(target=target, daemon=True).start()
        self.toast(f"{kind} started. The search keeps running.")
        return True

    def _side_label(self):
        extra = W.SEND_STATUS["text"]
        self.job_side.config(text=("Also running: " + ", ".join(self.side_jobs)
                                   + (f" — {extra}" if extra else "")) if self.side_jobs else "")
        sending = any(k in self.BACKGROUND_JOBS for k in self.side_jobs)
        self.side_stop.config(text="■ Stop sending" if sending else "")

    def stop_sending(self):
        W.SEND_STOP.set()
        self.side_stop.config(text="stopping…")
        self.toast("Sending stops after the current email. Unsent emails stay approved for later.", AMBER)

    def side_finished(self, kind, res, err, after):
        if kind in self.side_jobs:
            self.side_jobs.remove(kind)
        self._side_label()
        if err:
            self.log(f"\nPROBLEM ({kind}): {err}")
            messagebox.showerror(kind, str(err))
        else:
            self.toast(f"{kind} finished", GREEN)
            if after:
                try:
                    after(res)
                except Exception:
                    pass
        if self.current != "find":
            self.refresh_page()

    def toggle_pause(self):
        if W.PAUSE.is_set():
            W.PAUSE.clear()
            self.btn_pause.config(text="⏸  Pause")
            self.job_title.config(text=f"{self.job_kind}…")
            self.prog["phase_t0"] += time.time() - self.prog.pop("paused_at", time.time())
        else:
            W.PAUSE.set()
            self.btn_pause.config(text="▶  Resume")
            self.job_title.config(text=f"{self.job_kind} — paused")
            self.prog["paused_at"] = time.time()

    def stop_job(self):
        W.STOP.set()
        W.PAUSE.clear()
        self.job_title.config(text=f"{self.job_kind} — stopping (finishing current sites)…")
        self.btn_pause.config(state="disabled")

    def on_progress(self, d):
        p = self.prog
        phase = d.get("phase")
        done, total = d.get("done", 0), d.get("total", 0)
        if phase == "pages" or (phase == "check" and self.job_kind == "wixsite.com hunt" and done % 20 == 0):
            self.pages["find"].update_hunt()
        if phase == "step":
            p["steps"] = (done, total)
            p["step_label"] = d.get("label", "")
        else:
            if phase != p.get("phase") or done < p.get("last_done", 0):
                p["phase_t0"] = time.time()
            p["phase"], p["last_done"] = phase, done
            p["detail"] = (done, total, d.get("label", ""), d.get("wix"))
        steps_done, steps_total = p.get("steps", (0, 0))
        dd, dt_, dlabel, wix = p.get("detail", (0, 0, "", None))
        if steps_total:
            frac = (steps_done + (dd / dt_ if dt_ else 0)) / steps_total
            frac = min(frac, 1)
        elif dt_:
            frac = dd / dt_
        else:
            frac = None
        if frac is None:
            if str(self.pb_all.cget("mode")) != "indeterminate":
                self.pb_all.config(mode="indeterminate")
                self.pb_all.start(12)
            self.job_pct.config(text="")
        else:
            if str(self.pb_all.cget("mode")) == "indeterminate":
                self.pb_all.stop()
                self.pb_all.config(mode="determinate")
            self.pb_all.config(value=frac * 100)
            self.job_pct.config(text=f"{frac * 100:.0f}%")
        parts = []
        if steps_total:
            parts.append(f"Search {min(steps_done + 1, steps_total)} of {steps_total}")
        if p.get("step_label"):
            parts.append(p["step_label"])
        if dt_:
            parts.append(f"{dd:,}/{dt_:,} {'sites' if p.get('phase') == 'check' else ''}".strip())
            el = time.time() - p["phase_t0"]
            if dd > 3 and el > 5 and not W.PAUSE.is_set():
                rem = (dt_ - dd) * el / dd
                parts.append("about " + (f"{rem / 60:.0f} min" if rem > 90 else f"{rem:.0f} s") + " left")
        elif dlabel and dlabel != p.get("step_label"):
            parts.append(dlabel)
        if wix is not None:
            parts.append(f"{wix} on Wix")
        self.job_detail.config(text="  ·  ".join(parts))

    def job_finished(self, kind, res, err):
        self.pb_all.stop()
        self.pb_all.config(mode="determinate")
        self.btn_pause.config(state="disabled", text="⏸  Pause")
        self.btn_stop.config(state="disabled")
        stopped = W.STOP.is_set()
        W.PAUSE.clear()
        if err:
            self.job_title.config(text=f"{kind} — problem")
            self.job_detail.config(text=str(err)[:160])
            self.log(f"\nPROBLEM: {err}")
            messagebox.showerror(kind, str(err))
        else:
            self.pb_all.config(value=100 if not stopped else self.pb_all.cget("value"))
            self.job_pct.config(text="" if stopped else "100%")
            self.job_title.config(text=f"{kind} — {'stopped' if stopped else 'finished'}")
            if self.job_detail.cget("text") == "Starting…":
                self.job_detail.config(text="Done." if not stopped else "Stopped.")
            self.toast(f"{kind} {'stopped' if stopped else 'finished'}",
                       AMBER if stopped else GREEN)
        if getattr(self, "job_after", None):
            try:
                self.job_after(res)
            except Exception:
                pass
        self.refresh_page()

    def log(self, msg):
        self.pages["find"].append_log(msg)

    # ---------------- queue pump ----------------
    def poll(self):
        if self.side_jobs and getattr(self, "_last_side_text", None) != W.SEND_STATUS["text"]:
            self._last_side_text = W.SEND_STATUS["text"]
            self._side_label()
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1])
                elif kind == "prog":
                    self.on_progress(item[1])
                elif kind == "done":
                    self.job_finished(*item[1:])
                elif kind == "side_done":
                    self.side_finished(*item[1:])
                elif kind == "captured":
                    self.pages["yp"].on_captured(*item[1:])
                elif kind == "update":
                    self.on_update(item[1], item[2])
                elif kind == "toast":
                    self.toast(*item[1:])
                elif kind == "call":
                    item[1]()
                elif kind == "image":
                    self.pages["leads"].profile.set_image(*item[1:])
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def on_close(self):
        if self.job and self.job.is_alive():
            if not messagebox.askyesno("Quit", "A job is still running. Quit anyway?"):
                return
            W.STOP.set()
        if self.yp_proc and self.yp_proc.poll() is None:
            try:
                self.yp_proc.terminate()
            except Exception:
                pass
        if self.inbox:
            self.inbox.shutdown()
        self.root.destroy()


class Page:
    title = ""
    subtitle = ""

    def __init__(self, app: App):
        self.app = app
        self.frame = tk.Frame(app.pages_host, bg=BG)
        head = tk.Frame(self.frame, bg=BG)
        head.pack(fill="x", pady=(0, 12))
        ttk.Label(head, text=self.title, style="H1.TLabel").pack(side="left")
        ttk.Label(head, text="   " + self.subtitle, style="Sub.TLabel").pack(side="left", pady=(8, 0))
        self.head = head
        self.body = tk.Frame(self.frame, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.build()

    @property
    def db(self):
        return self.app.db

    def build(self):
        pass

    def refresh(self, **kw):
        pass


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardPage(Page):
    title = "Dashboard"
    subtitle = "Your lead machine at a glance"

    STATS = [("biz", "Businesses found", NAVY, "⌕"), ("wix", "Wix websites", TEAL, "◆"),
             ("super", "Super leads", RED, "★"), ("hot", "Hot leads", AMBER, "▲"),
             ("emailed", "Emailed", "#7A5AF8", "✉"), ("replied", "Replied", GREEN, "↩"),
             ("won", "Won", "#15803D", "✓")]

    def build(self):
        # --- welcome banner + next best step
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x")
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)
        nbg = "#0A1016" if THEME == "dark" else NAVY
        ban = tk.Frame(top, bg=nbg)
        ban.grid(row=0, column=0, sticky="nsew")
        tk.Frame(ban, bg=TEAL, height=4).pack(side="bottom", fill="x")
        bi = tk.Frame(ban, bg=nbg)
        bi.pack(fill="both", expand=True, padx=20, pady=14)
        self.hello = tk.Label(bi, bg=nbg, fg="white", font=F(15, "bold"), anchor="w")
        self.hello.pack(anchor="w")
        self.today = tk.Label(bi, bg=nbg, fg="#C9D3DD", font=F(10), anchor="w", justify="left")
        self.today.pack(anchor="w", pady=(4, 10))
        bb = tk.Frame(bi, bg=nbg)
        bb.pack(anchor="w")
        Btn(bb, text="✉  Open outreach", style="Primary.TButton",
            command=lambda: self.app.show("outreach")).pack(side="left")
        Btn(bb, text="⌕  Find leads", command=lambda: self.app.show("find")).pack(side="left", padx=8)
        nxt = tk.Frame(top, bg=INFO, highlightthickness=1, highlightbackground=INFO_BORDER)
        nxt.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        ni = tk.Frame(nxt, bg=INFO)
        ni.pack(fill="both", expand=True, padx=18, pady=14)
        tk.Label(ni, text="NEXT BEST STEP", bg=INFO, fg=ACCENT_TXT, font=F(8, "bold")).pack(anchor="w")
        self.next_lbl = tk.Label(ni, bg=INFO, fg=TEXT, font=F(11, "bold"), anchor="w", justify="left",
                                 wraplength=360)
        self.next_lbl.pack(anchor="w", pady=(4, 10))
        self.next_btn = Btn(ni, text="Go", style="Dark.TButton")
        self.next_btn.pack(anchor="w")

        # --- stat cards with round icons
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        self.stats = {}
        for i, (key, label, col, glyph) in enumerate(self.STATS):
            if col == NAVY and THEME == "dark":
                col = "#5B7088"
            c = card(row, pad=10)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            row.columnconfigure(i, weight=1)
            line = tk.Frame(c.inner, bg=CARD)
            line.pack(fill="x")
            ic = tk.Canvas(line, width=38, height=38, bg=CARD, highlightthickness=0)
            ic.pack(side="right")
            ic.create_oval(2, 2, 36, 36, fill=col, outline=col)
            ic.create_text(19, 19, text=glyph, fill="white", font=F(13, "bold"))
            v = tk.Label(line, text="0", bg=CARD, fg=col, font=F(19, "bold"))
            v.pack(side="left", anchor="w")
            tk.Label(c.inner, text=label, bg=CARD, fg=MUTED, font=F(9)).pack(anchor="w")
            self.stats[key] = v

        # --- map | tabs (best leads, replies, results) | to do
        mid = tk.Frame(self.body, bg=BG)
        mid.pack(fill="both", expand=True, pady=(12, 0))
        right = tk.Frame(mid, bg=BG, width=250)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)
        mp = card(mid, "Leads on the map", pad=12)
        mp.pack(side="left", fill="y")
        self.map = tk.Canvas(mp.inner, width=290, height=213, bg=CARD, highlightthickness=0)
        self.map.pack()
        self.map_info = tk.Label(mp.inner, bg=CARD, fg=MUTED, font=F(8), anchor="w", justify="left")
        self.map_info.pack(anchor="w", pady=(6, 0))
        tk.Label(mp.inner, text="TOP AREAS", bg=CARD, fg=MUTED, font=F(8, "bold")).pack(anchor="w", pady=(10, 2))
        self.top_box = tk.Frame(mp.inner, bg=CARD)
        self.top_box.pack(fill="x")
        self._map_img = None
        tabs = card(mid, pad=10)
        tabs.pack(side="left", fill="both", expand=True, padx=(12, 0))
        nb = ttk.Notebook(tabs.inner)
        nb.pack(fill="both", expand=True)
        t1 = tk.Frame(nb, bg=CARD)
        nb.add(t1, text=" Best leads ")
        fr, self.tree = make_tree(t1, [("level", "Level", 85), ("name", "Business", 170),
                                       ("loc", "Location", 130), ("score", "Score", 60),
                                       ("mk", "Marketing", 110)], height=10)
        fr.pack(fill="both", expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", lambda e: self.app.open_profile(self.tree.focus()))
        t2 = tk.Frame(nb, bg=CARD)
        nb.add(t2, text=" Replies ")
        fr3, self.rep_tree = make_tree(t2, [("when", "When", 90), ("name", "From", 200),
                                           ("kind", "Type", 100), ("text", "Message", 300)], height=10)
        fr3.pack(fill="both", expand=True, pady=(6, 0))
        self.rep_tree.bind("<Double-1>", lambda e: self.app.show("outreach", view="replies"))
        t3 = tk.Frame(nb, bg=CARD)
        nb.add(t3, text=" By category ")
        fr2, self.res_tree = make_tree(t3, [("cat", "Category", 200), ("em", "Emailed", 75),
                                            ("rep", "Replied", 75), ("rr", "Reply %", 70),
                                            ("bk", "Calls", 60), ("won", "Won", 60)], height=10)
        fr2.pack(fill="both", expand=True, pady=(6, 0))
        todo = card(right, "To do")
        todo.pack(fill="both", expand=True)
        self.todo_box = tk.Frame(todo.inner, bg=CARD)
        self.todo_box.pack(fill="both", expand=True)

    # ---------------- map ----------------
    def draw_map(self, recs):
        cv = self.map
        cv.delete("all")
        try:
            with open(os.path.join(ASSETS, "na_map.json"), encoding="utf-8") as f:
                meta = json.load(f)
            from PIL import Image, ImageTk
            im = Image.open(os.path.join(ASSETS, f"na_map_{'dark' if THEME == 'dark' else 'light'}.png"))
        except Exception:
            cv.create_text(180, 130, text="Map not available", fill=MUTED)
            return
        w, h = 290, int(290 * im.height / im.width)
        cv.config(width=w, height=h)
        self._map_img = ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))
        cv.create_image(0, 0, image=self._map_img, anchor="nw")
        by = {}
        for r in recs:
            code = r.get("region") or ""
            if code in W.REGIONS:
                d = by.setdefault(code, [0, 0])
                d[0] += 1
                d[1] += r["level"] == "super"
        cent = meta.get("centroids", {})
        biggest = max([v[0] for v in by.values()] or [1])
        other = 0
        for code, (n, sup) in sorted(by.items(), key=lambda kv: -kv[1][0]):
            pos = cent.get(W.REGIONS[code])
            if not pos:
                other += n
                continue
            x, y = pos[0] * w, pos[1] * h
            rad = 7 + 11 * (n / biggest) ** 0.5
            x = min(max(x, rad + 2), w - rad - 2)       # keep big circles inside the map
            y = min(max(y, rad + 2), h - rad - 2)
            col = RED if sup else TEAL
            tag = f"r_{code}"
            cv.create_oval(x - rad, y - rad, x + rad, y + rad, fill=col, outline="white", width=2, tags=(tag,))
            cv.create_text(x, y, text=str(n) if n < 1000 else f"{n // 1000}k", fill="white",
                           font=F(8 if n < 100 else 7, "bold"), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>", lambda e, c=code: self.app.show("leads", region=c))
            cv.tag_bind(tag, "<Enter>", lambda e, c=code, n=n, s=sup: self.map_info.config(
                text=f"{W.REGIONS[c]}: {n} Wix lead{'s' if n != 1 else ''}, {s} Super"))
            cv.tag_bind(tag, "<Leave>", lambda e: self.map_info.config(text=self._map_hint))
            cv.config(cursor="hand2")
        self._map_hint = ("Click a circle to see those leads.\n● red = has Super leads  ● teal = others" if by else
                          "Your leads will appear here after your first search.")
        if other:
            self._map_hint += f"\n{other} more in Alaska/Hawaii/territories"
        self.map_info.config(text=self._map_hint)
        for w in self.top_box.winfo_children():
            w.destroy()
        for code, (n, sup) in sorted(by.items(), key=lambda kv: (-kv[1][1], -kv[1][0]))[:5]:
            r = tk.Frame(self.top_box, bg=CARD, cursor="hand2")
            r.pack(fill="x", pady=1)
            a = tk.Label(r, text=W.REGIONS[code], bg=CARD, fg=TEXT, font=F(9, "bold"), cursor="hand2")
            a.pack(side="left")
            b = tk.Label(r, text=f"{n} leads · {sup} Super", bg=CARD, fg=RED if sup else MUTED, font=F(9),
                         cursor="hand2")
            b.pack(side="right")
            for w in (r, a, b):
                w.bind("<Button-1>", lambda e, c=code: self.app.show("leads", region=c))

    def refresh(self, **kw):
        db = self.db
        O.fix_draft_status(db)
        recs = db.lead_records()
        c = O.counts(db)
        lv = {"super": 0, "hot": 0, "normal": 0}
        for r in recs:
            lv[r["level"]] += 1
        vals = {"biz": db.q("SELECT COUNT(DISTINCT domain) FROM businesses")[0][0],
                "wix": len(recs), "super": lv["super"], "hot": lv["hot"],
                "emailed": c["emailed"] + c["replied"] + c["call_booked"] + c["proposal_sent"]
                + c["won"] + c["lost"] + c["no_reply"],
                "replied": c["replied"] + c["call_booked"] + c["proposal_sent"] + c["won"],
                "won": c["won"]}
        for k, v in vals.items():
            self.stats[k].config(text=f"{v:,}")
        s = O.settings(self.app.cfg)
        hour = dt.datetime.now().hour
        part = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
        self.hello.config(text=f"Good {part}, {(s.get('sender_name') or 'there').split()[0]}")
        self.today.config(text=(f"✉  Sent today {c['_sent_today']} of {O.daily_limit(db, self.app.cfg)}     "
                                f"✎  {c['_drafts']} drafts to check     ✓  {c['_approved']} approved     "
                                f"↩  {c['replied']} replies to answer"))
        status = {d: st for d, st in db.q("SELECT domain, status FROM outreach")}
        fresh = [r for r in recs if status.get(r["domain"], "new") == "new"]
        rank = {"super": 0, "hot": 1, "normal": 2}
        fresh.sort(key=lambda r: (rank.get(r["level"], 3), -(r["score"] or 0)))
        fresh_super = sum(r["level"] == "super" for r in fresh)
        nrep = db.q("SELECT COUNT(*) FROM replies r JOIN outreach o ON o.domain=r.domain WHERE r.handled=0"
                    " AND r.kind IN ('interested','question','other') AND o.status IN ('replied','later')")[0][0]
        if nrep:
            step, cmd, btn = (f"{nrep} repl{'y is' if nrep == 1 else 'ies are'} waiting for an answer.",
                              lambda: self.app.show("outreach", view="replies"), "Answer replies")
        elif c["_drafts"]:
            step, cmd, btn = (f"{c['_drafts']} emails are drafted. Check and approve them.",
                              lambda: self.app.show("outreach"), "Review drafts")
        elif fresh_super:
            step, cmd, btn = (f"{fresh_super} Super leads haven't been emailed yet. Contact them in one click.",
                              self.app.contact_dialog, "Contact Super + Hot")
        elif not recs:
            step, cmd, btn = ("Start by finding Wix websites in a state and category.",
                              lambda: self.app.show("find"), "Find leads")
        else:
            step, cmd, btn = ("All caught up. Search a new state or category for more leads.",
                              lambda: self.app.show("coverage"), "See what's searched")
        self.next_lbl.config(text=step)
        self.next_btn.config(text=btn + "  →", command=cmd)
        self.draw_map(recs)

        for w in self.todo_box.winfo_children():
            w.destroy()
        items = []
        if nrep:
            items.append((f"↩  Answer {nrep} repl{'y' if nrep == 1 else 'ies'}",
                          lambda: self.app.show("outreach", view="replies"), None))
        nb = c.get("call_booked", 0)
        if nb:
            items.append((f"☎  {nb} call{'s' if nb > 1 else ''} booked, open the call brief",
                          lambda: self.app.show("pipeline"), None))
        names = {r["domain"]: (r["name"] or r["domain"]) for r in recs}
        who = {}
        for dom, frm, subj in db.q("SELECT domain, from_addr, subject FROM replies ORDER BY id"):
            who[dom] = frm or subj
        for tid, dom, kind, due in O.due_tasks(db)[:8]:
            label = names.get(dom) or who.get(dom) or dom
            if kind == "inquiry":
                cmd = lambda: self.app.show("outreach", view="replies")
                items.append((f"★  New website inquiry: {label}", cmd, tid))
                continue
            items.append((f"★  {O.TASK_LABELS.get(kind, kind)}: {label}",
                          lambda d=dom: self.app.open_profile(d), tid))
        if not items:
            tk.Label(self.todo_box, text="Nothing waiting. Find or email more leads.", bg=CARD, fg=MUTED,
                     font=F(9), wraplength=210, justify="left").pack(anchor="w")
        for text, cmd, tid in items:
            r = tk.Frame(self.todo_box, bg=CARD)
            r.pack(fill="x", pady=3)
            lb = tk.Label(r, text=text, bg=CARD, fg=ACCENT_TXT, cursor="hand2", font=F(9, "bold"),
                          wraplength=160, justify="left", anchor="w")
            lb.pack(side="left", fill="x", expand=True)
            lb.bind("<Button-1>", lambda e, c=cmd: c())
            if tid:
                Btn(r, text="Done", width=5,
                    command=lambda t=tid: (O.done_task(db, t), self.refresh())).pack(side="right")

        self.res_tree.delete(*self.res_tree.get_children())
        for row in O.funnel(db):
            lab = self.app.cats.get(row["category"], {}).get("short") or row["category"].replace("_", " ").title()
            self.res_tree.insert("", "end", values=(lab, row["emailed"], row["replied"],
                                                    f"{100 * row['replied'] / row['emailed']:.0f}%" if row["emailed"] else "-",
                                                    row["booked"], row["won"]))
        self.rep_tree.delete(*self.rep_tree.get_children())
        try:
            reps = db.q("SELECT domain, from_addr, kind, snippet, received_at FROM replies "
                        "ORDER BY received_at DESC LIMIT 30")
        except Exception:
            reps = []
        for i, (dom, frm, kind, snip, when) in enumerate(reps):
            self.rep_tree.insert("", "end", iid=f"rep{i}", values=(
                (when or "")[:10], names.get(dom, frm or dom), (kind or "").replace("_", " "),
                " ".join((snip or "").split())[:120]))
        self.tree.delete(*self.tree.get_children())
        for r in fresh[:40]:
            self.tree.insert("", "end", iid=r["domain"], tags=(r["level"],), values=(
                level_text(r["level"]), r["name"] or r.get("site_name") or r["domain"],
                ", ".join(x for x in (r.get("city"), (r.get("region") or "")[3:]) if x),
                r["score"] or 0, marketing_text(r.get("marketing"))))


# ---------------------------------------------------------------------------
# Find leads
# ---------------------------------------------------------------------------
class FindPage(Page):
    title = "Find leads"
    subtitle = "Pick states and categories. Searches you already did are marked ✓ and skipped."

    def build(self):
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="both", expand=True)
        # 1. where
        c1 = card(top, "1.  Where", "Ctrl/Shift-click to pick several.\n✓ = categories already searched.")
        c1.pack(side="left", fill="y")
        self.country = tk.StringVar(value="US")
        r = tk.Frame(c1.inner, bg=CARD)
        r.pack(fill="x")
        for val, txt in (("US", "USA"), ("CA", "Canada")):
            ttk.Radiobutton(r, text=txt, value=val, variable=self.country,
                            command=self.fill_regions).pack(side="left", padx=(0, 12))
        self.rsearch = tk.StringVar()
        e = ttk.Entry(c1.inner, textvariable=self.rsearch)
        e.pack(fill="x", pady=6)
        e.bind("<KeyRelease>", lambda ev: self.fill_regions())
        lf = tk.Frame(c1.inner, bg=CARD)
        lf.pack(fill="both", expand=True)
        self.regions = tk.Listbox(lf, selectmode="extended", height=16, width=24, exportselection=False,
                                  font=F(10), activestyle="none", highlightthickness=1,
                                  highlightcolor=TEAL, highlightbackground=BORDER, relief="flat",
                                  selectbackground=TEAL, selectforeground="white")
        sb = ttk.Scrollbar(lf, command=self.regions.yview)
        self.regions.config(yscrollcommand=sb.set)
        self.regions.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.regions.bind("<<ListboxSelect>>", lambda e: self.mark_categories())
        Btn(c1.inner, text="Select all", command=self.select_all).pack(fill="x", pady=(6, 0))
        # 2. what
        c3 = card(top, "3.  How")
        c3.pack(side="right", fill="y")
        c2 = card(top, "2.  What", "Tier A = best fit for redesign pitches.")
        c2.pack(side="left", fill="both", expand=True, padx=12)
        tb = tk.Frame(c2.inner, bg=CARD)
        tb.pack(fill="x", pady=(0, 6))
        for t in ("A", "B", "C"):
            Btn(tb, text=f"Tier {t}", width=7, command=lambda t=t: self.pick_tier(t)).pack(side="left", padx=(0, 4))
        Btn(tb, text="All", width=5, command=lambda: self.pick_tier("ABC")).pack(side="left", padx=(0, 4))
        Btn(tb, text="None", width=6, command=lambda: self.pick_tier("")).pack(side="left")
        grid = tk.Frame(c2.inner, bg=CARD)
        grid.pack(fill="both", expand=True)
        self.cat_vars, self.cat_checks = {}, {}
        for i, (key, c) in enumerate(self.app.cats.items()):
            v = tk.BooleanVar(value=c["tier"] == "A")
            cb = ttk.Checkbutton(grid, text=c.get("short") or short_label(c["label"]), variable=v)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 14), pady=1)
            self.cat_vars[key], self.cat_checks[key] = v, cb
        # 3. how
        self.src_osm = tk.BooleanVar(value=True)
        self.src_ov = tk.BooleanVar(value=True)
        self.full = tk.BooleanVar(value=False)
        self.again = tk.BooleanVar(value=False)
        ttk.Checkbutton(c3.inner, text="OpenStreetMap (fast)", variable=self.src_osm).pack(anchor="w", pady=(8, 2))
        ttk.Checkbutton(c3.inner, text="Overture Maps (deep: many more\nbusinesses, slower)",
                        variable=self.src_ov).pack(anchor="w", pady=2)
        ttk.Separator(c3.inner).pack(fill="x", pady=8)
        ttk.Checkbutton(c3.inner, text="Full check (open every site,\nslower, misses nothing)",
                        variable=self.full).pack(anchor="w", pady=2)
        ttk.Checkbutton(c3.inner, text="Search again (redo ✓ searches)",
                        variable=self.again).pack(anchor="w", pady=2)
        wr = tk.Frame(c3.inner, bg=CARD)
        wr.pack(anchor="w", pady=(8, 0))
        ttk.Label(wr, text="Sites at once", style="Card.TLabel").pack(side="left")
        self.workers = tk.IntVar(value=W.DEFAULT_WORKERS)
        ttk.Spinbox(wr, from_=1, to=24, textvariable=self.workers, width=4).pack(side="left", padx=6)
        Btn(c3.inner, text="▶  Start search", style="Primary.TButton",
                   command=self.start).pack(fill="x", pady=(16, 4))
        Btn(c3.inner, text="Check my own list of websites…",
                   command=self.start_urls).pack(fill="x", pady=2)
        ttk.Separator(c3.inner).pack(fill="x", pady=10)
        ttk.Label(c3.inner, text="Deep hunt: free wixsite.com sites", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(c3.inner, text="Finds sites still on a free Wix address\n(your hottest leads). "
                  "The Pages box is only\nfor this hunt, not for Start search.", style="Muted.TLabel").pack(anchor="w", pady=(2, 6))
        hr = tk.Frame(c3.inner, bg=CARD)
        hr.pack(fill="x")
        ttk.Label(hr, text="Pages", style="Card.TLabel").pack(side="left")  # hunt only
        self.hunt_pages = tk.IntVar(value=3)
        ttk.Spinbox(hr, from_=1, to=50, textvariable=self.hunt_pages, width=4).pack(side="left", padx=6)
        Btn(hr, text="Run hunt", style="Dark.TButton", command=self.start_hunt).pack(side="left", fill="x", expand=True)
        self.hunt_lbl = tk.Label(c3.inner, bg=INFO, fg=TEXT, font=F(9), justify="left", anchor="w",
                                 padx=8, pady=6, highlightthickness=1, highlightbackground=INFO_BORDER)
        self.hunt_lbl.pack(fill="x", pady=(8, 0))
        # log
        lc = card(self.body, pad=8)
        lc.pack(fill="both", expand=False, pady=(12, 0))
        self.logbox = tk.Text(lc.inner, height=7, bg="#0F1822", fg="#D6E2EC", insertbackground="white",
                              font=("Consolas", 9), relief="flat", wrap="word", padx=10, pady=8)
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_config("wix", foreground="#5BD6A4")
        self.logbox.tag_config("head", foreground="#7FD3E6", font=("Consolas", 9, "bold"))
        self.logbox.tag_config("bad", foreground="#FF7A7F")
        self.logbox.config(state="disabled")
        self.fill_regions()

    def fill_regions(self):
        done = {}
        for j in self.db.job_table() if self.db else []:
            if j["status"] == "done":
                done.setdefault(j["region"], set()).add(j["category"])
        sel = set(self.selected_regions()) if hasattr(self, "region_keys") else set()
        self.regions.delete(0, "end")
        q = self.rsearch.get().strip().lower()
        self.region_keys = []
        for code, name in W.REGIONS.items():
            if not code.startswith(self.country.get() + "-"):
                continue
            if q and q not in name.lower() and q not in code.lower():
                continue
            n = len(done.get(code, set()) & set(self.app.cats))
            self.regions.insert("end", f"{name}" + (f"   ✓ {n}" if n else ""))
            if n:
                self.regions.itemconfig("end", fg=GREEN)
            self.region_keys.append(code)
            if code in sel:
                self.regions.selection_set("end")
        self.mark_categories()

    def selected_regions(self):
        return [self.region_keys[i] for i in self.regions.curselection()]

    def select_all(self):
        self.regions.selection_set(0, "end")
        self.mark_categories()

    def pick_tier(self, tiers):
        for k, v in self.cat_vars.items():
            v.set(self.app.cats[k]["tier"] in tiers if tiers else False)

    def sources(self):
        s = []
        if self.src_osm.get():
            s.append("openstreetmap")
        if self.src_ov.get():
            s.append("overture")
        return tuple(s)

    def mark_categories(self):
        regs = self.selected_regions()
        srcs = self.sources() or ("openstreetmap",)
        for k, cb in self.cat_checks.items():
            label = self.app.cats[k].get("short") or short_label(self.app.cats[k]["label"])
            if regs and self.db:
                n = sum(1 for r in regs if all(self.db.job_done(r, k, s) for s in srcs))
                if n == len(regs):
                    label += "  ✓"
                elif n:
                    label += f"  ✓ {n}/{len(regs)}"
            cb.config(text=label)

    def append_log(self, msg):
        tag = None
        if msg.lstrip().startswith("WIX"):
            tag = "wix"
        elif msg.lstrip().startswith(("=====", "[")):
            tag = "head"
        elif "PROBLEM" in msg or "failed" in msg.lower() or "isn't answering" in msg:
            tag = "bad"
        self.logbox.config(state="normal")
        self.logbox.insert("end", msg + "\n", tag)
        if int(self.logbox.index("end-1c").split(".")[0]) > 3000:
            self.logbox.delete("1.0", "500.0")
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def refresh(self, **kw):
        self.fill_regions()
        self.update_hunt()

    def update_hunt(self):
        if not self.db:
            return
        h = W.hunt_status(self.db)
        if not h["crawl"]:
            txt = "Not started yet."
        elif h["finished"]:
            txt = "✓ All Common Crawl pages done."
        else:
            txt = f"Done so far: page {h['page']} of crawl\n{h['crawl']}. Next run starts at page {h['page'] + 1}."
        txt += (f"\n{h['found']:,} sites found · {h['checked']:,} checked\n"
                f"{h['na']:,} Wix sites in USA/Canada")
        self.hunt_lbl.config(text=txt, fg=GREEN if h["finished"] else TEXT)

    def _common(self):
        regions = self.selected_regions()
        cats = [k for k, v in self.cat_vars.items() if v.get()]
        if not regions:
            messagebox.showwarning("Pick a state", "Pick at least one state or province.")
            return None
        return regions, cats

    def start(self):
        x = self._common()
        if not x:
            return
        regions, cats = x
        if not cats:
            return messagebox.showwarning("Pick categories", "Tick at least one category.")
        srcs = self.sources()
        if not srcs:
            return messagebox.showwarning("Pick a source", "Tick OpenStreetMap and/or Overture Maps.")
        todo = sum(1 for r in regions for c in cats for s in srcs if not self.db.job_done(r, c, s))
        if not todo and not self.again.get():
            return messagebox.showinfo("Already done",
                                       "You've already searched all of these. Tick 'Search again' "
                                       "to redo them, or pick other states/categories.")
        self.append_log(f"\nStarting: {len(regions)} region(s) × {len(cats)} categories "
                        f"({todo} new searches).")
        args = dict(workers=self.workers.get(), db_path=DB_PATH, out_dir=OUT_DIR,
                    full=self.full.get(), rerun=self.again.get(), sources=srcs,
                    label=None if len(cats) < 4 else f"{len(cats)}cats")
        self.app.run_job("Finding leads", lambda: W.run_job(regions, cats, self.app.cats, **args),
                         after=lambda res: self.show_summary())

    def show_summary(self):
        lines = list(W.LAST_SUMMARY)
        if not lines:
            return
        total = self.db.stats()[1]
        msg = "\n".join(lines[:40]) + (f"\n…and {len(lines) - 40} more" if len(lines) > 40 else "")
        msg += f"\n\nAll Wix sites in your database: {total:,}"
        (messagebox.showwarning if any(l.startswith("⚠") for l in lines) else messagebox.showinfo)(
            "Search summary", msg)

    def start_urls(self):
        x = self._common()
        if not x:
            return
        path = filedialog.askopenfilename(title="Your list of websites (one per line)",
                                          filetypes=[("Text or CSV", "*.txt *.csv"), ("All", "*.*")])
        if not path:
            return
        self.app.run_job("Checking your list", lambda: W.run_job(
            x[0][:1], ["custom"], self.app.cats, urls_file=path, workers=self.workers.get(),
            db_path=DB_PATH, out_dir=OUT_DIR, full=self.full.get(), label="my_list"))

    def start_hunt(self):
        self.app.run_job("wixsite.com hunt", lambda: W.run_wixsite_hunt(
            self.hunt_pages.get(), workers=self.workers.get(), db_path=DB_PATH))


# ---------------------------------------------------------------------------
# Yellow Pages (in-app window)
# ---------------------------------------------------------------------------
class YPPage(Page):
    title = "Yellow Pages"
    subtitle = "Search inside the app. Every page you view is captured automatically."

    def build(self):
        left = card(self.body, "Search Yellow Pages")
        left.pack(side="left", fill="y")
        b = left.inner
        ttk.Label(b, text="What", style="Card.TLabel").pack(anchor="w", pady=(10, 2))
        self.what = tk.StringVar(value="dentists")
        terms = sorted(set(YP_TERMS.values()))
        ttk.Combobox(b, textvariable=self.what, values=terms, width=32).pack(fill="x")
        ttk.Label(b, text="State / province", style="Card.TLabel").pack(anchor="w", pady=(10, 2))
        self.where = tk.StringVar(value="Texas")
        ttk.Combobox(b, textvariable=self.where, values=list(W.REGIONS.values()),
                     state="readonly", width=32).pack(fill="x")
        ttk.Label(b, text="City", style="Card.TLabel").pack(anchor="w", pady=(10, 2))
        self.city = tk.StringVar(value="Houston")
        ttk.Entry(b, textvariable=self.city).pack(fill="x")
        Btn(b, text="☰  Open Yellow Pages", style="Primary.TButton",
                   command=self.open_yp).pack(fill="x", pady=(16, 6))
        steps = ("How it works\n"
                 "1. Click Open. A Yellow Pages window opens.\n"
                 "2. If it asks “are you human”, tick it yourself.\n"
                 "3. Scroll the results. A dark badge shows how\n    many websites were captured.\n"
                 "4. Click Next page in Yellow Pages for more.\n"
                 "5. Come back and click “Check captured\n    websites” to find the Wix ones.")
        tk.Label(b, text=steps, bg=INFO, fg=TEXT, justify="left", font=F(9), padx=10, pady=10,
                 highlightthickness=1, highlightbackground=INFO_BORDER).pack(fill="x", pady=(10, 0))
        tk.Label(b, text="Google Maps: use the Chrome helper. Open one business on Maps,\n"
                 "click the helper, then 'Check if Wix & save to app'. Load the helper\n"
                 "from the 'chrome-helper' folder next to WixLeadBot.exe\n"
                 "(chrome://extensions > Developer mode > Load unpacked).\n\n"
                 "Yellow Pages' terms don't allow automated scraping, so the app\n"
                 "never clicks for you. It only reads pages you open yourself.",
                 bg=CARD, fg=MUTED, font=F(8), justify="left").pack(anchor="w", pady=(10, 0))

        right = card(self.body, "Captured websites")
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        r = right.inner
        self.stat = tk.Label(r, text="", bg=CARD, fg=TEXT, font=F(11, "bold"), anchor="w")
        self.stat.pack(fill="x", pady=(6, 8))
        fr, self.tree = make_tree(r, [("name", "Business", 190), ("site", "Website", 220),
                                      ("city", "City", 110), ("status", "Wix?", 90)], height=16)
        fr.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._dbl)
        br = tk.Frame(r, bg=CARD)
        br.pack(fill="x", pady=(10, 0))
        Btn(br, text="✓  Check captured websites for Wix", style="Primary.TButton",
                   command=self.check).pack(side="left")
        self.only_new = tk.BooleanVar(value=True)
        ttk.Checkbutton(br, text="Show this session only", variable=self.only_new,
                        command=self.refresh).pack(side="left", padx=12)

    def _dbl(self, e):
        d = self.tree.focus()
        if d and self.db.q("SELECT 1 FROM sites WHERE domain=? AND is_wix=1", (d,)):
            self.app.open_profile(d)

    def yp_url(self):
        term = self.what.get().strip() or "dentists"
        region = next((k for k, v in W.REGIONS.items() if v == self.where.get()), "US-TX")
        city = self.city.get().strip()
        code = region[3:]
        if region.startswith("CA-"):
            where = f"{city} {code}".strip()
            return f"https://www.yellowpages.ca/search/si/1/{quote(term)}/{quote_plus(where)}"
        where = f"{city}, {code}" if city else self.where.get()
        return ("https://www.yellowpages.com/search?search_terms=" + quote_plus(term) +
                "&geo_location_terms=" + quote_plus(where))

    def open_yp(self):
        if not self.app.inbox:
            messagebox.showwarning("Capture inbox off", "Another copy of the app is using port "
                                   f"{W.INBOX_PORT}. Close it and restart this app.")
            return
        url = self.yp_url()
        env = dict(os.environ, NA_INBOX_TOKEN=W.INBOX_TOKEN, NA_INBOX_PORT=str(W.INBOX_PORT))
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--yp-browser", url]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--yp-browser", url]
        try:
            self.app.yp_proc = subprocess.Popen(cmd, env=env)
        except OSError as e:
            return messagebox.showerror("Yellow Pages", str(e))
        self.app.toast("Yellow Pages window opening…")
        self.app.root.after(5000, lambda: self._check_proc(url))

    def _check_proc(self, url):
        p = self.app.yp_proc
        if p and p.poll() == 3:
            webbrowser.open(url)
            messagebox.showinfo(
                "Yellow Pages", "The built-in window needs Microsoft Edge WebView2, which wasn't "
                "found. Yellow Pages opened in your normal browser instead. Use the Chrome helper "
                "(chrome-extension folder) to capture pages from there.")

    def on_captured(self, new, total, items):
        for it in items:
            self.app.session_captured.append(it)
        if self.app.current == "yp":
            self.refresh()
        if new:
            self.app.toast(f"Captured {new} new website{'s' if new > 1 else ''} from Yellow Pages")

    def refresh(self, **kw):
        rows = self.db.q("""SELECT b.name, b.website, b.city, b.domain, s.is_wix, s.status
                            FROM businesses b LEFT JOIN sites s ON s.domain=b.domain
                            WHERE b.source=? ORDER BY b.added_at DESC""", (W.CAPTURE_SOURCE,))
        sess = {W.domain_of(i.get("website", "")) for i in self.app.session_captured}
        if self.only_new.get() and sess:
            rows = [r for r in rows if r[3] in sess]
        unchecked = sum(1 for r in rows if r[5] is None)
        wix = sum(1 for r in rows if r[4] == 1)
        self.stat.config(text=f"{len(rows):,} captured   ·   {unchecked:,} not checked yet   ·   "
                              f"{wix:,} on Wix")
        self.tree.delete(*self.tree.get_children())
        seen = set()
        for name, site, city, dom, is_wix, st in rows[:2000]:
            if dom in seen:
                continue
            seen.add(dom)
            flag = "WIX ✓" if is_wix == 1 else ("—" if st else "not checked")
            self.tree.insert("", "end", iid=dom, values=(name, site, city, flag),
                             tags=("super",) if is_wix == 1 else ())

    def check(self):
        self.app.run_job("Checking Yellow Pages websites", lambda: W.run_captured(
            db_path=DB_PATH, out_dir=OUT_DIR, workers=self.app.pages["find"].workers.get()))


# ---------------------------------------------------------------------------
# Leads + profile
# ---------------------------------------------------------------------------
class LeadsPage(Page):
    title = "Leads"
    subtitle = "Every Wix website found. Click one to see its profile."

    def build(self):
        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", pady=(0, 10))
        self.fsearch = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self.fsearch, width=20)
        e.pack(side="left")
        e.insert(0, "")
        e.bind("<KeyRelease>", self._search_later)
        self._search_job = None
        self.flevel = tk.StringVar(value="All levels")
        self.fregion = tk.StringVar(value="All regions")
        self.fcat = tk.StringVar(value="All categories")
        self.fstatus = tk.StringVar(value="Any status")
        self.femail = tk.BooleanVar(value=False)
        for var, vals, w in ((self.flevel, ["All levels", "Super", "Hot", "Normal"], 11),
                             (self.fregion, ["All regions"], 15),
                             (self.fcat, ["All categories"], 18),
                             (self.fstatus, ["Any status", "Not contacted"] +
                              [O.STATUS_LABELS[s] for s in O.STATUSES if s != "new"], 15)):
            cb = ttk.Combobox(bar, textvariable=var, values=vals, state="readonly", width=w)
            cb.pack(side="left", padx=(8, 0))
            cb.bind("<<ComboboxSelected>>", lambda ev: self.fill())
            if var is self.fregion:
                self.region_cb = cb
            if var is self.fcat:
                self.cat_cb = cb
        self.femail = tk.StringVar(value="Any contact")
        cbe = ttk.Combobox(bar, textvariable=self.femail, state="readonly", width=17,
                           values=["Any contact", "Has email", "No email (call list)", "Runs ads ($)"])
        cbe.pack(side="left", padx=8)
        cbe.bind("<<ComboboxSelected>>", lambda ev: self.fill())
        Btn(bar, text="Export CSV", command=self.export).pack(side="right")
        self.legend = tk.Frame(self.body, bg=BG)
        self.legend.pack(fill="x", pady=(0, 8))
        act = tk.Frame(self.body, bg=BG)
        act.pack(fill="x", pady=(0, 8))
        Btn(act, text="☑  Select all", command=self.select_all).pack(side="left")
        Btn(act, text="Clear", command=lambda: (self.tree.selection_set(()), self._sel_changed())).pack(
            side="left", padx=6)
        self.email_btn = Btn(act, text="✉  Email selected (0)", style="Primary.TButton",
                             command=self.email_selected)
        self.email_btn.pack(side="left", padx=(6, 0))
        tk.Label(act, text="Tip: Ctrl+click or Shift+click to pick several leads.", bg=BG, fg=MUTED,
                 font=F(9)).pack(side="left", padx=12)

        pw = ttk.PanedWindow(self.body, orient="horizontal")
        pw.pack(fill="both", expand=True)
        lc = card(pw, pad=0)
        fr, self.tree = make_tree(lc.inner, [("level", "Level", 80), ("name", "Business", 200),
                                             ("loc", "Location", 110), ("cat", "Category", 120),
                                             ("score", "Score", 50), ("email", "Email", 170),
                                             ("mk", "Marketing", 100), ("status", "Status", 90)], height=20)
        fr.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pw.add(lc, weight=3)
        self.profile = Profile(pw, self.app)
        pw.add(self.profile.outer, weight=2)
        self.pw = pw
        self._sash_done = False
        pw.bind("<Configure>", self._place_sash)
        self.records = {}

    def _search_later(self, e=None):
        if self._search_job:
            self.frame.after_cancel(self._search_job)
        self._search_job = self.frame.after(350, self.fill)

    def _place_sash(self, e):
        if not self._sash_done and e.width > 600:
            self.pw.sashpos(0, max(420, e.width - 500))
            self._sash_done = True

    def refresh(self, select=None, region=None, **kw):
        regs = sorted({r for (r,) in self.db.q("SELECT DISTINCT region FROM businesses")
                       if r and r in W.REGIONS})
        self.region_cb.config(values=["All regions"] + [W.REGIONS[r] for r in regs])
        if region in W.REGIONS:
            self.fsearch.set("")
            self.flevel.set("All levels")
            self.fcat.set("All categories")
            self.fstatus.set("Any status")
            self.femail.set("Any contact")
            self.fregion.set(W.REGIONS[region])
        cats = sorted({c for (c,) in self.db.q("SELECT DISTINCT category FROM businesses") if c})
        self.cat_cb.config(values=["All categories"] + [self.cat_label(c) for c in cats])
        if select:
            self.fsearch.set("")
            self.flevel.set("All levels")
            self.fregion.set("All regions")
            self.fcat.set("All categories")
            self.fstatus.set("Any status")
            self.femail.set("Any contact")
        self.fill()
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
            self.tree.see(select)
            self.tree.focus(select)

    def cat_label(self, c):
        return self.app.cats.get(c, {}).get("label") or c.replace("_", " ").title()

    def fill(self):
        recs = self.db.lead_records()
        status = {d: s for d, s in self.db.q("SELECT domain, status FROM outreach")}
        q = self.fsearch.get().strip().lower()
        lvl = self.flevel.get().lower()
        reg = self.fregion.get()
        cat = self.fcat.get()
        st = self.fstatus.get()
        counts = {"super": 0, "hot": 0, "normal": 0}
        self.tree.delete(*self.tree.get_children())
        self.records = {}
        for r in recs:
            counts[r["level"]] += 1
            s = status.get(r["domain"], "new")
            if lvl in ("super", "hot", "normal") and r["level"] != lvl:
                continue
            if reg != "All regions" and r["region_name"] != reg:
                continue
            if cat != "All categories" and self.cat_label(r["category"] or "") != cat:
                continue
            if st == "Not contacted" and s != "new":
                continue
            if st not in ("Any status", "Not contacted") and O.STATUS_LABELS.get(s) != st:
                continue
            if self.femail.get() == "Has email" and not r["emails"]:
                continue
            if self.femail.get().startswith("No email") and r["emails"]:
                continue
            if self.femail.get().startswith("Runs ads") and not marketing_text(r.get("marketing")).startswith("$"):
                continue
            name = r["name"] or r.get("site_name") or r["domain"]
            if q and q not in f"{name} {r['domain']} {r.get('city') or ''} {r.get('emails') or ''}".lower():
                continue
            self.records[r["domain"]] = r
            self.tree.insert("", "end", iid=r["domain"], tags=(r["level"],), values=(
                level_text(r["level"]), name,
                ", ".join(x for x in (r.get("city"), (r.get("region") or "")[3:]) if x),
                self.cat_label(r["category"] or ""), r["score"] or 0,
                (r["emails"] or "—").split(";")[0], marketing_text(r.get("marketing")),
                O.STATUS_LABELS.get(s, s)))
        for w in self.legend.winfo_children():
            w.destroy()
        for k in ("super", "hot", "normal"):
            b = badge(self.legend, f"{W.LEVELS[k][0]}  {counts[k]:,}", LEVEL_COLOR[k])
            b.pack(side="left", padx=(0, 8))
            b.config(cursor="hand2")
            b.bind("<Button-1>", lambda e, k=k: (self.flevel.set(W.LEVELS[k][0]), self.fill()))
        tk.Label(self.legend, text=f"   showing {len(self.records):,}", bg=BG, fg=MUTED,
                 font=F(9)).pack(side="left")

    def on_select(self, e=None):
        self._sel_changed()
        d = self.tree.focus() or (self.tree.selection() or [None])[0]
        if d and d in self.records:
            self.profile.show(self.records[d])

    def _sel_changed(self):
        n = len(self.tree.selection())
        self.email_btn.config(text=f"✉  Email selected ({n})")

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())
        self._sel_changed()

    def email_selected(self):
        sel = list(self.tree.selection())
        if not sel:
            return messagebox.showinfo("Email", "Pick one or more leads first (or click Select all).")
        self.app.contact_dialog(sel)

    def export(self):
        rows = [self.records[i] for i in self.tree.get_children()]
        if not rows:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=OUT_DIR,
                                            initialfile="leads.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cols = ["level", "name", "domain", "final_url", "region", "city", "category", "score",
                "emails", "email_sources", "phones", "listed_phone", "socials", "address",
                "issues", "source", "checked_at"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([W.LEVELS[r["level"]][0] if c == "level" else r.get(c, "") for c in cols])
        self.app.toast(f"Exported {len(rows)} leads")


class Profile:
    def __init__(self, parent, app: App):
        self.app = app
        self.outer = card(parent, pad=0)
        self.sf = ScrollFrame(self.outer.inner)
        self.sf.pack(fill="both", expand=True)
        self.lead = None
        self.img_ref = None
        self.wraps = []
        self.sf.body.bind("<Configure>", self._rewrap, add="+")
        self.empty()

    def _rewrap(self, e=None):
        w = self.sf.body.winfo_width()
        for lb, off in self.wraps:
            try:
                lb.config(wraplength=max(150, w - off))
            except tk.TclError:
                pass

    def W(self, label, off=60):
        self.wraps.append((label, off))
        return label

    @property
    def db(self):
        return self.app.db

    def clear(self):
        self.wraps = []
        for w in self.sf.body.winfo_children():
            w.destroy()

    def empty(self):
        self.clear()
        tk.Label(self.sf.body, text="\n\n★\n\nSelect a lead to see its profile", bg=CARD,
                 fg=MUTED, font=F(12)).pack(pady=60)

    def section(self, title):
        f = tk.Frame(self.sf.body, bg=CARD)
        f.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(f, text=title.upper(), bg=CARD, fg=MUTED, font=F(8, "bold")).pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=(3, 6))
        return f

    def kv(self, parent, label, widget_fn):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=2)
        tk.Label(r, text=label, bg=CARD, fg=MUTED, font=F(9), width=10, anchor="nw").pack(side="left", anchor="n")
        box = tk.Frame(r, bg=CARD)
        box.pack(side="left", fill="x", expand=True)
        widget_fn(box)

    def show(self, lead: dict):
        self.lead = lead
        if lead.get("marketing") is None and lead.get("final_url"):
            self._check_marketing(lead["domain"], lead["final_url"])
        self.clear()
        b = self.sf.body
        lvl = lead["level"]
        col = LEVEL_COLOR[lvl]
        tk.Frame(b, bg=col, height=6).pack(fill="x")
        head = tk.Frame(b, bg=CARD)
        head.pack(fill="x", padx=18, pady=(14, 0))
        name = lead["name"] or lead.get("site_name") or lead["domain"]
        av = tk.Canvas(head, width=58, height=58, bg=CARD, highlightthickness=0)
        av.pack(side="left", anchor="n")
        av.create_oval(2, 2, 56, 56, fill=col, outline="")
        initials = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", name)[:2]).upper() or "?"
        av.create_text(29, 29, text=initials, fill="white", font=F(16, "bold"))
        info = tk.Frame(head, bg=CARD)
        info.pack(side="left", fill="x", expand=True, padx=12)
        self.W(tk.Label(info, text=name, bg=CARD, fg=TEXT, font=F(15, "bold"), anchor="w",
                        justify="left"), 120).pack(anchor="w")
        cat = self.app.pages["leads"].cat_label(lead.get("category") or "")
        loc = ", ".join(x for x in (lead.get("city"), lead.get("region_name")) if x)
        self.W(tk.Label(info, text=f"{cat}  ·  {loc or 'Location unknown'}", bg=CARD, fg=MUTED,
                        font=F(10), anchor="w", justify="left"), 120).pack(anchor="w")
        br = tk.Frame(info, bg=CARD)
        br.pack(anchor="w", pady=(6, 0))
        badge(br, W.LEVELS[lvl][0].upper() + " LEAD", col).pack(side="left", padx=(0, 6))
        st = (O.get_outreach(self.db, lead["domain"]) or {}).get("status", "new")
        badge(br, O.STATUS_LABELS[st], STATUS_COLOR.get(st, MUTED)).pack(side="left", padx=(0, 6))
        if lead.get("free_domain"):
            badge(br, "FREE WIX ADDRESS", NAVY).pack(side="left", padx=(0, 6))
        if lead.get("no_solicit"):
            badge(br, "SAYS NO SOLICITATION", RED).pack(side="left")

        # score bar
        sc = lead.get("score") or 0
        sb = tk.Frame(b, bg=CARD)
        sb.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(sb, text=f"Opportunity score  {sc}/100", bg=CARD, fg=TEXT, font=F(10, "bold")).pack(anchor="w")
        cv = tk.Canvas(sb, height=12, bg=CARD, highlightthickness=0)
        cv.pack(fill="x", pady=(4, 0))
        cv.bind("<Configure>", lambda e, c=cv: (c.delete("all"),
                c.create_rectangle(0, 0, e.width, 12, fill=TROUGH, outline=""),
                c.create_rectangle(0, 0, e.width * sc / 100, 12, fill=col, outline="")))

        acts = tk.Frame(b, bg=CARD)
        acts.pack(fill="x", padx=18, pady=(14, 0))
        Btn(acts, text="✉  Email this lead", style="Primary.TButton",
                   command=lambda: self.app.contact_dialog([lead["domain"]])).pack(side="left")
        Btn(acts, text="Website",
                   command=lambda: open_url(lead.get("final_url") or lead.get("website"))).pack(side="left", padx=6)
        if C.phones(lead):
            Btn(acts, text="📞  Call", style="Dark.TButton",
                command=lambda: self.app.show("calls", select=lead["domain"])).pack(side="left", padx=(0, 6))
        Btn(acts, text="Call brief", command=self.open_brief).pack(side="left")
        mb = ttk.Menubutton(acts, text="More", width=7)
        menu = tk.Menu(mb, tearoff=0)
        menu.add_command(label="Do not contact", command=lambda: self.set_status("do_not_contact"))
        menu.add_command(label="This is my client (never contact)", command=self.mark_client)
        menu.add_command(label="Copy email address", command=self.copy_email)
        menu.add_command(label="Send this email to me (see it as the client)", command=self.send_to_me)
        menu.insert_command(0, label="Write the email myself (open a draft)", command=self.draft)
        menu.add_command(label="Copy short audit text", command=self.copy_audit)
        mb["menu"] = menu
        mb.pack(side="left", padx=6)

        self.img_lbl = tk.Label(b, bg=CARD)
        self.img_lbl.pack(padx=18, pady=(12, 0), anchor="w")
        if lead.get("og_image"):
            threading.Thread(target=self._fetch_image, args=(lead["domain"], lead["og_image"]),
                             daemon=True).start()

        c = self.section("Contact")
        site = lead.get("final_url") or lead.get("website")
        self.kv(c, "Website", lambda f: link(f, site, site).pack(anchor="w"))
        mk = [x.strip() for x in (lead.get("marketing") or "").split(";") if x.strip()]

        def mkt(f):
            if not mk:
                tk.Label(f, text="No ads, pixels or analytics found on the site.", bg=CARD, fg=MUTED,
                         font=F(9)).pack(anchor="w")
                return
            r = tk.Frame(f, bg=CARD)
            r.pack(anchor="w")
            for x in mk:
                badge(r, ("$ " if x in W.ADS_LABELS else "") + x, RED if x in W.ADS_LABELS else TEAL).pack(
                    side="left", padx=(0, 4))
            if any(x in W.ADS_LABELS for x in mk):
                tk.Label(f, text="They pay for ads, and every click lands on this website. Say so on the call: "
                         "a better site makes the same ad spend bring in more customers.", bg=CARD, fg=MUTED,
                         font=F(9), wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))
        self.kv(c, "Marketing", mkt)
        emails = [e.strip() for e in (lead.get("emails") or "").split(";") if e.strip()]
        srcs = {}
        for part in (lead.get("email_sources") or "").split(";"):
            if "<-" in part:
                e, u = part.split("<-", 1)
                srcs[e.strip()] = u.strip()

        def em(f):
            if not emails:
                tk.Label(f, text="No email on the site. Use phone or contact form.", bg=CARD,
                         fg=MUTED, font=F(9)).pack(anchor="w")
            for e in emails:
                r = tk.Frame(f, bg=CARD)
                r.pack(anchor="w")
                tk.Label(r, text=e, bg=CARD, fg=TEXT, font=F(10, "bold")).pack(side="left")
                if srcs.get(e):
                    link(r, "found on page", srcs[e], size=8).pack(side="left", padx=6)
            if lead.get("listed_email") and lead["listed_email"] not in emails:
                tk.Label(f, text=f"{lead['listed_email']} (from map listing)", bg=CARD, fg=MUTED,
                         font=F(9)).pack(anchor="w")
        self.kv(c, "Email", em)
        phones = [p for p in (lead.get("phones") or "").split(";") if p.strip()]
        if lead.get("listed_phone"):
            phones.append(lead["listed_phone"])
        self.kv(c, "Phone", lambda f: tk.Label(f, text="\n".join(dict.fromkeys(p.strip() for p in phones)) or "—",
                                               bg=CARD, justify="left").pack(anchor="w"))
        addr = lead.get("address") or ""
        if not addr:
            parts = []
            for x in (lead.get("street"), lead.get("city"), lead.get("postcode")):
                if x and not any(x in p for p in parts):
                    parts.append(x)
            addr = ", ".join(parts)
        self.kv(c, "Address", lambda f: self.W(tk.Label(f, text=addr or "—", bg=CARD,
                                                        justify="left"), 140).pack(anchor="w"))

        def soc(f):
            items = [x.split(": ", 1) for x in (lead.get("socials") or "").split("; ") if ": " in x]
            if not items:
                tk.Label(f, text="—", bg=CARD).pack(anchor="w")
            r = tk.Frame(f, bg=CARD)
            r.pack(anchor="w")
            for k, v in items:
                link(r, k.replace("x_twitter", "X").title(), v).pack(side="left", padx=(0, 10))
        self.kv(c, "Social", soc)

        s = self.section("What we found")
        if lead.get("title"):
            self.W(tk.Label(s, text=f"Google title: “{lead['title']}”", bg=CARD, fg=MUTED, font=F(9),
                            justify="left")).pack(anchor="w", pady=(0, 4))
        for iss in [i.strip() for i in (lead.get("issues") or "").split(";") if i.strip()]:
            r = tk.Frame(s, bg=CARD)
            r.pack(fill="x", pady=1)
            tk.Label(r, text="✗", bg=CARD, fg=RED, font=F(10, "bold")).pack(side="left", anchor="n")
            self.W(tk.Label(r, text=iss, bg=CARD, justify="left", anchor="w"), 80).pack(side="left", padx=6)

        self.build_audit_section(lead)
        self.build_ai_section(lead)
        self.build_mockup_section(lead)

        a = self.section("Quick audit text (paste into an email or a Loom)")
        t = tk.Text(a, height=12, wrap="word", font=F(9), bg=SOFT, relief="flat",
                    padx=8, pady=6, highlightthickness=1, highlightbackground=BORDER)
        t.insert("1.0", O.audit_text(lead))
        t.config(state="disabled")
        t.pack(fill="x")

        o = self.section("Outreach")
        r = tk.Frame(o, bg=CARD)
        r.pack(fill="x")
        tk.Label(r, text="Status", bg=CARD, fg=MUTED).pack(side="left")
        self.status_var = tk.StringVar(value=O.STATUS_LABELS[st])
        cb = ttk.Combobox(r, textvariable=self.status_var, state="readonly", width=16,
                          values=[O.STATUS_LABELS[x] for x in O.STATUSES])
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_status(
            next(k for k, v in O.STATUS_LABELS.items() if v == self.status_var.get())))
        msgs = O.messages(self.db, domain=lead["domain"])
        if msgs:
            fr, tr = make_tree(o, [("step", "Email", 60), ("subj", "Subject", 220),
                                   ("st", "Status", 80), ("date", "Date", 110)], height=min(5, len(msgs)))
            fr.pack(fill="x", pady=(8, 0))
            for m in msgs:
                tr.insert("", "end", values=(f"#{m['step']}", m["subject"], m["status"],
                                             (m["sent_at"] or m["created_at"] or "")[:16].replace("T", " ")))
        else:
            tk.Label(o, text="No emails yet.", bg=CARD, fg=MUTED, font=F(9)).pack(anchor="w", pady=(6, 0))
        tk.Label(o, text="Notes", bg=CARD, fg=MUTED).pack(anchor="w", pady=(10, 2))
        self.notes = tk.Text(o, height=4, wrap="word", font=F(10), relief="flat",
                             highlightthickness=1, highlightbackground=BORDER)
        self.notes.insert("1.0", (O.get_outreach(self.db, lead["domain"]) or {}).get("notes") or "")
        self.notes.pack(fill="x")
        Btn(o, text="Save notes", command=self.save_notes).pack(anchor="e", pady=(6, 0))

        src = self.section("Source")
        found = {"openstreetmap": "OpenStreetMap", "overture": "Overture Maps",
                 "browser-capture": "Yellow Pages capture", "wixsite-hunt": "wixsite.com hunt",
                 "url-file": "Your own list"}.get(lead.get("source"), lead.get("source"))
        tk.Label(src, text=f"Found via {found}  ·  checked {(lead.get('checked_at') or '')[:10]}\n"
                 f"Wix signals: {lead.get('wix_signals') or '—'}", bg=CARD, fg=MUTED, font=F(9),
                 justify="left", wraplength=300).pack(anchor="w")
        tk.Frame(b, bg=CARD, height=20).pack()
        self.sf.canvas.yview_moveto(0)
        self.sf.body.after(50, self._rewrap)

    # ----- full audit
    def build_audit_section(self, lead):
        sec = self.section("Full audit (Google speed, SEO, design, business)")
        a = A.get(self.db, lead["domain"])
        if not a:
            tk.Label(sec, text="Not audited yet. Takes about 30-60 seconds.", bg=CARD, fg=MUTED,
                     font=F(9)).pack(anchor="w")
            Btn(sec, text="Run full audit", style="Dark.TButton",
                       command=self.run_audit).pack(anchor="w", pady=(6, 0))
            return
        row = tk.Frame(sec, bg=CARD)
        row.pack(fill="x")
        ov = a.get("overall", 0)
        col = GREEN if ov >= 80 else AMBER if ov >= 50 else RED
        tk.Label(row, text=f"{ov}", bg=CARD, fg=col, font=F(22, "bold")).pack(side="left")
        tk.Label(row, text="/100 overall", bg=CARD, fg=MUTED).pack(side="left", padx=(2, 14), pady=(10, 0))
        for cid, lab in A.CATEGORIES:
            v = a.get("psi", {}).get("scores", {}).get(cid)
            if v is not None:
                c2 = GREEN if v >= 90 else AMBER if v >= 50 else RED
                badge(row, f"{lab.split(' ')[0]} {v}", c2).pack(side="left", padx=2, pady=(10, 0))
        if a.get("psi_error"):
            self.W(tk.Label(sec, text="PageSpeed: " + a["psi_error"], bg=CARD, fg=RED, font=F(8),
                            justify="left")).pack(anchor="w")
        for f in A.top_findings(a, 5):
            r = tk.Frame(sec, bg=CARD)
            r.pack(fill="x")
            tk.Label(r, text="✗", bg=CARD, fg=RED, font=F(9, "bold")).pack(side="left", anchor="n")
            self.W(tk.Label(r, text=f, bg=CARD, justify="left", font=F(9), anchor="w"), 80).pack(side="left", padx=6)
        b = tk.Frame(sec, bg=CARD)
        b.pack(anchor="w", pady=(6, 0))
        Btn(b, text="Open report", style="Primary.TButton",
                   command=lambda: open_url("file:///" + a["report"].replace(os.sep, "/"))
                   if a.get("report") else None).pack(side="left")
        Btn(b, text="Run again", command=self.run_audit).pack(side="left", padx=6)
        tk.Label(sec, text=f"Audited {a.get('created_at', '')[:10]}. Report: Ctrl+P in the browser to save as PDF.",
                 bg=CARD, fg=MUTED, font=F(8)).pack(anchor="w", pady=(4, 0))
        if WS.enabled(self.app.cfg):
            url = WS.audit_url(self.db, lead["domain"])
            v = WS.views(self.db, lead["domain"])
            w = tk.Frame(sec, bg=CARD)
            w.pack(fill="x", pady=(10, 0))
            if url:
                seen = (f"🔥 Opened {v['views']} time{'s' if v['views'] != 1 else ''}, last "
                        f"{dt.datetime.fromtimestamp(v['last']).strftime('%d %b %H:%M')}" if v.get("views")
                        else "Not opened yet")
                tk.Label(w, text=f"Review page on your website · {seen}", bg=CARD,
                         fg=RED if v.get("views") else MUTED, font=F(9, "bold")).pack(anchor="w")
                bb = tk.Frame(w, bg=CARD)
                bb.pack(anchor="w", pady=(4, 0))
                Btn(bb, text="Open review page", command=lambda: open_url(url)).pack(side="left")
                Btn(bb, text="Update page", command=self.publish_page).pack(side="left", padx=6)
            else:
                Btn(w, text="🌐  Make review page on my website", style="Dark.TButton",
                    command=self.publish_page).pack(anchor="w")

    def publish_page(self):
        lead = self.lead

        def go():
            url = WS.publish_audit(self.db, self.app.cfg, lead)
            WS.add_link_to_draft(self.db, lead["domain"], url)
            return url
        self.app.run_job("Review page", go, after=lambda url: (url and self.app.toast("Review page ready, "
                         "and the link is in the first email"), self._reshow(lead["domain"])))

    def run_audit(self):
        lead = self.lead
        key = S.get_secret(self.app.cfg, "psi_key")
        self.app.run_job("Auditing website", lambda: A.run(self.db, lead, key, O.settings(self.app.cfg)),
                         after=lambda res: self._reshow(lead["domain"]))

    def send_to_me(self):
        from tkinter import simpledialog
        lead = self.lead
        last = self.db.get_kv("test_to", "") or O.settings(self.app.cfg).get("email", "")
        to = simpledialog.askstring("Send to me", f"Send {lead.get('name') or lead['domain']}'s first email, "
                                    "exactly as they would get it, to which address?", initialvalue=last,
                                    parent=self.app.root)
        if not to or "@" not in to:
            return
        self.db.set_kv("test_to", to.strip())
        self.app.run_job("Test email to me", lambda: O.send_as_client(self.db, self.app.cfg, lead, to.strip()),
                         after=lambda res: res and messagebox.showinfo("Sent", res))

    def _check_marketing(self, domain, url):
        """Older leads were checked before ads/pixel detection existed: look once."""
        if domain in getattr(self, "_mk_busy", set()):
            return
        self._mk_busy = getattr(self, "_mk_busy", set()) | {domain}

        def go():
            try:
                import requests
                r = requests.get(url, timeout=15, headers={"User-Agent": W.USER_AGENT})
                found = "; ".join(W.detect_marketing(r.text))
            except Exception:
                found = ""
            self.db.x("UPDATE sites SET marketing=? WHERE domain=?", (found, domain))
            if found:
                self.app.q.put(("call", lambda: self._reshow(domain)))
        threading.Thread(target=go, daemon=True).start()

    def _reshow(self, domain):
        if self.lead and self.lead["domain"] == domain:
            rec = next((r for r in self.db.lead_records("s.domain=?", (domain,))), None)
            if rec:
                self.show(rec)

    # ----- Gemini plan
    def build_ai_section(self, lead):
        sec = self.section("Gemini plan + custom email")
        plan = ai.get_plan(self.db, lead["domain"])
        if not ai.enabled(self.app.cfg):
            tk.Label(sec, text="Add your free Gemini API key in Settings > AI & audit to get a tailored "
                     "plan and email for each business.", bg=CARD, fg=MUTED, font=F(9), wraplength=360,
                     justify="left").pack(anchor="w")
            return
        if not plan:
            Btn(sec, text="✦  Make plan + email with Gemini", style="Dark.TButton",
                       command=self.make_plan).pack(anchor="w")
            tk.Label(sec, text="Runs the full audit first if needed.", bg=CARD, fg=MUTED,
                     font=F(8)).pack(anchor="w", pady=(4, 0))
            return
        for title, key in (("Angle", "angle"), ("Package", "package")):
            if plan.get(key):
                r = tk.Frame(sec, bg=CARD)
                r.pack(fill="x", pady=1)
                tk.Label(r, text=title, bg=CARD, fg=MUTED, font=F(9), width=9, anchor="nw").pack(side="left", anchor="n")
                self.W(tk.Label(r, text=plan[key], bg=CARD, justify="left", font=F(9), anchor="w"), 110).pack(side="left")
        if plan.get("talking_points"):
            tk.Label(sec, text="Talking points", bg=CARD, fg=MUTED, font=F(9)).pack(anchor="w", pady=(4, 0))
            for t in plan["talking_points"]:
                self.W(tk.Label(sec, text="• " + str(t), bg=CARD, justify="left", font=F(9), anchor="w"), 60).pack(anchor="w")
        b = tk.Frame(sec, bg=CARD)
        b.pack(anchor="w", pady=(6, 0))
        Btn(b, text="✉  Use Gemini's email as draft", style="Primary.TButton",
                   command=self.draft_from_plan).pack(side="left")
        Btn(b, text="Write again", command=self.make_plan).pack(side="left", padx=6)

    def make_plan(self):
        lead = self.lead
        key = S.get_secret(self.app.cfg, "psi_key")

        def go():
            a = A.get(self.db, lead["domain"]) or A.run(self.db, lead, key, O.settings(self.app.cfg))
            return ai.make_plan(self.db, self.app.cfg, lead, a)
        self.app.run_job("Gemini plan", go, after=lambda res: self._reshow(lead["domain"]))

    def draft_from_plan(self):
        plan = ai.get_plan(self.db, self.lead["domain"]) or {}
        mid = O.make_draft(self.db, self.app.cfg, self.lead, 1, subject=plan.get("subject"),
                           body=plan.get("email"))
        if mid is None:
            existing = O.messages(self.db, domain=self.lead["domain"])
            if existing:
                return self.app.show("outreach", select=existing[0]["id"])
            return messagebox.showinfo("Not allowed", "No email address, or this lead is on your "
                                       "do-not-contact list / asks for no solicitation.")
        self.app.show("outreach", select=mid)

    # ----- mockup prompt
    def build_mockup_section(self, lead):
        sec = self.section("Mockup (make it in the Gemini app)")
        prompt = ai.mockup_prompt(lead, A.get(self.db, lead["domain"]), ai.get_plan(self.db, lead["domain"]))
        t = tk.Text(sec, height=7, wrap="word", font=F(9), bg=SOFT, relief="flat", padx=8, pady=6,
                    highlightthickness=1, highlightbackground=BORDER)
        t.insert("1.0", prompt)
        t.config(state="disabled")
        t.pack(fill="x")
        b = tk.Frame(sec, bg=CARD)
        b.pack(anchor="w", pady=(6, 0))

        def copy():
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(prompt)
            self.app.toast("Mockup prompt copied. Paste it into Gemini.")
        Btn(b, text="Copy prompt", style="Primary.TButton", command=copy).pack(side="left")
        Btn(b, text="Open Gemini", command=lambda: (copy(), open_url(ai.GEMINI_APP))).pack(side="left", padx=6)
        Btn(b, text="Attach mockup…", command=self.attach_mockup).pack(side="left")
        mf = A.mockup_file(lead["domain"])
        if mf:
            tk.Label(sec, text="Mockup saved ✓ (shown in the call brief, can be attached to emails)",
                     bg=CARD, fg=GREEN, font=F(8, "bold")).pack(anchor="w", pady=(6, 2))
            ml = tk.Label(sec, bg=CARD, cursor="hand2")
            ml.pack(anchor="w")
            ml.bind("<Button-1>", lambda e: open_url("file:///" + mf.replace(os.sep, "/")))
            try:
                from PIL import Image, ImageTk
                im = Image.open(mf)
                im.thumbnail((420, 260))
                self.mock_ref = ImageTk.PhotoImage(im)
                ml.config(image=self.mock_ref)
            except Exception:
                ml.config(text="Open mockup", fg=TEAL)

    def attach_mockup(self):
        path = filedialog.askopenfilename(title="Mockup image you made in Gemini",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not path:
            return
        try:
            A.save_mockup(self.lead["domain"], path)
        except (RuntimeError, OSError) as e:
            return messagebox.showerror("Mockup", str(e))
        self.app.toast("Mockup saved")
        self.show(self.lead)

    def open_brief(self):
        path = A.call_brief(self.db, self.app.cfg, self.lead)
        open_url("file:///" + path.replace(os.sep, "/"))

    def _fetch_image(self, domain, url):
        try:
            import io
            from PIL import Image
            import requests
            r = requests.get(url, timeout=12, headers={"User-Agent": W.USER_AGENT})
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im.thumbnail((440, 230))
            buf = io.BytesIO()
            im.save(buf, "PNG")
            self.app.q.put(("image", domain, buf.getvalue()))
        except Exception:
            pass

    def set_image(self, domain, data):
        if not self.lead or self.lead["domain"] != domain:
            return
        try:
            import base64
            self.img_ref = tk.PhotoImage(data=base64.b64encode(data))
            self.img_lbl.config(image=self.img_ref, highlightthickness=1, highlightbackground=BORDER)
        except tk.TclError:
            pass

    def draft(self):
        lead = self.lead
        if not O.best_email(lead):
            return messagebox.showinfo("No email", "No email address was found for this lead. "
                                       "Call them or use their website's contact form.")
        mid = O.make_draft(self.db, self.app.cfg, lead, 1)
        if mid is None:
            existing = O.messages(self.db, domain=lead["domain"])
            if existing:
                self.app.show("outreach", select=existing[0]["id"])
                return
            return messagebox.showinfo("Not allowed", "This address is on your do-not-contact list.")
        self.app.show("outreach", select=mid)

    def copy_audit(self):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(O.audit_text(self.lead))
        self.app.toast("Audit copied")

    def copy_email(self):
        e = O.best_email(self.lead)
        if e:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(e)
            self.app.toast("Email copied")

    def set_status(self, status):
        O.set_status(self.db, self.lead["domain"], status)
        self.app.toast(f"Status: {O.STATUS_LABELS[status]}")
        self.app.pages["leads"].fill()
        if self.app.pages["leads"].tree.exists(self.lead["domain"]):
            self.app.pages["leads"].tree.selection_set(self.lead["domain"])
        self.show(self.lead)

    def mark_client(self):
        O.suppress(self.db, self.lead["domain"], "client")
        self.set_status("do_not_contact")

    def save_notes(self):
        O.set_notes(self.db, self.lead["domain"], self.notes.get("1.0", "end").strip())
        self.app.toast("Notes saved")


# ---------------------------------------------------------------------------
# Outreach (approval queue + sending)
# ---------------------------------------------------------------------------
class OutreachPage(Page):
    title = "Outreach"
    subtitle = "Pick leads, check the emails in one window, click Send once. Nothing goes out without that."

    def build(self):
        top = card(self.body, pad=12)
        top.pack(fill="x")
        t = top.inner
        self.summary = tk.Label(t, bg=CARD, font=F(10, "bold"), anchor="w", justify="left")
        self.summary.pack(fill="x", pady=(0, 10))
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x")
        Btn(row, text="🚀  Contact Super + Hot", style="Dark.TButton",
                   command=self.app.contact_dialog).pack(side="left")
        Btn(row, text="Templates", command=self.bulk).pack(side="left", padx=(6, 0))
        Btn(row, text="⟳  Follow-ups", command=self.followups).pack(side="left", padx=6)
        Btn(row, text="↩  Check inbox", command=self.inbox).pack(side="left")
        Btn(row, text="🌐  Audit pages", command=self.audit_pages).pack(side="left", padx=6)
        Btn(row, text="✉  Send approved", style="Primary.TButton",
                   command=self.send).pack(side="right")
        self.warn = tk.Label(self.body, bg=WARN_BG, fg=RED_DARK, font=F(9, "bold"), anchor="w",
                             padx=10, pady=6, cursor="hand2")
        self.warn.bind("<Button-1>", lambda e: self.app.show("settings"))

        mid = tk.Frame(self.body, bg=BG)
        mid.pack(fill="both", expand=True, pady=(12, 0))
        left = card(mid, pad=10)
        left.pack(side="left", fill="both", expand=True)
        fb = tk.Frame(left.inner, bg=CARD)
        fb.pack(fill="x", pady=(0, 8))
        self.filter = tk.StringVar(value="campaigns")
        self.tab_btns = {}
        self.tab_names = {"campaigns": "Campaigns", "draft": "To approve", "approved": "Approved", "sent": "Sent",
                          "failed": "Failed", "cancelled": "Cancelled", "replies": "Replies"}
        for val, txt in self.tab_names.items():
            b = ttk.Radiobutton(fb, text=txt, value=val, variable=self.filter,
                                command=lambda: (self.fill(), self._sel_count()))
            self.tab_btns[val] = b
        fb.bind("<Configure>", lambda e: self._wrap_tabs(e.width))
        self._wrap_tabs(900)
        # selection bar first, at the bottom, so it is always visible
        selbar = tk.Frame(left.inner, bg=SOFT, highlightthickness=1, highlightbackground=BORDER)
        selbar.pack(side="bottom", fill="x", pady=(8, 0))
        sb = tk.Frame(selbar, bg=SOFT)
        sb.pack(fill="x", padx=8, pady=6)
        Btn(sb, text="☑  Select all", command=self.select_all).pack(side="left")
        Btn(sb, text="Clear", command=self.clear_sel).pack(side="left", padx=6)
        self.sel_hint = tk.Label(sb, text="", bg=SOFT, fg=MUTED, font=F(9))
        self.sel_hint.pack(side="left", padx=6)
        self.btn_send_sel = Btn(sb, text="📤  Send selected", style="Primary.TButton",
                                command=self.send_selected)
        self.btn_send_sel.pack(side="right")
        self.btn_approve_all = Btn(sb, text="✓  Approve all", command=self.approve_all)
        fr, self.tree = make_tree(left.inner, [("chk", "", 34), ("biz", "Business", 170), ("to", "To", 190),
                                               ("step", "Email", 80), ("date", "Date", 110)], height=18)
        self.tree.column("chk", width=34, minwidth=34, stretch=False, anchor="center")
        self.tree.heading("chk", text="☐", command=self.toggle_all)
        fr.pack(fill="both", expand=True)
        self.tree.bind("<Button-1>", self._tick_click, add="+")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sel_count(), add="+")
        right = card(mid, None, pad=14)
        right.pack(side="right", fill="both", expand=True, padx=(12, 0), before=left)
        r = right.inner
        head = tk.Frame(r, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="Email", bg=CARD, fg=TEXT, font=F(12, "bold")).pack(side="left")
        tools = tk.Frame(head, bg=CARD)
        tools.pack(side="right")
        Btn(tools, text="👁  Preview", command=self.preview).pack(side="left")
        Btn(tools, text="📎  Attach", command=self.attach).pack(side="left", padx=6)
        Btn(tools, text="👤  Profile", command=self.profile).pack(side="left")
        self.to = tk.StringVar()
        self.subj = tk.StringVar()
        row = tk.Frame(r, bg=CARD)
        row.pack(fill="x", pady=(12, 4))
        tk.Label(row, text="To", bg=CARD, fg=MUTED, width=8, anchor="w").pack(side="left")
        ttk.Entry(row, textvariable=self.to).pack(side="left", fill="x", expand=True)
        row = tk.Frame(r, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Subject", bg=CARD, fg=MUTED, width=8, anchor="w").pack(side="left")
        ttk.Entry(row, textvariable=self.subj).pack(side="left", fill="x", expand=True)
        # status line: why it failed / when it was sent / attachments
        self.att_lbl = tk.Label(r, bg=CARD, fg=MUTED, font=F(9, "bold"), anchor="w", justify="left",
                                padx=10, pady=6)
        self.att_lbl.pack(fill="x", pady=(6, 0))
        # action bar at the bottom: always visible
        bar = tk.Frame(r, bg=CARD)
        bar.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Frame(r, bg=BORDER, height=1).pack(side="bottom", fill="x", pady=(10, 0))
        br = self.left_acts = tk.Frame(bar, bg=CARD)
        br.pack(side="left")
        self.btn_skip = Btn(br, text="✕  Skip", command=lambda: self.set_selected("cancelled"))
        self.btn_skip.pack(side="left")
        self.btn_save = Btn(br, text="💾  Save", command=self.save)
        self.btn_save.pack(side="left", padx=6)
        self.btn_answer = Btn(br, text="✎  Draft an answer", style="Dark.TButton", command=self.answer)
        self.btn_spam = Btn(br, text="🚫  Spam", command=self.mark_spam)
        acts = tk.Frame(bar, bg=CARD)
        acts.pack(side="right")
        self.btn_approve = Btn(acts, text="✓  Approve", style="Dark.TButton", command=self.approve)
        self.btn_approve.pack(side="left", padx=(0, 6))
        self.btn_send1 = Btn(acts, text="📤  Send now", style="Primary.TButton", command=self.send_now, width=14)
        self.btn_send1.pack(side="left")
        self.btn_campaign = Btn(acts, text="📤  Review and send", style="Primary.TButton",
                                command=lambda: self.cur_campaign and self.app.review_batch(self.cur_campaign))
        self.cur_campaign = None
        self.body_t = tk.Text(r, wrap="word", font=F(10), relief="flat", padx=12, pady=10, width=44,
                              highlightthickness=1, highlightbackground=BORDER, height=16)
        self.body_t.pack(fill="both", expand=True, pady=(8, 0))

        self.cur = None
        self.names = {}

    def refresh(self, select=None, view=None, **kw):
        if view:
            self.filter.set(view)
        c = O.counts(self.db)
        s = O.settings(self.app.cfg)
        hrs = "" if not s["business_hours_only"] else ("   ·   sending now: yes" if O.in_business_hours()
                                                       else "   ·   outside US business hours, approved emails wait")
        self.summary.config(text=f"Drafts: {c['_drafts']}   ·   Approved: {c['_approved']}   ·   "
                                 f"Sent today: {c['_sent_today']}/{O.daily_limit(self.db, self.app.cfg)}{hrs}")
        self.update_tab_counts()
        problems = []
        if not S.get_secret(self.app.cfg, "smtp_password"):
            problems.append("connect your email account")
        if problems:
            self.warn.config(text="Before sending: " + " and ".join(problems) + ".  Click to open Settings →")
            self.warn.pack(fill="x", pady=(10, 0), after=self.body.winfo_children()[0])
        else:
            self.warn.pack_forget()
        self.names = {r["domain"]: (r["name"] or r.get("site_name") or r["domain"])
                      for r in self.db.lead_records()}
        if select:
            m = next((m for m in O.messages(self.db) if m["id"] == select), None)
            if m:
                self.filter.set(m["status"] if m["status"] in ("draft", "approved", "sent", "failed", "cancelled") else "draft")
        self.fill(select)
        self._sel_count()

    def update_tab_counts(self):
        """Show how many emails are in each tab, e.g. 'Approved (26)'."""
        n = {st: c for st, c in self.db.q("SELECT status, COUNT(*) FROM messages GROUP BY status")}
        n["replies"] = self.db.q("SELECT COUNT(*) FROM replies WHERE kind != 'spam'")[0][0]
        n["campaigns"] = len(O.campaign_stats(self.db))
        new_r = self.db.q("SELECT COUNT(*) FROM replies WHERE kind != 'spam' AND COALESCE(handled,0)=0")[0][0]
        for val, b in self.tab_btns.items():
            label = f"{self.tab_names[val]} ({n.get(val, 0)})"
            if val == "replies" and new_r:
                label = f"{self.tab_names[val]} ({n['replies']} · {new_r} new)"
            b.config(text=label)

    def fill(self, select=None):
        try:
            self.update_tab_counts()
        except Exception:
            pass
        self.tree.delete(*self.tree.get_children())
        if self.filter.get() == "campaigns":
            self._email_buttons("none")
            for c in O.campaign_stats(self.db):
                waiting = c["draft"] + c["approved"]
                self.tree.insert("", "end", iid=f"c{c['id']}", values=(
                    "", c["name"], f"Sent {c['sent']}/{c['total']}" + (f" · {waiting} waiting" if waiting else "")
                    + (f" · {c['failed']} failed" if c["failed"] else ""),
                    f"👁{c['opened']} ↩{c['replied']}", (c["created"] or "")[:16].replace("T", " ")))
            kids = self.tree.get_children()
            if kids:
                sel = select if select and self.tree.exists(str(select)) else kids[0]
                self.tree.selection_set(sel); self.tree.focus(sel); self.on_select()
            else:
                self.cur = None
                self.to.set(""); self.subj.set("")
                self.body_t.config(state="normal")
                self.body_t.delete("1.0", "end")
                self.body_t.insert("1.0", "No campaigns yet.\n\nGo to Leads, tick the leads you want, click "
                                          "'Email selected', then Send. Or click 'Contact Super + Hot'.")
            return
        if self.filter.get() == "replies":
            self._email_buttons("reply")
            for rid, dom, frm, subj, kind, when, handled in self.db.q(
                    "SELECT id, domain, from_addr, subject, kind, received_at, handled FROM replies "
                    "WHERE kind != 'spam' ORDER BY id DESC"):
                self.tree.insert("", "end", iid=f"r{rid}", values=(
                    "", self.names.get(dom, dom), frm, ai.REPLY_KINDS.get(kind, kind) + (" ✓" if handled else ""),
                    (when or "")[:16].replace("T", " ")))
            kids = self.tree.get_children()
            if kids:
                self.tree.selection_set(kids[0])
                self.tree.focus(kids[0])
                self.on_select()
            else:
                self.cur_reply = None
                self.to.set("")
                self.subj.set("")
                self.body_t.delete("1.0", "end")
                self.body_t.insert("1.0", "No replies from leads yet.")
            return
        for m in O.messages(self.db, self.filter.get()):
            self.tree.insert("", "end", iid=str(m["id"]), values=(
                "☐", self.names.get(m["domain"], m["domain"]), m["to_addr"],
                ("No internet" if O.NET_ERR_RE.search(m.get("error") or "") else "See reason")
                if m["status"] == "failed" else
                ["Again", "First", "Follow-up 1", "Follow-up 2", "Last"][m["step"]] if m["step"] <= 4 else "Check-back",
                (m["sent_at"] or m["created_at"] or "")[:16].replace("T", " ")))
        kids = self.tree.get_children()
        sel = str(select) if select and self.tree.exists(str(select)) else (kids[0] if kids else None)
        if sel:
            self.tree.selection_set(sel)
            self.tree.focus(sel)
            self.tree.see(sel)
            self.on_select()
        else:
            self.cur = None
            self.to.set("")
            self.subj.set("")
            self.body_t.delete("1.0", "end")

    def on_select(self, e=None):
        i = self.tree.focus()
        if not i:
            return
        if i.startswith("c"):
            self.show_campaign(int(i[1:]))
            return
        if i.startswith("r"):
            row = self.db.q("SELECT domain, from_addr, subject, snippet, kind FROM replies WHERE id=?", (int(i[1:]),))
            if not row:
                return
            dom, frm, subj, snip, kind = row[0]
            self.cur = None
            self.cur_reply = {"id": int(i[1:]), "domain": dom, "from": frm, "subject": subj,
                              "text": snip, "kind": kind}
            self.to.set(frm)
            self.subj.set(subj)
            self.body_t.config(state="normal")
            self.body_t.delete("1.0", "end")
            self.body_t.insert("1.0", f"[{ai.REPLY_KINDS.get(kind, kind)}]\n\n{snip}")
            self.body_t.config(state="disabled")
            self.att_lbl.config(text="")
            self._att_vis()
            return
        m = next((m for m in O.messages(self.db) if str(m["id"]) == i), None)
        if not m:
            return
        self.cur = m
        self.to.set(m["to_addr"])
        self.subj.set(m["subject"])
        self.body_t.config(state="normal")      # a disabled box ignores new text: always unlock first
        self.body_t.delete("1.0", "end")
        self.body_t.insert("1.0", m["body"])
        import json as _json
        atts = _json.loads(m.get("attachments") or "[]")
        self.att_lbl.config(text=("📎 Attached: " + ", ".join(os.path.basename(a) for a in atts)) if atts else "",
                            fg=MUTED, bg=SOFT if atts else CARD)
        if m["status"] in ("failed", "cancelled") and m.get("error"):
            self.att_lbl.config(text=("Why it failed: " if m["status"] == "failed" else "Why skipped: ")
                                + O.explain_error(m["error"]), fg=RED_DARK, bg=WARN_BG)
        elif m["status"] == "sent" and m.get("sent_at"):
            sig = O.lead_signals(self.db, m["domain"])
            self.att_lbl.config(text="Sent " + m["sent_at"][:16].replace("T", " ") + "".join(
                f"  ·  {t}" for t, on in (("opened their review", sig["opened"]), ("replied", sig["replied"]),
                                          ("bounced", sig["bounced"])) if on), fg=GREEN, bg=SOFT)
        editable = m["status"] in ("draft", "approved", "failed")
        self.body_t.config(state="normal" if editable else "disabled")
        self._email_buttons(m["status"])
        self._att_vis()

    def _att_vis(self):
        """Show the status strip only when it has something to say."""
        if self.att_lbl.cget("text"):
            self.att_lbl.pack(fill="x", pady=(6, 0), before=self.body_t)
        else:
            self.att_lbl.pack_forget()

    def _wrap_tabs(self, width):
        x, row, col = 0, 0, 0
        for b in self.tab_btns.values():
            w = b.winfo_reqwidth() + 10
            if x and x + w > width:
                row, col, x = row + 1, 0, 0
            b.grid(row=row, column=col, sticky="w", padx=(0, 10), pady=1)
            col += 1
            x += w

    def _email_buttons(self, status):
        """Only show the buttons that make sense for this email."""
        for b in (self.btn_approve, self.btn_send1, self.btn_skip, self.btn_save, self.btn_campaign,
                  self.btn_answer, self.btn_spam):
            b.pack_forget()
        if status == "none":
            return
        if status == "campaign":
            self.btn_campaign.pack(side="left")
            return
        if status == "reply":
            self.btn_answer.pack(side="left")
            self.btn_spam.pack(side="left", padx=6)
            return
        if status in ("draft", "approved", "failed"):
            self.btn_skip.pack(side="left")
            self.btn_save.pack(side="left", padx=6)
        if status in ("draft", "failed"):
            self.btn_approve.pack(side="left", padx=(0, 6))
        verb = {"failed": "↻  Try again", "sent": "📤  Send again", "cancelled": "📤  Send now"}.get(status, "📤  Send now")
        self.btn_send1.config(text=verb)
        self.btn_send1.pack(side="left")

    def _sync_ticks(self):
        sel = set(self.tree.selection())
        for k in self.tree.get_children():
            if k.isdigit():
                self.tree.set(k, "chk", "☑" if k in sel else "☐")
        kids = [k for k in self.tree.get_children() if k.isdigit()]
        self.tree.heading("chk", text="☑" if kids and len(sel) >= len(kids) else "☐")

    def _tick_click(self, e):
        """Click the box: add/remove that email from the selection (no Ctrl needed)."""
        if self.tree.identify_column(e.x) != "#1":
            return
        i = self.tree.identify_row(e.y)
        if not i or not i.isdigit():
            return
        if i in self.tree.selection():
            self.tree.selection_remove(i)
        else:
            self.tree.selection_add(i)
        self.tree.focus(i)
        self._sel_count()
        return "break"

    def clear_sel(self):
        self.tree.selection_set(())
        self._sel_count()

    def toggle_all(self):
        kids = [k for k in self.tree.get_children() if k.isdigit()]
        if kids and len(self.tree.selection()) >= len(kids):
            self.clear_sel()
        else:
            self.select_all()

    def _sel_ids(self):
        return [int(i) for i in self.tree.selection() if i.isdigit()]

    def _sel_count(self):
        n = len(self._sel_ids())
        tab = self.filter.get()
        ok = tab in ("draft", "approved", "failed", "sent", "cancelled")
        verb = {"failed": "Try again", "sent": "Send again"}.get(tab, "Send now")
        self.btn_send_sel.config(text=f"📤  {verb} ({n})" if n else f"📤  {verb}",
                                 state="normal" if ok and n else "disabled")
        if ok:
            self.btn_send_sel.pack(side="right")
        else:
            self.btn_send_sel.pack_forget()
        self.sel_hint.config(text="" if n else "Tick the boxes to pick emails")
        try:
            self._sync_ticks()
        except tk.TclError:
            pass

    def select_all(self):
        kids = [k for k in self.tree.get_children() if k.isdigit()]
        self.tree.selection_set(kids)
        self._sel_count()

    def send_selected(self):
        ids = self._sel_ids()
        if not ids:
            return
        self.save(quiet=True)
        tab = self.filter.get()
        room = max(0, O.daily_limit(self.db, self.app.cfg) - O.sent_today(self.db))
        extra = ""
        if tab == "sent":
            extra = "\n\nThese were already sent once: each lead gets the same email again."
        if len(ids) > room:
            extra += (f"\n\nToday {room} more can go out (daily limit). The other {len(ids) - room} "
                      "go out by themselves on the next days.")
        if not messagebox.askyesno("Send now", f"Send {len(ids)} selected email{'s' if len(ids) != 1 else ''} now?"
                                   f" They go out 1–2 minutes apart, in the background.{extra}"):
            return
        self.app.run_job("Sending emails", lambda: O.send_selected(self.db, self.app.cfg, list(ids)),
                         after=lambda r: r and (self.app.toast(f"{r['sent']} sent" + (
                             f", {r['waiting']} go out on the next days" if r["waiting"] else ""), GREEN),
                             self.refresh()))
        self.app.toast(f"Sending {len(ids)} emails in the background…")
        self.refresh()

    def show_campaign(self, cid):
        """What happened to every email in this campaign."""
        self.cur = None
        self.cur_campaign = cid
        c = next((c for c in O.campaign_stats(self.db) if c["id"] == cid), None)
        if not c:
            return
        ms = O.campaign_messages(self.db, cid)
        waiting = c["draft"] + c["approved"]
        self.to.set(f"{c['total']} leads")
        self.subj.set(c["name"])
        lines = [f"Sent {c['sent']} of {c['total']}   ·   Waiting {waiting}   ·   Opened their review {c['opened']}   ·   "
                 f"Replied {c['replied']}   ·   Bounced {c['bounced']}" + (f"   ·   Failed {c['failed']}" if c["failed"] else ""),
                 ""]
        label = {"draft": "Not sent yet (needs your Send)", "approved": "Queued (goes out within the daily limit)",
                 "failed": "FAILED", "cancelled": "Skipped"}
        for m in ms:
            nm = self.names.get(m["domain"], m["domain"])
            if m["status"] == "sent":
                sig = O.lead_signals(self.db, m["domain"])
                tags = [t for t, on in (("opened review", sig["opened"]), ("REPLIED", sig["replied"]),
                                        ("bounced", sig["bounced"])) if on]
                st = "Sent " + (m["sent_at"] or "")[:16].replace("T", " ") + (" · " + ", ".join(tags) if tags else "")
                mark = "✓"
            else:
                st = label.get(m["status"], m["status"]) + (f": {m['error']}" if m["status"] == "failed" and m.get("error") else "")
                mark = "•"
            lines.append(f"{mark} {nm}  <{m['to_addr']}>\n      {st}")
        self.body_t.config(state="normal")
        self.body_t.delete("1.0", "end")
        self.body_t.insert("1.0", "\n".join(lines))
        self.body_t.config(state="disabled")
        self.att_lbl.config(text="")
        self._att_vis()
        if waiting or c["failed"]:
            self.btn_campaign.config(text=f"📤  Review and send ({waiting + c['failed']})")
            self._email_buttons("campaign")
        else:
            self._email_buttons("none")

    def save(self, quiet=False):
        if not self.cur or self.cur["status"] not in ("draft", "approved", "failed"):
            return
        O.update_message(self.db, self.cur["id"], to_addr=self.to.get().strip(),
                         subject=self.subj.get().strip(), body=self.body_t.get("1.0", "end").rstrip())
        if not quiet:
            self.app.toast("Saved")

    def approve(self):
        if not self.cur:
            return
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.to.get().strip()):
            return messagebox.showwarning("Email", "The To address doesn't look right.")
        self.save(quiet=True)
        O.update_message(self.db, self.cur["id"], status="approved", approved_at=W.now(), error=None)
        self.app.toast("Approved ✓")
        kids = list(self.tree.get_children())
        idx = kids.index(str(self.cur["id"])) if str(self.cur["id"]) in kids else 0
        nxt = kids[idx + 1] if idx + 1 < len(kids) else None
        self.refresh(select=int(nxt) if nxt else None)
        self.filter.set("draft")
        self.fill(int(nxt) if nxt else None)

    def send_now(self):
        """Approve this one email and send it straight away, ahead of the queue."""
        if not self.cur:
            return
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.to.get().strip()):
            return messagebox.showwarning("Email", "The To address doesn't look right.")
        if max(0, O.daily_limit(self.db, self.app.cfg) - O.sent_today(self.db)) <= 0:
            return messagebox.showinfo("Send now", "Today's sending limit is reached. It goes out tomorrow if you approve it.")
        if not messagebox.askyesno("Send now", f"Send this email to {self.to.get().strip()} now?"):
            return
        self.save(quiet=True)
        mid = self.cur["id"]
        O.update_message(self.db, mid, status="approved", approved_at=W.now(), error=None)
        self.app.run_job("Sending emails", lambda: O.send_approved(self.db, self.app.cfg, only_ids=[mid]))
        self.refresh()

    def approve_all(self):
        kids = self.tree.get_children()
        if self.filter.get() != "draft" or not kids:
            return
        if not messagebox.askyesno("Approve all", f"Approve all {len(kids)} drafts shown?\n"
                                   "Tip: read at least a few first."):
            return
        for i in kids:
            O.update_message(self.db, int(i), status="approved", approved_at=W.now())
        self.refresh()

    def set_selected(self, status):
        if self.cur:
            O.update_message(self.db, self.cur["id"], status=status)
            if self.cur["step"] == 1 and status == "cancelled":
                st = O.get_outreach(self.db, self.cur["domain"])
                if st and st["status"] == "draft":
                    O.set_status(self.db, self.cur["domain"], "new")
            self.refresh()

    def profile(self):
        if self.cur:
            self.app.open_profile(self.cur["domain"])

    def bulk_ai(self):
        if not ai.enabled(self.app.cfg):
            return messagebox.showinfo("Gemini", "Add your free Gemini API key in Settings > AI & audit first.")
        if not messagebox.askyesno("Gemini emails", "For up to 25 Super/Hot leads with an email: run the "
                                   "full audit, ask Gemini for a plan and a custom email, and save it as a "
                                   "draft for your approval. Takes about 1 minute per lead. Start?"):
            return
        key = S.get_secret(self.app.cfg, "psi_key")
        self.app.run_job("Gemini emails", lambda: O.ai_draft_many(self.db, self.app.cfg, psi_key=key),
                         after=lambda n: (self.filter.set("draft"), self.refresh()))

    def preview(self):
        if not self.cur:
            return
        self.save(quiet=True)
        m = next((x for x in O.messages(self.db) if x["id"] == self.cur["id"]), self.cur)
        open_url("file:///" + O.preview_file(self.app.cfg, m, self.db).replace(os.sep, "/"))

    def attach(self):
        if not self.cur or self.cur["status"] not in ("draft", "approved", "failed"):
            return messagebox.showinfo("Attach", "Pick a draft first.")
        import json as _json
        mf = A.mockup_file(self.cur["domain"])
        path = filedialog.askopenfilename(title="File to attach (your mockup, a PDF...)",
                                          initialdir=os.path.dirname(mf) if mf else OUT_DIR,
                                          initialfile=os.path.basename(mf) if mf else "")
        if not path:
            return
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return messagebox.showwarning("Attach", "Keep attachments under 5 MB so the email isn't blocked.")
        atts = _json.loads(self.cur.get("attachments") or "[]") + [path]
        O.update_message(self.db, self.cur["id"], attachments=_json.dumps(atts))
        if self.cur["step"] == 1:
            self.app.toast("Tip: attachments in a first email often go to spam. Better in a follow-up.", AMBER)
        self.fill(self.cur["id"])

    def mark_spam(self):
        r = getattr(self, "cur_reply", None)
        if not r:
            return
        d = r["domain"]
        self.db.x("UPDATE replies SET kind='spam', handled=1 WHERE id=?", (r["id"],))
        self.db.x("UPDATE tasks SET done=1 WHERE domain=? AND kind IN ('inquiry','viewed')", (d,))
        if not self.db.q("SELECT 1 FROM messages WHERE domain=? AND status='sent'", (d,)):
            self.db.x("DELETE FROM outreach WHERE domain=?", (d,))      # never a lead conversation
        elif not self.db.q("SELECT 1 FROM replies WHERE domain=? AND kind!='spam'", (d,)):
            O.set_status(self.db, d, "emailed")                         # follow-ups continue
        self.app.toast("Marked as spam. It no longer counts as a reply.")
        self.fill()

    def answer(self):
        r = getattr(self, "cur_reply", None)
        if not r:
            return
        lead = next((x for x in self.db.lead_records("s.domain=?", (r["domain"],))), {"domain": r["domain"]})

        def go():
            return ai.draft_reply(self.app.cfg, lead, r["text"], r["kind"])

        def done(text):
            if not text:
                return
            subj = r["subject"] if r["subject"].lower().startswith("re:") else "Re: " + r["subject"]
            mid = O.make_draft(self.db, self.app.cfg, lead, 0, to_addr=r["from"], subject=subj, body=text)
            self.db.x("UPDATE replies SET handled=1 WHERE id=?", (r["id"],))
            self.filter.set("draft")
            self.refresh(select=mid)
        if ai.enabled(self.app.cfg):
            self.app.run_job("Gemini reply", go, after=done)
        else:
            done(go())

    def bulk(self):
        n = O.draft_for_level(self.db, self.app.cfg)
        self.app.toast(f"{n} new drafts created" if n else "No new Super/Hot leads with an email")
        self.filter.set("draft")
        self.refresh()

    def followups(self):
        n = O.create_due_followups(self.db, self.app.cfg)
        self.app.toast(f"{n} follow-ups ready" if n else "No follow-ups due yet")
        self.filter.set("draft")
        self.refresh()

    def send(self):
        c = O.counts(self.db)
        if not c["_approved"]:
            return messagebox.showinfo("Send", "Approve some emails first.")
        s = O.settings(self.app.cfg)
        if not messagebox.askyesno("Send", f"Send up to {min(c['_approved'], max(0, O.daily_limit(self.db, self.app.cfg) - c['_sent_today']))} "
                                   f"approved emails now?\nThey go out slowly, "
                                   f"{s['delay_min']}-{s['delay_max']} seconds apart."):
            return
        self.app.run_job("Sending emails", lambda: O.send_approved(self.db, self.app.cfg))

    def inbox(self):
        def go():
            res = O.check_inbox(self.db, self.app.cfg)
            if WS.enabled(self.app.cfg):
                try:
                    WS.run_background(self.db, self.app.cfg)
                except Exception as e:
                    W.log(f"Website: {e}")
            return res
        self.app.run_job("Checking inbox", go)

    def audit_pages(self):
        if not WS.enabled(self.app.cfg):
            messagebox.showinfo("Audit pages", "Connect your website first: Settings > Website.")
            return
        if not messagebox.askyesno("Audit pages", "Make a free review page on nadevelopers.com for every lead "
                                   "whose first email is waiting, and add the link to that email?\n\n"
                                   "Leads without an audit get one first (about 30-60 seconds each)."):
            return
        self.app.run_job("Audit pages", lambda: WS.publish_for_drafts(self.db, self.app.cfg),
                         after=lambda n: (self.app.toast(f"{n or 0} emails now link to their free review"),
                                          self.refresh()))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Inbox (your real info@ inbox, read inside the app)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Calls: you phone, the app gives you the script and does the paperwork
# ---------------------------------------------------------------------------
class CallsPage(Page):
    title = "Calls"
    subtitle = "Who to ring today, a script for each lead, one click to log it. You make every call yourself."

    def build(self):
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        self.stats = tk.Label(top, bg=BG, fg=TEXT, font=F(10, "bold"))
        self.stats.pack(side="left")
        self.only_now = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only where it's business hours now", variable=self.only_now,
                        command=self.fill).pack(side="left", padx=16)
        Btn(top, text="✍  Write top 20 scripts", command=self.write_scripts).pack(side="right")

        pw = ttk.Panedwindow(self.body, orient="horizontal")
        pw.pack(fill="both", expand=True)
        lc = card(pw, pad=8)
        fr, self.tree = make_tree(lc.inner, [("name", "Business", 160), ("phone", "Phone", 112),
                                             ("why", "Why call", 170), ("when", "Their time", 125)], height=20)
        fr.pack(fill="both", expand=True)
        self.tree.tag_configure("now", foreground=TEXT)
        self.tree.tag_configure("later", foreground=MUTED)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pw.add(lc, weight=2)

        rc = card(pw, pad=14)
        pw.add(rc, weight=3)
        r = rc.inner
        head = tk.Frame(r, bg=CARD)
        head.pack(fill="x")
        self.h_name = tk.Label(head, bg=CARD, fg=TEXT, font=F(14, "bold"), anchor="w")
        self.h_name.pack(side="left")
        tools = tk.Frame(head, bg=CARD)
        tools.pack(side="right")
        Btn(tools, text="↻  New script", command=lambda: self.load_script(refresh=True)).pack(side="left")
        Btn(tools, text="👤  Profile", command=self.profile).pack(side="left", padx=6)
        Btn(tools, text="Website", command=lambda: self.lead and open_url(
            self.lead.get("final_url") or self.lead.get("website"))).pack(side="left")
        prow = tk.Frame(r, bg=CARD)
        prow.pack(fill="x", pady=(8, 0))
        self.phone_v = tk.StringVar()
        self.phone_box = ttk.Combobox(prow, textvariable=self.phone_v, width=18, state="readonly", font=F(12))
        self.phone_box.pack(side="left")
        self.btn_call = Btn(prow, text="📞  Call now", style="Primary.TButton", command=self.dial, width=12)
        self.btn_call.pack(side="left", padx=8)
        Btn(prow, text="📋  Copy number", command=self.copy_number).pack(side="left")
        self.h_time = tk.Label(r, bg=CARD, fg=MUTED, font=F(10, "bold"), anchor="w")
        self.h_time.pack(fill="x", pady=(6, 0))
        self.h_info = tk.Label(r, bg=CARD, fg=MUTED, font=F(9), anchor="w", justify="left")
        self.h_info.pack(fill="x", pady=(6, 0))

        # log the call (bottom)
        log = tk.Frame(r, bg=SOFT, highlightthickness=1, highlightbackground=BORDER)
        log.pack(side="bottom", fill="x", pady=(10, 0))
        li = tk.Frame(log, bg=SOFT)
        li.pack(fill="x", padx=12, pady=10)
        tk.Label(li, text="How did it go?", bg=SOFT, fg=TEXT, font=F(10, "bold")).grid(row=0, column=0, sticky="w")
        self.outcome = tk.StringVar(value="")
        grid = tk.Frame(li, bg=SOFT)
        grid.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 6))
        for i, (k, lab) in enumerate(C.OUTCOMES):
            ttk.Radiobutton(grid, text=lab, value=k, variable=self.outcome,
                            command=self._outcome_changed).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 14))
        nr = tk.Frame(li, bg=SOFT)
        nr.grid(row=2, column=0, columnspan=3, sticky="we")
        li.columnconfigure(0, weight=1)
        tk.Label(nr, text="Notes", bg=SOFT, fg=MUTED).pack(side="left")
        self.notes_v = tk.StringVar()
        ttk.Entry(nr, textvariable=self.notes_v).pack(side="left", fill="x", expand=True, padx=6)
        self.cb_frame = tk.Frame(nr, bg=SOFT)
        tk.Label(self.cb_frame, text="Call back on", bg=SOFT, fg=MUTED).pack(side="left")
        self.cb_v = tk.StringVar()
        ttk.Entry(self.cb_frame, textvariable=self.cb_v, width=11).pack(side="left", padx=4)
        br = tk.Frame(li, bg=SOFT)
        br.grid(row=3, column=0, columnspan=3, sticky="we", pady=(8, 0))
        self.draft_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(br, text="Draft a follow-up email for me", variable=self.draft_v).pack(side="left")
        self.btn_log = Btn(br, text="✓  Save call  →  next", style="Primary.TButton", command=self.save_call)
        self.btn_log.pack(side="right")

        self.script = tk.Text(r, wrap="word", font=F(11), relief="flat", padx=14, pady=10, width=60,
                              highlightthickness=1, highlightbackground=BORDER, height=14, spacing1=2, spacing3=2)
        self.script.pack(fill="both", expand=True, pady=(10, 0))
        self.script.tag_configure("h", font=F(10, "bold"), foreground=TEAL, spacing1=10)
        self.script.tag_configure("b", font=F(11))
        self.script.tag_configure("m", font=F(9), foreground=MUTED)
        self.rows, self.lead = {}, None

    # ---------- list ----------
    def refresh(self, select=None, **kw):
        self.fill(select)

    def fill(self, select=None):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        items = C.call_list(self.db)
        if select and select not in {r["domain"] for r in items}:
            lead = next((x for x in self.db.lead_records() if x["domain"] == select), None)
            if lead and C.phones(lead):
                ok, when = C.good_time(lead)
                items.insert(0, {"domain": select, "name": lead.get("name") or select, "phone": C.phones(lead)[0],
                                 "why": "Picked from profile", "when": when, "ok_now": ok})
        for it in items:
            if self.only_now.get() and not it["ok_now"]:
                continue
            self.rows[it["domain"]] = it
            self.tree.insert("", "end", iid=it["domain"], tags=("now" if it["ok_now"] else "later",),
                             values=(it["name"], C.pretty(it["phone"]), it["why"],
                                     ("✓ " if it["ok_now"] else "") + (it["when"] or "")))
        st = C.stats_today(self.db)
        self.stats.config(text=f"To call: {len(self.rows)}   ·   Today: {st['calls']} calls, "
                               f"{st['talked']} conversations, {st['booked']} interested or booked")
        kids = self.tree.get_children()
        target = select if select and self.tree.exists(select) else (kids[0] if kids else None)
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self.on_select()
        else:
            self._show_empty()

    def _show_empty(self):
        self.lead = None
        self.h_name.config(text="Nobody to call right now")
        self.script.config(state="normal")
        self.script.delete("1.0", "end")
        self.script.insert("1.0", "Leads with a phone number show up here once they're Super or Hot, "
                                  "after you email them, or when they open their free review.", "m")
        self.script.config(state="disabled")

    def on_select(self, e=None):
        dom = self.tree.focus()
        if not dom:
            return
        self.lead = next((x for x in self.db.lead_records() if x["domain"] == dom), None)
        if not self.lead:
            return
        it = self.rows.get(dom, {})
        nums = C.phones(self.lead)
        self.h_name.config(text=C.clean_name(self.lead))
        self.phone_box.config(values=[C.pretty(n) for n in nums])
        self.phone_v.set(C.pretty(nums[0]) if nums else "")
        ok, when = C.good_time(self.lead)
        self.h_time.config(text=(("✓ Good time: " if ok else "⚠ Outside business hours: ") + when) if when else "",
                           fg=GREEN if ok else AMBER)
        st = (O.get_outreach(self.db, dom) or {}).get("status") or "new"
        hist = C.history(self.db, dom)
        last = hist[0] if hist else None
        info = [f"{W.LEVELS.get(self.lead['level'], (self.lead['level'],))[0]} lead · {O.STATUS_LABELS.get(st, st)}"
                f" · {self.lead.get('city') or ''} {self.lead.get('region') or ''}".strip(),
                f"Why call: {it.get('why', '')}"]
        if last:
            info.append(f"Last call {last['called_at'][:16].replace('T', ' ')}: "
                        f"{C.OUTCOME_LABELS.get(last['outcome'], last['outcome'])}"
                        + (f" — {last['notes']}" if last["notes"] else "") + f"  ({len(hist)} call{'s' if len(hist) > 1 else ''})")
        self.h_info.config(text="\n".join(info))
        self.outcome.set("")
        self.notes_v.set("")
        self.cb_v.set((dt.date.today() + dt.timedelta(days=2)).isoformat())
        self._outcome_changed()
        self.load_script()

    # ---------- script ----------
    def load_script(self, refresh=False):
        if not self.lead:
            return
        lead = self.lead
        r = self.db.q("SELECT data, source FROM call_scripts WHERE domain=?", (lead["domain"],))
        if r and not refresh:
            return self.show_script(json.loads(r[0][0]), r[0][1])
        self.script.config(state="normal")
        self.script.delete("1.0", "end")
        self.script.insert("1.0", "Writing the call script" + (" with Gemini…" if ai.enabled(self.app.cfg) else "…"), "m")
        self.script.config(state="disabled")

        def work():
            try:
                sc, src = C.get_script(self.db, self.app.cfg, lead, refresh=refresh)
                self.app.root.after(0, lambda: self.lead and self.lead["domain"] == lead["domain"]
                                    and self.show_script(sc, src))
            except Exception as ex:
                self.app.root.after(0, lambda: self.app.toast(f"Script failed: {ex}"))
        threading.Thread(target=work, daemon=True).start()

    def show_script(self, sc, src):
        t = self.script
        t.config(state="normal")
        t.delete("1.0", "end")
        t.insert("end", ("Written by Gemini for this business" if src == "ai" else
                         "Written from what the bot found on their site (add a Gemini key for a fully custom script)")
                 + "\n", "m")
        for h, body in C.script_text(sc):
            t.insert("end", h.upper() + "\n", "h")
            t.insert("end", body + "\n", "b")
        t.config(state="disabled")
        t.yview_moveto(0)

    def write_scripts(self):
        doms = list(self.rows)[:20]
        if not doms:
            return
        leads = [x for x in self.db.lead_records() if x["domain"] in set(doms)]

        def work():
            n = 0
            for i, lead in enumerate(leads):
                if W.stopping():
                    break
                W.progress(phase="ai", done=i, total=len(leads), label=f"Call script: {lead.get('name') or lead['domain']}")
                if not self.db.q("SELECT 1 FROM call_scripts WHERE domain=?", (lead["domain"],)):
                    C.get_script(self.db, self.app.cfg, lead)
                    n += 1
            return n
        self.app.run_job("Writing call scripts", work,
                         after=lambda n: self.app.toast(f"{n or 0} call scripts written", GREEN))

    # ---------- calling ----------
    def _digits(self):
        return re.sub(r"\D", "", self.phone_v.get())[-10:]

    def dial(self):
        d = self._digits()
        if len(d) != 10:
            return
        ok, when = C.good_time(self.lead or {})
        if not ok and when and not messagebox.askyesno(
                "Call now?", f"It's {when}, outside normal business hours. Call anyway?"):
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(C.tel(d))
            else:
                open_url(C.tel(d))
            self.app.toast(f"Opening your calling app for {C.pretty(d)}… After the call, pick how it went below.")
        except Exception:
            self.copy_number()
            messagebox.showinfo("Call", "No calling app is set up for phone links on this PC, so the number is "
                                        "copied. Paste it into your calling app (WhatsApp, Viber, Zoom Phone…).")

    def copy_number(self):
        d = self._digits()
        if d:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append("+1" + d)
            self.app.toast(f"Copied +1{d}")

    def _outcome_changed(self):
        if self.outcome.get() == "call_back":
            self.cb_frame.pack(side="left", padx=(8, 0))
        else:
            self.cb_frame.pack_forget()
        self.btn_log.config(state="normal" if self.outcome.get() and self.lead else "disabled")

    def save_call(self):
        if not self.lead or not self.outcome.get():
            return
        out = self.outcome.get()
        cb = self.cb_v.get().strip() if out == "call_back" else None
        if cb:
            try:
                dt.date.fromisoformat(cb)
            except ValueError:
                return messagebox.showwarning("Call back", "Use the date format 2026-12-01.")
        if out == "do_not_call" and not messagebox.askyesno(
                "Do not contact", "Mark this lead Do not contact? No more calls or emails will go to them."):
            return
        r = C.log_call(self.db, self.app.cfg, self.lead, self._digits(), out, self.notes_v.get(), cb,
                       draft_email=self.draft_v.get())
        self.app.toast("Saved. " + " · ".join(r["done"]), GREEN)
        kids = list(self.tree.get_children())
        cur = self.lead["domain"]
        nxt = kids[kids.index(cur) + 1] if cur in kids and kids.index(cur) + 1 < len(kids) else None
        self.fill(nxt)

    def profile(self):
        if self.lead:
            self.app.show("leads", select=self.lead["domain"])



class InboxPage(Page):
    title = "Inbox"
    subtitle = "Your email inbox. Emails from your leads are marked, so you see who really replied."

    def build(self):
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", pady=(0, 10))
        Btn(top, text="⟳  Refresh", style="Primary.TButton", command=self.load).pack(side="left")
        self.show_var = tk.StringVar(value="leads")
        self.show_btns = {}
        self.show_names = {"leads": "From my leads", "all": "Everything", "other": "Not from leads"}
        for val, lab in self.show_names.items():
            b = ttk.Radiobutton(top, text=lab, value=val, variable=self.show_var, command=self.fill)
            b.pack(side="left", padx=(14, 0))
            self.show_btns[val] = b
        self.status = tk.Label(top, bg=BG, fg=MUTED, font=F(9))
        self.status.pack(side="right")
        pw = ttk.Panedwindow(self.body, orient="horizontal")
        pw.pack(fill="both", expand=True)
        lc = card(pw, pad=0)
        fr, self.tree = make_tree(lc.inner, [("when", "When", 115), ("from", "From", 210),
                                             ("subject", "Subject", 300), ("lead", "Lead", 160)], height=20)
        fr.pack(fill="both", expand=True)
        self.tree.tag_configure("lead", background=LEVEL_TINT.get("super", CARD))
        self.tree.tag_configure("unread", font=F(10, "bold"))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pw.add(lc, weight=3)
        rc = card(pw)
        pw.add(rc, weight=2)
        self.h_from = tk.Label(rc.inner, bg=CARD, fg=TEXT, font=F(11, "bold"), anchor="w", justify="left",
                               wraplength=420)
        self.h_from.pack(anchor="w")
        self.h_subj = tk.Label(rc.inner, bg=CARD, fg=MUTED, font=F(10), anchor="w", justify="left",
                               wraplength=420)
        self.h_subj.pack(anchor="w", pady=(2, 6))
        self.h_lead = tk.Frame(rc.inner, bg=CARD)
        self.h_lead.pack(anchor="w", fill="x")
        self.text = tk.Text(rc.inner, wrap="word", font=F(10), bg=SOFT, fg=TEXT, relief="flat",
                            padx=10, pady=8, height=16)
        self.text.pack(fill="both", expand=True, pady=(8, 8))
        self.acts = tk.Frame(rc.inner, bg=CARD)
        self.acts.pack(fill="x")
        self.items = []
        self.cur = None

    def refresh(self, **kw):
        s = O.settings(self.app.cfg)
        if not (s.get("imap_host") and S.get_secret(self.app.cfg, "smtp_password")):
            self.status.config(text="")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", "Connect your email first: Settings > Email account.\n\nThen your "
                                    "info@nadevelopers.com inbox shows here, with emails from your leads marked.")
            return
        if not self.items:
            self.load()

    def load(self):
        try:
            O.clean_false_replies(self.db)
        except Exception:
            pass
        self.status.config(text="Loading your inbox…")

        def go():
            return O.inbox_list(self.db, self.app.cfg, limit=120)

        def done(items):
            self.items = items or []
            self.fill()
        self.app.run_job("Loading inbox", go, after=done)

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        show = self.show_var.get()
        names = {r["domain"]: (r["name"] or r["domain"]) for r in self.db.lead_records()}
        n_leads = 0
        for i, m in enumerate(self.items):
            is_lead = bool(m["lead"]) and not m["auto"]
            n_leads += is_lead
            if (show == "leads" and not is_lead) or (show == "other" and is_lead):
                continue
            tags = (("lead",) if is_lead else ()) + (("unread",) if m["unread"] else ())
            who = m["name"] if m["name"] == m["from"] else f"{m['name']} <{m['from']}>"
            lead = names.get(m["lead"], m["lead"] or "") + (" (auto-reply)" if m["auto"] and m["lead"] else "")
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(m["date"], who, m["subject"], lead or "—"))
        n_unread_leads = sum(1 for m in self.items if m["lead"] and not m["auto"] and m["unread"])
        cnt = {"leads": n_leads, "all": len(self.items), "other": len(self.items) - n_leads}
        for val, b in self.show_btns.items():
            extra = f" · {n_unread_leads} unread" if val == "leads" and n_unread_leads else ""
            b.config(text=f"{self.show_names[val]} ({cnt[val]}{extra})")
        self.status.config(text=f"{len(self.items)} newest emails · {n_leads} from leads")
        if show == "leads" and not n_leads and self.items:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", "No emails from your leads yet.\n\nSwitch to 'Everything' to see your whole "
                                    "inbox. If a lead wrote from an address the app didn't recognise, open "
                                    "the email and click 'This is from a lead'.")

    def on_select(self, e=None):
        sel = self.tree.selection()
        if not sel:
            return
        m = self.items[int(sel[0])]
        self.cur = dict(m)
        self.h_from.config(text=f"{m['name']}  <{m['from']}>" if m["name"] != m["from"] else m["from"])
        self.h_subj.config(text=f"{m['subject']}   ·   {m['date']}")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "Opening…")
        self._lead_bar()

        def go():
            return O.inbox_read(self.app.cfg, m["uid"])

        def done(full):
            if full and self.cur and self.cur["uid"] == m["uid"]:
                self.cur["text"] = full["text"]
                self.text.delete("1.0", "end")
                self.text.insert("1.0", full["text"] or "(empty)")
        def worker():
            try:
                r = go()
            except Exception as e:
                r = {"text": f"Couldn't open this email: {e}"}
            self.app.q.put(("call", lambda: done(r)))
        threading.Thread(target=worker, daemon=True).start()

    def _lead_bar(self):
        for w in self.h_lead.winfo_children():
            w.destroy()
        for w in self.acts.winfo_children():
            w.destroy()
        m = self.cur
        lead = next(iter(self.db.lead_records("s.domain=?", (m["lead"],))), None) if m.get("lead") else None
        if lead:
            st = (O.get_outreach(self.db, lead["domain"]) or {}).get("status", "new")
            badge(self.h_lead, "LEAD", RED).pack(side="left")
            tk.Label(self.h_lead, text=f"  {lead['name'] or lead['domain']}  ·  status: "
                     f"{O.STATUS_LABELS.get(st, st)}", bg=CARD, fg=TEXT, font=F(9, "bold")).pack(side="left")
            if m["auto"]:
                tk.Label(self.h_lead, text="  (automatic reply, not counted)", bg=CARD, fg=MUTED,
                         font=F(9)).pack(side="left")
            Btn(self.acts, text="✦  Reply with Gemini", style="Primary.TButton",
                command=lambda: self.reply(lead)).pack(side="left")
            Btn(self.acts, text="Open lead", command=lambda: self.app.open_profile(lead["domain"])).pack(
                side="left", padx=6)
            Btn(self.acts, text="Not a reply", command=lambda: self.not_reply(lead)).pack(side="left")
        else:
            tk.Label(self.h_lead, text="Not from one of your leads", bg=CARD, fg=MUTED, font=F(9)).pack(side="left")
            Btn(self.acts, text="This is from a lead…", style="Primary.TButton",
                command=self.link_to_lead).pack(side="left")
            Btn(self.acts, text="Reply in my email app",
                command=lambda: open_url(f"mailto:{m['from']}?subject=Re: {m['subject']}")).pack(side="left", padx=6)

    def reply(self, lead):
        m = self.cur
        text = m.get("text") or self.text.get("1.0", "end")
        kind = "interested"

        def go():
            k = ai.classify(self.app.cfg, f"Subject: {m['subject']}\n{text}")
            return k, ai.draft_reply(self.app.cfg, lead, text, k)

        def done(res):
            if not res:
                return
            k, body = res
            subj = m["subject"] if m["subject"].lower().startswith("re:") else "Re: " + m["subject"]
            mid = O.make_draft(self.db, self.app.cfg, lead, 0, to_addr=m["from"], subject=subj, body=body)
            self.app.toast("Reply drafted. Check it in Outreach, then approve and send.")
            self.app.show("outreach", view="draft", select=mid)
        if ai.enabled(self.app.cfg):
            self.app.run_job("Gemini reply", go, after=done)
        else:
            done((kind, ai.draft_reply(self.app.cfg, lead, text, kind)))

    def not_reply(self, lead):
        d = lead["domain"]
        self.db.x("DELETE FROM replies WHERE domain=? AND from_addr=?", (d, self.cur["from"]))
        st = (O.get_outreach(self.db, d) or {}).get("status")
        if st in ("replied", "later", "lost") and not self.db.q("SELECT 1 FROM replies WHERE domain=?", (d,)):
            O.set_status(self.db, d, "emailed")
        self.cur["lead"] = None
        for it in self.items:
            if it["from"] == self.cur["from"]:
                it["lead"] = None
        self.app.toast("OK, not counted as a reply. Follow-ups continue.")
        self.fill()
        self._lead_bar()

    def link_to_lead(self):
        rows = self.db.q("SELECT o.domain, o.status FROM outreach o WHERE o.status NOT IN ('new','draft')")
        names = {r["domain"]: (r["name"] or r["domain"]) for r in self.db.lead_records()}
        opts = sorted(((names.get(d, d), d) for d, _ in rows), key=lambda x: x[0].lower())
        if not opts:
            return messagebox.showinfo("Inbox", "You haven't emailed any leads yet.")
        win = tk.Toplevel(self.app.root)
        win.title("Which lead is this from?")
        win.configure(bg=CARD)
        win.transient(self.app.root)
        tk.Label(win, text=f"{self.cur['from']} wrote. Which lead is it?", bg=CARD, fg=TEXT,
                 font=F(10, "bold")).pack(padx=16, pady=(14, 6), anchor="w")
        var = tk.StringVar(value=opts[0][0])
        cb = ttk.Combobox(win, textvariable=var, values=[o[0] for o in opts], width=44, state="readonly")
        cb.pack(padx=16)

        def ok():
            dom = dict(opts).get(var.get())
            win.destroy()
            if not dom:
                return
            m = self.cur
            text = m.get("text") or ""
            kind = ai.classify(self.app.cfg, f"Subject: {m['subject']}\n{text}")
            self.db.x("INSERT OR IGNORE INTO replies (domain, from_addr, subject, snippet, kind, received_at)"
                      " VALUES (?,?,?,?,?,?)", (dom, m["from"], m["subject"], text[:3000], kind, W.now()))
            O.set_status(self.db, dom, {"unsubscribe": "unsubscribed", "no": "lost", "later": "later"}.get(kind, "replied"))
            for it in self.items:
                if it["from"] == m["from"]:
                    it["lead"] = dom
            self.cur["lead"] = dom
            self.app.toast(f"Linked to {var.get()}: {ai.REPLY_KINDS.get(kind, kind)}")
            self.fill()
            self._lead_bar()
        Btn(win, text="Link", style="Primary.TButton", command=ok).pack(padx=16, pady=14, anchor="e")


class PipelinePage(Page):
    title = "Pipeline"
    subtitle = "Everyone you've contacted, from first email to won."

    COLS = [("draft", "Draft ready"), ("emailed", "Emailed"), ("replied", "Replied"),
            ("call_booked", "Call booked"), ("proposal_sent", "Proposal sent"),
            ("won", "Won"), ("lost", "Lost / closed")]

    def build(self):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x")
        self.boxes = {}
        self.filter = None
        for i, (key, label) in enumerate(self.COLS):
            c = card(row, pad=10)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            row.columnconfigure(i, weight=1)
            col = STATUS_COLOR.get(key, MUTED)
            tk.Frame(c.inner, bg=col, height=4).pack(fill="x", pady=(0, 6))
            v = tk.Label(c.inner, text="0", bg=CARD, fg=col, font=F(20, "bold"), cursor="hand2")
            v.pack(anchor="w")
            lb = tk.Label(c.inner, text=label, bg=CARD, fg=MUTED, font=F(9), cursor="hand2")
            lb.pack(anchor="w")
            for w in (c, c.inner, v, lb):
                w.bind("<Button-1>", lambda e, k=key: self.set_filter(k))
            self.boxes[key] = (c, v)
        lc = card(self.body, pad=10)
        lc.pack(fill="both", expand=True, pady=(12, 0))
        bar = tk.Frame(lc.inner, bg=CARD)
        bar.pack(fill="x", pady=(0, 8))
        self.flabel = tk.Label(bar, text="All", bg=CARD, font=F(11, "bold"))
        self.flabel.pack(side="left")
        Btn(bar, text="Show all", command=lambda: self.set_filter(None)).pack(side="left", padx=10)
        Btn(bar, text="Open profile", command=self.open).pack(side="right")
        Btn(bar, text="Call brief", command=self.brief).pack(side="right", padx=4)
        for key, label in (("won", "Won"), ("lost", "Lost"), ("later", "Not now"), ("proposal_sent", "Proposal sent"),
                           ("call_booked", "Call booked"), ("replied", "Replied")):
            Btn(bar, text=f"→ {label}", command=lambda k=key: self.move(k)).pack(side="right", padx=2)
        fr, self.tree = make_tree(lc.inner, [("level", "Level", 85), ("biz", "Business", 230),
                                             ("email", "Email", 200), ("status", "Status", 110),
                                             ("step", "Emails sent", 85), ("last", "Last contact", 120),
                                             ("notes", "Notes", 220)], height=16)
        fr.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.open())

    def set_filter(self, k):
        self.filter = k
        self.flabel.config(text=dict(self.COLS).get(k, "All") if k else "All")
        self.refresh()

    def refresh(self, **kw):
        c = O.counts(self.db)
        for key, (box, v) in self.boxes.items():
            n = c.get(key, 0)
            if key == "lost":
                n = sum(c.get(x, 0) for x in ("lost", "no_reply", "unsubscribed", "bounced", "do_not_contact"))
            v.config(text=str(n))
            box.config(highlightbackground=TEAL if self.filter == key else BORDER,
                       highlightthickness=2 if self.filter == key else 1)
        recs = {r["domain"]: r for r in self.db.lead_records()}
        self.tree.delete(*self.tree.get_children())
        for o in self.db.q("SELECT domain, status, step, to_addr, last_sent_at, notes FROM outreach"
                           " ORDER BY updated_at DESC"):
            dom, st, step, to, last, notes = o
            if self.filter == "lost":
                if st not in ("lost", "no_reply", "unsubscribed", "bounced", "do_not_contact"):
                    continue
            elif self.filter and st != self.filter:
                continue
            r = recs.get(dom, {})
            lvl = r.get("level", "normal")
            self.tree.insert("", "end", iid=dom, tags=(lvl,), values=(
                level_text(lvl), r.get("name") or r.get("site_name") or dom, to or "",
                O.STATUS_LABELS.get(st, st), step or 0, (last or "")[:16].replace("T", " "),
                (notes or "").replace("\n", " ")[:80]))

    def move(self, status):
        for d in self.tree.selection():
            O.set_status(self.db, d, status)
        self.refresh()

    def open(self):
        d = self.tree.focus()
        if d:
            self.app.open_profile(d)

    def brief(self):
        d = self.tree.focus()
        lead = next((r for r in self.db.lead_records("s.domain=?", (d,))), None) if d else None
        if lead:
            path = A.call_brief(self.db, self.app.cfg, lead)
            open_url("file:///" + path.replace(os.sep, "/"))


# ---------------------------------------------------------------------------
# Coverage (what has been searched)
# ---------------------------------------------------------------------------
class CoveragePage(Page):
    title = "Coverage"
    subtitle = "Which states and categories you've already searched."

    def build(self):
        top = card(self.body, pad=12)
        top.pack(fill="x")
        self.sumlbl = tk.Label(top.inner, bg=CARD, font=F(10), anchor="w")
        self.sumlbl.pack(side="left")
        Btn(top.inner, text="Allow searching selected again", command=self.clear).pack(side="right")
        lc = card(self.body, pad=10)
        lc.pack(fill="both", expand=True, pady=(12, 0))
        f = tk.Frame(lc.inner, bg=CARD)
        f.pack(fill="both", expand=True)
        cols = [("done", "Categories done", 120), ("src", "Source", 120), ("biz", "Businesses", 100),
                ("wix", "Wix found", 90), ("when", "Last searched", 140), ("st", "Status", 90)]
        self.tree = ttk.Treeview(f, columns=[c[0] for c in cols], show="tree headings", height=20)
        self.tree.heading("#0", text="State / category")
        self.tree.column("#0", width=280)
        for k, l, w in cols:
            self.tree.heading(k, text=l)
            self.tree.column(k, width=w, anchor="w")
        vsb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("done", foreground=GREEN)
        self.tree.tag_configure("bad", foreground=RED)

    def refresh(self, **kw):
        self.tree.delete(*self.tree.get_children())
        jobs = self.db.job_table()
        by = {}
        for j in jobs:
            by.setdefault(j["region"], []).append(j)
        ncat = len(self.app.cats)
        for reg in [r for r in W.REGIONS if r in by] + [r for r in by if r not in W.REGIONS]:
            js = by[reg]
            done = {j["category"] for j in js if j["status"] == "done"}
            node = self.tree.insert("", "end", iid=reg, text=W.REGIONS.get(reg, reg),
                                    values=(f"{len(done & set(self.app.cats))} / {ncat}", "",
                                            sum(j["businesses"] or 0 for j in js),
                                            sum(j["wix"] or 0 for j in js),
                                            max((j["finished_at"] or "") for j in js)[:16].replace("T", " "), ""),
                                    tags=("done",) if done else ())
            for j in sorted(js, key=lambda j: j["category"]):
                self.tree.insert(node, "end", iid=f"{reg}|{j['category']}|{j['source']}",
                                 text=self.app.pages["leads"].cat_label(j["category"]),
                                 values=("", j["source"], j["businesses"] or 0, j["wix"] or 0,
                                         (j["finished_at"] or "")[:16].replace("T", " "), j["status"]),
                                 tags=("done",) if j["status"] == "done" else ("bad",) if j["status"] == "failed" else ())
        regs_done = sum(1 for r in by if any(j["status"] == "done" for j in by[r]))
        self.sumlbl.config(text=f"{regs_done} of {len(W.REGIONS)} states/provinces started   ·   "
                                f"{sum(1 for j in jobs if j['status'] == 'done')} searches finished")

    def clear(self):
        sel = self.tree.selection()
        if not sel:
            return messagebox.showinfo("Coverage", "Select a state or a category row first.")
        if not messagebox.askyesno("Search again", "Mark the selected searches as not done, so "
                                   "they run again next time? (Leads you found are kept.)"):
            return
        for i in sel:
            if "|" in i:
                reg, cat, src = i.split("|")
                self.db.x("DELETE FROM jobs WHERE region=? AND category=? AND source=?", (reg, cat, src))
            else:
                self.db.clear_jobs(i)
        self.refresh()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SettingsPage(Page):
    title = "Settings"
    subtitle = "Email account, your details, templates and security."

    def build(self):
        nb = ttk.Notebook(self.body)
        nb.pack(fill="both", expand=True)
        self.vars = {}
        # --- email account
        t1 = tk.Frame(nb, bg=CARD)
        nb.add(t1, text="  Email account  ")
        f = tk.Frame(t1, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20)
        tk.Label(f, text="The bot sends from your own mailbox, so replies land in your normal inbox.\n"
                 "Use an APP PASSWORD, not your real password: Google: myaccount.google.com > Security > "
                 "2-Step Verification > App passwords.\nMicrosoft 365: your admin must allow 'Authenticated SMTP'. "
                 "Zoho: Settings > Security > App passwords.", bg=CARD, fg=MUTED, justify="left",
                 font=F(9)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self.provider = tk.StringVar()
        tk.Label(f, text="Provider", bg=CARD).grid(row=1, column=0, sticky="w", pady=4)
        cb = ttk.Combobox(f, textvariable=self.provider, values=list(O.PROVIDERS), state="readonly", width=32)
        cb.grid(row=1, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self.pick_provider)
        Btn(f, text="Detect from my email address", command=self.detect).grid(
            row=1, column=2, sticky="w", padx=8)
        r = 2
        for key, label, w in (("email", "Email address", 34), ("smtp_host", "SMTP server", 34),
                              ("smtp_port", "SMTP port", 8), ("imap_host", "IMAP server", 34),
                              ("imap_port", "IMAP port", 8)):
            tk.Label(f, text=label, bg=CARD).grid(row=r, column=0, sticky="w", pady=4)
            v = self.vars[key] = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=w).grid(row=r, column=1, sticky="w")
            r += 1
        tk.Label(f, text="App password", bg=CARD).grid(row=r, column=0, sticky="w", pady=4)
        self.apppw = tk.StringVar()
        ttk.Entry(f, textvariable=self.apppw, show="•", width=34).grid(row=r, column=1, sticky="w")
        self.pwstate = tk.Label(f, bg=CARD, fg=MUTED, font=F(9))
        self.pwstate.grid(row=r, column=2, sticky="w", padx=8)
        r += 1
        bf = tk.Frame(f, bg=CARD)
        bf.grid(row=r, column=1, sticky="w", pady=(14, 0))
        Btn(bf, text="Save", style="Primary.TButton", command=self.save_email).pack(side="left")
        Btn(bf, text="Save + send me a test email", command=self.test_email).pack(side="left", padx=8)

        # --- your details
        t2 = tk.Frame(nb, bg=CARD)
        nb.add(t2, text="  Your details  ")
        f = tk.Frame(t2, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20)
        r = 0
        for key, label in (("sender_name", "Your name"), ("company", "Company"),
                           ("website", "Website"), ("calendly", "Booking link")):
            tk.Label(f, text=label, bg=CARD).grid(row=r, column=0, sticky="w", pady=4)
            v = self.vars[key] = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=44).grid(row=r, column=1, sticky="w")
            r += 1
        tk.Label(f, text="Postal address", bg=CARD).grid(row=r, column=0, sticky="nw", pady=4)
        self.addr = tk.Text(f, width=44, height=3, font=F(10), relief="flat", highlightthickness=1,
                            highlightbackground=BORDER)
        self.addr.grid(row=r, column=1, sticky="w", pady=4)
        tk.Label(f, text="Required by US law (CAN-SPAM) in every sales email.\nShown only in the "
                 "email footer. A PO box or registered\nbusiness address is fine.", bg=CARD, fg=MUTED,
                 font=F(8), justify="left").grid(row=r, column=2, sticky="nw", padx=10)
        r += 1
        for key, label, lo, hi in (("daily_limit", "Emails per day", 1, 200),
                                   ("delay_min", "Wait between emails (min sec)", 10, 900),
                                   ("delay_max", "Wait between emails (max sec)", 10, 1800)):
            tk.Label(f, text=label, bg=CARD).grid(row=r, column=0, sticky="w", pady=4)
            v = self.vars[key] = tk.StringVar()
            ttk.Spinbox(f, from_=lo, to=hi, textvariable=v, width=8).grid(row=r, column=1, sticky="w")
            r += 1
        self.warm = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Warm up: start at 25 a day and add 5 each day up to 'Emails per day' "
                        "(drops back to 25 if many emails bounce)", variable=self.warm).grid(
            row=r, column=1, columnspan=2, sticky="w", pady=4)
        self.bh = tk.BooleanVar()
        ttk.Checkbutton(f, text="Only send Mon–Fri, 9am–5pm New York time (better replies)",
                        variable=self.bh).grid(row=r + 1, column=1, sticky="w", pady=4)
        tk.Label(f, text="Follow-up days", bg=CARD).grid(row=r + 2, column=0, sticky="w", pady=4)
        self.vars["followup_days"] = tk.StringVar()
        ttk.Entry(f, textvariable=self.vars["followup_days"], width=14).grid(row=r + 2, column=1, sticky="w")
        Btn(f, text="Save", style="Primary.TButton", command=self.save_details).grid(
            row=r + 3, column=1, sticky="w", pady=(14, 0))

        # --- AI & audit
        t6 = tk.Frame(nb, bg=CARD)
        nb.add(t6, text="  AI & audit  ")
        f = tk.Frame(t6, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20)
        tk.Label(f, text="Gemini API key (free): aistudio.google.com > Get API key > Create API key.\n"
                 "Used for each business's plan, custom email and reply sorting. Mockups you make yourself "
                 "in the Gemini app.\nPageSpeed key (optional, free): console.cloud.google.com > enable "
                 "'PageSpeed Insights API' > Credentials > API key. Without it Google limits audits.",
                 bg=CARD, fg=MUTED, font=F(9), justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self.gem_key, self.psi_key, self.gem_model = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (lab, var, show) in enumerate((("Gemini API key", self.gem_key, "•"),
                                             ("Gemini model (optional)", self.gem_model, ""),
                                             ("PageSpeed API key", self.psi_key, "•"))):
            tk.Label(f, text=lab, bg=CARD).grid(row=i + 1, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=var, show=show, width=44).grid(row=i + 1, column=1, sticky="w")
        self.ai_state = tk.Label(f, bg=CARD, fg=MUTED, font=F(9), justify="left")
        self.ai_state.grid(row=4, column=1, sticky="w", pady=(6, 0))
        bf = tk.Frame(f, bg=CARD)
        bf.grid(row=5, column=1, sticky="w", pady=(12, 0))
        Btn(bf, text="Save", style="Primary.TButton", command=self.save_ai).pack(side="left")
        Btn(bf, text="Save + test Gemini", command=self.test_ai).pack(side="left", padx=8)
        ttk.Separator(f).grid(row=6, column=0, columnspan=3, sticky="ew", pady=18)
        tk.Label(f, text="Inbox health: checks your sending domain's SPF, DKIM and DMARC records, which "
                 "decide whether your emails land in the inbox or spam.", bg=CARD, fg=MUTED, font=F(9),
                 wraplength=620, justify="left").grid(row=7, column=0, columnspan=3, sticky="w")
        Btn(f, text="Check my sending domain", command=self.check_domain).grid(row=8, column=0, sticky="w", pady=8)

        # --- website (nadevelopers.com)
        t8 = tk.Frame(nb, bg=CARD)
        nb.add(t8, text="  Website  ")
        f = tk.Frame(t8, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20)
        tk.Label(f, text="Connect your WordPress site. Needs the free 'NA Lead Bot Bridge' plugin (Plugins > Add New "
                 "> Upload Plugin) and an Application Password: in WordPress go to Users > Profile > "
                 "Application Passwords, type 'Wix Lead Bot', click Add, and paste the password here.",
                 bg=CARD, fg=MUTED, font=F(9), wraplength=640, justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        self.ws_url, self.ws_user, self.ws_pw = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (lab, var, show) in enumerate((("Website address", self.ws_url, ""),
                                             ("WordPress username", self.ws_user, ""),
                                             ("Application Password", self.ws_pw, "•"))):
            tk.Label(f, text=lab, bg=CARD).grid(row=i + 1, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=var, show=show, width=44).grid(row=i + 1, column=1, sticky="w")
        self.ws_state = tk.Label(f, bg=CARD, fg=MUTED, font=F(9), justify="left", wraplength=520)
        self.ws_state.grid(row=4, column=1, sticky="w", pady=(6, 8))
        self.ws_opts = {}
        for i, (k, lab) in enumerate((
                ("enabled", "Connected (turn off to pause everything below)"),
                ("audit_pages", "Free review page for each lead, linked in the first email"),
                ("use_offer", "Use the announcement bar text as the offer in emails"),
                ("use_portfolio", "Use my real projects and client reviews in emails"),
                ("inquiries", "Bring website contact-form inquiries into the app"),
                ("won_projects", "When I mark a deal Won, add a draft project on the site"))):
            v = tk.BooleanVar()
            ttk.Checkbutton(f, text=lab, variable=v).grid(row=5 + i, column=1, sticky="w", pady=1)
            self.ws_opts[k] = v
        bf = tk.Frame(f, bg=CARD)
        bf.grid(row=12, column=1, sticky="w", pady=(14, 0))
        Btn(bf, text="Save", style="Primary.TButton", command=self.save_website).pack(side="left")
        Btn(bf, text="Save + test connection", command=self.test_website).pack(side="left", padx=8)
        Btn(bf, text="Sync projects + offer now", command=self.sync_website).pack(side="left")

        # --- email content (branding)
        t7 = tk.Frame(nb, bg=CARD)
        nb.add(t7, text="  Email design  ")
        f = tk.Frame(t7, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20, fill="x")
        tk.Label(f, text="Every email gets a designed version: the first one is light and personal (your logo, "
                 "a 'what I noticed' card for their site, a call button, your signature card). Follow-ups add a "
                 "logo header, recent work, a client review and your offer. Answers to replies stay short.", bg=CARD, fg=MUTED, font=F(9),
                 wraplength=760, justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        self.ed = {k: tk.StringVar() for k in ("proof_line", "portfolio_url", "offer", "offer_until",
                                               "job_title", "whatsapp")}
        for i, (key, label) in enumerate((("proof_line", "Proof line"), ("portfolio_url", "Portfolio link"),
                                          ("offer", "Current offer"), ("offer_until", "Offer ends (YYYY-MM-DD)"),
                                          ("job_title", "Your title"), ("whatsapp", "WhatsApp number (only the link is shown)"))):
            tk.Label(f, text=label, bg=CARD).grid(row=i + 1, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=self.ed[key], width=70).grid(row=i + 1, column=1, sticky="w")
        tk.Label(f, text="The offer line is added to follow-ups until the end date, then disappears by itself.",
                 bg=CARD, fg=MUTED, font=F(8)).grid(row=7, column=1, sticky="w")
        tk.Label(f, text="Client reviews\n(one per line:\nquote | name)", bg=CARD, justify="left").grid(
            row=8, column=0, sticky="nw", pady=(10, 0))
        self.testi = tk.Text(f, width=70, height=5, font=F(9), relief="flat", highlightthickness=1,
                             highlightbackground=BORDER, wrap="word")
        self.testi.grid(row=8, column=1, sticky="w", pady=(10, 0))
        tk.Label(f, text="Branded design for", bg=CARD).grid(row=9, column=0, sticky="w", pady=(12, 0))
        bf = tk.Frame(f, bg=CARD)
        bf.grid(row=9, column=1, sticky="w", pady=(12, 0))
        self.brand_vars = {}
        for step, lab in ((1, "First email"), (2, "Follow-up 1"), (3, "Follow-up 2"), (4, "Last email"),
                          (5, "Check-back"), (0, "Answers to replies")):
            v = self.brand_vars[step] = tk.BooleanVar()
            ttk.Checkbutton(bf, text=lab, variable=v).pack(side="left", padx=(0, 10))
        tk.Label(f, text="Email colours", bg=CARD).grid(row=10, column=0, sticky="w", pady=(12, 0))
        tf = tk.Frame(f, bg=CARD)
        tf.grid(row=10, column=1, sticky="w", pady=(12, 0))
        self.etheme = tk.StringVar(value="light")
        ttk.Radiobutton(tf, text="White (recommended: reads well everywhere)", value="light",
                        variable=self.etheme).pack(side="left", padx=(0, 14))
        ttk.Radiobutton(tf, text="Dark (navy, premium look)", value="dark", variable=self.etheme).pack(side="left")
        bb = tk.Frame(f, bg=CARD)
        bb.grid(row=11, column=1, sticky="w", pady=(14, 0))
        Btn(bb, text="Save", style="Primary.TButton", command=self.save_design).pack(side="left")
        Btn(bb, text="👁  Preview first email", command=lambda: self.preview_design(1)).pack(side="left", padx=8)
        Btn(bb, text="👁  Preview a follow-up", command=lambda: self.preview_design(3)).pack(side="left")
        Btn(bb, text="✉  Send me real samples", command=self.send_samples).pack(side="left", padx=8)

        # --- templates
        t3 = tk.Frame(nb, bg=CARD)
        nb.add(t3, text="  Email templates  ")
        f = tk.Frame(t3, bg=CARD)
        f.pack(fill="both", expand=True, padx=24, pady=16)
        top = tk.Frame(f, bg=CARD)
        top.pack(fill="x")
        self.tstep = tk.IntVar(value=1)
        for i, txt in ((1, "First email"), (2, "Follow-up 1"), (3, "Follow-up 2"), (4, "Last email")):
            ttk.Radiobutton(top, text=txt, value=i, variable=self.tstep, command=self.load_tpl).pack(side="left", padx=(0, 12))
        tk.Label(f, text="Placeholders: {business} {greeting} {site} {city} {issues_bullets} {quick_win} "
                 "{calendly} {company} {sender_name} {website}.  The footer with your address and "
                 "unsubscribe line is added automatically.", bg=CARD, fg=MUTED, font=F(8),
                 wraplength=900, justify="left").pack(anchor="w", pady=8)
        self.tsubj = tk.StringVar()
        ttk.Entry(f, textvariable=self.tsubj).pack(fill="x")
        self.tbody = tk.Text(f, wrap="word", font=F(10), relief="flat", height=16, padx=8, pady=6,
                             highlightthickness=1, highlightbackground=BORDER)
        self.tbody.pack(fill="both", expand=True, pady=8)
        b = tk.Frame(f, bg=CARD)
        b.pack(fill="x")
        Btn(b, text="Save template", style="Primary.TButton", command=self.save_tpl).pack(side="left")
        Btn(b, text="Reset to default", command=self.reset_tpl).pack(side="left", padx=8)

        # --- never contact
        t4 = tk.Frame(nb, bg=CARD)
        nb.add(t4, text="  Never contact  ")
        f = tk.Frame(t4, bg=CARD)
        f.pack(fill="both", expand=True, padx=24, pady=16)
        tk.Label(f, text="Your clients, unsubscribes and bounces. Add an email or a whole domain "
                 "(e.g. pristinedental.com).", bg=CARD, fg=MUTED).pack(anchor="w")
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x", pady=8)
        self.supp_in = tk.StringVar()
        ttk.Entry(row, textvariable=self.supp_in, width=40).pack(side="left")
        Btn(row, text="Add as client", command=lambda: self.add_supp("client")).pack(side="left", padx=6)
        Btn(row, text="Remove selected", command=self.del_supp).pack(side="left")
        fr, self.supp = make_tree(f, [("v", "Email / domain", 300), ("why", "Reason", 160),
                                      ("when", "Added", 150)], height=14)
        fr.pack(fill="both", expand=True)

        # --- security
        t5 = tk.Frame(nb, bg=CARD)
        nb.add(t5, text="  Security  ")
        f = tk.Frame(t5, bg=CARD)
        f.pack(anchor="nw", padx=24, pady=20)
        self.old, self.new1, self.new2 = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (lab, var) in enumerate((("Current password", self.old), ("New password", self.new1),
                                        ("New password again", self.new2))):
            tk.Label(f, text=lab, bg=CARD).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(f, textvariable=var, show="•", width=30).grid(row=i, column=1, sticky="w")
        Btn(f, text="Change password", style="Primary.TButton", command=self.change_pw).grid(
            row=3, column=1, sticky="w", pady=(12, 0))
        tk.Label(f, text="Your app password is never stored, only a secure hash. Your email app "
                 "password is encrypted with it.\nForgot it? Delete config.json next to the app: "
                 "your leads stay, but you'll set a new password and re-enter your email password.",
                 bg=CARD, fg=MUTED, font=F(9), justify="left").grid(row=4, column=0, columnspan=3,
                                                                     sticky="w", pady=(18, 0))

    def refresh(self, **kw):
        s = O.settings(self.app.cfg)
        self.provider.set(s["provider"])
        for k, v in self.vars.items():
            v.set(", ".join(map(str, s[k])) if k == "followup_days" else str(s[k]))
        self.addr.delete("1.0", "end")
        self.addr.insert("1.0", s["postal_address"])
        self.bh.set(bool(s["business_hours_only"]))
        self.warm.set(bool(s.get("warmup", True)))
        has = bool(S.get_secret(self.app.cfg, "smtp_password"))
        self.pwstate.config(text="saved (encrypted)" if has else "not set", fg=GREEN if has else RED)
        self.apppw.set("")
        self.gem_key.set("")
        self.psi_key.set("")
        self.gem_model.set((self.app.cfg.get("ai", {}) or {}).get("model", ""))
        g, p = S.get_secret(self.app.cfg, "gemini_key"), S.get_secret(self.app.cfg, "psi_key")
        self.ai_state.config(text=f"Gemini key: {'saved (encrypted)' if g else 'not set'}   ·   "
                                  f"PageSpeed key: {'saved (encrypted)' if p else 'not set (optional)'}",
                             fg=GREEN if g else MUTED)
        for k, v in self.ed.items():
            v.set(str(s.get(k) or ""))
        self.testi.delete("1.0", "end")
        self.testi.insert("1.0", "\n".join(f"{q} | {n}" for q, n in (s.get("testimonials") or [])))
        for step, v in self.brand_vars.items():
            v.set(step in (s.get("branded_steps") or []))
        ws = WS.settings(self.app.cfg)
        self.ws_url.set(ws["url"])
        self.ws_user.set(ws["user"])
        self.ws_pw.set("")
        for k, v in self.ws_opts.items():
            v.set(bool(ws.get(k)))
        haspw = bool(S.get_secret(self.app.cfg, "wp_app_password"))
        synced = self.db.get_kv("wp_synced_at", "") if self.db else ""
        self.ws_state.config(text=(f"Application Password: {'saved (encrypted)' if haspw else 'not set'}"
                                   + (f"   ·   last sync {synced[:16].replace('T', ' ')}" if synced else "")),
                             fg=GREEN if haspw and ws["enabled"] else MUTED)
        self.etheme.set(s.get("email_theme") or "light")
        self.load_tpl()
        self.fill_supp()

    def detect(self):
        addr = self.vars["email"].get().strip()
        if "@" not in addr:
            return messagebox.showwarning("Email", "Type your email address first.")
        try:
            name, hosts = O.detect_provider(addr)
        except Exception as e:
            return messagebox.showerror("Email", f"Couldn't look it up: {e}")
        if not name:
            return messagebox.showinfo("Email", "Couldn't tell the provider from your mail servers:\n"
                                       + ("\n".join(hosts) or "none found")
                                       + "\n\nPick 'Other' and ask your host for SMTP/IMAP settings.")
        self.provider.set(name)
        self.pick_provider()
        messagebox.showinfo("Email", f"{addr} is hosted by {name}.\nServer settings filled in. "
                            "Now paste an app password and click 'Save + send me a test email'.")

    def save_ai(self, quiet=False):
        if self.gem_key.get().strip():
            S.save_secret(self.app.cfg, "gemini_key", self.gem_key.get().strip())
        if self.psi_key.get().strip():
            S.save_secret(self.app.cfg, "psi_key", self.psi_key.get().strip())
        self.app.cfg.set("ai", {"model": self.gem_model.get().strip()})
        self.app.cfg.save()
        if not quiet:
            self.app.toast("Saved")
        self.refresh()

    def save_website(self, quiet=False):
        s = WS.settings(self.app.cfg)
        s.update(url=self.ws_url.get().strip().rstrip("/") or WS.DEFAULTS["url"], user=self.ws_user.get().strip())
        for k, v in self.ws_opts.items():
            s[k] = bool(v.get())
        if self.ws_pw.get().strip():
            S.save_secret(self.app.cfg, "wp_app_password", self.ws_pw.get().strip())
            s["enabled"] = True
        self.app.cfg.set("website", s)
        self.app.cfg.save()
        if not quiet:
            self.app.toast("Saved")
        self.refresh()

    def test_website(self):
        self.save_website(quiet=True)
        if not WS.enabled(self.app.cfg):
            messagebox.showinfo("Website", "Fill in the address, username and Application Password, and tick "
                                "'Connected'.")
            return
        self.app.run_job("Testing website", lambda: WS.test(self.app.cfg),
                         after=lambda res: res and messagebox.showinfo("Website", res))

    def sync_website(self):
        self.save_website(quiet=True)
        if WS.enabled(self.app.cfg):
            self.app.run_job("Syncing website", lambda: WS.sync(self.db, self.app.cfg),
                             after=lambda res: (res and self.app.toast(res), self.refresh()))

    def test_ai(self):
        self.save_ai(quiet=True)
        self.app.run_job("Testing Gemini", lambda: ai.ask(self.app.cfg, "Reply with exactly: Gemini works",
                                                          want_json=False),
                         after=lambda res: res and messagebox.showinfo("Gemini", f"Gemini answered: {res[:80]}"))

    def check_domain(self):
        addr = O.settings(self.app.cfg)["email"]

        def show(res):
            if res:
                messagebox.showinfo("Inbox health for " + addr.split("@")[-1],
                                    "\n".join(("✓ " if ok else "✗ ") + t for ok, t in res) +
                                    "\n\nFix any ✗ in your domain/email admin panel. Also: start with "
                                    "10-15 emails a day and raise slowly over 3-4 weeks.")
        self.app.run_job("Checking domain", lambda: O.domain_health(addr), after=show)

    def pick_provider(self, e=None):
        sh, sp, ih, ip = O.PROVIDERS[self.provider.get()]
        if sh:
            self.vars["smtp_host"].set(sh)
            self.vars["smtp_port"].set(str(sp))
            self.vars["imap_host"].set(ih)
            self.vars["imap_port"].set(str(ip))

    def _save(self, keys):
        s = dict(self.app.cfg.get("outreach", {}))
        for k in keys:
            v = self.vars[k].get().strip()
            if k in ("smtp_port", "imap_port", "daily_limit", "delay_min", "delay_max"):
                try:
                    v = int(v)
                except ValueError:
                    raise ValueError(f"{k.replace('_', ' ')} must be a number")
            if k == "followup_days":
                v = [int(x) for x in re.findall(r"\d+", v)][:3] or [3, 7, 14]
            s[k] = v
        s["provider"] = self.provider.get()
        self.app.cfg.set("outreach", s)
        self.app.cfg.save()

    def save_email(self, quiet=False):
        try:
            self._save(["email", "smtp_host", "smtp_port", "imap_host", "imap_port"])
        except ValueError as e:
            return messagebox.showerror("Settings", str(e))
        if self.apppw.get():
            S.save_secret(self.app.cfg, "smtp_password", self.apppw.get().replace(" ", ""))
        if not quiet:
            self.app.toast("Email settings saved")
        self.refresh()

    def test_email(self):
        self.save_email(quiet=True)

        def go():
            return O.test_connection(self.app.cfg)
        self.app.run_job("Testing email", go, after=lambda res: res and messagebox.showinfo("Email", res))

    def save_details(self):
        try:
            self._save(["sender_name", "company", "website", "calendly", "daily_limit",
                        "delay_min", "delay_max", "followup_days"])
        except ValueError as e:
            return messagebox.showerror("Settings", str(e))
        s = self.app.cfg.get("outreach")
        s["postal_address"] = self.addr.get("1.0", "end").strip()
        s["business_hours_only"] = self.bh.get()
        s["warmup"] = self.warm.get()
        if s["delay_max"] < s["delay_min"]:
            s["delay_max"] = s["delay_min"]
        self.app.cfg.save()
        self.app.toast("Saved")

    def save_design(self, quiet=False):
        s = dict(self.app.cfg.get("outreach", {}))
        for k, v in self.ed.items():
            s[k] = v.get().strip()
        if s["offer_until"]:
            try:
                dt.date.fromisoformat(s["offer_until"])
            except ValueError:
                return messagebox.showerror("Email design", "Offer end date must look like 2026-12-01.")
        tl = []
        for line in self.testi.get("1.0", "end").splitlines():
            if line.strip():
                q, _, n = line.partition("|")
                tl.append([q.strip().strip('"“”'), n.strip() or "Client"])
        s["testimonials"] = tl
        s["branded_steps"] = [k for k, v in self.brand_vars.items() if v.get()]
        s["email_theme"] = self.etheme.get()
        self.app.cfg.set("outreach", s)
        self.app.cfg.save()
        if not quiet:
            self.app.toast("Saved")

    def send_samples(self):
        self.save_design(quiet=True)

        def work():
            try:
                self.app.q.put(("toast", O.send_samples(self.app.cfg, self.db)))
            except Exception as e:
                self.app.q.put(("toast", f"Couldn't send: {e}. Check Settings > Email account.", RED))
        threading.Thread(target=work, daemon=True).start()

    def preview_design(self, step=3):
        self.save_design(quiet=True)
        st = O.settings(self.app.cfg)
        lead = next(iter(self.db.lead_records()), {"domain": "example.com", "name": "Bright Smile Dental",
                                                    "final_url": "https://example.com", "category": "dentist"})
        subj, body = O.templates(self.app.cfg)[step]
        msg = {"step": step, "domain": lead["domain"], "to_addr": O.best_email(lead) or "owner@example.com",
               "subject": O._fill(subj, lead, st), "body": O._fill(body, lead, st) + O._fill(O.FOOTER, lead, st)}
        open_url("file:///" + O.preview_file(self.app.cfg, msg, self.db).replace(os.sep, "/"))

    def load_tpl(self):
        subj, body = O.templates(self.app.cfg)[self.tstep.get()]
        self.tsubj.set(subj)
        self.tbody.delete("1.0", "end")
        self.tbody.insert("1.0", body)

    def save_tpl(self):
        t = self.app.cfg.get("templates", {})
        t[str(self.tstep.get())] = [self.tsubj.get(), self.tbody.get("1.0", "end").rstrip()]
        self.app.cfg.set("templates", t)
        self.app.cfg.save()
        self.app.toast("Template saved")

    def reset_tpl(self):
        t = self.app.cfg.get("templates", {})
        t.pop(str(self.tstep.get()), None)
        self.app.cfg.set("templates", t)
        self.app.cfg.save()
        self.load_tpl()

    def fill_supp(self):
        self.supp.delete(*self.supp.get_children())
        for v, why, when in self.db.q("SELECT value, reason, added_at FROM suppress ORDER BY added_at DESC"):
            self.supp.insert("", "end", iid=v, values=(v, why, (when or "")[:16].replace("T", " ")))

    def add_supp(self, reason):
        v = self.supp_in.get().strip().lower()
        v = re.sub(r"^https?://(www\.)?", "", v).split("/")[0]
        if v:
            O.suppress(self.db, v, reason)
            self.supp_in.set("")
            self.fill_supp()

    def del_supp(self):
        for i in self.supp.selection():
            O.unsuppress(self.db, i)
        self.fill_supp()

    def change_pw(self):
        if not S.check_password(self.app.cfg, self.old.get()):
            return messagebox.showerror("Password", "Current password is wrong.")
        prob = S.password_problem(self.new1.get())
        if prob:
            return messagebox.showerror("Password", prob)
        if self.new1.get() != self.new2.get():
            return messagebox.showerror("Password", "New passwords don't match.")
        S.set_password(self.app.cfg, self.new1.get())
        for v in (self.old, self.new1, self.new2):
            v.set("")
        self.app.toast("Password changed")


_SINGLE = None


def main():
    if "--yp-browser" in sys.argv:
        import yp_browser
        i = sys.argv.index("--yp-browser")
        url = sys.argv[i + 1] if len(sys.argv) > i + 1 else "https://www.yellowpages.com"
        sys.exit(yp_browser.run(url, W.BUNDLED, W.HERE))
    os.makedirs(OUT_DIR, exist_ok=True)
    # Only one copy at a time: two copies could send the same emails twice.
    import socket
    global _SINGLE
    _SINGLE = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        _SINGLE.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        _SINGLE.bind(("127.0.0.1", 47219))
        _SINGLE.listen(1)
    except OSError:
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("Wix Lead Bot", "Wix Lead Bot is already open. Use the window that's already "
                            "running (check the taskbar).")
        r.destroy()
        sys.exit(0)
    try:
        from ctypes import windll  # sharper text on Windows
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

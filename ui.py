# -*- coding: utf-8 -*-
"""公司标题钓鱼排查 GUI。FOFA 精确 title → 探活 → 备案 → 后缀/关键字扩搜。"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, Button, Frame, IntVar, Label, PhotoImage, StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from engine import (
    APP_DIR,
    ROOT as BUNDLE,
    HuntConfig,
    TitlePhishEngine,
    export_xlsx,
    group_hits,
    load_runtime,
    probe_settings,
    save_runtime,
    split_list,
    tool_inventory,
)

HERE = APP_DIR
ASSETS = BUNDLE / "assets"
CFG_PATH = HERE / "last_config.json"
OUT_DIR = HERE / "out"
SLOGANS = [
    "真正的大师永远怀着一颗学徒的心",
]
VERDICT_ORDER = [
    "可疑钓鱼", "可疑-被拦", "可疑-不通", "需人工",
    "测绘过期", "博彩/冒备案", "自有", "排除",
]
TAG_COLORS = {
    "可疑钓鱼": ("#FF6B6B", "#1A1A1A"),
    "可疑-被拦": ("#E67E22", "#1A1A1A"),
    "可疑-不通": ("#F4D03F", "#1A1A1A"),
    "需人工": ("#F5B041", "#1A1A1A"),
    "测绘过期": ("#AED6F1", "#1A1A1A"),
    "博彩/冒备案": ("#BB8FCE", "#1A1A1A"),
    "自有": ("#7DCEA0", "#1A1A1A"),
    "排除": ("#D5D8DC", "#1A1A1A"),
}
COLS = (
    ("verdict", "判定", 90),
    ("url", "URL", 280),
    ("fofa_title", "FOFA标题", 200),
    ("live_title", "活体标题", 200),
    ("ip", "IP", 120),
    ("alive", "存活", 110),
    ("icp", "备案号", 150),
    ("icp_org", "备案主体", 140),
    ("note", "说明", 220),
)


STATUS_FG = {
    "可用": "#1e8e3e",
    "无效": "#d93025",
    "未知": "#888888",
    "探测中": "#e67e22",
    "未启用": "#888888",
}


class SettingsDialog:
    """FOFA Key / 代理 / 公开备案反查。保存到 config.json。"""

    def __init__(self, master: Tk, on_log=None) -> None:
        self.on_log = on_log or (lambda m: None)
        rt = load_runtime()
        self.win = Toplevel(master)
        self.win.title("配置")
        self.win.transient(master)
        self.win.resizable(True, True)
        self.win.minsize(900, 520)
        self.win.grab_set()

        self.fofa_key = StringVar(value=rt.get("fofa_key") or "")
        self.fofa_mode = StringVar(value=rt.get("fofa_mode") or "official")
        try:
            iv = int(float(rt.get("fofa_interval") or 2))
        except (TypeError, ValueError):
            iv = 2
        self.fofa_interval = IntVar(value=iv if iv >= 1 else 2)
        self.proxy = StringVar(value=rt.get("proxy") or "http://127.0.0.1:7897")
        self.proxy_enable = BooleanVar(value=bool(rt.get("proxy_enable")))
        self.show_key = BooleanVar(value=False)
        self.st_fofa = StringVar(value="未知")
        self.st_proxy = StringVar(value="未知")
        self.st_beian = StringVar(value="未知")
        self._busy = False

        font = ("Microsoft YaHei UI", 11)
        font_b = ("Microsoft YaHei UI", 14, "bold")
        self.win.option_add("*Font", font)

        ttk.Label(self.win, text="接口配置", font=font_b).pack(anchor="w", padx=24, pady=(18, 8))

        form = ttk.Frame(self.win)
        form.pack(fill="x", padx=24, pady=8)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="FOFA Key", width=12).grid(row=0, column=0, sticky="e", padx=(0, 12), pady=10)
        self.key_ent = ttk.Entry(form, textvariable=self.fofa_key, font=font, show="*")
        self.key_ent.grid(row=0, column=1, sticky="ew", pady=10, ipady=6)
        ttk.Button(form, text="显示", width=8, command=self._toggle_key).grid(row=0, column=2, padx=8)
        self.lb_fofa = Label(form, textvariable=self.st_fofa, fg=STATUS_FG["未知"], width=8, anchor="w", font=font)
        self.lb_fofa.grid(row=0, column=3, sticky="w", padx=6)
        ttk.Button(form, text="申请", width=8, command=lambda: webbrowser.open("https://fofa.info")).grid(row=0, column=4)

        ttk.Label(form, text="FOFA 模式", width=12).grid(row=1, column=0, sticky="e", padx=(0, 12), pady=10)
        mode_fr = ttk.Frame(form)
        mode_fr.grid(row=1, column=1, columnspan=3, sticky="w", pady=10)
        ttk.Combobox(mode_fr, textvariable=self.fofa_mode, values=("official", "relay"), width=14, state="readonly").pack(
            side="left", ipady=4
        )
        ttk.Label(mode_fr, text="间隔秒").pack(side="left", padx=(20, 8))
        ttk.Spinbox(mode_fr, from_=1, to=8, increment=1, width=8, textvariable=self.fofa_interval).pack(side="left", ipady=4)

        ttk.Label(form, text="代理", width=12).grid(row=2, column=0, sticky="e", padx=(0, 12), pady=10)
        ttk.Entry(form, textvariable=self.proxy, font=font).grid(row=2, column=1, sticky="ew", pady=10, ipady=6)
        ttk.Checkbutton(form, text="启用", variable=self.proxy_enable).grid(row=2, column=2, sticky="w", padx=8)
        self.lb_proxy = Label(form, textvariable=self.st_proxy, fg=STATUS_FG["未知"], width=8, anchor="w", font=font)
        self.lb_proxy.grid(row=2, column=3, sticky="w", padx=6)

        ttk.Label(form, text="备案反查", width=12).grid(row=3, column=0, sticky="e", padx=(0, 12), pady=10)
        ttk.Label(form, text="icplishi.com 公开备案（公司名→根域，别人不用部署）").grid(
            row=3, column=1, sticky="w", pady=10
        )
        self.lb_beian = Label(form, textvariable=self.st_beian, fg=STATUS_FG["未知"], width=8, anchor="w", font=font)
        self.lb_beian.grid(row=3, column=3, sticky="w", padx=6)

        ttk.Label(self.win, text="探测结果").pack(anchor="w", padx=24, pady=(8, 4))
        self.result_txt = ScrolledText(self.win, height=8, wrap="word", font=("Microsoft YaHei UI", 10))
        self.result_txt.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        self.result_txt.insert("1.0", "填好 FOFA Key 后点「探测是否有效」。备案反查走公开接口，不用部署工信部。探活始终不走代理。")
        self.result_txt.configure(state="disabled")

        btns = ttk.Frame(self.win)
        btns.pack(fill="x", padx=24, pady=(4, 20))
        Button(
            btns, text="取消", width=12, height=2, bg="#e74c3c", fg="white",
            relief="flat", font=font, command=self.win.destroy,
        ).pack(side="right", padx=6)
        Button(
            btns, text="保存", width=12, height=2, bg="#27ae60", fg="white",
            relief="flat", font=font, command=self._save,
        ).pack(side="right", padx=6)
        self.btn_probe = Button(
            btns, text="探测是否有效", width=16, height=2, bg="#f39c12", fg="white",
            relief="flat", font=font, command=self._probe,
        )
        self.btn_probe.pack(side="right", padx=6)

        self.win.geometry("960x560")
        self.win.update_idletasks()
        try:
            px = master.winfo_rootx() + 40
            py = master.winfo_rooty() + 40
            self.win.geometry("960x560+%s+%s" % (px, py))
        except Exception:
            pass
        self.key_ent.focus_set()

    def _toggle_key(self) -> None:
        show = not self.show_key.get()
        self.show_key.set(show)
        self.key_ent.configure(show="" if show else "*")

    def _set_status(self, name: str, status: str) -> None:
        var = {"FOFA": self.st_fofa, "代理": self.st_proxy, "备案反查": self.st_beian}.get(name)
        lab = {"FOFA": self.lb_fofa, "代理": self.lb_proxy, "备案反查": self.lb_beian}.get(name)
        if var is not None:
            var.set(status)
        if lab is not None:
            lab.configure(fg=STATUS_FG.get(status, STATUS_FG["未知"]))

    def _set_result(self, text: str) -> None:
        self.result_txt.configure(state="normal")
        self.result_txt.delete("1.0", "end")
        self.result_txt.insert("1.0", text or "")
        self.result_txt.configure(state="disabled")

    def _save(self) -> None:
        try:
            interval = float(self.fofa_interval.get() or 2)
        except (TypeError, ValueError):
            interval = 2.0
        save_runtime({
            "fofa_key": (self.fofa_key.get() or "").strip(),
            "fofa_mode": (self.fofa_mode.get() or "official").strip() or "official",
            "fofa_interval": interval,
            "proxy": (self.proxy.get() or "").strip(),
            "proxy_enable": bool(self.proxy_enable.get()),
        })
        self.on_log("[配置] 已写入 config.json")
        self.win.destroy()

    def _probe(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.btn_probe.configure(state="disabled")
        for name in ("FOFA", "代理", "备案反查"):
            self._set_status(name, "探测中")
        self._set_result("探测中…")
        payload = {
            "fofa_key": (self.fofa_key.get() or "").strip(),
            "fofa_mode": (self.fofa_mode.get() or "official").strip() or "official",
            "proxy": (self.proxy.get() or "").strip(),
            "proxy_enable": bool(self.proxy_enable.get()),
        }

        def work() -> None:
            try:
                rows = probe_settings(log=self.on_log, **payload)
                self.win.after(0, lambda: self._probe_done(rows, ""))
            except Exception:
                tb = traceback.format_exc()
                self.win.after(0, lambda: self._probe_done([], tb))

        threading.Thread(target=work, daemon=True).start()

    def _probe_done(self, rows: list, err: str) -> None:
        self._busy = False
        try:
            self.btn_probe.configure(state="normal")
        except Exception:
            return
        if err:
            self._set_result(err[:800])
            return
        lines = []
        for row in rows:
            name = row.get("name") or ""
            status = row.get("status") or "未知"
            self._set_status(name, status)
            lines.append("%s %s  %s" % (name, status, row.get("detail") or ""))
            self.on_log("[探测] %s %s  %s" % (name, status, row.get("detail") or ""))
        self._set_result("\n".join(lines) if lines else "没有结果")


def _dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _set_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("linshen.TwinTitle")
    except Exception:
        pass


def _ascii_ico() -> str:
    """Tk iconbitmap 吃不了中文路径，拷到 LOCALAPPDATA。"""
    src = ASSETS / "linshen.ico"
    if not src.is_file():
        return ""
    dst = Path(os.environ.get("LOCALAPPDATA") or ".") / "TwinTitle" / "linshen.ico"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (not dst.is_file()) or dst.stat().st_size != src.stat().st_size or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)
        return str(dst)
    except OSError:
        return str(src)


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("TwinTitle — 同题猎手")
        self.root.geometry("1280x820")
        self.root.minsize(980, 640)
        self.q: queue.Queue = queue.Queue()
        self.engine: TitlePhishEngine | None = None
        self.worker: threading.Thread | None = None
        self.result: dict | None = None
        self.running = False

        self.official_var = StringVar()
        self.url_var = StringVar()
        self.size_var = IntVar(value=50)
        self.timeout_var = IntVar(value=8)
        self.max_probe_var = IntVar(value=80)
        self.do_roots = BooleanVar(value=True)
        self.do_exact = BooleanVar(value=True)
        self.do_probe = BooleanVar(value=True)
        self.do_icp = BooleanVar(value=True)
        self.do_suffix = BooleanVar(value=True)
        self.do_keywords = BooleanVar(value=True)
        self.filter_var = StringVar(value="全部")
        self.status_var = StringVar(value="就绪。公司全称一行一个，可批量。")
        self._icon_photo = None
        self._brand_icon = None
        self._slogan_i = 0
        self.slogan_var = StringVar(value=SLOGANS[0])

        self._style()
        self._set_icon()
        self._build()
        self._load_cfg()
        self.root.after(200, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_icon(self) -> None:
        ascii_ico = _ascii_ico()
        if ascii_ico:
            try:
                self.root.iconbitmap(default=ascii_ico)
            except Exception:
                try:
                    self.root.iconbitmap(ascii_ico)
                except Exception:
                    pass
        png = ASSETS / "linshen32.png"
        if png.is_file():
            try:
                self._icon_photo = PhotoImage(file=str(png))
                self.root.iconphoto(True, self._icon_photo)
            except Exception:
                pass
        if not ascii_ico:
            return
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetAncestor(self.root.winfo_id(), 2) or self.root.winfo_id()
            user32 = ctypes.windll.user32
            IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
            WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
            h_small = user32.LoadImageW(None, ascii_ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            h_big = user32.LoadImageW(None, ascii_ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if h_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
            if h_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
        except Exception:
            pass

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except Exception:
            pass
        font = ("Microsoft YaHei UI", 9)
        self.root.option_add("*Font", font)
        style.configure("TButton", padding=(10, 4))
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Treeview", rowheight=26, font=font)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("Accent.TButton", padding=(12, 5))

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        brand = Frame(self.root, bg="#121212")
        brand.pack(fill="x")
        row = Frame(brand, bg="#121212")
        row.pack(fill="x", padx=12, pady=(10, 8))
        side_w = 40
        left = Frame(row, bg="#121212", width=side_w, height=36)
        left.pack(side="left")
        left.pack_propagate(False)
        png32 = ASSETS / "linshen32.png"
        if png32.is_file():
            try:
                self._brand_icon = PhotoImage(file=str(png32))
                Label(left, image=self._brand_icon, bg="#121212", bd=0).pack(anchor="w")
            except Exception:
                pass
        mid = Frame(row, bg="#121212")
        mid.pack(side="left", fill="both", expand=True)
        Label(
            mid, textvariable=self.slogan_var, fg="#e6c35c", bg="#121212",
            font=("Microsoft YaHei UI", 12), anchor="center", justify="center",
        ).pack(fill="x")
        Label(
            mid, text="by 林神", fg="#c9a227", bg="#121212",
            font=("Microsoft YaHei UI", 9), anchor="center",
        ).pack(fill="x")
        right = Frame(row, bg="#121212", width=side_w, height=36)
        right.pack(side="right")
        right.pack_propagate(False)
        self.root.after(10000, self._tick_slogan)

        head = ttk.Frame(self.root)
        head.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(head, text="TwinTitle  同题猎手", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Button(head, text="配置", command=self.open_settings).pack(side="right")
        ttk.Label(head, text="FOFA Key / 代理 / 备案反查").pack(side="right", padx=(0, 8))
        top = ttk.LabelFrame(self.root, text="排查目标")
        top.pack(fill="x", padx=10, pady=(8, 4))

        ttk.Label(top, text="公司名称（一行一个，可批量）").pack(anchor="w", padx=8, pady=(6, 0))
        self.company_txt = ScrolledText(top, height=4, wrap="word")
        self.company_txt.pack(fill="x", padx=8, pady=(0, 4))

        r0 = ttk.Frame(top)
        r0.pack(fill="x", **pad)
        ttk.Label(r0, text="官网 URL", width=10).pack(side="left")
        ttk.Entry(r0, textvariable=self.url_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Label(r0, text="官网根域", width=10).pack(side="left")
        ttk.Entry(r0, textvariable=self.official_var).pack(side="left", fill="x", expand=True)
        ttk.Label(r0, text="单家可空自动填；批量时忽略这两项").pack(side="left", padx=8)

        mid = ttk.Frame(top)
        mid.pack(fill="x", **pad)
        left = ttk.Frame(mid)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.Frame(mid)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="别名根域（可空，按官网名改后缀看是否注册）").pack(anchor="w")
        self.alias_txt = ScrolledText(left, height=4, wrap="word")
        self.alias_txt.pack(fill="both", expand=True)
        ttk.Label(right, text="扩搜关键字（可空，用官网标题自动 fuzz）").pack(anchor="w")
        self.kw_txt = ScrolledText(right, height=4, wrap="word")
        self.kw_txt.pack(fill="both", expand=True)

        opt = ttk.Frame(top)
        opt.pack(fill="x", **pad)
        for text, var in (
            ("反查根域", self.do_roots),
            ("精确 title", self.do_exact),
            ("探活", self.do_probe),
            ("查备案", self.do_icp),
            ("改后缀", self.do_suffix),
            ("关键字扩搜", self.do_keywords),
        ):
            ttk.Checkbutton(opt, text=text, variable=var).pack(side="left", padx=(0, 10))
        ttk.Label(opt, text="条数").pack(side="left")
        ttk.Spinbox(opt, from_=10, to=200, increment=10, width=6, textvariable=self.size_var).pack(side="left", padx=(2, 8))
        ttk.Label(opt, text="超时秒").pack(side="left")
        ttk.Spinbox(opt, from_=5, to=30, width=5, textvariable=self.timeout_var).pack(side="left", padx=(2, 8))
        ttk.Label(opt, text="探活上限").pack(side="left")
        ttk.Spinbox(opt, from_=10, to=300, increment=10, width=6, textvariable=self.max_probe_var).pack(side="left", padx=(2, 8))

        btns = ttk.Frame(top)
        btns.pack(fill="x", **pad)
        self.btn_start = ttk.Button(btns, text="开始排查", command=self.start, style="Accent.TButton")
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_stop = ttk.Button(btns, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="导出 xlsx", command=self.export).pack(side="left", padx=(0, 6))
        ttk.Label(btns, text="筛选").pack(side="left", padx=(16, 4))
        filt = ttk.Combobox(
            btns, textvariable=self.filter_var, width=12, state="readonly",
            values=["全部"] + VERDICT_ORDER,
        )
        filt.pack(side="left")
        filt.bind("<<ComboboxSelected>>", lambda _e: self._fill_tree())

        body = ttk.Panedwindow(self.root, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=4)

        tree_fr = ttk.Frame(body)
        body.add(tree_fr, weight=3)
        cols = [c[0] for c in COLS]
        self.tree = ttk.Treeview(tree_fr, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="公司 / 分类")
        self.tree.column("#0", width=220, minwidth=140, stretch=False)
        for key, name, width in COLS:
            self.tree.heading(key, text=name, command=lambda k=key: self._sort(k))
            self.tree.column(key, width=width, minwidth=60, stretch=True)
        ys = ttk.Scrollbar(tree_fr, orient="vertical", command=self.tree.yview)
        xs = ttk.Scrollbar(tree_fr, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        tree_fr.rowconfigure(0, weight=1)
        tree_fr.columnconfigure(0, weight=1)
        for tag, (bg, fg) in TAG_COLORS.items():
            self.tree.tag_configure(tag, background=bg, foreground=fg)
        self.tree.tag_configure("company", background="#1f2a36", foreground="#f4e3b2")
        self.tree.tag_configure("cat", font=("Microsoft YaHei UI", 9, "bold"))
        self.tree.bind("<Double-1>", self._open_url)
        self.tree.bind("<Button-3>", self._copy_menu)

        bottom = ttk.Panedwindow(body, orient="horizontal")
        body.add(bottom, weight=2)
        log_fr = ttk.LabelFrame(bottom, text="过程日志")
        ana_fr = ttk.LabelFrame(bottom, text="分析结果")
        bottom.add(log_fr, weight=3)
        bottom.add(ana_fr, weight=2)
        self.log_txt = ScrolledText(log_fr, height=10, wrap="word", state="disabled")
        self.log_txt.pack(fill="both", expand=True, padx=4, pady=4)
        self.ana_txt = ScrolledText(ana_fr, height=10, wrap="word", state="disabled")
        self.ana_txt.pack(fill="both", expand=True, padx=4, pady=4)

        status = ttk.Frame(self.root)
        status.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(status, textvariable=self.status_var).pack(side="left")
        missing = [x.get("name") for x in tool_inventory() if not x.get("ok")]
        if missing:
            self.status_var.set("缺：" + "、".join(str(x) for x in missing))

    def _text_get(self, widget: ScrolledText) -> str:
        return widget.get("1.0", "end").strip()

    def _text_set(self, widget: ScrolledText, value: str) -> None:
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)

    def _set_text(self, widget: ScrolledText, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if value:
            widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _append_log(self, msg: str) -> None:
        self.log_txt.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_txt.insert("end", "[%s] %s\n" % (ts, msg))
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")

    def _apply_discovered(self, payload: dict) -> None:
        domains = payload.get("official_domains") or []
        if domains:
            self.official_var.set(", ".join(domains))
        url = payload.get("official_url") or ""
        if url:
            self.url_var.set(url)
        kws = payload.get("keywords") or []
        if kws:
            self._text_set_edit(self.kw_txt, "\n".join(kws))
        aliases = payload.get("alias_domains") or []
        if aliases:
            self._text_set_edit(self.alias_txt, "\n".join(aliases))

    def _tick_slogan(self) -> None:
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        self._slogan_i = (self._slogan_i + 1) % len(SLOGANS)
        self.slogan_var.set(SLOGANS[self._slogan_i])
        self.root.after(10000, self._tick_slogan)

    def _text_set_edit(self, widget: ScrolledText, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _cfg_dict(self) -> dict:
        return {
            "title": "",
            "official": "",
            "url": "",
            "alias": "",
            "keywords": "",
            "size": int(self.size_var.get() or 50),
            "timeout": int(self.timeout_var.get() or 8),
            "max_probe": int(self.max_probe_var.get() or 80),
            "do_roots": bool(self.do_roots.get()),
            "do_exact": bool(self.do_exact.get()),
            "do_probe": bool(self.do_probe.get()),
            "do_icp": bool(self.do_icp.get()),
            "do_suffix": bool(self.do_suffix.get()),
            "do_keywords": bool(self.do_keywords.get()),
        }

    def _apply_cfg(self, data: dict) -> None:
        self.size_var.set(int(data.get("size") or 50))
        self.timeout_var.set(int(data.get("timeout") or 8))
        self.max_probe_var.set(int(data.get("max_probe") or 80))
        self.do_roots.set(bool(data.get("do_roots", True)))
        self.do_exact.set(bool(data.get("do_exact", True)))
        self.do_probe.set(bool(data.get("do_probe", True)))
        self.do_icp.set(bool(data.get("do_icp", True)))
        self.do_suffix.set(bool(data.get("do_suffix", True)))
        self.do_keywords.set(bool(data.get("do_keywords", True)))

    def _load_cfg(self) -> None:
        if not CFG_PATH.exists():
            return
        try:
            data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            self._apply_cfg(data)
        except Exception:
            pass

    def _save_cfg(self) -> None:
        try:
            CFG_PATH.write_text(json.dumps(self._cfg_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _hunt_cfgs(self):
        d = self._cfg_dict()
        names = split_list(d["title"])
        shared = len(names) == 1
        cfgs = []
        for name in names:
            cfgs.append(HuntConfig(
                title=name,
                official_domains=split_list(d["official"]) if shared else [],
                official_url=(d["url"] or "").strip() if shared else "",
                alias_domains=split_list(d["alias"]) if shared else [],
                keywords=split_list(d["keywords"]) if shared else [],
                do_roots=d.get("do_roots", True),
                do_exact=d["do_exact"],
                do_probe=d["do_probe"],
                do_icp=d["do_icp"],
                do_suffix=d["do_suffix"],
                do_keywords=d["do_keywords"],
                size=max(10, min(200, d["size"])),
                probe_timeout=max(5, min(40, d["timeout"])),
                max_probe=max(5, min(400, d["max_probe"])),
            ))
        return cfgs

    def start(self) -> None:
        if self.running:
            return
        cfgs = self._hunt_cfgs()
        if not cfgs:
            messagebox.showwarning("缺参数", "先填公司名称（一行一个，可批量）。")
            return
        bad = [x.get("name") for x in tool_inventory() if not x.get("ok") and x.get("name") in ("httpx", "curl", "FOFA API", "FOFA Key")]
        if "FOFA Key" in bad:
            messagebox.showwarning("缺配置", "右上角「配置」里填写 FOFA Key。")
            return
        if "FOFA API" in bad:
            messagebox.showwarning("缺工具", "缺少 tools\\lib\\fofa_api.py。")
            return
        sample = cfgs[0]
        if not sample.do_roots and not sample.do_exact and not sample.do_keywords and not sample.do_suffix:
            messagebox.showwarning("缺步骤", "至少勾一项：反查根域 / 精确 title / 关键字扩搜 / 改后缀。")
            return
        self._save_cfg()
        self.result = None
        self._clear_tree()
        self._set_text(self.ana_txt, "")
        self._set_text(self.log_txt, "")
        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        if len(cfgs) > 1:
            self.status_var.set("批量排查 %s 家… 每家先反查根域，再 fuzz 标题。" % len(cfgs))
        else:
            self.status_var.set("排查中… 先反查根域、探官网，再 fuzz 标题。")
        self.engine = TitlePhishEngine(log=lambda m: self.q.put(("log", m)))

        def work() -> None:
            try:
                result = self.engine.run_batch(cfgs) if len(cfgs) > 1 else self.engine.run(cfgs[0])
                self.q.put(("done", result))
            except Exception:
                self.q.put(("error", traceback.format_exc()))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self) -> None:
        if self.engine:
            self.engine.stop()
            self._append_log("已请求停止，等当前 FOFA/探活结束。")
            self.status_var.set("正在停止…")

    def open_settings(self) -> None:
        if self.running:
            messagebox.showinfo("排查中", "先停掉当前排查再改配置。")
            return
        SettingsDialog(self.root, on_log=self._append_log)

    def export(self) -> None:
        if not self.result:
            messagebox.showinfo("没有结果", "先跑完一次排查。")
            return
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        if self.result.get("batch"):
            company = "批量_%s家" % len(self.result.get("jobs") or [])
        else:
            company = (self.result.get("company") or "hunt").replace("/", "_")
        default = OUT_DIR / ("%s_钓鱼排查_%s.xlsx" % (company, datetime.now().strftime("%Y%m%d_%H%M")))
        path = filedialog.asksaveasfilename(
            title="导出分析结果",
            defaultextension=".xlsx",
            initialfile=default.name,
            initialdir=str(OUT_DIR),
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            export_xlsx(path, self.result)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self.status_var.set("已导出 " + path)
        if messagebox.askyesno("导出完成", "已写出：\n%s\n打开所在目录？" % path):
            os.startfile(str(Path(path).parent))

    def _clear_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    def _fill_tree(self) -> None:
        self._clear_tree()
        if not self.result:
            return
        want = self.filter_var.get()
        hits = list(self.result.get("hits") or [])
        n_show = 0
        open_cats = {"可疑钓鱼", "可疑-被拦", "可疑-不通", "需人工"}
        for block in group_hits(hits):
            cats = []
            n_company = 0
            for verdict, hs in block["cats"]:
                if want != "全部" and verdict != want:
                    continue
                cats.append((verdict, hs))
                n_company += len(hs)
            if not cats:
                continue
            cid = self.tree.insert(
                "", "end",
                text="%s  (%s)" % (block["company"], n_company),
                values=("", "", "", "", "", "", "", "", ""),
                tags=("company",),
                open=True,
            )
            for verdict, hs in cats:
                vid = self.tree.insert(
                    cid, "end",
                    text="%s  (%s)" % (verdict, len(hs)),
                    values=(verdict, "", "", "", "", "", "", "", ""),
                    tags=("cat", verdict),
                    open=verdict in open_cats,
                )
                for h in hs:
                    vals = (
                        h.verdict, h.url, h.fofa_title, h.live_title, h.ip,
                        h.alive, h.icp, h.icp_org, h.note,
                    )
                    self.tree.insert(vid, "end", text="", values=vals, tags=(h.verdict or "",))
                    n_show += 1
        total = len(hits)
        self.status_var.set("显示 %s / %s 条。公司下按可疑分类。双击打开 URL。" % (n_show, total))

    def _sort(self, col: str) -> None:
        for company in self.tree.get_children(""):
            for cat in self.tree.get_children(company):
                rows = [(self.tree.set(k, col), k) for k in self.tree.get_children(cat)]
                rows.sort(key=lambda x: x[0])
                for i, (_, k) in enumerate(rows):
                    self.tree.move(k, cat, i)

    def _selected_url(self) -> str:
        sel = self.tree.selection()
        if not sel:
            return ""
        iid = sel[0]
        tags = set(self.tree.item(iid, "tags") or ())
        if "company" in tags or "cat" in tags:
            return ""
        return self.tree.set(iid, "url")

    def _open_url(self, _evt=None) -> None:
        url = self._selected_url()
        if url:
            webbrowser.open(url)

    def _copy_menu(self, evt) -> None:
        row = self.tree.identify_row(evt.y)
        if row:
            self.tree.selection_set(row)
        url = self._selected_url()
        if not url:
            return
        menu = Toplevel(self.root)
        menu.withdraw()
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.status_var.set("已复制 " + url)
        menu.destroy()

    def _finish(self) -> None:
        self.running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "done":
                    self.result = payload
                    if not payload.get("batch"):
                        self._apply_discovered(payload)
                    self._set_text(self.ana_txt, payload.get("summary") or "")
                    self._fill_tree()
                    self._finish()
                    n = len(payload.get("hits") or [])
                    jobs = payload.get("jobs") or []
                    if payload.get("batch"):
                        self.status_var.set("完成，%s 家 / %s 条。按公司分组看可疑。" % (len(jobs), n))
                    else:
                        self.status_var.set("完成，%s 条。根域和 fuzz 标题已回填。" % n)
                    self._save_cfg()
                elif kind == "error":
                    self._append_log(str(payload))
                    self._finish()
                    self.status_var.set("出错，看日志。")
                    messagebox.showerror("排查失败", str(payload)[:800])
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askokcancel("退出", "排查还在跑，确认退出？"):
                return
            if self.engine:
                self.engine.stop()
        self._save_cfg()
        self.root.destroy()


def main() -> None:
    os.environ.setdefault("FOFA_API_MODE", "official")
    try:
        _set_app_id()
        _dpi()
        root = Tk()
        App(root)
        root.mainloop()
    except Exception:
        tb = traceback.format_exc()
        try:
            (HERE / "crash.log").write_text(tb, encoding="utf-8")
        except OSError:
            pass
        try:
            messagebox.showerror("同题猎手启动失败", tb[:1500])
        except Exception:
            sys.stderr.write(tb + "\n")
            sys.stderr.flush()
        raise


if __name__ == "__main__":
    main()

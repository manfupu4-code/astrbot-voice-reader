# -*- coding: utf-8 -*-
"""控制面板（Tkinter）"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from .config import Config
from .engines import EDGE_VOICES, SapiEngine
from .player import (
    ST_CANCELED, ST_DONE, ST_ERROR, ST_PENDING, ST_READING,
    ST_STOPPED, ST_TIMEOUT, VoiceCore, log,
)

# ---- 主题 ----
BG = "#1e1f22"
PANEL = "#2b2d31"
FG = "#e6e6e6"
ACC = "#4a9eff"
MUTED = "#8b8d91"

STATUS_COLOR = {
    ST_PENDING: "#f0c040",
    ST_READING: ACC,
    ST_DONE: "#4caf50",
    ST_TIMEOUT: "#ff9800",
    ST_STOPPED: "#9e9e9e",
    ST_CANCELED: "#6b6d70",
    ST_ERROR: "#e53935",
}


def set_system_volume(pct: int) -> bool:
    """设置 Windows 主音量（需要 pycaw）"""
    try:
        from pycaw.pycaw import AudioUtilities
        ev = AudioUtilities.GetSpeakers().EndpointVolume
        ev.SetMute(0, None)
        ev.SetMasterVolumeLevelScalar(max(0.0, min(1.0, pct / 100.0)), None)
        return True
    except Exception:
        return False


def get_system_volume() -> int:
    try:
        from pycaw.pycaw import AudioUtilities
        return round(AudioUtilities.GetSpeakers().EndpointVolume.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return -1


class Panel(tk.Tk):
    def __init__(self, core: VoiceCore, cfg: Config):
        super().__init__()
        self.core = core
        self.cfg = cfg
        self.title("AstrBot 语音朗读器 · 控制面板")
        self.geometry("900x640")
        self.minsize(760, 520)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._style()
        self._top()
        self._settings()
        self._queue()
        self.refresh()

    # ---------- 样式 ----------
    def _style(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TLabelframe", background=BG, foreground=ACC)
        st.configure("TLabelframe.Label", background=BG, foreground=ACC)
        st.configure("TButton", background="#33363b", foreground=FG, borderwidth=0, padding=6)
        st.map("TButton", background=[("active", ACC)])
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                     foreground=FG, rowheight=24, borderwidth=0)
        st.configure("Treeview.Heading", background="#33363b", foreground=FG)
        st.map("Treeview", background=[("selected", "#1d4d80")])
        st.configure("TCombobox", fieldbackground=PANEL, background="#33363b", foreground=FG)

    # ---------- 顶部 ----------
    def _top(self) -> None:
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        self.lb_state = tk.Label(bar, text="● 运行中", bg=BG, fg="#4caf50",
                                 font=("Microsoft YaHei UI", 11, "bold"))
        self.lb_state.pack(side="left")
        self.lb_stat = tk.Label(bar, text="", bg=BG, fg=MUTED,
                                font=("Microsoft YaHei UI", 9))
        self.lb_stat.pack(side="right")

    # ---------- 设置 ----------
    def _slider(self, parent, label, var, frm, to, res, cb, color=ACC, width=6):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=10, pady=5)
        tk.Label(row, text=label, bg=BG, fg=FG, width=9, anchor="w",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Scale(row, from_=frm, to=to, resolution=res, orient="horizontal",
                 variable=var, bg=BG, fg=FG, troughcolor=PANEL,
                 highlightthickness=0, length=430, command=cb).pack(side="left")
        lb = tk.Label(row, text=str(var.get()), bg=BG, fg=color, width=width,
                      font=("Microsoft YaHei UI", 10, "bold"))
        lb.pack(side="left")
        return lb

    def _settings(self) -> None:
        box = ttk.LabelFrame(self, text=" 设置 ")
        box.pack(fill="x", padx=12, pady=4)

        self.v_vol = tk.IntVar(value=int(self.cfg.get("volume", 80)))
        self.lb_vol = self._slider(box, "音量", self.v_vol, 0, 100, 1, self.on_vol)
        self.lb_vol.config(text=f"{self.v_vol.get()}%")

        self.v_gap = tk.DoubleVar(value=float(self.cfg.get("gap", 0)))
        self.lb_gap = self._slider(box, "段间隔", self.v_gap, 0, 30, 0.5, self.on_gap)
        self.lb_gap.config(text=f"{self.v_gap.get():.1f}s")

        self.v_max = tk.DoubleVar(value=float(self.cfg.get("max_sec", 7)))
        self.lb_max = self._slider(box, "单段最长", self.v_max, 2, 60, 0.5,
                                   self.on_max, color="#ff9800")
        self.lb_max.config(text=f"{self.v_max.get():.1f}s")

        self.v_rate = tk.IntVar(value=int(self.cfg.get("rate", 0)))
        self.lb_rate = self._slider(box, "语速", self.v_rate, -5, 10, 1, self.on_rate)
        self.lb_rate.config(text=str(self.v_rate.get()))

        # 音色
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", padx=10, pady=5)
        tk.Label(row, text="音色", bg=BG, fg=FG, width=9, anchor="w",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        self._labels = list(EDGE_VOICES.keys())
        self._ids = list(EDGE_VOICES.values())
        cur = self.cfg.get("voice") or ""
        self.v_voice = tk.StringVar(
            value=self._labels[self._ids.index(cur)] if cur in self._ids else self._labels[0])
        cb = ttk.Combobox(row, textvariable=self.v_voice, values=self._labels,
                          state="readonly", width=24, font=("Microsoft YaHei UI", 10))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self.on_voice)
        tk.Label(row, text="（需联网；失败自动回退系统语音）", bg=BG, fg="#6b6d70",
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=10)

        # 按钮
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", padx=10, pady=(4, 8))
        self.btn_pause = ttk.Button(row, text="⏸ 暂停", command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=(0, 6))
        for text, cmd in (
            ("⏹ 停止当前", self.core.stop_current),
            ("🗑 清空待读", self.core.clear_pending),
            ("重读选中", self.requeue_selected),
            ("🔊 测试", self.test_speak),
            ("清屏", self.core.clear_finished),
        ):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=6)

    # ---------- 队列 ----------
    def _queue(self) -> None:
        box = ttk.LabelFrame(self, text=" 朗读队列 ")
        box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        wrap = tk.Frame(box, bg=BG)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("seq", "status", "n", "t", "text")
        self.tv = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for col, title, width, anchor in (
            ("seq", "#", 48, "center"),
            ("status", "状态", 86, "center"),
            ("n", "字数", 60, "center"),
            ("t", "入队", 80, "center"),
            ("text", "内容", 540, "w"),
        ):
            self.tv.heading(col, text=title)
            self.tv.column(col, width=width, anchor=anchor, stretch=(col == "text"))

        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for status, color in STATUS_COLOR.items():
            self.tv.tag_configure(status, foreground=color)

    # ---------- 事件 ----------
    def on_vol(self, _=None) -> None:
        v = self.v_vol.get()
        self.lb_vol.config(text=f"{v}%")
        set_system_volume(v)
        self.cfg["volume"] = v
        self.cfg.save()

    def on_gap(self, _=None) -> None:
        g = round(self.v_gap.get(), 1)
        self.lb_gap.config(text=f"{g:.1f}s")
        self.cfg["gap"] = g
        self.cfg.save()

    def on_max(self, _=None) -> None:
        m = round(self.v_max.get(), 1)
        self.lb_max.config(text=f"{m:.1f}s")
        self.cfg["max_sec"] = m
        self.cfg.save()

    def on_rate(self, _=None) -> None:
        r = self.v_rate.get()
        self.lb_rate.config(text=str(r))
        self.cfg["rate"] = r
        self.cfg.save()
        eng = self.core.engine
        if eng is None:
            return
        try:
            if isinstance(eng, SapiEngine):
                eng.sp.Rate = max(-10, min(10, r))
            else:
                eng.set_rate(r)
        except Exception:
            pass

    def on_voice(self, _=None) -> None:
        label = self.v_voice.get()
        vid = EDGE_VOICES.get(label)
        if vid:
            self.cfg["voice"] = vid
            self.cfg.save()
            log(f"切换音色 -> {label}")

    def toggle_pause(self) -> None:
        self.core.paused = not self.core.paused
        self.btn_pause.config(text="▶ 继续" if self.core.paused else "⏸ 暂停")
        self.lb_state.config(text="⏸ 已暂停" if self.core.paused else "● 运行中",
                             fg="#f0c040" if self.core.paused else "#4caf50")

    def test_speak(self) -> None:
        self.core.add("这是一条测试语音，用来检查音量、语速和单段时长限制是否正常。")

    def requeue_selected(self) -> None:
        sel = self.tv.selection()
        if sel:
            try:
                self.core.requeue(int(self.tv.item(sel[0], "values")[0]))
            except (ValueError, IndexError):
                pass

    def on_close(self) -> None:
        self.core.quit = True
        self.core.stop_current()
        self.cfg.save()
        self.destroy()

    # ---------- 刷新 ----------
    def refresh(self) -> None:
        items = self.core.snapshot()
        rows = {str(it["seq"]): it for it in items}

        # 删除已清掉的
        for iid in self.tv.get_children():
            if self.tv.item(iid, "values")[0] not in rows:
                self.tv.delete(iid)

        # 更新 / 新增
        existing = {self.tv.item(i, "values")[0] for i in self.tv.get_children()}
        for it in items:
            seq = str(it["seq"])
            vals = (it["seq"], it["status"], it["n"], it["t"],
                    it["text"].replace("\n", " ")[:70])
            if seq in existing:
                for iid in self.tv.get_children():
                    if self.tv.item(iid, "values")[0] == seq:
                        self.tv.item(iid, values=vals, tags=(it["status"],))
                        break
            else:
                self.tv.insert("", "end", values=vals, tags=(it["status"],))

        # 自动跟随正在朗读的条目
        for it in items:
            if it["status"] == ST_READING:
                for iid in self.tv.get_children():
                    if self.tv.item(iid, "values")[0] == str(it["seq"]):
                        self.tv.see(iid)
                        break
                break

        pending = sum(1 for x in items if x["status"] == ST_PENDING)
        done = sum(1 for x in items if x["status"] == ST_DONE)
        cut = sum(1 for x in items if x["status"] == ST_TIMEOUT)
        self.lb_stat.config(
            text=f"共 {len(items)} 条 | 待读 {pending} | 已读 {done} | "
                 f"超时 {cut} | 系统音量 {get_system_volume()}%"
        )
        self.after(500, self.refresh)

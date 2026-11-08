# -*- coding: utf-8 -*-
"""朗读核心：数据库监视 + 队列 + 播放线程 + 热键"""
from __future__ import annotations

import json
import os
import queue as pyqueue
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import db_source
from .config import Config
from .engines import BaseEngine, SapiEngine, create_engine
from .textproc import split_sentences

APP_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = APP_DIR / "reader.log"
STATE_FILE = APP_DIR / "state.json"
STOP_FLAG = APP_DIR / "stop.flag"

# 状态常量
ST_PENDING = "待读"
ST_READING = "朗读中"
ST_DONE = "已读"
ST_TIMEOUT = "超时截断"
ST_STOPPED = "已停止"
ST_CANCELED = "已取消"
ST_ERROR = "出错"


# ---------------------------------------------------------
#  日志（带大小轮转）
# ---------------------------------------------------------
class Log:
    def __init__(self, path: Path = LOG_FILE, max_mb: float = 5):
        self.path = path
        self.max_bytes = int(max_mb * 1024 * 1024)
        self._lock = threading.Lock()

    def __call__(self, msg: str) -> None:
        line = time.strftime("[%H:%M:%S] ") + str(msg)
        print(line, flush=True)
        with self._lock:
            try:
                if self.path.exists() and self.path.stat().st_size > self.max_bytes:
                    backup = self.path.with_suffix(".log.1")
                    try:
                        if backup.exists():
                            backup.unlink()
                        self.path.rename(backup)
                    except OSError:
                        pass
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


log = Log()


# ---------------------------------------------------------
#  播放核心
# ---------------------------------------------------------
class VoiceCore:
    def __init__(self, cfg: Config, on_change: Optional[Callable[[], None]] = None):
        self.cfg = cfg
        self.log = log
        self.on_change = on_change

        self.lock = threading.Lock()
        self.items: list[dict] = []
        self._pending: pyqueue.Queue[int] = pyqueue.Queue()
        self._seq = 0

        self.stop_evt = threading.Event()
        self.paused = False
        self.error_streak = 0

        self.quit = False
        self._reading_since = 0.0
        self._reading_seq = 0
        self.engine: Optional[BaseEngine] = None
        self._engine_voice: Optional[str] = None

    # ---------- 队列操作 ----------
    def add(self, text: str) -> None:
        with self.lock:
            self._seq += 1
            item = {
                "seq": self._seq,
                "text": text,
                "status": ST_PENDING,
                "n": len(text),
                "t": time.strftime("%H:%M:%S"),
            }
            self.items.append(item)
            self._pending.put(self._seq)
        self._notify()

    def add_turn(self, paras: list[str]) -> None:
        """新一轮对话：打断当前 + 清空积压（只读最新一轮）"""
        if not paras:
            return
        if self.cfg.get("only_latest_turn", True):
            self.stop_current()
            self.clear_pending()
        self.log(f"===== 新一轮对话，{len(paras)} 段 =====")
        for p in paras:
            self.add(p)

    def get(self, seq: int) -> Optional[dict]:
        with self.lock:
            for it in self.items:
                if it["seq"] == seq:
                    return it
        return None

    def snapshot(self) -> list[dict]:
        with self.lock:
            return [dict(x) for x in self.items]

    def clear_pending(self) -> None:
        with self.lock:
            for it in self.items:
                if it["status"] == ST_PENDING:
                    it["status"] = ST_CANCELED
            while not self._pending.empty():
                try:
                    self._pending.get_nowait()
                except pyqueue.Empty:
                    break
        self._notify()

    def clear_finished(self) -> None:
        with self.lock:
            self.items = [x for x in self.items if x["status"] in (ST_PENDING, ST_READING)]
        self._notify()

    def requeue(self, seq: int) -> None:
        it = self.get(seq)
        if it and it["status"] != ST_READING:
            it["status"] = ST_PENDING
            self._pending.put(seq)
            self._notify()

    def stop_current(self) -> None:
        self.stop_evt.set()

    def _notify(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ---------- 引擎 ----------
    def _ensure_engine(self) -> BaseEngine:
        voice = self.cfg.get("voice") or ""
        if self.engine is None or self._engine_voice != voice:
            self.engine = create_engine(voice, int(self.cfg.get("rate", 0)))
            self._engine_voice = voice
            self.log(f"引擎: {self.engine.name} {getattr(self.engine, 'voice', '')}")
        return self.engine

    # ---------- 播放线程 ----------
    def player_loop(self) -> None:
        while not self.quit:
            if self.paused:
                time.sleep(0.1)
                continue
            try:
                seq = self._pending.get(timeout=0.2)
            except pyqueue.Empty:
                self._consume_stop_flag()
                continue

            item = self.get(seq)
            if not item or item["status"] != ST_PENDING:
                continue

            self.stop_evt.clear()
            item["status"] = ST_READING
            self._reading_since = time.time()
            self._reading_seq = seq
            self._notify()

            try:
                self._ensure_engine()
                reason = self._speak_item(item["text"])
            except Exception as e:
                self.log(f"朗读异常: {e}")
                reason = ST_ERROR

            item["status"] = reason
            self._reading_since = 0.0
            self.log(f"#{seq} -> {reason}")
            self._notify()

            gap = float(self.cfg.get("gap", 0.0))
            end = time.time() + gap
            while time.time() < end and not self.quit:
                time.sleep(0.05)

    def _consume_stop_flag(self) -> None:
        if STOP_FLAG.exists():
            try:
                STOP_FLAG.unlink()
            except OSError:
                pass

    def _speak_item(self, text: str) -> str:
        """整句朗读：到时限停在句子边界，不切半句"""
        max_sec = float(self.cfg.get("max_sec", 7.0))
        chunks = split_sentences(text)
        if not chunks:
            return ST_DONE

        engine = self.engine
        prefetch = getattr(engine, "prefetch", None)
        if callable(prefetch):
            prefetch(chunks)

        played = 0.0
        for i, chunk in enumerate(chunks):
            if self.stop_evt.is_set():
                return ST_STOPPED
            if played >= max_sec:
                self.log(f"已播 {played:.1f}s 达到 {max_sec:.1f}s 上限 "
                         f"-> 停在句子边界 ({i}/{len(chunks)} 句)")
                return ST_TIMEOUT
            played += float(engine.speak(chunk, self.stop_evt) or 0.0)
            if self.stop_evt.is_set():
                return ST_STOPPED
        return ST_DONE


# ---------------------------------------------------------
#  数据库监视线程
# ---------------------------------------------------------
class DbWatcher(threading.Thread):
    def __init__(self, core: VoiceCore, db: Path):
        super().__init__(daemon=True)
        self.core = core
        self.db = db
        self.cfg = core.cfg

    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: dict) -> None:
        try:
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def run(self) -> None:
        state = self._load_state()

        # 首次运行：定位到末尾，不朗读历史
        got = db_source.fetch_latest_conversation(self.db)
        if got:
            cid, messages = got
            turns = db_source.assistant_turns(messages)
            state = {"conv": cid, "turn": len(turns)}
            self._save_state(state)
            log(f"起点已定位：历史 {len(turns)} 轮（不朗读）")
        else:
            log("尚未找到会话，等待中…")

        interval = float(self.cfg.get("poll_interval", 0.4))
        while not self.core.quit:
            try:
                got = db_source.fetch_latest_conversation(self.db)
                if got:
                    cid, messages = got
                    turns = db_source.assistant_turns(messages)
                    if state.get("conv") != cid:
                        state = {"conv": cid, "turn": 0}
                    done = int(state.get("turn", 0))
                    if len(turns) < done:            # 上下文被裁剪
                        done = len(turns)
                        state["turn"] = done
                    elif len(turns) > done:
                        # 同一次轮询里的多条新消息 = 同一轮回复（工具调用会拆成多条）
                        batch = [p for t in turns[done:] for p in t]
                        if batch:
                            self.core.add_turn(batch)
                        state["turn"] = len(turns)
                        self._save_state(state)
            except Exception as e:
                log(f"轮询异常: {e}")
            time.sleep(interval)


# ---------------------------------------------------------
#  热键线程
# ---------------------------------------------------------
def _parse_hotkey(spec: str) -> list[int]:
    vk_map = {
        "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "win": 0x5B,
    }
    keys = []
    for part in spec.lower().replace(" ", "").split("+"):
        if part in vk_map:
            keys.append(vk_map[part])
        elif len(part) == 1 and part.isalnum():
            keys.append(ord(part.upper()))
        elif part.startswith("f") and part[1:].isdigit():
            keys.append(0x70 + int(part[1:]) - 1)
    return keys


class HotkeyWatcher(threading.Thread):
    def __init__(self, core: VoiceCore, spec: str):
        super().__init__(daemon=True)
        self.core = core
        self.keys = _parse_hotkey(spec)
        self._last = 0.0

    def run(self) -> None:
        if not self.keys:
            return
        import ctypes
        user32 = ctypes.windll.user32
        while not self.core.quit:
            try:
                down = all(user32.GetAsyncKeyState(k) & 0x8000 for k in self.keys)
                # Shift 左右任一即可
                if 0x10 in self.keys:
                    down = down or all(
                        (user32.GetAsyncKeyState(0xA0) & 0x8000
                         or user32.GetAsyncKeyState(0xA1) & 0x8000)
                        if k == 0x10 else user32.GetAsyncKeyState(k) & 0x8000
                        for k in self.keys
                    )
                now = time.time()
                if down and now - self._last > 0.8:
                    self._last = now
                    log("热键触发 -> 停止当前")
                    self.core.stop_current()
                if STOP_FLAG.exists():
                    self.core.stop_current()
                    try:
                        STOP_FLAG.unlink()
                    except OSError:
                        pass
            except Exception:
                pass
            time.sleep(0.05)


# ---------------------------------------------------------
#  看门狗：防止某次朗读卡死整个播放线程
# ---------------------------------------------------------
class Watchdog(threading.Thread):
    def __init__(self, core: "VoiceCore", grace: float = 25.0):
        super().__init__(daemon=True)
        self.core = core
        self.grace = grace

    def run(self) -> None:
        while not self.core.quit:
            try:
                since = self.core._reading_since
                if since and time.time() - since > (
                    float(self.core.cfg.get("max_sec", 7.0)) + self.grace
                ):
                    log(f"看门狗：#{self.core._reading_seq} 朗读超时，强制中断")
                    self.core.stop_current()
                    eng = self.core.engine
                    if eng is not None:
                        try:
                            eng.purge()
                        except Exception:
                            pass
                    self.core._reading_since = 0.0
            except Exception:
                pass
            time.sleep(2.0)

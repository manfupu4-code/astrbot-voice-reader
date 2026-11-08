# -*- coding: utf-8 -*-
"""TTS 引擎：系统 SAPI（离线）与 Edge-TTS（在线，音质更好）"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Optional

APP_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = APP_DIR / "tts_cache"


class BaseEngine:
    name = "base"
    voice = None

    def speak(self, text: str, stop_event: threading.Event) -> float:
        """朗读一句，返回实际播放秒数；被 stop_event 打断则提前返回"""
        raise NotImplementedError

    def purge(self) -> None:
        pass


# ---------------------------------------------------------
#  系统 SAPI —— 离线可用，音色偏机械
# ---------------------------------------------------------
class SapiEngine(BaseEngine):
    name = "Windows SAPI"

    def __init__(self, rate: int = 0, volume: int = 100):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()          # 必须在当前线程初始化 COM
        self._pycom = pythoncom
        self.sp = win32com.client.Dispatch("SAPI.SpVoice")
        self.sp.Rate = max(-10, min(10, int(rate)))
        self.sp.Volume = max(0, min(100, int(volume)))
        self._pick_chinese_voice()

    def _pick_chinese_voice(self) -> None:
        try:
            voices = self.sp.GetVoices()
            for i in range(voices.Count):
                desc = voices.Item(i).GetDescription()
                if any(k in desc for k in ("Huihui", "Chinese", "中文")):
                    self.sp.Voice = voices.Item(i)
                    return
        except Exception:
            pass

    def speak(self, text: str, stop_event: threading.Event) -> float:
        SVSF_ASYNC, SVSF_PURGE = 1, 2
        t0 = time.time()
        self.sp.Speak(text, SVSF_ASYNC | SVSF_PURGE)

        # 宽限期：等它真正开口（最多 3 秒）
        while time.time() - t0 < 3.0:
            if stop_event.is_set():
                self.purge()
                return time.time() - t0
            try:
                if self.sp.Status.RunningState == 2:
                    break
            except Exception:
                return time.time() - t0
            time.sleep(0.03)

        while True:
            if stop_event.is_set():
                self.purge()
                return time.time() - t0
            try:
                if self.sp.Status.RunningState != 2:
                    break
            except Exception:
                break
            time.sleep(0.05)
        return time.time() - t0

    def purge(self) -> None:
        try:
            self.sp.Speak("", 3)
        except Exception:
            pass


# ---------------------------------------------------------
#  Edge-TTS —— 微软神经语音，接近真人，需要联网
# ---------------------------------------------------------
EDGE_VOICES = {
    "晓伊（女·活泼）": "zh-CN-XiaoyiNeural",
    "晓晓（女·温柔）": "zh-CN-XiaoxiaoNeural",
    "云希（男·少年）": "zh-CN-YunxiNeural",
    "云扬（男·播音）": "zh-CN-YunyangNeural",
    "云健（男·激情）": "zh-CN-YunjianNeural",
    "云夏（男·可爱）": "zh-CN-YunxiaNeural",
    "小北（东北话）": "zh-CN-liaoning-XiaobeiNeural",
    "小妮（陕西话）": "zh-CN-shaanxi-XiaoniNeural",
}


class EdgeTtsEngine(BaseEngine):
    name = "Edge-TTS"

    def __init__(self, voice: str = "zh-CN-XiaoyiNeural", rate: int = 0):
        import pygame

        self.pygame = pygame
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=44100)
        self.voice = voice
        self.set_rate(rate)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.cache_dir = str(CACHE_DIR)
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self.synth_timeout = 20.0   # 单句合成最长等待（秒）
        self.lock_timeout = 30.0    # 等待其他线程释放缓存锁的上限

    # ---- 语速：面板的 -10~10 换算成百分比 ----
    def set_rate(self, rate: int) -> None:
        self.rate_pct = max(-90, min(100, int(rate) * 5))
        sign = "+" if self.rate_pct >= 0 else ""
        self.rate = f"{sign}{self.rate_pct}%"

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lk = self._locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._locks[key] = lk
            return lk

    def _synth(self, text: str) -> str:
        """合成并返回 mp3 路径（带缓存、加锁、原子写入）"""
        import edge_tts

        key = hashlib.md5((self.voice + self.rate + text).encode("utf-8")).hexdigest()
        path = os.path.join(self.cache_dir, key + ".mp3")

        if os.path.exists(path) and os.path.getsize(path) > 1024:
            return path

        lock = self._lock_for(key)
        if not lock.acquire(timeout=self.lock_timeout):
            raise RuntimeError("合成等待超时")
        try:
            if os.path.exists(path) and os.path.getsize(path) > 1024:
                return path
            tmp = path + ".part"

            async def go():
                await asyncio.wait_for(
                    edge_tts.Communicate(text, self.voice, rate=self.rate).save(tmp),
                    timeout=self.synth_timeout,
                )

            try:
                asyncio.run(go())
                if os.path.getsize(tmp) <= 1024:
                    raise RuntimeError("合成结果为空（可能被网络限制）")
                os.replace(tmp, path)      # 原子替换，避免读到半个文件
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        finally:
            lock.release()
        return path

    def _safe_synth(self, text: str) -> Optional[str]:
        try:
            return self._synth(text)
        except Exception:
            return None

    def prefetch(self, texts: list[str]) -> None:
        """并行预合成，降低第一句的等待时间"""
        texts = [t for t in texts if t]
        if not texts:
            return

        def work():
            try:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
                    list(ex.map(self._safe_synth, texts))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def speak(self, text: str, stop_event: threading.Event) -> float:
        path = self._synth(text)
        m = self.pygame.mixer.music
        try:
            m.load(path)
        except Exception:
            # 缓存损坏：删掉重来一次
            try:
                os.remove(path)
            except OSError:
                pass
            m.load(self._synth(text))

        m.play()
        t0 = time.time()
        while True:
            if stop_event.is_set():
                m.stop()
                return time.time() - t0
            if not m.get_busy() and time.time() - t0 > 0.2:
                return time.time() - t0
            time.sleep(0.03)

    def purge(self) -> None:
        try:
            self.pygame.mixer.music.stop()
        except Exception:
            pass


# ---------------------------------------------------------
def create_engine(voice: str = "", rate: int = 0) -> BaseEngine:
    """按配置创建引擎；Edge 失败时自动回退到 SAPI"""
    if voice:
        try:
            return EdgeTtsEngine(voice, rate)
        except Exception:
            pass
    return SapiEngine(rate)

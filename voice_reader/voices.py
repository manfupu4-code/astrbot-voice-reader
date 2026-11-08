# -*- coding: utf-8 -*-
"""音色目录：内置常用音色 + 在线拉取完整列表 + 用户自定义

设计目标：不把音色写死在代码里。用户可以在面板里刷新列表、挑选、保存，
也可以手动往 config.json 里塞自定义音色。
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
CACHE_FILE = APP_DIR / "voices_cache.json"
CACHE_TTL = 7 * 24 * 3600      # 缓存一周

# 内置兜底（离线也能用）
BUILTIN: list[dict[str, Any]] = [
    {"id": "zh-CN-XiaoyiNeural", "label": "晓伊 · 女 · 活泼", "locale": "zh-CN"},
    {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓 · 女 · 温柔", "locale": "zh-CN"},
    {"id": "zh-CN-YunxiNeural", "label": "云希 · 男 · 少年", "locale": "zh-CN"},
    {"id": "zh-CN-YunyangNeural", "label": "云扬 · 男 · 播音", "locale": "zh-CN"},
    {"id": "zh-CN-YunjianNeural", "label": "云健 · 男 · 激情", "locale": "zh-CN"},
    {"id": "zh-CN-YunxiaNeural", "label": "云夏 · 男 · 可爱", "locale": "zh-CN"},
    {"id": "zh-CN-liaoning-XiaobeiNeural", "label": "小北 · 女 · 东北话", "locale": "zh-CN"},
    {"id": "zh-CN-shaanxi-XiaoniNeural", "label": "小妮 · 女 · 陕西话", "locale": "zh-CN"},
    {"id": "zh-HK-HiuMaanNeural", "label": "曉曼 · 女 · 粤语", "locale": "zh-HK"},
    {"id": "zh-TW-HsiaoChenNeural", "label": "曉臻 · 女 · 台湾", "locale": "zh-TW"},
]

_GENDER_CN = {"Female": "女", "Male": "男"}

# 常见音色的中文名（没有的会退回英文短名）
CN_NAMES = {
    "zh-CN-XiaoxiaoNeural": "晓晓",
    "zh-CN-XiaoyiNeural": "晓伊",
    "zh-CN-YunjianNeural": "云健",
    "zh-CN-YunxiNeural": "云希",
    "zh-CN-YunxiaNeural": "云夏",
    "zh-CN-YunyangNeural": "云扬",
    "zh-CN-liaoning-XiaobeiNeural": "小北",
    "zh-CN-shaanxi-XiaoniNeural": "小妮",
    "zh-HK-HiuGaaiNeural": "曉佳",
    "zh-HK-HiuMaanNeural": "曉曼",
    "zh-HK-WanLungNeural": "雲龍",
    "zh-TW-HsiaoChenNeural": "曉臻",
    "zh-TW-HsiaoYuNeural": "曉雨",
    "zh-TW-YunJheNeural": "雲哲",
}

_LOCALE_CN = {
    "zh-CN": "普通话", "zh-CN-liaoning": "东北话", "zh-CN-shaanxi": "陕西话",
    "zh-HK": "粤语", "zh-TW": "台湾",
}


def _norm(item: dict) -> dict:
    """把 edge-tts 返回的原始条目规整成统一结构"""
    sid = item.get("ShortName") or item.get("id") or ""
    locale = item.get("Locale") or ""
    gender = _GENDER_CN.get(item.get("Gender", ""), "")
    tags = (item.get("VoiceTag") or {}).get("VoicePersonalities") or []
    short = CN_NAMES.get(sid) or sid.replace("Neural", "").split("-")[-1]
    parts = [short]
    if locale in _LOCALE_CN:
        parts.append(_LOCALE_CN[locale])
    if gender:
        parts.append(gender)
    if tags:
        parts.append("/".join(tags[:2]))
    return {"id": sid, "label": " · ".join(parts), "locale": locale}


def fetch_online(timeout: float = 20.0) -> list[dict]:
    """从 edge-tts 拉取完整音色列表（需要联网）"""
    import edge_tts

    async def go():
        return await asyncio.wait_for(edge_tts.list_voices(), timeout=timeout)

    raw = asyncio.run(go())
    return [v for v in raw if v.get("ShortName")]


def save_cache(voices: list[dict]) -> None:
    try:
        CACHE_FILE.write_text(
            json.dumps({"ts": time.time(), "voices": voices}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def load_cache(allow_expired: bool = False) -> list[dict]:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not allow_expired and time.time() - data.get("ts", 0) > CACHE_TTL:
        return []
    return data.get("voices", [])


def get_catalog(extra: list[dict] | None = None, only_zh: bool = False) -> list[dict]:
    """取音色目录：缓存 > 内置。extra 为用户自定义音色"""
    cached = load_cache()
    if cached:
        voices = [_norm(v) if "ShortName" in v else v for v in cached]
    else:
        voices = BUILTIN
    if only_zh:
        voices = [v for v in voices if v["locale"].startswith("zh")]
    if extra:
        extra_norm = [_norm(e) if "ShortName" in e else e for e in extra]
        voices = voices + extra_norm
    # 去重
    seen, out = set(), []
    for v in voices:
        if v["id"] and v["id"] not in seen:
            seen.add(v["id"])
            out.append(v)
    return out


def refresh(only_zh: bool = False) -> tuple[bool, str]:
    """刷新在线音色列表并写缓存，返回 (成功?, 提示)"""
    try:
        voices = fetch_online()
        if not voices:
            return False, "在线列表为空"
        save_cache(voices)
        n_zh = len([v for v in voices if str(v.get("Locale", "")).startswith("zh")])
        return True, f"已获取 {len(voices)} 个音色，其中中文 {n_zh} 个"
    except Exception as e:
        return False, f"拉取失败：{e}"


def label_of(voice_id: str, catalog: list[dict] | None = None) -> str:
    for v in (catalog or get_catalog()):
        if v["id"] == voice_id:
            return v["label"]
    return voice_id or "系统语音"

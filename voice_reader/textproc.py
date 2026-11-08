# -*- coding: utf-8 -*-
"""文本清洗：把 Markdown / 富文本清洗成适合朗读的纯口语"""
from __future__ import annotations

import re

# 系统提示块
RE_SYSTEM = re.compile(r"<system_reminder>.*?</system_reminder>", re.S)
# 代码块（整体跳过）
RE_CODEBLOCK = re.compile(r"```.*?```", re.S)
# 行内代码
RE_INLINE_CODE = re.compile(r"`[^`]*`")
# 表情包标记 &&happy&&
RE_MEME = re.compile(r"&&[a-zA-Z_]+&&")
# 链接与图片
RE_URL = re.compile(r"https?://\S+")
RE_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Markdown 强调符号
RE_MD = re.compile(r"[*_#>]+")
# 分隔线
RE_HR = re.compile(r"^\s*[-=]{3,}\s*$", re.M)
# 多余空白
RE_SPACES = re.compile(r"[ \t\u3000]+")
RE_BLANK = re.compile(r"\n{2,}")
# 句子切分（保留标点）
RE_SENT = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def clean_text(raw: str) -> str:
    """把一段 Markdown 洗成适合朗读的纯文本"""
    if not raw:
        return ""
    t = raw
    t = RE_SYSTEM.sub(" ", t)
    t = RE_CODEBLOCK.sub(" ", t)      # 代码块跳过（可读性太差）
    t = RE_INLINE_CODE.sub(" ", t)
    t = RE_MEME.sub(" ", t)           # 表情标记不念
    t = RE_IMG.sub(" ", t)
    t = RE_URL.sub(" ", t)
    t = RE_HR.sub(" ", t)
    t = t.replace("|", "，")           # 表格竖线转停顿
    t = t.replace("---", "，")
    t = RE_MD.sub("", t)
    t = t.replace("•", "，")
    t = RE_SPACES.sub(" ", t)
    t = RE_BLANK.sub("\n", t)

    lines = [ln.strip() for ln in t.split("\n")]
    lines = [ln for ln in lines if ln and not re.fullmatch(r"[，。、；：\s:;]+", ln)]
    return " ".join(lines).strip()


def split_sentences(text: str, soft_len: int = 24) -> list[str]:
    """按标点切成小句，保证不会从半个字断开"""
    parts: list[str] = []
    for m in RE_SENT.finditer(text or ""):
        s = m.group().strip()
        if not s:
            continue
        while len(s) > soft_len:
            idx = max(s.rfind(c, 0, soft_len) for c in "，,、：:")
            if idx <= 2:
                idx = soft_len
            parts.append(s[: idx + 1].strip())
            s = s[idx + 1 :].strip()
        if s:
            parts.append(s)
    return parts


def split_paragraphs(raw: str, limit: int = 110) -> list[str]:
    """把一整条回复拆成若干「段」，每段作为独立朗读单元"""
    if not raw or not raw.strip():
        return []
    out: list[str] = []
    for block in re.split(r"\n\s*\n", raw):
        t = clean_text(block)
        if not t:
            continue
        buf = ""
        for s in split_sentences(t):
            if buf and len(buf) + len(s) > limit:
                out.append(buf)
                buf = s
            else:
                buf += s
        if buf:
            out.append(buf)
    return out

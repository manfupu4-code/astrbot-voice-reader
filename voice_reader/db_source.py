# -*- coding: utf-8 -*-
"""AstrBot 数据库读取：自动定位 data_v4.db，提取助手回复"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .textproc import split_paragraphs


def find_database(hint: str = "") -> Optional[Path]:
    """按优先级查找 AstrBot 的 data_v4.db

    1. 环境变量 ASTRBOT_DB
    2. 配置里的 db_path
    3. 常见安装位置（取最新的一个）
    """
    candidates: list[Path] = []

    env = os.environ.get("ASTRBOT_DB", "").strip()
    if env:
        candidates.append(Path(env))
    if hint and hint.strip():
        candidates.append(Path(hint.strip()))

    home = Path.home()
    patterns = [
        home / ".astrbot_launcher" / "instances" / "*" / "core" / "data" / "data_v4.db",
        home / ".astrbot" / "data" / "data_v4.db",
        home / "astrbot" / "data" / "data_v4.db",
        Path("data") / "data_v4.db",
    ]
    for pat in patterns:
        if "*" in str(pat):
            candidates.extend(Path(p) for p in glob.glob(str(pat)))
        elif pat.exists():
            candidates.append(pat)

    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return None
    # 多个实例时，取最近修改的那个
    return max(existing, key=lambda p: p.stat().st_mtime)


def open_readonly(db: Path) -> sqlite3.Connection:
    """只读打开，绝不写库"""
    uri = f"file:{db.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=3.0)
    con.row_factory = sqlite3.Row
    return con


def fetch_latest_conversation(db: Path) -> Optional[tuple[str, list[dict[str, Any]]]]:
    """取最近更新的会话，返回 (conversation_id, messages)"""
    con = open_readonly(db)
    try:
        row = con.execute(
            "SELECT conversation_id, content FROM conversations "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    cid = row["conversation_id"]
    try:
        data = json.loads(row["content"] or "[]")
    except Exception:
        data = []
    if not isinstance(data, list):
        data = []
    return cid, data


def _message_raw_text(msg: dict[str, Any]) -> str:
    """取出单条消息的纯文本部分（忽略 think / 工具调用）"""
    parts = msg.get("content")
    if isinstance(parts, str):
        return parts
    if isinstance(parts, list):
        buf = []
        for p in parts:
            if isinstance(p, dict) and p.get("type") == "text":
                buf.append(p.get("text", ""))
        return "\n".join(buf)
    return ""


def assistant_turns(messages: list[dict[str, Any]]) -> list[list[str]]:
    """把助手消息按「轮」拆成段落列表

    返回 [[段1, 段2, ...], [段...], ...]，每个内层列表是一轮完整回复。
    """
    turns: list[list[str]] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        raw = _message_raw_text(msg)
        paras = split_paragraphs(raw)
        if paras:
            turns.append(paras)
    return turns

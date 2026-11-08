# -*- coding: utf-8 -*-
"""配置管理：读写 config.json，带默认值与校验"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS: Dict[str, Any] = {
    # 数据库（留空则自动查找）
    "db_path": "",
    # 朗读
    "voice": "zh-CN-XiaoyiNeural",   # 为空字符串则使用系统 SAPI
    "custom_voices": [],             # 自定义音色，格式 [{"id": "...", "label": "..."}]
    "volume": 80,                    # 系统主音量 0-100
    "gap": 0.0,                      # 上一段念完到下一段的间隔（秒）
    "max_sec": 7.0,                  # 单段最多朗读时长（秒，按整句断）
    "rate": 0,                       # 语速：SAPI 为 -10~10，Edge 自动换算
    # 行为
    "only_latest_turn": True,        # True=只读最新一轮，新对话覆盖旧对话
    "hotkey": "shift+win+e",         # 静音热键
    "poll_interval": 0.4,            # 数据库轮询间隔（秒）
    "log_max_mb": 5,                 # 日志超过此大小自动轮转
}


class Config:
    """轻量配置对象，支持 dict 式访问"""

    def __init__(self, data: Dict[str, Any] | None = None):
        self._d: Dict[str, Any] = dict(DEFAULTS)
        if data:
            self._d.update({k: v for k, v in data.items() if k in DEFAULTS})

    # ---- dict 接口 ----
    def get(self, key: str, default=None):
        return self._d.get(key, default)

    def __getitem__(self, key):
        return self._d[key]

    def __setitem__(self, key, value):
        self._d[key] = value

    def update(self, **kw):
        self._d.update(kw)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._d)

    # ---- 持久化 ----
    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        p = path or CONFIG_PATH
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        else:
            # 首次运行：写出带注释意义的默认配置
            cfg = cls(data)
            cfg.save(p)
            return cfg
        return cls(data)

    def save(self, path: Path | None = None) -> None:
        p = path or CONFIG_PATH
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                json.dumps(self._d, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

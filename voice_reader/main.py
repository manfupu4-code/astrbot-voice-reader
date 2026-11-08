# -*- coding: utf-8 -*-
"""AstrBot 语音朗读器 —— 程序入口"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from .config import Config
from .db_source import find_database
from .engines import create_engine
from .player import DbWatcher, HotkeyWatcher, VoiceCore, Watchdog, log
from . import voices as voice_catalog


def _bootstrap(cfg: Config, db_override: str) -> Path | None:
    db = find_database(db_override or cfg.get("db_path", ""))
    if db is None:
        log("✗ 找不到 AstrBot 的 data_v4.db")
        log("  请用 --db 指定路径，或设置环境变量 ASTRBOT_DB")
        return None
    log(f"数据库: {db}")
    return db


def cmd_list_voices(refresh: bool = False) -> int:
    """列出可用音色"""
    if refresh:
        ok, msg = voice_catalog.refresh()
        log(msg)
        if not ok:
            log("使用离线内置列表")
    catalog = voice_catalog.get_catalog()
    zh = [v for v in catalog if v["locale"].startswith("zh")]
    print(f"\n共 {len(catalog)} 个音色，其中中文 {len(zh)} 个：\n")
    for v in zh:
        print(f"  {v['id']:<34} {v['label']}")
    others = len(catalog) - len(zh)
    if others:
        print(f"\n  另有 {others} 个其他语种音色，可用 --list-voices 查看全部后手动指定")
    print()
    return 0


def cmd_test(cfg: Config) -> int:
    """自检：播报一句测试语音"""
    engine = create_engine(cfg.get("voice") or "", int(cfg.get("rate", 0)))
    log(f"引擎: {engine.name}")
    engine.speak("语音朗读器自检通过，我是你的嗓子。", threading.Event())
    return 0


def cmd_run(cfg: Config, db: Path, gui: bool, volume: int | None) -> int:
    if volume is not None:
        cfg["volume"] = volume
        cfg.save()
        try:
            from .panel import set_system_volume
            set_system_volume(volume)
        except Exception:
            pass

    core = VoiceCore(cfg)
    watcher = DbWatcher(core, db)

    threads = [
        threading.Thread(target=core.player_loop, daemon=True, name="player"),
        watcher,
        HotkeyWatcher(core, cfg.get("hotkey", "shift+win+e")),
        Watchdog(core),
    ]
    for t in threads:
        t.start()

    log("=" * 52)
    log(f"语音朗读器启动 | 音色 {cfg.get('voice') or '系统默认'}")
    log(f"热键 {cfg.get('hotkey')} 停止当前 | 单段上限 {cfg.get('max_sec')}s")
    log("=" * 52)

    if not gui:
        try:
            while not core.quit:
                threading.Event().wait(0.5)
        except KeyboardInterrupt:
            log("收到中断，退出")
            core.quit = True
            core.stop_current()
        return 0

    try:
        from .panel import Panel
    except Exception as e:              # tkinter 不可用时自动降级
        log(f"面板不可用（{e}），以无界面模式运行")
        return cmd_run(cfg, db, gui=False, volume=None)

    Panel(core, cfg).mainloop()
    core.quit = True
    core.stop_current()
    return 0


def build_parser() -> argparse.ArgumentParser:
    from . import __version__

    p = argparse.ArgumentParser(
        prog="astrbot-voice-reader",
        description="让 AstrBot 用扬声器把回复念出来（实时、可控、可打断）",
    )
    p.add_argument("--db", default="", help="AstrBot 的 data_v4.db 路径（默认自动查找）")
    p.add_argument("--voice", default=None, help="音色 ID，如 zh-CN-XiaoyiNeural；留空用系统语音")
    p.add_argument("--volume", type=int, default=None, help="系统音量 0-100")
    p.add_argument("--no-gui", action="store_true", help="不启动面板，纯后台运行")
    p.add_argument("--test", action="store_true", help="自检：播报一句测试语音后退出")
    p.add_argument("--list-voices", action="store_true", help="列出可用音色")
    p.add_argument("--refresh-voices", action="store_true",
                   help="联网刷新音色列表（配合 --list-voices 使用）")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load()

    if args.voice is not None:
        cfg["voice"] = args.voice.strip()
        cfg.save()

    if args.list_voices:
        return cmd_list_voices(refresh=args.refresh_voices)

    if args.test:
        return cmd_test(cfg)

    db = _bootstrap(cfg, args.db)
    if db is None:
        return 2
    return cmd_run(cfg, db, gui=not args.no_gui, volume=args.volume)


if __name__ == "__main__":
    sys.exit(main())

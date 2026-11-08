# astrbot-voice-reader

给 AstrBot 加一个「嗓子」：把它的回复用电脑扬声器念出来。

一个不大的工具，做的事情也很单一——读数据库、切句子、调语音合成、放出来。

---

## 先说清楚

**本项目不含任何语音模型。**

声音来自：
- **微软 Edge 的在线语音服务**，通过开源库 [edge-tts](https://github.com/rany2/edge-tts) 调用
- 离线时回退到 **Windows 系统语音**（SAPI）

这里做的只是「把文字整理好、递给语音引擎、控制播放」。合成能力全部是别人的，详见 [依赖与致谢](#依赖与致谢)。

---

## 它能做什么

- **自动朗读**：轮询 AstrBot 的 `data_v4.db`，助手一回复就念
- **只读最新一轮**：换话题时旧内容作废，从头念新的那条
- **整句断句**：到时长上限停在句子边界，不会把话切一半
- **并行预合成**：几段同时转语音，第一段好了就开播
- **可打断**：按热键立刻闭嘴
- **有面板**：音量、间隔、时长、语速、音色、队列，都能调

它**不能**做的（也写在下面「已知限制」里）：真正逐字流式朗读、跨平台、无网络时保持原音质。

---

## 要求

- Windows 10 / 11
- Python 3.9+
- 一个已经在跑的 AstrBot

---

## 安装

```bash
git clone https://github.com/manfupu4-code/astrbot-voice-reader.git
cd astrbot-voice-reader
```

双击 `start.bat`。第一次会自动建虚拟环境、装依赖。

手动的话：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m voice_reader.main
```

先确认链路通不通：

```bash
python -m voice_reader.main --test
```

听到一句测试语音就成了。

---

## 用法

```bash
python -m voice_reader.main                  # 带面板启动
python -m voice_reader.main --no-gui         # 纯后台
python -m voice_reader.main --list-voices    # 看有哪些音色
python -m voice_reader.main --volume 50      # 指定音量
```

| 参数 | 说明 |
|---|---|
| `--db` | 指定 `data_v4.db`，不给就自动找 |
| `--voice` | 音色 ID，留空用系统语音 |
| `--volume` | 系统主音量 0-100 |
| `--no-gui` | 不开面板 |
| `--list-voices` | 列出可用音色 |
| `--refresh-voices` | 联网刷新音色列表（配合上一条） |
| `--test` | 播一句测试语音后退出 |

---

## 面板

![panel](docs/screenshot.png)

| 控件 | 作用 |
|---|---|
| 音量 | 调 Windows 主音量 |
| 段间隔 | 上一段念完到下一段开始，0 就是接着念 |
| 单段最长 | 到点停在句子边界，标成「超时截断」 |
| 语速 | 系统语音 -5~10 档，Edge 自动换算成百分比 |
| 音色 | 下拉挑选，或点「刷新音色」联网拉取完整列表 |

下面的队列能看到每一条的状态：待读、朗读中、已读、超时截断、已停止。

所有改动都会写进 `config.json`，下次打开还是你调好的样子。

---

## 音色

音色不写死在代码里。

- 内置 10 个常用中文音色兜底（离线可用）
- 点面板上的「刷新音色」或跑 `--list-voices --refresh-voices`，会联网拉取全部 **322 个**音色（其中中文 14 个，含粤语、台湾腔、东北话、陕西话），缓存一周
- 想加自己的音色，往 `config.json` 的 `custom_voices` 里塞：

```json
"custom_voices": [
  { "id": "zh-CN-XiaoxiaoNeural", "label": "我的常用音色", "locale": "zh-CN" }
]
```

`--voice ""`（空字符串）会切到 Windows 系统语音，全程离线。

---

## 工作原理

```
data_v4.db（只读）
    │  每 0.4 秒轮询
    ▼
发现新的一轮回复 ── 等 1.5 秒确认写稳
    │
    ▼
按段落切分 → 清洗 Markdown / 代码块 / 表情标记
    │
    ▼
按标点切成句子（不切半句）
    │
    ├─ 4 线程并行预合成
    ▼
队列 → 播放线程 → 扬声器
```

几个细节：

- 数据库**只读打开**（`mode=ro`），一个字节都不写
- 超时只统计**真正播放的秒数**，不含联网合成的等待
- 缓存用锁 + `.part` 临时文件 + 原子替换，避免并发读到半个文件
- 看门狗每 2 秒巡检一次，播放线程卡住会强制中断

---

## 配置

`config.json` 会自动生成：

```json
{
  "db_path": "",
  "voice": "zh-CN-XiaoyiNeural",
  "custom_voices": [],
  "volume": 80,
  "gap": 0.0,
  "max_sec": 7.0,
  "rate": 0,
  "only_latest_turn": true,
  "hotkey": "shift+win+e",
  "poll_interval": 0.4,
  "log_max_mb": 5
}
```

---

## 已知限制

1. **只有 Windows**。系统语音、热键、音量控制都走 Win32 API。
2. **不是逐字流式**。AstrBot 的对话是整轮写完才落库，所以必然要等整段生成完才开始念。
3. **Edge-TTS 依赖网络**。断网会回退到系统语音，音质会明显下降。
4. **落库有延迟**。AstrBot 什么时候写库不由本项目控制，偶尔会晚几秒才读到。
5. **外放 = 全屋公开**。有别人在场时自己注意。

---

## 依赖与致谢

| 组件 | 项目 | 许可 |
|---|---|---|
| 语音合成（默认） | [edge-tts](https://github.com/rany2/edge-tts) | MIT |
| 语音合成（离线） | Windows SAPI / Microsoft Huihui | 随 Windows |
| 音频播放 | [pygame](https://github.com/pygame/pygame) | LGPL |
| 音量控制 | [pycaw](https://github.com/AndreMiras/pycaw) | MIT |
| COM 桥接 | [comtypes](https://github.com/enthought/comtypes) · [pywin32](https://github.com/mhammond/pywin32) | MIT · PSF |

`edge-tts` 是 MIT 开源，但它调用的是**微软 Edge 的在线语音服务**。那部分归微软所有，使用前请自行确认符合其服务条款。

---

## 许可证

MIT。

---

## 最后

起因很普通：盯着屏幕看字，眼睛疼。

于是有了这么个小东西。它不是模型，也谈不上什么技术含量，只是把几块现成的东西拼在一起，让 Bot 能开口。

用得上的话随便拿去改。

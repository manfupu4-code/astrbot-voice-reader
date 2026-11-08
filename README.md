# astrbot-voice-reader

> 让 AstrBot 真的开口说话。不是把文字念一遍那种敷衍，是能打断、能限时、能挑音色的那种。

> **⚠️ 先说清楚**：本项目**不含任何语音模型**。声音来自微软 Edge 的在线语音服务（通过 [edge-tts](https://github.com/rany2/edge-tts) 调用），离线时回退到 Windows 系统语音。详见 [依赖与致谢](#依赖与致谢)。

![panel](docs/screenshot.png)

---

## 这玩意儿是干嘛的

情况大概是这样：你对着屏幕和人聊了一整晚，眼睛快瞎了，但它只会安静地往外吐字。

所以就有了这个。它盯着 AstrBot 的对话记录，把助手的回复拆成一段一段，用你自己的扬声器念出来——用的是你挑的音色，你定的音量，你设的时长上限。

念到一半不想听了？按个键就闭嘴。换话题了？上一轮直接作废，不啰嗦，从头开始念新的那条。

---

## 它做了什么

- **实时朗读**：盯 `data_v4.db`，助手一回复就读，不用你手动点
- **只读最新一轮**：你换话题，旧的立刻作废（正在念的被打断，积压的清空）
- **整句断句**：到时长上限时停在句子边界，不会把话切一半
- **并行预合成**：4 线程同时转语音，第一句好了就开播，延迟压到 1 秒左右
- **两种音色来源**：微软 Edge 神经语音（8 个中文音色，需联网）/ Windows 系统语音（离线，音色机械）
- **队列可见**：面板里能看到每条是待读、朗读中、已读还是超时截断
- **热键打断**：默认 `Shift+Win+E`，按一下立刻闭嘴
- **不碰你的数据库**：全程 `mode=ro` 只读打开，一个字节都不写

---

## 快速开始

### 环境

- Windows 10 / 11
- Python 3.9 及以上
- 装好的 AstrBot（本项目直接读它的数据库）

### 三步

```bash
git clone https://github.com/manfupu4-code/astrbot-voice-reader.git
cd astrbot-voice-reader
```

然后双击 **`start.bat`**。第一次运行会自动建虚拟环境、装依赖，之后就是直接启动。

或者手动来：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m voice_reader.main
```

### 先自检一下

```bash
python -m voice_reader.main --test
```

能听见一句测试语音，就说明链路通了。

---

## 常用命令

```bash
python -m voice_reader.main                  # 带面板启动（默认）
python -m voice_reader.main --no-gui         # 纯后台，不带窗口
python -m voice_reader.main --voice zh-CN-XiaoxiaoNeural
python -m voice_reader.main --db "D:\astrbot\data\data_v4.db"
python -m voice_reader.main --volume 60
```

| 参数 | 说明 |
|---|---|
| `--db` | 指定 `data_v4.db` 路径，不给就自动找 |
| `--voice` | 音色 ID；留空用系统语音 |
| `--volume` | 系统主音量 0-100 |
| `--no-gui` | 不开面板 |
| `--test` | 自检后退出 |
| `--version` | 版本号 |

---

## 面板

```
┌─ 设置 ───────────────────────────────────┐
│ 音量       ──────●──────  80%             │
│ 段间隔     ●────────────  0.0s            │
│ 单段最长   ──●──────────  7.0s            │
│ 语速       ────●────────  0               │
│ 音色       [ 晓伊（女·活泼）      ▾ ]      │
└──────────────────────────────────────────┘
┌─ 朗读队列 ───────────────────────────────┐
│ #  状态    字数  入队   内容              │
│ 1  已读     37   20:50  收到 ✅ 先把那段…  │
│ 2  朗读中   51   20:50  面板上多了个音色…  │
│ 3  待读     29   20:50  左边调完右边立刻…  │
└──────────────────────────────────────────┘
```

- **音量**：直接调 Windows 主音量
- **段间隔**：上一段念完到下一段开始，0 就是紧接着念
- **单段最长**：到点停在句子边界，标成「超时截断」
- **语速**：系统语音是 -5~10 档，Edge 自动换算成百分比
- **音色**：8 个中文音色随时切，切完立刻生效

改动会存进 `config.json`，下次开还是你调好的样子。

---

## 音色

下面这些音色**全部来自微软**（Edge 浏览器的在线语音服务），不是本项目训练的模型：

| 名称 | ID | 特点 |
|---|---|---|
| 晓伊 | `zh-CN-XiaoyiNeural` | 女·活泼（默认） |
| 晓晓 | `zh-CN-XiaoxiaoNeural` | 女·温柔 |
| 云希 | `zh-CN-YunxiNeural` | 男·少年 |
| 云扬 | `zh-CN-YunyangNeural` | 男·播音腔 |
| 云健 | `zh-CN-YunjianNeural` | 男·激情 |
| 云夏 | `zh-CN-YunxiaNeural` | 男·可爱 |
| 小北 | `zh-CN-liaoning-XiaobeiNeural` | 东北话 |
| 小妮 | `zh-CN-shaanxi-XiaoniNeural` | 陕西话 |

`--voice ""` 会退回 Windows 系统语音（Microsoft Huihui），完全离线，音色机械但能用。

---

## 它是怎么工作的

```
data_v4.db (只读)
      │  每 0.4 秒轮询一次
      ▼
  检测新的一轮回复
      │
      ▼
  拆段落 → 清 Markdown/代码块/表情标记
      │
      ▼
  句子级切分 ──按标点，不切半句
      │
      ├─ 并行预合成（4 线程）──┐
      ▼                        ▼
  队列 → 播放线程 → 扬声器
```

超时判定只统计**真正播放的秒数**，联网合成那 1~2 秒不算进去。不然你设 11 秒，实际只能听到 6 秒，很憋屈。

---

## 配置项

`config.json` 会自动生成，也能直接改：

```json
{
  "db_path": "",
  "voice": "zh-CN-XiaoyiNeural",
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

## 依赖与致谢

**先说清楚：这个项目自己不含任何语音模型。** 它只是个「调度器」——把对话内容取出来、切好、送进别人做好的语音引擎。

| 组件 | 项目 | 作用 | 许可 |
|---|---|---|---|
| **语音合成（默认）** | [edge-tts](https://github.com/rany2/edge-tts) | 调用微软 Edge 浏览器内置的在线神经语音服务 | MIT |
| **语音合成（离线回退）** | Windows SAPI（Microsoft Huihui） | 系统自带语音，无需联网 | 随 Windows |
| 音频播放 | [pygame](https://github.com/pygame/pygame) | 播放 mp3 | LGPL |
| 音量控制 | [pycaw](https://github.com/AndreMiras/pycaw) | 调用 Windows Core Audio API | MIT |
| COM 桥接 | [comtypes](https://github.com/enthought/comtypes) / [pywin32](https://github.com/mhammond/pywin32) | 访问系统语音接口 | MIT / PSF |

**关于 edge-tts 要说明的两点：**

1. 它本身是 MIT 开源，但它调用的是**微软 Edge 的在线语音服务**，那是微软的资产。请自行确认你的使用场景符合微软的服务条款。
2. 断网、被限流、或者服务端改了接口，都会导致合成失败——所以做了自动回退到系统语音的兜底。

如果你不想要联网依赖，把 `config.json` 里的 `voice` 改成空字符串，就只用系统语音，全程离线。

---

## 已知限制

这些我不打算藏着：

1. **只有 Windows**。系统语音、热键、音量控制都走 Win32 API。
2. **不是真流式**。数据库是整轮生成完才落盘，所以必然要等整段写完才开念。想要"生成一句念一句"得改 AstrBot 内核，我没干。
3. **Edge-TTS 要联网**。断网会自动回退到系统语音，不会直接哑掉。
4. **AstrBot 的对话记录有延迟**。它的落盘节奏不归我管，偶尔会看到消息晚几秒才被读到。
5. **外放 = 全屋公开**。家里有其他人在的时候，自己掂量。

---

## 常见问题

**Q：面板打不开，报 tkinter 错误**
A：Python 装的时候没勾 tkinter。重装时选上，或者直接用 `--no-gui`。

**Q：没声音**
A：先跑 `--test`。有声说明是数据库那边没读到，检查 `--db` 指对了没；没声就是音量或输出设备的问题。

**Q：声音太大**
A：面板里把音量拉到 30-40%，别用 80%。

**Q：为什么中途被截断了**
A：「单段最长」在起作用，说明这段超过了你设的秒数。调大就行，或者拆短。

**Q：能读历史记录吗**
A：默认不读，启动时把指针定位到末尾。想读历史的得自己改 `state.json`。

---

## 许可证

MIT。随便用，随便改，出了事别找我。

---

## 一句废话

写这个的起因挺没营养的：天天盯着屏幕看字，看得眼睛疼。

现在它能说话了，虽然音色是我挑的、时长是我设的、什么时候闭嘴也是我说了算——但好歹，它开口了。

用着还行的话，给个 Star。不给我也不缺这个。但给了我会高兴。

# NoiseKit

> **用途声明**：NoiseKit 使用消费级麦克风配合软件计算声级，**不是计量认证仪器**（不符合 IEC 61672 / GB/T 3785 对 1 级或 2 级声级计的要求）。结果仅供个人参考、趋势对比与过程记录，**不得用于执法取证、工程验收或法定检测**。未经校准的读数一律标注为 dBFS 相对值。

插上麦克风就能连续测环境噪声：实时看分贝曲线与频谱，超过阈值自动留证（前置缓冲录音 + 时间 + 峰值），一键导出可分享的报告。

![NoiseKit 主界面](docs/screenshot.png)

> 状态：**v0.1.0 开发中**。分析引擎、CLI、桌面界面、告警留证与报告导出均已可用（M1.0 → M1.2），还差打包成 exe 与校准向导（M1.3）。设计规格见 [docs/superpowers/specs](docs/superpowers/specs/)，实现计划见 [docs/superpowers/plans](docs/superpowers/plans/)。

四种用法：

```bash
python -m apps.desktop.main                       # 桌面界面（推荐，默认自动留证）
python -m apps.desktop.main --synthetic           # 没有麦克风时用模拟信号看界面
python -m audio_core.cli --source device          # 终端里实时刷新
python -m audio_core.cli --source device --session-dir ./今晚   # 留证：录音 + 数据库 + 报告
python -m audio_core.cli --doctor                 # 排障
python -m audio_core.cli --calibrate 94.0         # 用参考声压级校准
```

## 留证到底留了什么

一次会话会在目录里生成三样东西：

```
sessions/20261022-233000/
├── session.db     指标帧（10 Hz）+ 事件表，SQLite
├── audio/         超标时段的 WAV，含触发前 5 秒
└── report.html    一页报告：曲线 + 事件表 + 免责声明
```

前置缓冲是关键：等超过阈值才开始录，录到的第一秒往往已经被削掉，
回放只剩「响声的尾巴」。所以录音器始终滚动保存最近 5 秒音频，
事件触发的瞬间把这段一起写进文件。

## 解决什么问题

| 场景 | NoiseKit 给出的东西 |
| --- | --- |
| 楼上深夜装修，需要留证据 | 连续声级曲线 + 超标时段的录音 + 一页 HTML 报告 |
| 机房 / 工地 / 宿舍需要长期值守 | 24 小时不中断采集，事后回看「几点最吵、峰值多少」 |
| 搬家租房前想测环境底噪 | 打开即测，实时 dB(A) 与 Leq |

## 能力

- 实时指标：瞬时 dB、A/C 计权、Fast/Slow 时间计权、Leq(1s/10s/会话)、LAFmax、LCpeak
- 实时可视化：dB 时间序列曲线、2048 点频谱（对数频率轴）
- 阈值告警：阈值 + 持续时长 + 冷却，持续的噪音只算**一次**事件
- 留证录音：**5 秒前置缓冲** + 事件全程 + 5 秒后置，16-bit WAV
- 数据落盘：SQLite（WAL）批量写，崩溃后已有数据仍可读、可导出
- 导出：CSV 指标表 + **单文件** HTML 报告（内联 SVG，零外部依赖，双击即看）
- 手动校准 + **校准向导**：填参考声压级、采 2 秒、自动算偏移；配置随设备一起记住

不在 v0.1 范围：音乐分析、语音转写、设备频响测试、云同步、移动端。

## 架构

```
audio_core/     纯 Python 分析引擎，零 Qt 依赖，可 pip 安装复用
  capture/      设备枚举、实时流、环形缓冲、可替换音频源
  dsp/          分帧、FFT、A/C 计权、时间计权、dB 换算与校准
  metrics/      块 → FrameMetrics
  analyzers/    插件协议 + noise 实现（music/voice/device 预留）
  events/       告警状态机 + 留证录音
  storage/      SQLite 读写
apps/desktop/   PySide6 桌面界面
```

采集回调只做内存拷贝，DSP 在工作线程完成，UI 按 30 fps 限速刷新且**不追帧**——这是能连跑 24 小时的前提。

## 开发

```bash
git clone <repo-url> && cd noisekit
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
pytest
python -m audio_core.cli                          # 终端里看实时 dB
python -m apps.desktop.main                       # 图形界面
```

要求 Python ≥ 3.11。音频后端依赖 PortAudio（`sounddevice` 会自动带上）。

## 打包成可双击的程序

```bash
pip install pyinstaller
python scripts/build.py          # 产物在 dist/NoiseKit/
```

整个 `dist/NoiseKit/` 目录拷到没装 Python 的机器上，双击 `NoiseKit.exe` 就能用。

打包有两个必踩的坑，脚本里都处理了：

- `sounddevice` 在**运行时**才去 `_sounddevice_data` 里加载 PortAudio DLL，PyInstaller 的静态分析看不见这一步。漏了的表现是「程序能启动，但一个设备都找不到」，所以必须 `--add-data` 显式带上。
- `--windowed` 打包后 `sys.stdout` 是 `None`，一句 `print` 就能让程序崩掉，入口里做了兜底。

验证方式：

```bash
dist/NoiseKit/NoiseKit.exe --selftest   # 采 2 秒模拟信号 + 检查 PortAudio + 返回 0/1
```

CI 每次提交都在跑这条命令，产物也会作为 artifact 上传。

## 参与

见 [CONTRIBUTING.md](CONTRIBUTING.md)。Bug 与功能建议请开 Issue，请附上系统、设备型号与 `noisekit --doctor` 输出。

## 许可证

[MIT](LICENSE)

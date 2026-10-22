# NoiseKit 设计规格（M1：环境噪声监测）

- 状态：已确认
- 日期：2026-10-22
- 技术栈：Python 3.11 + PySide6 6.9 + sounddevice / numpy / scipy
- 仓库根：`E:\project\noisekit`

## 1. 目标与非目标

### 1.1 一句话定位

插上麦克风就能连续测环境噪声：实时看分贝曲线与频谱，超过阈值自动留证（前置缓冲录音 + 时间 + 峰值），一键导出可分享的报告。

### 1.2 交付目标

M1 产出一个 **能连续稳定运行 24 小时以上** 的桌面程序，以及一个 **零 Qt 依赖、可被 pip 安装和复用** 的分析引擎库。

### 1.3 明确的非目标（M1 不做）

| 砍掉的功能 | 原因 |
| --- | --- |
| 音乐分析器（BPM/调性/音高） | 与噪声监测无共用路径，只保留插件接口与空实现 |
| 语音分析器（VAD/转写/说话人） | 依赖外部模型，体积与算力超出 M1 |
| 设备实测（频响/失真/扫频） | 需要测量学规范与校准信号源 |
| 多设备同步、云同步、移动端 | 无用户证据支撑，YAGNI |
| 任何 AI 推理 | M1 全部指标为确定性 DSP |

### 1.4 合规免责（必须出现在 README 首屏与程序「关于」页）

> NoiseKit 使用消费级麦克风配合软件计算声级，**不是计量认证仪器**（不符合 IEC 61672 / GB/T 3785 对 1 级或 2 级声级计的要求）。测量结果仅供个人参考、趋势对比与过程记录，**不得用于执法取证、工程验收或法定检测**。未经校准的读数一律标注为 dBFS 相对值。

## 2. 用户场景

1. **邻里噪音留证**：楼上夜间施工，需要连续的声级曲线 + 超标时段的录音，导出成一页报告给对方或物业看。
2. **值守监测**：机房、工地、宿舍楼长期运行，事后回看「几点最吵、峰值多少」。
3. **快速评估**：搬家/租房前测一下环境底噪。

三个场景的共同需求是：**不中断地采、看得懂曲线、超标有证据**。M1 的功能优先级由这三个场景决定。

## 3. 功能需求

优先级：P0 = M1 必须交付；P1 = M1 内尽量交付。

| 编号 | 需求 | 优先级 |
| --- | --- | --- |
| FR-1 | 枚举输入设备（名称/通道数/默认采样率），可选择并保存偏好 | P0 |
| FR-2 | 实时采集，采样率按 48000 → 44100 → 设备默认 依次降级协商 | P0 |
| FR-3 | 计算并显示：瞬时 dB、A 计权 dB、C 计权 dB、Fast/Slow 时间计权、Leq(1s/10s/会话)、LAFmax、LCpeak | P0 |
| FR-4 | dB 时间序列曲线（默认显示最近 5 分钟，可缩放） | P0 |
| FR-5 | 实时频谱（2048 点 FFT，对数频率轴，dB 刻度） | P0 |
| FR-6 | 阈值告警：超过阈值且持续达到设定时长即触发一次事件，含 5 秒前置缓冲与 5 秒后置缓冲录音 | P0 |
| FR-7 | 会话数据持久化到 SQLite（会话、指标帧、事件三类表） | P0 |
| FR-8 | 事件音频以 16-bit WAV 存盘，文件名含时间戳与峰值 | P0 |
| FR-9 | 导出：CSV（指标帧）与 HTML 报告（内嵌曲线图与事件列表） | P0 |
| FR-10 | 手动校准：输入参考声压级，程序反算校准偏移并持久化 | P1 |
| FR-11 | 掉帧/溢出计数在状态栏可见 | P1 |
| FR-12 | 插件接口 `Analyzer` 与 music/voice/device 三个空实现占位 | P1 |

### 3.1 默认参数

| 参数 | 默认值 | 可配置 |
| --- | --- | --- |
| 告警阈值 | 65 dB(A) | 是 |
| 触发持续时长 | 3 秒 | 是 |
| 前置缓冲 | 5 秒 | 是 |
| 后置缓冲 | 5 秒 | 是 |
| 事件冷却时间 | 10 秒（避免同一段噪音重复切事件） | 是 |
| 指标落盘频率 | 10 Hz | 否（M1 固定） |
| 界面刷新频率 | 30 fps | 否（M1 固定） |

## 4. 指标定义（消除歧义，实现必须与此一致）

### 4.1 处理链

```
设备回调(不阻塞) → 环形缓冲 → 工作线程取 480 样本块(10 ms @ 48 kHz)
  → 去直流 → 分块均方(mean square)
  → 时间计权(一阶指数) → 电平 = 10·log10(ms)  → dBFS
  → 流式 A/C 计权滤波(IIR，样本级状态) → dB(A) / dB(C)
  → 加校准偏移 → dB SPL
```

### 4.2 关键定义

- **dBFS**：`10·log10(mean_square)`，满量程正弦（±1.0）对应约 −3.01 dBFS。块长固定 480 样本（48 kHz 下 10 ms）；采样率不同时取 `round(0.01·fs)` 并保证 ≥ 256。
- **时间计权**：一阶指数平均，时间常数 Fast = 125 ms、Slow = 1000 ms、Impulse 上升 35 ms / 下降 1500 ms。系数 `α = 1 − exp(−Δt/τ)`，Δt = 块长。
- **A/C 计权**：以 IEC 61672-1 的模拟原型零极点（A：原点四阶零点，极点 129.4²、676.7、4636、76655²；C：原点二阶零点，极点 129.4²、76655²）经双线性变换为流式 IIR，1 kHz 处归一化到 0 dB，按样本保持滤波状态。验收条件：1 kHz 处 A 计权增益 0 ± 0.1 dB，C 计权 0 ± 0.1 dB；100 Hz 处 A 计权 −19.1 ± 0.5 dB。
- **Leq(T)**：窗口 T 内 mean_square 的能量平均再转 dB，不做时间计权。会话 Leq 为自会话开始累计。
- **LAFmax**：整个会话中 A 计权 + Fast 时间计权序列的最大值。**LCpeak**：C 计权瞬时采样级（块内最大值）的会话峰值。
- **校准**：`dB SPL = dBFS + offset`。未校准时 `offset = None`，界面所有数值后缀显示「dBFS(相对)」；校准时 `offset = 参考声压级 − 当前 dBFS`，精度到 0.1 dB。

### 4.3 计权实现方式的修订（2026-10-22，实现阶段推翻了初稿）

初稿定的是「频域加权」：对每块做 FFT，乘计权增益后按 Parseval 求能量。**实现时发现这条路走不通**——指标块的块长是 10 ms（48 kHz 下 480 样本），频率分辨率只有 100 Hz。A 计权在 100 Hz 处已经是 −19 dB、20 Hz 处 −50 dB，用 100 Hz 的分辨率去表达这条曲线，等于把 100 Hz 以下全部抹成 0 dB，会直接违反本规格自己写在 §4.2 的验收条件。

改为 **模拟原型零极点 + `scipy.signal.bilinear_zpk` 的流式 IIR**，按样本保持滤波器状态：

- 采样率精确、无块边界瞬态，Leq 与时间计权都在物理正确的信号上计算；
- 一次设计、逐样本 `sosfilt`，10 ms 块的 CPU 开销可忽略；
- 计权曲线另有解析实现 `a_weight_db(f) / c_weight_db(f)`，供频谱标注、报告绘图和交叉验算。

代价是：界面上的频谱仍是未计权的原始谱，A 计权曲线以参考曲线的形式叠加显示，而不是直接作用在频谱上。这个代价可以接受——看频谱的人和看 dB(A) 的人关心的不是同一件事。

## 5. 架构

```
noisekit/
├── audio_core/                 纯 Python，无 Qt 依赖，可独立 pip 安装
│   ├── capture/
│   │   ├── source.py           AudioSource 协议（可替换为 WAV 回放/合成源）
│   │   ├── devices.py          list_devices() → DeviceInfo
│   │   ├── stream.py           SoundDeviceSource：回调只做拷贝
│   │   └── ring.py             固定容量环形缓冲，带溢出计数
│   ├── dsp/
│   │   ├── framing.py
│   │   ├── fft.py              加窗、单边谱、Parseval 能量校正
│   │   ├── weighting.py        A/C 计权频域增益表
│   │   ├── time_weight.py      Fast/Slow/Impulse 一阶指数
│   │   └── level.py            ms→dBFS、dBFS→dBSPL、校准
│   ├── metrics/
│   │   └── meter.py            SoundLevelMeter：块 → FrameMetrics
│   ├── analyzers/
│   │   ├── base.py             Analyzer 协议 + 注册表
│   │   ├── noise.py            噪声分析器（M1 唯一实现）
│   │   ├── music.py            占位：NotImplementedError + docstring
│   │   ├── voice.py            占位
│   │   └── device.py           占位
│   ├── events/
│   │   ├── detector.py         阈值 + 持续 + 冷却 状态机（纯函数）
│   │   └── recorder.py         前置/后置缓冲 → WAV 落盘
│   ├── storage/
│   │   ├── schema.py           SQLite DDL
│   │   ├── writer.py           批量写（独立线程）
│   │   └── query.py            按会话读取帧与事件
│   └── report/
│       ├── csv_export.py
│       └── html_export.py      内嵌 SVG 曲线，无外部依赖
├── apps/desktop/
│   ├── main.py                 入口：QApplication + 依赖装配
│   ├── worker.py              AnalysisWorker(QThread)：采集→分析→三路分发
│   ├── windows/main_window.py
│   └── widgets/               level_meter / time_series / spectrum / event_list
├── tests/
├── docs/superpowers/{specs,plans}/
├── pyproject.toml
├── LICENSE (MIT)
└── README.md
```

### 5.1 组件边界（每个组件的「做什么 / 怎么用 / 依赖什么」）

| 组件 | 做什么 | 接口 | 依赖 |
| --- | --- | --- | --- |
| `capture.ring.RingBuffer` | 线程安全的定长样本缓冲，溢出计数 | `write(samples)` / `read(n)` / `overflows` | 无 |
| `capture.source.AudioSource` | 抽象音频来源，统一块迭代 | `blocks() -> Iterator[ndarray]` | 无 |
| `capture.stream.SoundDeviceSource` | 真实设备采集，回调只拷贝 | 实现 `AudioSource` | sounddevice |
| `dsp.weighting` | 计权增益表 | `a_weight_db(freqs)` / `c_weight_db(freqs)` | numpy |
| `metrics.meter.SoundLevelMeter` | 块 → 指标 | `process(block, ts) -> FrameMetrics` | dsp |
| `analyzers.base.Analyzer` | 插件协议 | `process(block) -> dict` | 无 |
| `events.detector.ThresholdDetector` | 告警状态机 | `update(level, ts) -> Event \| None` | 无 |
| `events.recorder.EventRecorder` | 前后缓冲拼接成 WAV | `on_frame()` / `finalize()` | numpy |
| `storage.writer.SessionWriter` | 批量落盘 | `add_frame()` / `flush()` / `close()` | sqlite3 |
| `apps.desktop.worker.AnalysisWorker` | 装配与分发，不写业务逻辑 | Qt signal | audio_core |

**架构约束**：`audio_core` 内不允许 `import PySide6`（CI 用脚本强制检查）。UI 只消费 `FrameMetrics` 与事件对象，不参与任何 DSP 计算。

## 6. 数据模型

```sql
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,        -- ISO8601 本地时间
    ended_at TEXT,
    device_name TEXT,
    sample_rate INTEGER NOT NULL,
    calibration_offset REAL,         -- NULL = 未校准
    label TEXT,                      -- 用户可填「楼上装修」
    notes TEXT
);

CREATE TABLE frames (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts REAL NOT NULL,                -- 会话内相对秒
    dbfs REAL NOT NULL,
    db_a REAL NOT NULL,
    db_c REAL NOT NULL,
    spl REAL, db_spl_a REAL, db_spl_c REAL,   -- 未校准时为 NULL
    leq_1s REAL, leq_10s REAL,
    lafmax REAL, lcpeak REAL
);
CREATE INDEX idx_frames_session_ts ON frames(session_id, ts);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    started_at REAL NOT NULL,        -- 会话内相对秒
    ended_at REAL,
    threshold REAL NOT NULL,
    peak_db_a REAL NOT NULL,
    audio_path TEXT,
    pre_roll REAL NOT NULL,
    post_roll REAL
);
CREATE INDEX idx_events_session ON events(session_id);
```

- 写入使用单事务批量提交（每 100 帧或每 2 秒取先到者），避免 SQLite 每帧 fsync。
- `writer` 使用 WAL 模式，保证长跑时读写不互斥。
- 会话异常退出（崩溃/断电）时，`ended_at` 为 NULL 的会话在下次启动时标记为「未正常结束」并允许导出已有数据。

## 7. 线程模型与数据流

```
[PortAudio 回调线程]  只做 memcpy → RingBuffer（绝不加锁做重活，绝不分配大对象）
        │
        ▼
[AnalysisWorker 线程] 读块 → SoundLevelMeter → FrameMetrics
        ├─→ (a) Qt signal，按 30 fps 限速投递 → UI 渲染
        ├─→ (b) ThresholdDetector → 事件；EventRecorder 写 WAV
        └─→ (c) 写入无锁队列 → [Writer 线程] 批量 SQLite
```

- **UI 不追帧**：信号携带「最新快照」，积压时丢弃中间帧，只保留最新一帧，保证界面永不因分析落后而卡顿。
- **缓冲水位**：环形缓冲目标水位 3 秒音频；超过 80% 水位时状态栏提示「处理落后」，超过容量丢最旧数据并累加 `overflows`。
- **关闭流程**：停止采集 → 清空缓冲 → flush 队列 → 关闭 WAV → 关闭会话事务 → 退出。

## 8. 错误处理与降级

| 故障 | 处理 |
| --- | --- |
| 设备被独占 / 拔掉 | 停止流，指数退避重连（1s→2s→4s→…最大 30s），状态栏显示「重连中（第 N 次）」，不弹模态框 |
| 采样率不支持 | 48000 → 44100 → 设备默认 依次尝试，全部失败则报错并给出可选设备列表 |
| 环形缓冲溢出 | 计数 + 状态栏可见，会话继续，不崩、不静默丢弃 |
| SQLite 写失败（磁盘满/被占用） | 降级为内存队列（上限 60 秒数据），状态栏红色告警，恢复后回灌 |
| WAV 写入失败 | 该事件标记 `audio_path = NULL`，事件本身仍保留，报告里注明「音频缺失」 |
| 校准值未设置 | 全部数值走 dBFS 路径，界面统一加「(相对)」后缀 |
| 无任何输入设备 | 启动时给出友好空状态页，而非异常栈 |

**原则**：麦克风采集是主流程，任何单点失败都不得终止会话；用户永远能看到「现在到底在不在采」。

## 9. 测试策略

CI 与本地都 **不需要真实麦克风**。

| 层次 | 方式 | 验收 |
| --- | --- | --- |
| 单元：DSP | 合成正弦/白噪 | 1 kHz 正弦 FFT 峰值频率误差 < 1 Hz；A 计权 1 kHz 增益 0 ± 0.1 dB；白噪 10 秒 Leq 与解析值误差 < 0.5 dB |
| 单元：时间计权 | 阶跃信号 | Fast 达到 63% 稳态 ≈ 125 ms（±10%），Slow ≈ 1000 ms |
| 单元：告警状态机 | 合成电平序列 | 短于持续时长不触发；触发后不重复；冷却期内不触发；持续超限只产生一个事件 |
| 集成：引擎 | WAV 回放源（`WavFileSource`）驱动完整链路 | 输出帧数、时间戳单调、指标量级正确 |
| 集成：存储 | 临时 SQLite | 崩溃恢复后数据可读；批量写计数一致 |
| UI 冒烟 | pytest-qt | 主窗可构造、能加载假数据、不抛异常 |
| 约束检查 | 脚本 | `audio_core` 中不存在 `PySide6` 导入 |

`WavFileSource` 与 `SyntheticSource` 是测试基础设施的一部分，与 `SoundDeviceSource` 同实现 `AudioSource` 协议。

## 10. 里程碑

| 阶段 | 交付 | 验收标准 |
| --- | --- | --- |
| M1.0 | 仓库骨架、pyproject、CI、`audio_core` 采集+DSP+指标、CLI 打印实时 dB | `python -m audio_core.cli` 能在终端看到每秒刷新的 dB/Leq；DSP 单测全绿 |
| M1.1 | PySide6 主窗：电平表、dB 曲线、频谱 | 真实麦克风下界面流畅，30 fps 无卡顿，掉帧计数正确 |
| M1.2 | 告警留证、SQLite、WAV、CSV/HTML 导出 | 制造一次超标，事件落库 + 音频可播放 + 报告可打开 |
| M1.3 | 校准流程、PyInstaller 打包、README/截图/文档 | 双击 exe 可用；1 小时长跑内存稳定 |

## 11. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 数值被误当法定依据 | README 首屏 + 关于页 + 报告页脚三处免责 |
| Windows WASAPI 独占模式导致无声 | 默认用端口音频默认主机 API，文档给排障清单 |
| PyInstaller 打包漏 portaudio 动态库 | 打包脚本显式 `--add-binary`，CI 产物做冒烟启动 |
| 长跑内存增长（SQLite/曲线缓存） | 环形缓冲定长、曲线用环形数组、写入队列有界 |
| 时钟漂移导致 24h 后时间戳偏移 | 时间戳以 `time.monotonic()` 计算相对秒，会话开始时间另存墙钟 |
| 开源申请通过率低 | 项目本身按「有人真用」标准做，不承诺申请结果 |

## 12. 开源配套

- 许可证 MIT（最大化采用率）；`README.md` 含定位、截图、快速上手、免责声明、指标说明。
- `CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`CHANGELOG.md`、Issue/PR 模板。
- GitHub Actions：`ruff` + `pytest`（Windows/macOS/Linux 三平台）、打包产物冒烟。
- 版本语义化，首个公开版本 `v0.1.0`。

## 13. 后续版本（不在 M1 承诺范围）

- v0.2：音乐分析器（BPM/调性）、频谱瀑布图、事件音频 FLAC 压缩
- v0.3：语音分析器（VAD + 静音裁剪）、多会话对比
- v0.4：headless 守护模式 + 远程查看（对应设计中的架构 B/C 演进）

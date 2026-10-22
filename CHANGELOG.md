# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化。

## [0.1.0] - 开发中

### 新增

- `audio_core` 分析引擎：定长环形缓冲、合成/回放/真实设备三种音频源
- A/C 计权（IEC 61672-1 原型 + 双线性变换的流式 IIR），1 kHz 归一化到 0 dB
- Fast / Slow / Impulse 时间计权，Leq(1s/10s/会话)、LAFmax、LCpeak
- 频谱分析：2048 点 Hann 窗单边谱，峰值幅度 dBFS 刻度
- 手动校准：由参考声压级反算偏移；未校准时读数标注「相对」
- 分析器插件注册表，`noise` 已实现，`music` / `voice` / `device` 预留
- CLI：`noisekit`，支持 `--source`、`--doctor`、`--list-devices`、`--calibrate`
- 桌面界面（PySide6）：设备选择、电平表、声级曲线、实时频谱、状态栏掉帧统计
- 工作线程按 30 fps 限速投递，界面不追帧、不阻塞采集
- 合成信号源支持真实节奏（`--synthetic` 可直接演示）
- 50 项单元与集成测试，全部无需真实麦克风即可运行；界面测试用离屏平台

### 已知限制

- 告警留证、SQLite 存储、报告导出尚未完成（M1.2）
- 校准流程目前只有 CLI 与手动填偏移，可视化校准向导未做（M1.3）
- 未做计量认证，不可用于法定检测

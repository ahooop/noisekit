# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化。

## [0.1.1] - 2026-10-24

### 新增

- 开源配套补齐：`CODE_OF_CONDUCT.md`、Issue 表单（Bug / 功能建议，带必填的排障字段）、PR 模板、Dependabot 每周依赖更新（数值底座的升级单独成组，避免与界面依赖混在一个 PR 里）
- `.github/workflows/publish.yml`：tag 触发把 sdist 与 wheel 发到 PyPI，走 Trusted Publishing（OIDC），仓库里不存任何 token；构建后先装进干净环境跑一次 CLI，再放行上传
- 发布手册 [docs/releasing.md](docs/releasing.md)：版本号四处同步、推标签、首次配置 PyPI、发布后核对与回滚
- README 顶部加 CI / Release / License 徽章

### 变更

- **PyPI 发行名改为 `noisekit-spl`**：`noisekit` 在 PyPI 已被一个无关项目（语音降噪数据集生成器）占用，直接用原名发布必然撞名。import 包名 `audio_core` 与命令 `noisekit` 保持不变，另加 `noisekit-spl` 命令别名，避免 console script 被同名包覆盖后找不到自己的入口
- 包元数据补齐：英文 summary、`[project.urls]`（Homepage / Repository / Issues / Changelog）、Windows 与科学计算相关 classifier
- README 顶部增加英文摘要（中文正文不变），方便英文读者与审核方快速判断项目
- 版本号统一到 0.1.1（`pyproject.toml`、`audio_core.__version__` 与 README 状态行）

## [0.1.0] - 2026-10-22

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
- 阈值告警状态机：持续时长触发 + 后置缓冲 + 冷却，持续噪音只产生一个事件
- 触发前峰值追踪：等满触发时长期间的最响值不会丢
- 留证录音：5 秒前置缓冲 + 事件全程，16-bit WAV
- SQLite 持久化：独立写线程批量提交，`ended_at IS NULL` 即可识别未正常结束的会话
- 导出：CSV 指标表、单文件 HTML 报告（内联 SVG 曲线、事件表、免责声明）
- 一次性完成 CLI 与界面两边的会话封装（`RecordingSession`），避免两套逻辑走偏
- 可视化校准向导：填参考声压级 → 采 2 秒 → 反算偏移并记住
- 配置持久化（`%APPDATA%/NoiseKit/config.json`）：设备、校准值、阈值、窗口大小；配置损坏也能正常启动
- PyInstaller 打包脚本，产物为免安装目录；`--selftest` 做打包冒烟（含 PortAudio 加载检查）
- CI 增加 Windows 打包任务，每次提交都验证「exe 能启动、能分析、能找到音频后端」
- 93 项单元与集成测试，全部无需真实麦克风即可运行；界面测试用离屏平台

### 已知限制

- 打包产物约 290 MB（PySide6 + SciPy 占大头），尚未做进一步裁剪
- 未做计量认证，不可用于法定检测

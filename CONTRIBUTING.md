# 参与 NoiseKit

感谢愿意花时间。这是一个面向普通人的噪声测量工具，**正确性比功能数量重要**。

## 开发环境

```bash
git clone <repo-url> && cd noisekit
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -e ".[dev,audio,gui]"
python -m pytest
python -m ruff check .
python scripts/check_core_purity.py
```

## 提交前必须全绿

```bash
python -m ruff check .        # 规范
python -m pytest -q           # 测试
python scripts/check_core_purity.py   # audio_core 不得依赖 GUI
```

## 代码约定

- **`audio_core` 不得导入任何 GUI 框架**。引擎要能被别人装进无头环境。
- 声学量的计算只在 `audio_core` 里发生。界面只消费 `FrameMetrics`，不做 DSP。
- 新的分析方向请实现 `audio_core/analyzers/base.py` 的协议并注册，不要改引擎主流程。
- 涉及声学量的改动**必须带测试**，且测试要能在没有麦克风的机器上跑（用 `SyntheticSource` 或 `WavFileSource`）。
- 注释写「为什么」，不写「是什么」。中文注释没问题。

## 提交信息

`<类型>: <一句话>`，类型用 `feat` / `fix` / `docs` / `test` / `refactor` / `perf` / `build`。
例如：`fix: A 计权极点符号错误导致读数恒为下限`

## 报告问题

请附上：

1. 操作系统与版本
2. 麦克风型号
3. `noisekit --doctor` 输出
4. 预期与实际

**注意**：本项目不做计量认证。请勿提交「读数与专业声级计差 3 dB 算 bug」这类问题——除非你同时给出了校准过程与参考仪器型号。

## 不接受

- 引入需要联网的依赖
- 把免责声明改弱或删除
- 只为增加功能数量、没有真实使用场景的 PR

## 这个 PR 做了什么

<!-- 一句话说清目的。修 bug 请写清触发的条件。 -->

## 为什么这么做

<!-- 讲取舍：为什么不选另一条路、对现有行为有什么影响。 -->

## 检查清单

- [ ] `python -m ruff check .` 通过
- [ ] `python -m pytest -q` 通过
- [ ] `python scripts/check_core_purity.py` 通过（`audio_core` 不引入 GUI 依赖）
- [ ] 涉及声学量的改动带了测试，且测试不需要真实麦克风
- [ ] 没有弱化或删除免责声明
- [ ] 新增依赖是必需的，且不需要联网运行

## 相关 Issue

<!-- 例如 Closes #12；没有就写「无」 -->

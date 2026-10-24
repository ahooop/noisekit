# 发布手册

一次发布由**一个 tag** 驱动，两条流水线并行跑：

| 工作流 | 触发 | 产物 | 需要配置 |
| --- | --- | --- | --- |
| [`release.yml`](../.github/workflows/release.yml) | 推送 `v*` 标签 | GitHub Release + Windows 免安装包 zip | 无（用自带的 `GITHUB_TOKEN`） |
| [`publish.yml`](../.github/workflows/publish.yml) | 推送 `v*` 标签 | sdist + wheel → PyPI | 一次性配置 Trusted Publisher + 仓库变量 |

## 1. 改版本号

四处必须一致，漏一处 `--version` 和 PyPI 上显示的数字就会打架：

| 位置 | 内容 |
| --- | --- |
| `pyproject.toml` | `version = "0.1.2"` |
| `audio_core/__init__.py` | `__version__ = "0.1.2"` |
| `CHANGELOG.md` | 新增 `## [0.1.2] - YYYY-MM-DD` 段落 |
| `README.md` | 状态行里的 `v0.1.2` |

Release 正文会自动从 `CHANGELOG.md` 里同名版本段落抽取，所以那一节的写法决定了
发布页长什么样：用 `###` 分小节，条目一句话说清「改了什么、对用户有什么影响」。

## 2. 本地自检

```bash
python -m ruff check .
python -m pytest -q
python scripts/check_core_purity.py
python -m build && python -m twine check dist/*
```

## 3. 推标签

```bash
git add -A
git commit -m "chore(release): v0.1.2"
git push origin main
git tag -a v0.1.2 -m "NoiseKit 0.1.2"
git push origin v0.1.2
```

标签必须指向那条 `chore(release)` 提交。`release.yml` 里的 `gh release create`
带了 `--verify-tag`，标签不存在会直接失败，不会留下半成品 Release。

## 4. 首次启用 PyPI（只做一次）

`noisekit` 这个名字在 PyPI 上已被无关项目占用，发行名固定为 **`noisekit-spl`**。

1. 登录 [pypi.org](https://pypi.org)，进入 **Your account → Publishing**；
2. 点 **Add a new pending publisher**，填：

   | 字段 | 值 |
   | --- | --- |
   | PyPI Project Name | `noisekit-spl` |
   | Owner | `ahooop` |
   | Repository name | `noisekit` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. 回到 GitHub 仓库：**Settings → Secrets and variables → Actions → Variables**，
   新建 `PYPI_PUBLISH`，值为 `true`。

配置完成前，`publish` job 一直是 `skipped`（不会让 tag 推送变红）。配置之后，
下一次推标签会自动把两个产物传上去，不需要任何 API token 落在仓库里。

## 5. 发布后核对

```bash
# 1) Release 有 zip
gh release view v0.1.2

# 2) 包真的能装
pip install --upgrade noisekit-spl==0.1.2
noisekit --version

# 3) 干净环境里能跑
python -m venv /tmp/nk && /tmp/nk/bin/pip install noisekit-spl==0.1.2
/tmp/nk/bin/noisekit --source synthetic --duration 1
```

三条都过，再去看版本徽章是否变绿。

## 出错了怎么办

- **release 失败**：修好 workflow 后重跑该 run，或删标签重推
  （`git push --delete origin v0.1.2` 后重新打标签）。
- **PyPI 传错了**：PyPI 不允许覆盖已上传的文件，只能 `yank` 掉再发一个补丁版本；
  所以上面的「安装冒烟」是发布前的最后一道闸。
- **只是版本号写错**：别改已发布的标签，发 `0.1.3`。

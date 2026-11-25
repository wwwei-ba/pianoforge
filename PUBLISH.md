# 发布到 GitHub

仓库已经初始化并提交好了（分支 `main`，72 个文件）。剩下的只有“推到远端”这一步，
在**能正常访问 github.com 的网络**上执行即可。

## 1. 改成你自己的提交身份

当前提交用的是占位身份，改成你自己的：

```bat
git config user.name  "你的名字"
git config user.email "你的邮箱"
git commit --amend --reset-author --no-edit
```

## 2. 认证（三选一）

**A. GitHub CLI（推荐）**

```bat
gh auth login            :: 选 GitHub.com → HTTPS → Login with a web browser
```

**B. 个人访问令牌**

到 <https://github.com/settings/tokens> 建一个带 `repo` 权限的 token，然后：

```bat
set GH_TOKEN=ghp_xxxxxxxx
```

**C. GitHub Desktop / 手动**

直接把 `D:\deepfile\pianoforge` 拖进 GitHub Desktop，点 Publish repository。

## 3. 创建仓库并推送

```bat
cd D:\deepfile\pianoforge
gh repo create pianoforge --public --source=. --remote=origin --push ^
   --description "Audio -> piano score, fingerstyle tab and rendered piano track"
```

没有 gh 时：

```bat
git remote add origin https://github.com/<你的用户名>/pianoforge.git
git push -u origin main
```

## 4. 仓库设置建议

| 项目 | 建议 |
| --- | --- |
| Description | Audio → editable piano score, fingerstyle guitar tab and rendered piano track |
| Topics | `music` `transcription` `piano` `midi` `musicxml` `demucs` `librosa` `python` |
| License | MIT（已随仓库附上） |
| Releases | 可选：附上打包好的 `PianoForge.exe` 与采样/模型说明 |

## 5. 首批 issue 模板（可选）

- 转谱质量问题：附音频片段 + `out/<歌名>/_analysis/report.json`
- 启动/环境问题：附 `cache/gui_error.log` 与 `python -V`

## 已知不含在仓库里的东西

`.gitignore` 已排除：`.venv/`、`cache/`、`out/`、`bin/`（采样与模型）、`samples/`、
`corpus/`、编译产物 `PianoForge.exe`、以及开发期的一次性脚本。
克隆后按 README 的「安装」一节补齐依赖与 `tools/fetch_assets.py` 的采样即可。

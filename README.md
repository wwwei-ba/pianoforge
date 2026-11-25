# PianoForge · 音频 → 钢琴谱 + 指弹吉他谱 + 钢琴音轨

> **⚠️ 初代版本 / First release**
>
> 此项目为初代版本，功能与效果仍在打磨。若遇到 bug、转谱异常或想反馈建议，欢迎联系 **QQ：3790504481**。
>
> This is the first generation of PianoForge — rough edges are expected. If you hit a bug or want to share feedback, reach me on **QQ: 3790504481**.

把任意一首歌的音频文件转成可以直接编辑、打印、弹奏的四个文件：

| 输出 | 文件 | 用途 |
| --- | --- | --- |
| 曲谱音频 | audio.wav | 生成的钢琴演奏，长度与原曲完全一致 |
| 原曲 | original.<扩展名> | 源音频副本，歌曲文件夹自包含 |
| 钢琴谱 | piano.pdf | 直接看/打印；可编辑的 MusicXML 在 _analysis/piano.musicxml |
| 吉他谱 | guitar.pdf | 指弹六线谱；MusicXML 与文本谱在 _analysis/ |

中间产物（MIDI、OGG、和弦、分析报告、校验图）都收在 _analysis/ 下，不再堆在歌曲目录里。

## 快速开始

```bat
:: 图形界面：可直接把音频文件拖进窗口，或点“选择文件”
run_gui.cmd

:: 命令行
pf.cmd transcribe "D:\\music\\song.ogg"
pf.cmd transcribe "D:\\music\\song.mp3" --no-sep     :: 跳过分轨，速度更快
```

输出默认写到 `out\<歌曲名>\`。

## 中英双语

两处都能切换，切换后立即生效并记住选择：

| 入口 | 用法 |
| --- | --- |
| 图形界面 | 右上角下拉框选 `中文` / `English`，界面文字立刻切换 |
| 命令行 | `pf.cmd --lang en --help`，或 `pf.cmd transcribe "歌.mp3" --lang zh` |

语言判定顺序：环境变量 `PIANOFORGE_LANG` → `cache/settings.json` → Windows 界面语言 → 英文。
文案集中在 `src/pianoforge/i18n.py`，加一种语言只要在那个字典里补一列。

## 桌面快捷方式与图标

桌面上的 `PianoForge.lnk` 双击即可打开图形界面（无命令行窗口）。

启动方式有两种，快捷方式会自动选：

| 情况 | 快捷方式指向 |
| --- | --- |
| 工程目录正常 | `.venv\Scripts\pythonw.exe -m pianoforge.gui` |
| 工程目录/解释器带 **Low 完整性标签**（沙箱、部分安全软件造成） | `python_medium.txt` 里记录的解释器，并把 `src` 与 venv 的 `site-packages` 加进搜索路径 |

带 Low 标签的 exe 会被 Windows 强制以低完整性运行，**无法调用资源管理器**（「打开文件夹」失效、
spawn explorer.exe 会报 0xc0000142）。这种方式可以绕过它，让应用以正常权限运行。

`PianoForge.exe`（源码 `launcher/PianoForgeLauncher.cs`）同样会优先读取 `python_medium.txt`，
图标内嵌在 exe 里；`PianoForge.cmd` 是等价的无快捷方式入口。

- 图标是程序化**原创绘制**的：深紫圆角底 + 五线谱 + 钢琴键盘 + 一条从冷色升到暖色的旋律曲线与符头，
  由 `tools/make_icon.py` 用 Pillow 从零画出来，没有任何外部素材。
- `.ico` 里 16–256 px **全部是标准 BMP(DIB) 条目**（不是 PNG 压缩条目），含透明掩码；
  PNG 条目会被 Windows 的快捷方式图标加载器拒绝，早期版本就是这样变成空白图标的。
- **图标副本安装在 `%LOCALAPPDATA%\PianoForge\PianoForge-<hash>.ico`**：这是关键。
  本项目目录在 D 盘，Windows 的 shell 图标加载器读不到那里的 .ico（同一个文件放到用户目录就正常），
  所以 `make_shortcut.py` 会先把图标装到用户目录，再让快捷方式指向它，文件名带内容哈希用于绕过图标缓存。

```bat
python tools\make_icon.py        :: 重新生成 assets\pianoforge.ico 与预览图
launcher\build.cmd               :: 重新编译 PianoForge.exe（内嵌图标）
python tools\make_shortcut.py    :: 安装图标到用户目录并生成 assets\PianoForge.lnk
```

换图标：改 `make_icon.py` 里的配色/几何 → 依次跑上面三条 → 把 `assets\PianoForge.lnk` 复制到桌面覆盖。

验证图标是否正确：`tools\IconProbe.exe <某个.lnk> out.png 128` 会用资源管理器同一个接口把图标画出来。

## 图形界面

三个标签页：

| 标签 | 能做什么 |
| --- | --- |
| **转谱** | 选文件 / 拖拽导入；是否分轨；**转谱引擎（神经网络 / 经典）**；**九段进度条**；实时日志 |
| **结果与预览** | 左侧**按歌曲成树的文件列表**（歌 → 曲谱音频 / 原曲 / 钢琴谱 / 吉他谱），右侧内置预览乐谱（**滚轮连续滚动**、缩放、适应宽度）；底部**播放器**：播放/暂停、进度条拖动定位、音量（自动记忆）、钢琴轨↔原曲 A/B 切换；刷新、删除这首歌、复制路径、打开文件夹 |
| **乐谱库** | 所有已生成曲目集中检索：搜索框过滤 + 树形列表，点选即在右侧预览 |

细节：

- **同名歌曲只保留一份**：导入或开始转谱时若检测到同名产物，会弹窗询问是否覆盖；选择覆盖才会删除旧目录再重跑。
- 预览用 PyMuPDF 把 PDF 渲成图片显示在窗口里，不需要 WPS / Adobe；页面按可视区域懒渲染。
- 播放用 Windows `winsound`（异步），OGG 自动转临时 WAV；A/B 对比就在结果页两个按钮之间切。
- 「打开文件夹」在本机 `ShellExecute` 被系统拒绝（错误码 5），程序改为直接 `explorer.exe /e,<路径>` 并逐级降级；若仍失败，结果页本身已能完成浏览与播放。
## 处理流程

1. **解码**：ffmpeg / libsndfile 读取任意音频，统一为 22.05 kHz 单声道做分析，44.1 kHz 渲染。
2. **分轨**（可选，默认开）：Demucs `htdemucs` 分出 drums / bass / other / vocals；旋律从 other(+vocals) 提取，鼓只用来稳定节拍。
3. **节拍 / 调性**：librosa 节拍跟踪 + Krumhansl–Schmuckler 调性识别。
4. **旋律**：CQT 谐波叠加显著度 → 带音域先验与休止状态的 Viterbi 路径 → 起音切分 → 音高量化。
5. **和声**：拍点同步 chroma + 和弦模板 + Viterbi 平滑，得到逐拍和弦（含七和弦、挂留、减和弦）。
6. **多音高转谱**：对去掉鼓的谐波混音做“贪心谐波匹配追踪”——每帧挑出最符合谐波模板的音高、
   减掉它的能量再找下一个，得到原曲里**真实在响的音**（含和弦音与低音），而不是靠和弦名重新配器。
7. **编配**：
   - 钢琴：右手是旋律，高音谱第二声部放转谱得到的和弦音（按八分音符栅格取值并合并延音，保证可读）；
     左手是贝斯轨单独转谱出来的低音线。这样弹出来的和声与低音走向都贴着原曲。
   - 吉他：在同一把位内为每个拍点挑选弦/品，旋律放在高音弦，低音放在 6–4 弦。
8. **渲染**：FluidR3_GM 钢琴采样（85 个音）+ 逐采样音准校正 + 旋律/伴奏分层混音 + 混响，导出 WAV/OGG，另存 MIDI。
9. **核验**：把生成的钢琴音轨重新做一次旋律提取，与原曲旋律逐帧比对（音高准确率、八度错误率、轮廓相关、chroma 相似度）。

## 核验指标（如何判断“弹出来和原曲一样”）

`report.json` 里的 `metrics` 字段：

- `melody_pitch_exact_pct`：两段音频旋律逐帧完全相同音高的比例（越高越好）。
- `melody_pitch_within_semitone_pct`：允许 1 个半音误差的比例。
- `melody_octave_error_pct`：相差一个八度的比例（应接近 0）。
- `melody_contour_corr`：旋律走向相关系数。
- `chroma_similarity`：和声内容相似度（12 维音级分布余弦相似度）。
- `score_note_precision_pct` / `score_note_recall_pct`：写进谱子的音与参考旋律的吻合/召回。

参考曲 `Fukashigi no Carte Lofi` 上的实测（146 秒，73.8 BPM，D 小调）：

    melody_pitch_exact_pct            78.5 %
    melody_pitch_within_semitone_pct  87.1 %
    melody_octave_error_pct            0.4 %
    melody_contour_corr                0.78
    score_note_precision_pct         100.0 %
    score_note_recall_pct             93.0 %
    chroma_similarity                  0.75

## 可调参数

```python
pipeline.run(path,
             use_separation=True,   # 是否先分轨
             melody_lo=55,          # 旋律最低音（MIDI）
             melody_hi=96,          # 旋律最高音
             sr=22050)              # 分析采样率
```

旋律跟踪的超参可用环境变量 `PF_MELODY_LO` / `PF_MELODY_HI` 覆盖，
也可以直接调用 `pipeline.run(..., melody_lo=..., melody_hi=...)`。

## 安装（从仓库克隆）

```bat
git clone https://github.com/<you>/pianoforge.git
cd pianoforge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python tools\fetch_assets.py      :: 可选：下载钢琴采样（约 8 MB）
```

> PyTorch 用 CPU 版即可：`pip install torch --index-url https://download.pytorch.org/whl/cpu`
> 仓库里的 requirements.txt 按开发机冻结；装不上时先装 torch，再装其余依赖。

跑起来：

```bat
pf.cmd transcribe "D:\music\song.ogg"     :: 命令行
run_gui.cmd                                  :: 图形界面
```

**二进制资源不在仓库里**（体积与授权原因）：

| 资源 | 位置 | 没有时的行为 |
| --- | --- | --- |
| FluidR3_GM 钢琴采样 | `bin/samples/piano_mp3/*.mp3` | 退回内置合成器音色 |
| Basic Pitch ONNX 模型 | `bin/models/nmp.onnx` | 退回经典 DSP 转谱 |

`python tools\fetch_assets.py --check` 可以查看缺什么。

## 自带工具

| 脚本 | 作用 |
| --- | --- |
| `tools/summary_table.py` | 汇总 out/ 下所有歌曲的质量指标 |
| `tools/align_eval.py` | 时间对齐的音级 / 起音 F1 |
| `tools/ref_compare2.py` | 与参考谱按小节比对（Jaccard / 音级） |
| `tools/score_audit.py` | 谱面内部规则检查（同音重复、半音冲突、音域） |
| `tools/check_tuning.py` | 测量每个钢琴采样的音准偏差 |
| `tools/sep6.py` | 六分轨（piano/guitar/bass/drums/other/vocals） |
| `tools/migrate_outputs.py` | 旧版输出目录迁移到四件套结构 |
| `tools/fetch_assets.py` | 下载钢琴采样、检查模型 |
| `tools/make_icon.py` / `make_shortcut.py` | 生成图标 / 创建桌面快捷方式 |
| `tests/validate_musicxml.py` | 校验每小节/每声部时值是否严格等于 4/4 |

## 已知限制

- 复调密集、鼓点很重的曲子，旋律提取可能串到伴奏声部；可试着调高 `melody_lo`。
- 谱面按“检测到的中位速度”写成固定 BPM，现场演奏的自由速度会被拉直。
- 指弹谱是“旋律 + 低音 + 和弦音”的合理编配，不追求与原曲每个声部一一对应。
- 生成的 PDF 由 Verovio 排版；用 MuseScore 打开 MusicXML 可获得更完整的排版与播放。
- **「打开文件夹」依赖系统外壳**：窗口标题出现「· 受限权限」时，说明这个进程是用受限令牌启动的
  （沙箱、自动化脚本、部分安全软件都会这样），Windows 禁止它调用资源管理器。关掉该窗口，
  从**桌面图标**正常启动（标题不带「受限权限」）即可打开；任何情况下路径都会复制到剪贴板。

## 目录结构

    pianoforge/
      src/pianoforge/        # 库代码（分析、编配、排版、渲染、评测）
      tools/                 # 语料生成、回归测试、采样校准
      bin/samples/piano_mp3/ # FluidR3_GM 钢琴采样
      out/                   # 每首歌的输出
      cache/                 # 分轨缓存、参数、音准表
      pf.cmd / run_gui.cmd   # 启动器
## 性能与健壮性（2026-11-22）

- 转谱速度：第一首样本 80.9 s → **61.5 s**；4 分钟歌曲约 95–101 s。
  优化点：静音分轨跳过、分轨转谱线程并发、逐小节 chroma 改用 `chroma_stft`、对比矫正默认关闭。
- 音质：加入**延音踏板模拟**与**强拍重音**，chroma 0.8343 → **0.8476**。
- 自检：每次转谱结束检查 MusicXML 可解析、音频非静音、PDF 存在，结果写入 `_analysis/report.json` 的 `selfcheck`。
- 阶段耗时写入 `report.json` 的 `stage_seconds` 并打印。
- 静音/过短输入会给出明确错误（退出码 2），不再崩溃。

### 可选开关（环境变量）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PF_THREADS` | 1 | 0 = 顺序转谱（排查问题用） |
| `PF_DENSE` | 0 | 1 = 启用经典算法补齐转谱（更慢、音更多） |
| `PF_REFINE` | 0 | 对比矫正轮数 |
| `PF_PEDAL` | 1 | 0 = 关闭踏板延音 |
| `PF_HARMONY` | 4 | 每小节和弦声部上限 |
| `PF_BUDGET` | 0 | >0 时限制每小节不同音高数 |
| `PF_STEMS6` | 空 | 六分轨缓存目录（配合 `--engine max`） |

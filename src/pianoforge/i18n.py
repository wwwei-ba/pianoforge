"""Bilingual (Chinese / English) UI strings and the persisted language setting.

Language resolution order:  PIANOFORGE_LANG env var  ->  cache/settings.json  ->
Windows UI language  ->  English.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS = os.path.join(ROOT, "cache", "settings.json")

LANGUAGES = [("zh", "中文"), ("en", "English")]

# key: (Chinese, English)
S: dict[str, tuple[str, str]] = {
    # ---- window chrome -------------------------------------------------
    "app.title": ("PianoForge · 音频转钢琴谱与指弹谱", "PianoForge · Audio to piano score & tab"),
    "app.subtitle": ("选一首歌，得到可编辑的钢琴谱、指弹六线谱和一条钢琴音轨。",
                     "Pick a song; get an editable piano score, a fingerstyle tab and a piano track."),
    "app.language": ("语言", "Language"),
    "app.browse": ("选择文件", "Browse"),
    "app.path_hint": ("音频文件路径（ogg / mp3 / wav / flac / m4a）",
                      "Audio file path (ogg / mp3 / wav / flac / m4a)"),
    "app.separate": ("先分轨并去除人声（更慢、更干净）",
                      "Separate stems and strip vocals (slower, cleaner)"),
    "app.engine": ("转谱引擎", "engine"),
    "app.engine_full": ("标准（推荐）", "Standard"),
    "app.engine_neural": ("精准（少而准）", "Precise"),
    "app.engine_piano": ("纯钢琴", "Solo piano"),
    "app.engine_classic": ("经典（不用模型）", "Classic (no model)"),
    "app.stage": ("第 {cur}/{total} 步", "step {cur}/{total}"),
    "app.run": ("开始转谱", "Transcribe"),
    "app.open_out": ("打开输出文件夹", "Open output folder"),
    "app.title_limited": (" · 受限权限", " · restricted"),
    "app.low_integrity": ("注意：当前以受限权限运行，“打开文件夹”可能不可用。请从桌面图标重新启动。",
                          "note: running with restricted rights - \"open folder\" may be unavailable. "
                          "Restart from the desktop icon."),
    "app.ready": ("就绪", "ready"),
    "app.working": ("处理中…", "working…"),
    "app.done": ("完成", "done"),
    "app.failed": ("失败", "failed"),
    "app.log_ready": ("PianoForge 已就绪，选择音频后点击“开始转谱”。",
                      "PianoForge is ready. Pick an audio file and press Transcribe."),
    "app.drop_hint": ("把音频文件拖进这个窗口即可导入", "Drop an audio file anywhere in this window"),
    "app.drop_hover": ("松开鼠标导入这个文件", "Release to load this file"),
    "app.drop_ok": ("已导入：{name}", "loaded: {name}"),
    "app.drop_bad": ("只支持音频文件：ogg / mp3 / wav / flac / m4a", "audio files only: ogg / mp3 / wav / flac / m4a"),
    "app.open_failed": ("无法打开文件夹：{msg}", "cannot open folder: {msg}"),
    "app.open_none": ("还没有输出目录，先转一首歌吧", "no output folder yet - transcribe something first"),
    "app.warn_title": ("需要音频文件", "Audio file needed"),
    "app.warn_body": ("请先选择一个存在的音频文件。", "Please choose an existing audio file first."),
    "app.summary_tempo": ("速度 {bpm} BPM，调性 {key}", "{bpm} BPM, key {key}"),
    "app.summary_notes": ("旋律音 {notes} 个，和弦 {chords} 段", "{notes} melody notes, {chords} chord segments"),
    "app.summary_metrics": ("旋律音高一致 {exact}%（半音内 {within}%）",
                            "melody pitch match {exact}% (within a semitone {within}%)"),
    "app.summary_chroma": ("和声相似度 {chroma}", "chroma similarity {chroma}"),
    "app.summary_out": ("输出目录：{dir}", "outputs in {dir}"),
    "app.error": ("出错了：{msg}", "ERROR: {msg}"),

    # ---- tabs ----------------------------------------------------------
    "tab.transcribe": ("转谱", "Transcribe"),
    "tab.results": ("结果与预览", "Results & preview"),
    "tab.scores": ("乐谱库", "Score library"),
    "tab.compose": ("编曲", "Compose"),

    # ---- results tab ---------------------------------------------------
    "res.empty": ("还没有结果，先在“转谱”页跑一首歌。", "No results yet - transcribe a song first."),
    "res.files": ("生成的文件", "Generated files"),
    "res.preview": ("乐谱预览", "Score preview"),
    "res.page": ("第 {cur} / {total} 页", "page {cur} / {total}"),
    "res.zoom": ("{pct}%", "{pct}%"),
    "res.play_piano": ("▶ 播放钢琴轨", "▶ Play piano track"),
    "res.play_original": ("▶ 播放原曲", "▶ Play original"),
    "res.stop": ("■ 停止", "■ Stop"),
    "res.open_folder": ("打开文件夹", "Open folder"),
    "res.opened": ("已打开：{path}", "opened: {path}"),
    "res.open_low_il": ("当前窗口以受限权限运行，Windows 不允许它打开资源管理器。\n"
                        "文件都在左侧列表里：点「钢琴谱」预览、点「曲谱音频」试听。\n"
                        "路径已复制到剪贴板，可直接粘到资源管理器。",
                        "this window runs with restricted rights, so Windows blocks the "
                        "file manager.\nUse the list on the left (piano score / audio).\n"
                        "The path was copied to the clipboard."),
    "res.open_denied": ("系统拒绝打开资源管理器。路径已复制到剪贴板。",
                        "the shell refused to open the folder. The path is on the clipboard."),
    "res.copy_path": ("复制路径", "Copy path"),
    "res.copied": ("路径已复制到剪贴板", "path copied to clipboard"),
    "res.open_failed": ("打不开文件夹：{msg}\n可以点“复制路径”手动打开。",
                        "cannot open the folder: {msg}\nuse Copy path instead."),
    "res.no_preview": ("选中左边的 PDF 可以在这里预览", "select a PDF on the left to preview it"),
    "res.no_audio": ("还没有可播放的音频", "no audio to play yet"),
    "res.playing": ("正在播放：{name}", "playing: {name}"),
    "res.stopped": ("已停止", "stopped"),
    "res.audio_missing": ("文件不存在：{path}", "file not found: {path}"),
    "res.song": ("歌曲", "song"),
    "res.art_audio": ("曲谱音频", "rendered audio"),
    "res.art_original": ("原曲", "original track"),
    "res.art_piano": ("钢琴谱", "piano score"),
    "res.art_guitar": ("吉他谱", "guitar tab"),
    "res.volume": ("音量", "Volume"),
    "res.mute": ("静音", "Mute"),
    "res.unmute": ("恢复音量", "Unmute"),
    "res.src_piano": ("钢琴轨", "piano"),
    "res.src_original": ("原曲", "original"),
    "res.mark": ("复制当前时间", "copy time"),
    "res.reloaded": ("音频已更新，重新载入：{name}", "audio changed, reloaded: {name}"),
    "res.system_player": ("系统播放器", "system player"),
    "res.fallback_player": ("内置播放失败，已交给系统播放器", "in-app playback failed, opened system player"),
    "res.marked": ("已复制时间点 {t}", "copied {t}"),
    "res.refresh": ("刷新列表", "Refresh"),
    "res.delete": ("删除这首歌", "Delete song"),
    "res.delete_title": ("删除确认", "Delete"),
    "res.delete_body": ("确定删除《{name}》的全部产物吗？此操作不可恢复。",
                        "Delete every generated file for \"{name}\"? This cannot be undone."),
    "res.removed": ("已删除旧的同名产物：{name}", "removed previous output: {name}"),
    "res.overwrite_title": ("同名歌曲已存在", "A song with the same name exists"),
    "res.overwrite_body": ("已经有一份名为《{name}》的转谱结果。\n要用这次的结果覆盖它吗？",
                           "There is already a result named \"{name}\".\nOverwrite it with this run?"),
    "res.no_original": ("这首歌没有记录原曲路径（编曲导出的产物没有原曲）",
                        "no original track recorded for this song"),

    # ---- score library -------------------------------------------------
    "lib.title": ("所有已生成的乐谱（点选查看）", "all generated scores (click to view)"),
    "lib.search": ("搜索乐曲…", "search songs…"),
    "lib.piano": ("钢琴谱", "piano score"),
    "lib.tab": ("指弹六线谱", "fingerstyle tab"),

    # ---- compose tab ---------------------------------------------------
    "comp.hint": ("左键在网格上添加音符，右键删除；拖动可连续画。",
                  "Left-click to add a note, right-click to delete, drag to paint."),
    "comp.bars": ("小节", "Bars"),
    "comp.tempo": ("速度", "Tempo"),
    "comp.key": ("调性", "Key"),
    "comp.note_len": ("时值", "Length"),
    "comp.play": ("▶ 试听", "▶ Play"),
    "comp.stop": ("■ 停止", "■ Stop"),
    "comp.clear": ("清空", "Clear"),
    "comp.export": ("导出谱子与音频", "Export score & audio"),
    "comp.notes": ("音符：{n}", "notes: {n}"),
    "comp.empty": ("还没有音符", "no notes yet"),
    "comp.exported": ("已导出到：{dir}", "exported to: {dir}"),
    "comp.need_notes": ("先点几个音符吧", "add a few notes first"),

    # ---- pipeline log --------------------------------------------------
    "pipe.silent_input": ("输入音频几乎是静音，无法转谱", "the input audio is silent; nothing to transcribe"),
    "pipe.too_short": ("输入音频短于 1 秒，无法转谱", "the input is shorter than 1 second"),
    "pipe.decode": ("[1/9] 解码 {path}", "[1/9] decoding {path}"),
    "pipe.duration": ("      {dur:.1f} 秒 @ {sr} Hz", "      {dur:.1f}s @ {sr} Hz"),
    "pipe.separation": ("[2/9] 分轨（demucs htdemucs）", "[2/9] source separation (demucs htdemucs)"),
    "pipe.stems": ("      分轨：{stems}", "      stems: {stems}"),
    "pipe.vocals_backing": ("      检测到伴唱（RMS {rms}），保留在和声中、不作主旋律",
                              "      backing vocals detected (RMS {rms}); kept in the harmony"),
    "pipe.vocals_cleaned": ("      已用软掩码抑制伴奏轨里残留的人声",
                             "      residual vocals suppressed with a soft mask"),
    "pipe.vocals_clean_failed": ("      人声抑制失败：{err}", "      vocal suppression failed: {err}"),
    "pipe.vocal_melody": ("      人声旋律作为主旋律：{n} 个音（覆盖 {cover}% 时长）",
                           "      vocal line used as melody: {n} notes ({cover}% of the track)"),
    "pipe.vocal_melody_failed": ("      人声旋律提取失败：{err}", "      vocal melody extraction failed: {err}"),
    "pipe.vocals_dropped": ("      检测到人声（RMS {rms}），已从转谱中剔除",
                             "      vocals detected (RMS {rms}), excluded from transcription"),
    "pipe.stems6": ("      六分轨：{stems}", "      six stems: {stems}"),
    "pipe.separation_failed": ("      分轨失败（{err}），改用整轨分析", "      separation failed ({err}); continuing without it"),
    "pipe.no_separation": ("[2/9] 已跳过分轨", "[2/9] source separation skipped"),
    "pipe.harmonic": ("[3/9] 谐波/打击乐分离", "[3/9] harmonic separation"),
    "pipe.tempo": ("[4/9] 节拍 / 调性", "[4/9] tempo / beats / key"),
    "pipe.tempo_result": ("      {bpm:.1f} BPM，{key} 调，{beats} 个拍点",
                          "      {bpm:.1f} BPM, key {key}, {beats} beats"),
    "pipe.chords": ("[5/9] 和弦识别", "[5/9] chord recognition"),
    "pipe.chords_result": ("      {n} 个和弦片段", "      {n} chord segments"),
    "pipe.melody": ("[6/9] 旋律提取", "[6/9] melody extraction"),
    "pipe.melody_outliers": ("      剔除旋律离群音：{n} 个", "      melody outliers dropped: {n}"),
    "pipe.melody_smoothed": ("      旋律跳音改归伴奏：{n} 个", "      isolated melody notes moved to accompaniment: {n}"),
    "pipe.rerender": ("      乐谱微调 {n} 处，已重新渲染音频", "      {n} score fixes, audio re-rendered"),
    "pipe.melody_raw": ("      {n} 个原始旋律音", "      {n} raw melody notes"),
    "pipe.melody_quant": ("      {n} 个量化后旋律音", "      {n} quantised melody notes"),
    "pipe.arrange": ("[7/9] 编配", "[7/9] building arrangements"),
    "pipe.poly": ("      多音高转谱：{n} 个音", "      polyphonic transcription: {n} notes"),
    "pipe.full": ("      补齐转谱：追加 {extra} 个音", "      dense pass: {extra} extra notes"),
    "pipe.octave_fix": ("      八度校正：{n} 个旋律音", "      octave fix: {n} melody notes"),
    "pipe.piano_mode": ("      纯钢琴模式：取转谱最高声部为旋律（{n} 个音）",
                        "      solo-piano mode: melody = top voice ({n} notes)"),
    "pipe.max_recall": ("      最大召回转谱：{n} 个音", "      max-recall transcription: {n} notes"),
    "pipe.instrument_pass": ("      分乐器转谱：追加 {n} 个音", "      instrument-aware pass: {n} extra notes"),
    "pipe.instrument_failed": ("      分乐器转谱失败：{err}", "      instrument-aware pass failed: {err}"),
    "pipe.neural": ("      神经网络转谱（Basic Pitch）：{n} 个音",
                    "      neural transcription (Basic Pitch): {n} notes"),
    "pipe.poly_failed": ("      多音高转谱失败：{err}", "      polyphonic transcription failed: {err}"),
    "pipe.arrange_poly": ("      按实际转谱音符编写钢琴谱：{n} 个事件",
                          "      piano built from transcribed notes: {n} events"),
    "pipe.arrange_result": ("      钢琴 {p} 个事件，六线谱 {g} 个事件",
                            "      piano events {p}, tab events {g}"),
    "pipe.refine_start": ("      原曲对比：起始和声相似度 {score}", "      comparing with the original: start {score}"),
    "pipe.refine_iter": ("      第 {i} 轮矫正：{n} 个小节偏薄，和声相似度 {before} → {after}",
                          "      refinement {i}: {n} thin bars, harmony {before} -> {after}"),
    "pipe.refine_failed": ("      对比矫正跳过：{err}", "      refinement skipped: {err}"),
    "pipe.write": ("[8/9] 写出乐谱与音频", "[8/9] writing scores and audio"),
    "pipe.evaluate": ("[9/9] 与原曲比对", "[9/9] evaluating against the original"),
    "pipe.timing": ("      耗时（秒）：{parts}", "      seconds per stage: {parts}"),
    "pipe.transcribe_sec": ("      转谱+编配用时 {sec} 秒", "      transcription+arrangement: {sec}s"),
    "pipe.refine_sec": ("      对比矫正用时 {sec} 秒", "      refinement: {sec}s"),
    "pipe.selfcheck": ("      自检：{ok}（音频 {sec}s，RMS {rms}）",
                       "      self-check: {ok} (audio {sec}s, RMS {rms})"),
    "pipe.selfcheck_failed": ("      自检失败：{err}", "      self-check failed: {err}"),
    "pipe.done": ("完成，用时 {sec} 秒 → {dir}", "done in {sec}s -> {dir}"),
    "pipe.fig_skip": ("      跳过验证图：{err}", "      verification figure skipped: {err}"),
    "pipe.encode_failed": ("      音频转码失败：{err}", "      encode failed: {err}"),
    "pipe.original_copy_failed": ("      原曲副本写入失败：{err}", "      original copy failed: {err}"),

    # ---- CLI -----------------------------------------------------------
    "cli.desc": ("把音乐文件转成钢琴谱、指弹六线谱与钢琴音轨。",
                 "Transcribe a music file into a piano score, a fingerstyle guitar tab and a piano track."),
    "cli.transcribe_help": ("对单个音频文件跑完整流程", "run the full pipeline on one audio file"),
    "cli.batch_help": ("批量处理整个文件夹并输出指标表", "run over a folder and print a metrics table"),
    "cli.out_help": ("输出目录", "output directory"),
    "cli.title_help": ("乐谱标题", "score title"),
    "cli.sep_help": ("先用 demucs 分轨", "use demucs source separation"),
    "cli.no_sep_help": ("跳过分轨", "skip source separation"),
    "cli.lang_help": ("界面语言：zh 或 en", "interface language: zh or en"),
    "cli.input_error": ("无法转谱：{err}", "cannot transcribe: {err}"),
    "cli.melody_lo_help": ("旋律最低音（MIDI）", "lowest melody pitch (MIDI)"),
    "cli.melody_hi_help": ("旋律最高音（MIDI）", "highest melody pitch (MIDI)"),
    "cli.limit_help": ("最多处理几个文件", "process at most this many files"),
    "cli.failed": ("失败", "FAILED"),
    "cli.summary": ("=== 汇总 ===", "=== summary ==="),
}

_state = {"lang": None}


def _from_env() -> str | None:
    v = os.environ.get("PIANOFORGE_LANG", "").strip().lower()
    return v if v in ("zh", "en") else None


def _from_settings() -> str | None:
    try:
        data = json.load(open(SETTINGS, encoding="utf-8"))
        v = str(data.get("language", "")).lower()
        return v if v in ("zh", "en") else None
    except Exception:
        return None


def _from_windows() -> str:
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (langid & 0x3FF) == 0x04:  # Chinese
            return "zh"
    except Exception:
        pass
    try:
        import locale
        if (locale.getdefaultlocale()[0] or "").lower().startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"


def get_language() -> str:
    if _state["lang"]:
        return _state["lang"]
    lang = _from_env() or _from_settings() or _from_windows()
    _state["lang"] = lang
    return lang


def get_settings() -> dict:
    try:
        data = json.load(open(SETTINGS, encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_setting(key: str, value) -> None:
    """Persist one small user preference (language, volume, window state...)."""
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        data = get_settings()
        data[key] = value
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


def get_setting(key: str, default=None):
    return get_settings().get(key, default)


def set_language(code: str, persist: bool = True) -> str:
    code = "zh" if str(code).lower().startswith("zh") else "en"
    _state["lang"] = code
    if persist:
        set_setting("language", code)
    return code


def tr(message_id: str, **fmt) -> str:
    pair = S.get(message_id)
    if pair is None:
        text = message_id
    else:
        text = pair[0] if get_language() == "zh" else pair[1]
    if fmt:
        try:
            return text.format(**fmt)
        except Exception:
            return text
    return text


def language_name(code: str | None = None) -> str:
    code = code or get_language()
    for c, name in LANGUAGES:
        if c == code:
            return name
    return code

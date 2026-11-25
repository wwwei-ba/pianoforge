"""Double-clicking a score must never play another song's audio."""
import os
import sys

ROOT = r"D:\deepfile\pianoforge"
sys.path.insert(0, os.path.join(ROOT, "src"))
import pianoforge.gui as gui

gui.messagebox.showwarning = lambda *a, **k: None
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: None

app = gui.App()
app.withdraw()
app.update()

songs = [s for s in app.tree.get_children() if os.path.isdir(s)]
assert len(songs) >= 2, "need at least two songs to test"
a, b = songs[0], songs[1]

problems = []


def check(label, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + label + (("  " + str(detail)) if detail else ""))
    if not ok:
        problems.append(label)


# 1. activating song A loads A's audio
app._activate_song(a)
check("activate A loads A audio", app.player.path == gui.find_artifact(a, "audio"),
      app.player.path)

# 2. selecting B's score leaf must switch the player to B (not stay on A)
leaf = gui.find_artifact(b, "piano")
app.tree.selection_set(leaf)
app.update()
app.on_results_select()
check("select B score loads B audio", app.player.path == gui.find_artifact(b, "audio"),
      app.player.path)
check("viewer shows B score", app.viewer.title.cget("text").startswith(os.path.basename(b)),
      app.viewer.title.cget("text"))

# 3. double-clicking a score must not start playback at all
app.player.stop(silent=True)
app.tree.selection_set(leaf)
app.update()
app.on_results_double()
check("double-click score does not play", not app.player.playing,
      f"playing={app.player.playing} path={app.player.path}")

# 4. double-clicking the audio leaf does play it
audio_leaf = gui.find_artifact(b, "audio")
app.tree.selection_set(audio_leaf)
app.update()
app.on_results_double()
check("double-click audio plays that file", app.player.path == audio_leaf,
      app.player.path)
app.player.stop(silent=True)

# 5. every song's leaves resolve to their own audio
bad = []
for s in songs:
    for key in ("piano", "guitar", "audio", "original"):
        p = gui.find_artifact(s, key)
        if not p:
            continue
        if os.path.dirname(p) != s:
            bad.append((p, s))
check("all leaves live in their song folder", not bad, bad[:2])

app.destroy()
print("problems:", len(problems))
sys.exit(1 if problems else 0)

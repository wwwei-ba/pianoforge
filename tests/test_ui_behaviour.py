"""Small UI behaviours: volume apply-on-release, language switch, viewer keep-place."""
import os
import sys

ROOT = r"D:\deepfile\pianoforge"
sys.path.insert(0, os.path.join(ROOT, "src"))
import pianoforge.gui as gui

gui.messagebox.showwarning = lambda *a, **k: None
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: None

problems = []


def check(label, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + label + (("  " + str(detail)) if detail else ""))
    if not ok:
        problems.append(label)


app = gui.App()
app.withdraw()
app.update()

# volume: dragging must not restart playback, release must
app.player.playing = False
app.player.volume = 0.8
calls = []
app.player.play_from = lambda t: calls.append(t)
app.player.playing = True
app.player.on_volume(0.42)
check("volume drag does not restart", calls == [], calls)
app.player.volume = 0.42
app.player._remember_volume()
check("volume release applies", len(calls) == 1, calls)
app.player.playing = False

# stored volume
check("volume persisted", abs(float(gui.get_setting("volume", 0)) - 0.42) < 0.001,
      gui.get_setting("volume"))

# language switch relabels tree rows
songs = app.tree.get_children()
if songs:
    before = [app.tree.item(c, "text") for c in app.tree.get_children(songs[0])]
    app.apply_language("en")
    app.update()
    songs = app.tree.get_children()
    after = [app.tree.item(c, "text") for c in app.tree.get_children(songs[0])]
    check("tree labels follow language", before != after, (before, after))
    app.apply_language("zh")
    app.update()

# refresh keeps the same score open (no scroll reset)
if songs:
    app._activate_song(songs[0])
    shown = app.viewer.path
    app.refresh_results()
    check("refresh keeps current score", app.viewer.path == shown, app.viewer.path)

app.destroy()
print("problems:", len(problems))
sys.exit(1 if problems else 0)

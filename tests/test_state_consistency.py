"""Selection must always keep viewer + player in sync with the clicked song."""
import os
import shutil
import sys

ROOT = r"D:\deepfile\pianoforge"
sys.path.insert(0, os.path.join(ROOT, "src"))
import pianoforge.gui as gui

gui.messagebox.showwarning = lambda *a, **k: None
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: None
gui.messagebox.askyesno = lambda *a, **k: True

problems = []


def check(label, ok, detail=""):
    print(("OK   " if ok else "FAIL ") + label + (("  " + str(detail)) if detail else ""))
    if not ok:
        problems.append(label)


app = gui.App()
app.withdraw()
app.update()

songs = [s for s in app.tree.get_children() if os.path.isdir(s)]
check("songs present", len(songs) >= 2, len(songs))

# 1. every song activates with its own audio + score
for s in songs:
    app._activate_song(s)
    want_audio = gui.find_artifact(s, "audio")
    got = app.player.path
    if want_audio:
        check(f"activate {os.path.basename(s)[:18]}", got == want_audio, got)
    else:
        check(f"no-audio song clears player {os.path.basename(s)[:12]}", got is None, got)
    title = app.viewer.title.cget("text")
    check(f"viewer follows {os.path.basename(s)[:14]}",
          title.startswith(os.path.basename(s)), title)

# 2. every leaf selection keeps the player inside that leaf's folder
bad = []
for s in songs:
    for child in app.tree.get_children(s):
        app.tree.selection_set(child)
        app.update()
        app.on_results_select()
        p = app.player.path
        if p is not None and os.path.dirname(p) != s:
            bad.append((os.path.basename(child), os.path.basename(p), os.path.basename(s)))
check("leaf selection stays in its song", not bad, bad[:3])
app.player.stop(silent=True)

# 3. deleting the active song clears the player (work on a throwaway copy)
src = songs[0]
tmp = os.path.join(ROOT, "out", "zz_test_delete")
shutil.rmtree(tmp, ignore_errors=True)
shutil.copytree(src, tmp)
app.refresh_results()
app.tree.selection_set(tmp)
app.update()
app.on_results_select()
check("copy activated", app.player.path and app.player.path.startswith(tmp), app.player.path)
app.delete_song()
app.update()
check("delete clears player", app.player.path is None, app.player.path)
check("delete removes folder", not os.path.isdir(tmp), tmp)

# 4. library selection shows the clicked score
lib_songs = app.lib_tree.get_children()
if lib_songs:
    kids = app.lib_tree.get_children(lib_songs[0])
    if kids:
        app.lib_tree.selection_set(kids[0])
        app.update()
        app.on_library_select()
        check("library shows clicked score",
              os.path.basename(os.path.dirname(app.lib_viewer.title.cget("text").split(" · ")[0]))
              in os.path.basename(lib_songs[0]),
              app.lib_viewer.title.cget("text"))

app.destroy()
print("problems:", len(problems))
sys.exit(1 if problems else 0)

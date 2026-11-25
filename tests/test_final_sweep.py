import os, sys, types, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import pianoforge.gui as gui

gui.messagebox.showwarning = lambda *a, **k: print("  [warn]", a[1][:50] if len(a) > 1 else "")
gui.messagebox.showerror = lambda *a, **k: print("  [error]", a[1][:80] if len(a) > 1 else "")
gui.messagebox.askyesno = lambda *a, **k: True
gui.messagebox.showinfo = lambda *a, **k: print("  [info]", a[1][:60].replace("\n", " ") if len(a) > 1 else "")

problems = []


def check(label, fn):
    try:
        fn()
        print(f"OK   {label}")
    except Exception as exc:
        problems.append((label, exc))
        print(f"FAIL {label}: {type(exc).__name__} {exc}")
        traceback.print_exc()


app = gui.App()
app.withdraw()
app.update()

check("tabs", lambda: print("   tabs:", [app.nb.tab(i, "text") for i in app.nb.tabs()]))
check("language en", lambda: (app.apply_language("en"), app.update()))
check("language zh", lambda: (app.apply_language("zh"), app.update()))
check("song tree", lambda: print("   songs:", [os.path.basename(s) for s in app.tree.get_children()]))
check("song children", lambda: print("   files:", [os.path.basename(c) for c in app.tree.get_children(app.tree.get_children()[0])]))
check("lib tree", lambda: print("   lib songs:", [os.path.basename(s) for s in app.lib_tree.get_children()]))
check("select lib score", lambda: (app.lib_tree.selection_set(
    gui.find_artifact(os.path.join(ROOT, "out", "fukashigi_lofi"), "piano")), app.update()))
check("viewer scroll", lambda: (app.viewer._scroll(3), app.viewer._scroll(-3),
                                 app.viewer.zoom(0.1), app.viewer.zoom(-0.1)))
check("viewer layout", lambda: (bool(app.viewer._offsets) or app.viewer.doc is None) or
      (_ for _ in ()).throw(AssertionError("pages not laid out")))
check("drop audio", lambda: app.on_drop(types.SimpleNamespace(
    data="{D:/deepfile/pianoforge/samples/ref/fukashigi_lofi.ogg}")))
check("play piano", lambda: app.play_piano())
check("stop", lambda: app.stop_audio())
check("copy path", lambda: app.copy_path())
check("three tabs", lambda: (len(app.nb.tabs()) == 3) or (_ for _ in ()).throw(
    AssertionError(f"expected 3 tabs, found {len(app.nb.tabs())}")))
check("open folder", lambda: app.open_out())

app.destroy()
print("\nproblems:", len(problems))
for label, exc in problems:
    print("  ", label, "->", exc)

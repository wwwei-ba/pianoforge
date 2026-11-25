"""The score viewer must stack pages and scroll with the wheel."""
import sys, os
sys.path.insert(0, r"D:\deepfile\pianoforge\src")
import pianoforge.gui as gui

app = gui.App()
app.geometry("1180x820")
app.nb.select(app.tab_r)
app.update()
app.update_idletasks()
pdf = os.path.join(r"D:\deepfile\pianoforge\out", "layout_test", "piano.pdf")
v = app.viewer
v.show(pdf)
app.update()
v.fit_width()
app.update()

print("pages:", v.doc.page_count if v.doc else 0)
print("offsets:", len(v._offsets))
print("rendered:", sorted(v._photos.keys()))
print("scrollregion:", v.canvas.cget("scrollregion"))
print("zoom:", round(v.zoom_factor, 2))

# simulate a wheel scroll
v._scroll(6)
app.update()
print("view after scroll:", [round(x, 3) for x in v.canvas.yview()])

# zoom buttons
v.zoom(0.3)
app.update()
print("after zoom:", round(v.zoom_factor, 2), "offsets:", len(v._offsets))
app.destroy()

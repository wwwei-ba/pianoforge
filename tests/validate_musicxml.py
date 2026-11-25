import sys, os
import xml.etree.ElementTree as ET

path = sys.argv[1] if len(sys.argv) > 1 else r"D:/deepfile/pianoforge/out/fukashigi_lofi/score_piano.musicxml"
tree = ET.parse(path)
root = tree.getroot()
divisions = int(root.find(".//divisions").text)
mpl = 4 * divisions
print("divisions", divisions, "measure_len", mpl)

bad = 0
for part in root.findall("part"):
    measures = part.findall("measure")
    bad_in_part = 0
    for m in measures:
        acc = {}
        for el in m:
            if el.tag in ("note", "forward"):
                v = el.find("voice")
                vid = v.text if v is not None else "1"
                g = el.find("staff")
                key = (g.text if g is not None else "1", vid)
                if el.tag == "forward" or el.find("chord") is None:
                    acc[key] = acc.get(key, 0) + int(el.find("duration").text)
        for key, total in acc.items():
            if total != mpl:
                bad_in_part += 1
                if bad_in_part <= 5:
                    print("  measure", m.get("number"), "staff/voice", key, "total", total)
    print("part", part.get("id"), "measures", len(measures), "bad", bad_in_part)
    bad += bad_in_part
print("bad total:", bad)

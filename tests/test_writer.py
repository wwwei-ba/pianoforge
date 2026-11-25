import sys
sys.path.insert(0, r"D:/deepfile/pianoforge/src")
from pianoforge.musicxml import Event, Part, write_score, decompose

part = Part(part_id="P1", name="Piano", staves=2, clefs=[("G", 2), ("F", 4)])
part.events = [
    Event(start=0, dur=478, pitches=[72], staff=1, voice=1),
    Event(start=478, dur=500, pitches=[74], staff=1, voice=1),
    Event(start=978, dur=942, pitches=[76], staff=1, voice=1),
    Event(start=0, dur=480, pitches=[48], staff=2, voice=1),
    Event(start=480, dur=1440, pitches=[55], staff=2, voice=1),
]
print("decompose 478:", decompose(478))
write_score(r"D:/deepfile/pianoforge/cache/test_writer.xml", [part], "t", "c", 100, 0, 1920)
print(open(r"D:/deepfile/pianoforge/cache/test_writer.xml", encoding="utf-8").read()[:1800])

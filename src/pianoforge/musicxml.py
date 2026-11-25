"""A small, dependency-free MusicXML 4.0 writer (grand staff + tab)."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

STEP_NAMES = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
ALTERS = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
FLAT_NAMES = ["C", "D", "D", "E", "E", "F", "G", "G", "A", "A", "B", "B"]
FLAT_ALTERS = [0, -1, 0, -1, 0, 0, -1, 0, -1, 0, -1, 0]

DIVISIONS = 480
TYPE_TICKS = {
    "whole": 4 * DIVISIONS, "half": 2 * DIVISIONS, "quarter": DIVISIONS,
    "eighth": DIVISIONS // 2, "16th": DIVISIONS // 4, "32nd": DIVISIONS // 8,
    "64th": DIVISIONS // 16,
}
TICK_TYPES = sorted(((v, k) for k, v in TYPE_TICKS.items()), key=lambda x: -x[0])

KEY_FIFTHS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
}


def spell(midi: int, fifths: int = 0) -> tuple[str, int, int]:
    pc = midi % 12
    octave = midi // 12 - 1
    if fifths < 0 or pc in (1, 3, 6, 8, 10):
        if fifths < 0 and pc in (1, 3, 6, 8, 10):
            return FLAT_NAMES[pc], FLAT_ALTERS[pc], octave
    return STEP_NAMES[pc], ALTERS[pc], octave


def duration_type(ticks: int) -> tuple[str, int]:
    """Return (type-name, dots) closest to ticks."""
    best = None
    for base_ticks, name in TICK_TYPES:
        for dots in (2, 1, 0):
            total = base_ticks + dots * base_ticks // 2
            err = abs(total - ticks)
            if best is None or err < best[0]:
                best = (err, name, dots)
    return best[1], best[2]


@dataclass
class Event:
    """A note or chord at an absolute tick position."""
    start: int
    dur: int
    pitches: list[int]
    staff: int = 1
    voice: int = 1
    string_frets: list[tuple[int, int]] | None = None  # (string, fret) per pitch
    dynamic: str | None = None

    @property
    def end(self) -> int:
        return self.start + self.dur


@dataclass
class Part:
    part_id: str
    name: str
    staves: int = 1
    clefs: list[tuple[str, int]] = field(default_factory=lambda: [("G", 2)])
    tab: bool = False
    events: list[Event] = field(default_factory=list)


def _add_note(parent, ev: Event, pitch: int, dur: int, tie_start: bool, tie_stop: bool,
              note_type: str, dots: int, fifths: int, is_tab: bool = False,
              tech: tuple[int, int] | None = None, chord: bool = False,
              staff: int = 1, multi: bool = False):
    n = ET.SubElement(parent, "note")
    if chord:
        ET.SubElement(n, "chord")
    p = ET.SubElement(n, "pitch")
    step, alter, octv = spell(pitch, fifths)
    ET.SubElement(p, "step").text = step
    if alter:
        ET.SubElement(p, "alter").text = str(alter)
    ET.SubElement(p, "octave").text = str(octv)
    ET.SubElement(n, "duration").text = str(dur)
    if tie_stop:
        ET.SubElement(n, "tie", type="stop")
    if tie_start:
        ET.SubElement(n, "tie", type="start")
    ET.SubElement(n, "voice").text = str(ev.voice)
    ET.SubElement(n, "type").text = note_type
    for _ in range(dots):
        ET.SubElement(n, "dot")
    if tie_start or tie_stop:
        notations = ET.SubElement(n, "notations")
        if tie_stop:
            ET.SubElement(notations, "tied", type="stop")
        if tie_start:
            ET.SubElement(notations, "tied", type="start")
        if tech is not None:
            _tech(notations, *tech)
    elif tech is not None:
        notations = ET.SubElement(n, "notations")
        _tech(notations, *tech)
    if is_tab or multi:
        ET.SubElement(n, "staff").text = str(staff)


def _tech(notations, string: int, fret: int):
    tech = ET.SubElement(notations, "technical")
    ET.SubElement(tech, "string").text = str(string)
    ET.SubElement(tech, "fret").text = str(fret)


def _add_rest(parent, start: int, dur: int, staff: int, voice: int):
    while dur > 0:
        ntype, dots = duration_type(dur)
        d = TYPE_TICKS[ntype] + dots * TYPE_TICKS[ntype] // 2
        if d <= 0:
            d = dur
        d = min(d, dur)
        n = ET.SubElement(parent, "note")
        ET.SubElement(n, "rest")
        ET.SubElement(n, "duration").text = str(d)
        ET.SubElement(n, "voice").text = str(voice)
        ntype2, dots2 = duration_type(d)
        ET.SubElement(n, "type").text = ntype2
        for _ in range(dots2):
            ET.SubElement(n, "dot")
        if staff != 1:
            ET.SubElement(n, "staff").text = str(staff)
        dur -= d


def _layout_part(part: Part, total_ticks: int) -> list[list[tuple[int, Event]]]:
    """Split events into measures, returning per-measure (offset, event)."""
    measure_ticks = 4 * DIVISIONS
    n_measures = max(1, (total_ticks + measure_ticks - 1) // measure_ticks)
    measures = [[] for _ in range(n_measures)]
    for ev in part.events:
        start = ev.start
        end = ev.start + ev.dur
        m = start // measure_ticks
        while start < end and m < n_measures:
            m_start = m * measure_ticks
            m_end = m_start + measure_ticks
            seg_start = max(start, m_start)
            seg_end = min(end, m_end)
            if seg_end > seg_start:
                measures[m].append((seg_start - m_start, seg_start, seg_end, ev))
            start = m_end
            m += 1
    return measures, n_measures, measure_ticks


TYPE_VALUES: list[tuple[int, str, int]] = []
for _name, _ticks in TYPE_TICKS.items():
    for _dots in (2, 1, 0):
        TYPE_VALUES.append((_ticks + _dots * _ticks // 2, _name, _dots))
TYPE_VALUES.sort(key=lambda x: -x[0])


def decompose(ticks: int) -> list[tuple[int, str, int]]:
    """Split a duration into standard note values (greedy, longest first)."""
    out: list[tuple[int, str, int]] = []
    remaining = int(ticks)
    guard = 0
    while remaining > 0 and guard < 64:
        guard += 1
        for value, name, dots in TYPE_VALUES:
            if value <= remaining:
                out.append((value, name, dots))
                remaining -= value
                break
        else:
            out.append((remaining, "32nd", 0))
            remaining = 0
    return out


def _emit_group(m_el, ev: Event, pitches: list[int], ticks: int, fifths: int,
                staff: int, voice: int, techs, tie_from_prev: bool, multi: bool = False):
    pieces = decompose(ticks)
    for pi, (value, name, dots) in enumerate(pieces):
        tie_start = pi < len(pieces) - 1
        tie_stop = (pi > 0) or (pi == 0 and tie_from_prev)
        for ni, pitch in enumerate(pitches):
            tech = techs[ni] if techs and ni < len(techs) else None
            _add_note(m_el, ev, pitch, value,
                      tie_start=tie_start, tie_stop=tie_stop,
                      note_type=name, dots=dots, fifths=fifths,
                      is_tab=False, tech=tech, chord=(ni > 0),
                      staff=staff, multi=multi)


def _emit_forward(m_el, ticks: int, voice: int):
    """Advance the cursor without printing a rest (keeps tab clean)."""
    if ticks > 0:
        f = ET.SubElement(m_el, "forward")
        ET.SubElement(f, "duration").text = str(int(ticks))
        ET.SubElement(f, "voice").text = str(voice)


def _emit_rest(m_el, ticks: int, staff: int, voice: int):
    for value, name, dots in decompose(ticks):
        n = ET.SubElement(m_el, "note")
        ET.SubElement(n, "rest")
        ET.SubElement(n, "duration").text = str(value)
        ET.SubElement(n, "voice").text = str(voice)
        ET.SubElement(n, "type").text = name
        for _ in range(dots):
            ET.SubElement(n, "dot")
        if staff != 1:
            ET.SubElement(n, "staff").text = str(staff)


def write_score(path: str, parts: list[Part], title: str, composer: str, tempo: float,
                fifths: int, total_ticks: int, time_sig=(4, 4)) -> str:
    root = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = title
    ident = ET.SubElement(root, "identification")
    cre = ET.SubElement(ident, "creator", type="composer")
    cre.text = composer
    ET.SubElement(ident, "encoding").text = "pianoforge"

    pl = ET.SubElement(root, "part-list")
    for p in parts:
        sp = ET.SubElement(pl, "score-part", id=p.part_id)
        ET.SubElement(sp, "part-name").text = p.name

    measure_ticks = 4 * DIVISIONS
    for p in parts:
        part_events = sorted(p.events, key=lambda e: (e.start, e.dur))
        last_end = max([e.start + e.dur for e in part_events], default=0)
        n_measures = max(1, (max(total_ticks, last_end) + measure_ticks - 1) // measure_ticks)
        part_el = ET.SubElement(root, "part", id=p.part_id)

        for mi in range(n_measures):
            m_start = mi * measure_ticks
            m_end = m_start + measure_ticks
            m_el = ET.SubElement(part_el, "measure", number=str(mi + 1))
            if mi == 0:
                attrs = ET.SubElement(m_el, "attributes")
                ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
                key = ET.SubElement(attrs, "key")
                ET.SubElement(key, "fifths").text = str(fifths)
                time = ET.SubElement(attrs, "time")
                ET.SubElement(time, "beats").text = str(time_sig[0])
                ET.SubElement(time, "beat-type").text = str(time_sig[1])
                if p.staves > 1:
                    ET.SubElement(attrs, "staves").text = str(p.staves)
                for si, (sign, line) in enumerate(p.clefs, start=1):
                    clef = ET.SubElement(attrs, "clef")
                    if p.staves > 1:
                        clef.set("number", str(si))
                    ET.SubElement(clef, "sign").text = sign
                    ET.SubElement(clef, "line").text = str(line)
                if p.tab:
                    details = ET.SubElement(attrs, "staff-details")
                    ET.SubElement(details, "staff-lines").text = "6"
                    for i, (note, octv) in enumerate([("E", 4), ("B", 3), ("G", 3),
                                                      ("D", 3), ("A", 2), ("E", 2)], start=1):
                        st = ET.SubElement(details, "staff-tuning", line=str(i))
                        ET.SubElement(st, "tuning-step").text = note
                        ET.SubElement(st, "tuning-octave").text = str(octv)
                direction = ET.SubElement(m_el, "direction", placement="above")
                dt = ET.SubElement(direction, "direction-type")
                words = ET.SubElement(dt, "words", {"font-weight": "bold"})
                words.text = f"Tempo {int(round(tempo))}"
                ET.SubElement(direction, "sound", tempo=str(round(tempo, 2)))

            for staff in range(1, p.staves + 1):
                segs_all = []
                for ev in part_events:
                    if ev.staff != staff:
                        continue
                    s, e = max(ev.start, m_start), min(ev.start + ev.dur, m_end)
                    if e > s:
                        segs_all.append((s - m_start, e - m_start, s, e, ev))
                voices = sorted({ev.voice for *_, ev in segs_all}) or [1]
                first_stream = staff == 1
                for vi, voice in enumerate(voices):
                    if not first_stream or vi > 0:
                        bk = ET.SubElement(m_el, "backup")
                        ET.SubElement(bk, "duration").text = str(measure_ticks)
                    first_stream = False
                    segs = sorted([g for g in segs_all if g[4].voice == voice],
                                  key=lambda x: (x[0], x[2]))
                    cursor = 0
                    i = 0
                    while i < len(segs):
                        off = segs[i][0]
                        j = i
                        while j + 1 < len(segs) and segs[j + 1][0] == off and \
                                segs[j + 1][4].dur == segs[i][4].dur:
                            j += 1
                        group = segs[i:j + 1]
                        if off > cursor:
                            if voice > 1:
                                _emit_forward(m_el, off - cursor, voice)
                            else:
                                _emit_rest(m_el, off - cursor, staff, voice)
                        dur = group[0][1] - group[0][0]
                        if dur > 0:
                            ev0 = group[0][4]
                            pitches = [g[4].pitches[0] for g in group]
                            techs = []
                            for g in group:
                                if g[4].string_frets:
                                    techs.append(g[4].string_frets[0])
                                else:
                                    techs.append(None)
                            tie_from_prev = group[0][2] > ev0.start
                            _emit_group(m_el, ev0, pitches, dur, fifths, staff, voice, techs,
                                        tie_from_prev, multi=p.staves > 1 or p.tab)
                        cursor = max(cursor, group[0][1])
                        i = j + 1
                    if cursor < measure_ticks:
                        if voice > 1:
                            _emit_forward(m_el, measure_ticks - cursor, voice)
                        else:
                            _emit_rest(m_el, measure_ticks - cursor, staff, voice)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path
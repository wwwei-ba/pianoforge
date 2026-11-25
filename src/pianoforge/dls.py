"""Minimal DLS Level-2 sampler (reads the Windows GM sound set, gm.dls).

Used to render the transcribed score with a real sampled piano instead of a
synthetic tone. Only what a player needs is parsed: instrument regions, key/velocity
ranges, sample links and loop points.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

DEFAULT_DLS = r"C:\Windows\System32\drivers\gm.dls"


def _chunks(data: bytes, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        yield cid, body, size
        pos = body + size + (size & 1)


def _find(data: bytes, start: int, end: int, cid: bytes):
    for c, body, size in _chunks(data, start, end):
        if c == cid:
            return body, size
    return None, None


@dataclass
class Region:
    key_low: int
    key_high: int
    vel_low: int
    vel_high: int
    unity: int
    fine: int
    gain_db: float
    loop_start: int
    loop_length: int
    table_index: int


@dataclass
class Instrument:
    program: int
    bank: int
    regions: list[Region] = field(default_factory=list)


class DLS:
    def __init__(self, path: str = DEFAULT_DLS):
        self.data = open(path, "rb").read()
        if self.data[:4] != b"RIFF" or self.data[8:12] != b"DLS ":
            raise ValueError("not a DLS file")
        self._read_pool()
        self._read_instruments()

    # -- wave pool ---------------------------------------------------------
    def _read_pool(self):
        d = self.data
        body, size = _find(d, 12, len(d), b"ptbl")
        if body is None:
            raise ValueError("no ptbl")
        n = struct.unpack("<I", d[body + 4:body + 8])[0]
        self.cues = [struct.unpack("<II", d[body + 8 + i * 12:body + 16 + i * 12]) for i in range(n)]

        # locate the wave pool list
        pos = 12
        self.pool_start = None
        while pos + 8 <= len(d):
            cid = d[pos:pos + 4]
            sz = struct.unpack("<I", d[pos + 4:pos + 8])[0]
            if cid == b"LIST" and d[pos + 8:pos + 12] == b"wvpl":
                self.pool_start = pos + 12
                self.pool_end = pos + 8 + sz
                break
            pos += 8 + sz + (sz & 1)
        if self.pool_start is None:
            raise ValueError("no wvpl")

    def sample_at(self, index: int) -> tuple[np.ndarray, int]:
        """Return (mono float32 samples, sample rate) for a pool table entry."""
        off, size = self.cues[index]
        base = self.pool_start + off
        end = base + size
        fmt = None
        pcm = None
        stack = [(base, end)]
        while stack and (fmt is None or pcm is None):
            s, e = stack.pop()
            for cid, body, sz in _chunks(self.data, s, e):
                if cid == b"fmt ":
                    fmt = self.data[body:body + sz]
                elif cid == b"data":
                    pcm = self.data[body:body + sz]
                elif cid == b"LIST" and self.data[body:body + 4] in (b"wave", b"wave"):
                    stack.append((body + 4, body + sz))
        if fmt is None or pcm is None:
            raise ValueError(f"bad wave {index}")
        tag, channels, rate, _avg, _align, bits = struct.unpack("<HHIIHH", fmt[:16])
        if tag not in (1, 0xFFFE) or bits != 16:
            raise ValueError(f"unsupported format {tag}/{bits}")
        arr = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            arr = arr.reshape(-1, channels).mean(axis=1)
        return arr, int(rate)

    # -- instruments -------------------------------------------------------
    def _read_instruments(self):
        d = self.data
        body, size = _find(d, 12, len(d), b"LIST")
        # find the lins list header
        pos = 12
        self.instruments: dict[tuple[int, int], Instrument] = {}
        while pos + 8 <= len(d):
            cid = d[pos:pos + 4]
            sz = struct.unpack("<I", d[pos + 4:pos + 8])[0]
            if cid == b"LIST" and d[pos + 8:pos + 12] == b"lins":
                self._read_lins(pos + 12, pos + 8 + sz)
                break
            pos += 8 + sz + (sz & 1)

    def _read_lins(self, start: int, end: int):
        for cid, body, sz in _chunks(self.data, start, end):
            if cid != b"LIST" or self.data[body:body + 4] != b"ins ":
                continue
            self._read_instrument(body + 4, body + sz)

    def _read_instrument(self, start: int, end: int):
        d = self.data
        hdr = None
        regions: list[Region] = []
        for cid, body, sz in _chunks(d, start, end):
            if cid == b"insh":
                nreg, locale, bank = struct.unpack("<III", d[body:body + 12])
                hdr = (nreg, locale, bank)
            elif cid == b"LIST" and d[body:body + 4] == b"lrgn":
                regions = self._read_regions(body + 4, body + sz)
            elif cid == b"rgn " or cid == b"rgn2":
                regions.append(self._read_region(body))
        if hdr is None:
            return
        nreg, locale, bank = hdr
        program = bank & 0x7F
        banknum = (bank >> 8) & 0x7F
        self.instruments[(banknum, program)] = Instrument(program=program, bank=banknum, regions=regions)

    def _read_regions(self, start: int, end: int) -> list[Region]:
        out = []
        for cid, body, sz in _chunks(self.data, start, end):
            if cid == b"LIST" and self.data[body:body + 4] in (b"rgn ", b"rgn2"):
                r = self._read_region(body + 4)
                if r:
                    out.append(r)
            elif cid in (b"rgn ", b"rgn2"):
                r = self._read_region(body)
                if r:
                    out.append(r)
        return out

    def _read_region(self, start: int) -> Region | None:
        d = self.data
        key_low = key_high = vel_low = vel_high = None
        unity, fine, gain = 60, 0, 0.0
        loop_start, loop_length = 0, 0
        table_index = None
        for cid, body, sz in _chunks(d, start, start + 4096):
            if cid == b"rgnh" and sz >= 12:
                key_low, key_high, vel_low, vel_high = struct.unpack("<HHHH", d[body:body + 8])
            elif cid == b"wsmp" and sz >= 20:
                _cb, unity, fine, atten, _opts, nloops = struct.unpack("<IHHiII", d[body:body + 20])
                gain = -atten / 65536.0  # attenuation in 1/65536 dB
                if nloops and sz >= 36:
                    ls, ll = struct.unpack("<II", d[body + 28:body + 36])
                    loop_start, loop_length = ls, ll
            elif cid == b"wlnk" and sz >= 8:
                table_index = struct.unpack("<I", d[body + 4:body + 8])[0]
        if key_low is None or table_index is None:
            return None
        return Region(key_low, key_high, vel_low, vel_high, unity, fine, gain,
                      loop_start, loop_length, table_index)

    # -- playback ----------------------------------------------------------
    def note_sample(self, program: int, bank: int = 0):
        inst = self.instruments.get((bank, program)) or self.instruments.get((0, program))
        return inst

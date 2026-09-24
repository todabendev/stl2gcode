# s2g_segments.py: 2026-05-29 - 1257
# Segment, Segments, Chain, Chains classes and segment file I/O.
# Imports Point and Points from stl2gcode_points.
# Used by stl2gcode_app.py.

import math
import s2g_debug as dbg

s2g_segments_stamp = "s2g_segments.py:"

# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------


class Segment:

    def __init__(self, sid, pt1, pt2, ang):
        self.sid = sid
        self.pid1 = pt1.pid
        self.pid2 = pt2.pid
        self.pt1 = pt1        # Point reference (entry side)
        self.pt2 = pt2        # Point reference (exit side)
        self.normal_angle = ang  # angle of left normal in XY plane (radians)
        self.chainid = None
        self.moveid = None
        self.type = 'L'        # 'L', 'A', 'H', 'D'
        self.next_seg = None       # next segment in chain (direct ref)
        self.prev_seg = None       # prev segment in chain (direct ref)
        self.arc_start = None       # first arc point (arc segs only)
        self.arc_end = None       # last arc point (arc segs only)
        self.center_pt = None       # arc center point (arc segs only)
        self.arc_chain = None      # reference to a chain object that have been replaced
#        self.dump()

    def change_direction(self):
        self.pt1, self.pt2 = self.pt2, self.pt1
        self.pid1, self.pid2 = self.pid2, self.pid1
        self.next_seg, self.prev_seg = self.prev_seg, self.next_seg
        if self.arc_chain is not None:
            self.arc_start, self.arc_end = self.arc_end, self.arc_start
            self.arc_chain.reverse()

    def segarea(self):
        return ((self.pt1.tx * self.pt2.ty) -
                (self.pt2.tx * self.pt1.ty))

    def set_type(self, typ):
        self.type = typ

    def is_arc(self):
        return self.type in ('A', 'H', 'D')

    def dump(self):
        if not dbg.debug_enabled():
            return
        if self.type != 'L':
            return
        x1, y1 = self.pt1.tx, self.pt1.ty
        x2, y2 = self.pt2.tx, self.pt2.ty
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0
        nx = math.cos(self.normal_angle)
        ny = math.sin(self.normal_angle)
        dbg.log(f"LN  {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f} #0000ff {self.sid}", True)
#        dbg.log(f"NRM {mx:.3f} {my:.3f} {nx:.4f} {ny:.4f} #00aa00 {self.sid}", True)

    def __repr__(self):
        return f"Segment(sid={self.sid}, type={self.type!r}, pt1={self.pt1.pid}, pt2={self.pt2.pid})"

# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


class Segments:

    def __init__(self, opts):
        self.oPoints = opts
        self.segct = 0
        self.seg_dict = {}      # sid -> Segment

    def new_segment(self, pt1, pt2, ang):
        """Create a new L segment, add to dict, return sid."""
        self.segct += 1
        sid = self.segct
        seg = Segment(sid, pt1, pt2, ang)
        self.seg_dict[sid] = seg
        return sid

    def find_seed_segment(self):
        for seg in self.seg_dict.values():
            if seg.chainid is None:
                if seg.pt1.degree() > 3:
                    return seg
        for seg in self.seg_dict.values():
            if seg.chainid is None:
                if seg.pt2.degree() > 3:
                    seg.change_direction()
                    return seg
        for seg in self.seg_dict.values():
            if seg.chainid is None:
                if seg.pt1.degree() > 1:
                    return seg
        return None

    def find_unchained_sid(self, pt):
        for sid in pt.seg_arr:
            seg = self.seg_dict.get(sid)
            if seg is not None and seg.chainid is None:
                return sid
        return None

    def remove(self, sid):
        """Remove from index. Object lives on via chain references."""
        if sid in self.seg_dict:
            del self.seg_dict[sid]

    def refer(self, sid):
        """Return Segment for sid, or None if not in dict."""
        return self.seg_dict.get(sid)

    def count(self):
        return len(self.seg_dict)

    def __repr__(self):
        return f"Segments(count={self.count()}, segct={self.segct})"

# s2g_paths.py: 2026-06-25 - 2100
# Move, Path, Paths classes and offset path computation.
# Imports Point and Points from s2g_points.
# Used by s2g_app.py to create offset paths from chains.

import math
import s2g_debug as dbg
import s2g_geometry as geo

s2g_paths_stamp = "s2g_paths.py: 2026-06-25 - 2100"

# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


class Move:

    def __init__(self, mid, seg, tradius):
        self.mid = mid
        seg.moveid = mid
        self.sid = seg.sid
        self.type = seg.type
        self.segpt1 = seg.pt1
        self.segpt2 = seg.pt2
        self.normal = seg.normal_angle
        self._offsets(tradius)
        self.endpt1 = [-999.0, -999.0]
        self.endpt2 = [-999.0, -999.0]
        self.eid = None
        self.arc_center = None
        self.arc_rotation = None
        self.arc_I = None
        self.arc_J = None
        self.error_flags = ''

    def _offsets(self, dist):
        ox = math.cos(self.normal) * dist
        oy = math.sin(self.normal) * dist
        self.offpt1 = (self.segpt1.tx + ox, self.segpt1.ty + oy)
        self.offpt2 = (self.segpt2.tx + ox, self.segpt2.ty + oy)

    def has_error(self):
        return bool(self.error_flags)

    def dump(self):
        if not dbg.debug_enabled():
            return
        if self.type != 'L':
            return
        dbg.log(f"LN  {self.endpt1[0]:.3f} {self.endpt1[1]:.3f} "
                f"{self.endpt2[0]:.3f} {self.endpt2[1]:.3f} #ff0000 {self.sid}  {self.mid}", True)

    def __repr__(self):
        return (f"Move(sid={self.sid}, type={self.type!r}, "
                f"flags={self.error_flags!r})")


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

class Path:

    def __init__(self, pid, ochain, tradius):
        self.pathid = pid
        ochain.pathid = pid
        self.cid = ochain.cid
        self.ochain = ochain
        self.tradius = tradius
        self.type = ochain.type
        self.area = ochain.area
        self.closed = ochain.closed
        self.movect = 0
        self.move_dict = {}

    def build_moves(self):
        first_sid = self.ochain.first_seg_ref.sid
        seg = self.ochain.first_seg_ref
        while True:
            seg.dump()
            self.movect += 2
            omove = Move(self.movect, seg, self.tradius)
            seg.move_ref = omove
            self.move_dict[omove.mid] = omove
            seg = seg.next_seg
            if seg.sid == first_sid:
                break

    def calc_endpoints(self):
        ofirst = None
        for omove in self.move_dict.values():
            if ofirst is None:
                ofirst = omove
            nextid = omove.mid + 2
            if nextid in self.move_dict:
                onext = self.move_dict.get(nextid)
            else:
                onext = ofirst
            self.resolve_corner(omove, onext)
        for omove in self.move_dict.values():
            omove.dump()

    def _corner_point(self, omove, onext, nt):
        tool_diameter = self.tradius * 2.0

        pt = geo.line_intersect(
            omove.offpt1[0], omove.offpt1[1],
            omove.offpt2[0], omove.offpt2[1],
            onext.offpt1[0], onext.offpt1[1],
            onext.offpt2[0], onext.offpt2[1])

        if pt is not None and (
                min(omove.offpt1[0], omove.offpt2[0]) <= pt[0] <= max(omove.offpt1[0], omove.offpt2[0]) and
                min(omove.offpt1[1], omove.offpt2[1]) <= pt[1] <= max(omove.offpt1[1], omove.offpt2[1])):
            omove.endpt2 = pt
            onext.endpt1 = pt
            return
        if pt is not None and math.hypot(pt[0] - omove.offpt2[0],
                                         pt[1] - omove.offpt2[1]) <= (tool_diameter * 0.75):
            omove.endpt2 = pt
            onext.endpt1 = pt
            return

        half_nt = math.radians(nt / 2.0)
        bx = math.cos(omove.normal + half_nt)
        by = math.sin(omove.normal + half_nt)

        corner_x, corner_y = omove.segpt2.tx, omove.segpt2.ty
        px = corner_x + 0.6 * self.tradius * bx
        py = corner_y + 0.6 * self.tradius * by

        perp_x, perp_y = -by, bx
        p1x = px - perp_x
        p1y = py - perp_y
        p2x = px + perp_x
        p2y = py + perp_y

        end_pt = geo.line_intersect(
            omove.offpt1[0], omove.offpt1[1],
            omove.offpt2[0], omove.offpt2[1],
            p1x, p1y, p2x, p2y)
        if end_pt is None:
            end_pt = omove.offpt2

        start_pt = geo.line_intersect(
            onext.offpt1[0], onext.offpt1[1],
            onext.offpt2[0], onext.offpt2[1],
            p1x, p1y, p2x, p2y)
        if start_pt is None:
            start_pt = onext.offpt1

        omove.endpt2 = end_pt
        onext.endpt1 = start_pt

    def resolve_corner(self, omove, onext):
        d1x, d1y = geo.unit_vector(omove.segpt1.tx, omove.segpt1.ty,
                                   omove.segpt2.tx, omove.segpt2.ty)
        d2x, d2y = geo.unit_vector(onext.segpt1.tx, onext.segpt1.ty,
                                   onext.segpt2.tx, onext.segpt2.ty)
        nt = geo.normalized_turn(d1x, d1y, d2x, d2y)
        self._corner_point(omove, onext, nt)

    def __repr__(self):
        return (f"Path(cid={self.cid}, type={self.type!r}, "
                f"closed={self.closed}, area={self.area:.2f})")

    def find_arc(self, oarc):
        next_mid = 0
        while True:
            arc_move = oarc.detect(self, next_mid)
            if arc_move is None:
                break
            self.move_dict[arc_move.mid] = arc_move
            self.move_dict = dict(sorted(self.move_dict.items()))
            next_mid = arc_move.eid

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

class Paths:

    def __init__(self, oChains, oConfig):
        self.oChains = oChains
        self.oConfig = oConfig
        self.path_dict = {}
        self.pathct = 0
        self.any_errors = False

    def create_paths(self):
        tool_radius = self.oConfig.tool_radius

        for ochain in self.oChains.sorted_by_area():
            if not ochain.closed:
                continue
            self.pathct += 1
            opath = Path(self.pathct, ochain, tool_radius)
            self.path_dict[opath.pathid] = opath
            opath.build_moves()

    def calc_endpoints(self):
        for opath in self.path_dict.values():
            opath.calc_endpoints()

    def sorted_by_area(self):
        aPaths = list(self.path_dict.values())
        aPaths.sort(key=lambda c: abs(c.area), reverse=True)
        return aPaths

    def find_arcs(self, oarc):
        for opath in self.path_dict.values():
            opath.find_arc(oarc)

    def refer(self, cid):
        return self.path_dict.get(cid)

    def count(self):
        return len(self.path_dict)

    def __repr__(self):
        return f"Paths(count={self.count()})"

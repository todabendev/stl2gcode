# s2g_arcs.py: 2026-09-24 - 0702
# Arc detection on resolved move_dict entries.
# Replaces old function-based arc detection entirely.
# Arc(oConfig) -- one instance serves all paths.
# Called after Paths.calc_endpoints() via oPaths.find_arcs(oarc).

import math
import os
import s2g_debug as dbg
import s2g_geometry as geo
from s2g_paths import Move

s2g_arcs_stamp = "s2g_arcs.py: 2026-09-24 - 0702"

if os.environ.get("dbgclaude", "").upper() == "Y":
    print(s2g_arcs_stamp)

ARC_ANGLE_TOL = 0.01        # radians -- tolerance for normal delta consistency
ARC_MIN_RUN   = 3           # minimum moves to qualify as an arc
ARC_CENTER_MIN = 5          # minimum moves to use best-separation strategy
ARC_DRILL_TOL  = 0.10       # +/- 10% of tool diameter for drill classification
GRBL_RADIUS_TOL = 0.005     # GRBL constraint: |start-center| == |end-center|


# ---------------------------------------------------------------------------
# Angle helpers
# Normal angles come from atan2 and lie in (-pi, pi]. Only differences
# between neighboring normals are wrapped; stored normals are never changed.
# ---------------------------------------------------------------------------

def angle_delta(a, b):
    """Return a - b reduced to (-pi, pi]."""
    d = a - b
    return math.atan2(math.sin(d), math.cos(d))


def angle_mean(a, b):
    """Return the mean direction of angles a and b (wrap-safe)."""
    return math.atan2(math.sin(a) + math.sin(b), math.cos(a) + math.cos(b))


# ---------------------------------------------------------------------------
# Arc
# ---------------------------------------------------------------------------

class Arc:

    def __init__(self, oConfig):
        self.oConfig = oConfig

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def detect(self, opath, start_mid=0):
        """
        Scan opath.move_dict from start_mid for the first qualifying arc run.
        Returns a new Move (type 'A', 'H', or 'D') or None.
        Consumed moves are marked type '-'.
        """
        moves = self._active_moves(opath, start_mid)
        if len(moves) < ARC_MIN_RUN:
            return None

        run = self._find_run(moves)
        if run is None:
            return None

        center = self._compute_center(run)
        if center is None:
            return None

        first = run[0]
        last  = run[-1]
        rotation = self._arc_rotation(run)
        avg_normal = angle_mean(run[-1].normal, run[0].normal)

        all_consumed = (len(run) == len(moves))

        if all_consumed and opath.type in ('Interior', 'Hole', 'Drill'):
            # Hole/Drill: radius is taken from the source outline.
            p1 = (first.segpt1.tx, first.segpt1.ty)
            p2 = (last.segpt2.tx,  last.segpt2.ty)
            center = self._adjust_center(center, p1, p2)
            radius = math.hypot(p1[0] - center[0], p1[1] - center[1])
            arc_move = self._make_hole_move(run, center, radius, opath)
        else:
            # Arc: the GCode is written from the offset endpoints, so the
            # center must be equidistant from those points, not the outline.
            p1 = (first.endpt1[0], first.endpt1[1])
            p2 = (last.endpt2[0],  last.endpt2[1])
            center = self._adjust_center(center, p1, p2, force=True)
            radius = math.hypot(p1[0] - center[0], p1[1] - center[1])
            arc_move = self._make_arc_move(run, center, radius, rotation,
                                           avg_normal, opath)

        for omove in run:
            omove.type = '-'

        return arc_move

    # -----------------------------------------------------------------------
    # Private -- run finding
    # -----------------------------------------------------------------------

    def _active_moves(self, opath, start_mid):
        """Return ordered list of moves with type not '-' or 'A', from start_mid."""
        result = []
        for mid, omove in opath.move_dict.items():
            if mid < start_mid:
                continue
            if omove.type in ('-', 'A', 'H', 'D'):
                continue
            result.append(omove)
        return result

    def _find_run(self, moves):
        """
        Find the first run of ARC_MIN_RUN or more consecutive moves with
        consistent non-zero normal angle delta within max_arc_angle.
        Returns the run as a list of Move objects, or None.
        """
        n = len(moves)
        i = 0
        while i <= n - ARC_MIN_RUN:
            delta = angle_delta(moves[i + 1].normal, moves[i].normal)
            if abs(delta) < ARC_ANGLE_TOL:
                i += 1
                continue
            if abs(delta) > self.oConfig.max_arc_angle + ARC_ANGLE_TOL:
                i += 1
                continue
            run = [moves[i], moves[i + 1]]
            j = i + 2
            while j < n:
                next_delta = angle_delta(moves[j].normal, moves[j - 1].normal)
                if abs(next_delta - delta) <= ARC_ANGLE_TOL:
                    run.append(moves[j])
                    j += 1
                else:
                    break
            if len(run) >= ARC_MIN_RUN:
                return run
            i += 1
        return None

    # -----------------------------------------------------------------------
    # Private -- center computation
    # -----------------------------------------------------------------------

    def _compute_center(self, run):
        """
        Compute arc center from normal-line intersections.
        For ARC_CENTER_MIN or more moves: use the pair with largest angular
        separation among interior moves.
        For shorter runs: average all pairwise intersections.
        Interior segment length established from equal-length middle moves.
        End moves use synthetic midpoint anchor.
        """
        n = len(run)
        interior_len = self._interior_seg_length(run)

        if n >= ARC_CENTER_MIN:
            # Use interior moves only (skip first and last)
            interior = run[1:-1]
            best_a, best_b = self._best_pair(interior)
            pt = self._normal_line_intersect(best_a, best_b, interior_len, run)
            return pt
        else:
            # Average all pairwise intersections
            pts = []
            for a in range(n):
                for b in range(a + 1, n):
                    pt = self._normal_line_intersect(
                        run[a], run[b], interior_len, run)
                    if pt is not None:
                        pts.append(pt)
            if not pts:
                return None
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            return (cx, cy)

    def _interior_seg_length(self, run):
        """
        Return the length of interior (equal-length) segments.
        Uses the median of middle moves if run is long enough,
        otherwise uses the longest segment as reference.
        """
        if len(run) >= 5:
            middle = run[2:-2]
        elif len(run) >= 3:
            middle = run[1:-1]
        else:
            middle = run
        lengths = [math.hypot(m.segpt2.tx - m.segpt1.tx,
                              m.segpt2.ty - m.segpt1.ty) for m in middle]
        lengths.sort()
        return lengths[len(lengths) // 2]

    def _best_pair(self, moves):
        """Return the pair of moves with the largest difference in normal angle."""
        best_sep = -1.0
        best_a = moves[0]
        best_b = moves[-1]
        n = len(moves)
        for i in range(n):
            for j in range(i + 1, n):
                sep = abs(angle_delta(moves[j].normal, moves[i].normal))
                if sep > best_sep:
                    best_sep = sep
                    best_a = moves[i]
                    best_b = moves[j]
        return best_a, best_b

    def _anchor(self, omove, interior_len, run):
        """
        Return the normal-line anchor point for omove.
        End moves (first or last in run) use synthetic midpoint.
        Interior moves use actual midpoint.
        """
        is_end = (omove is run[0] or omove is run[-1])
        if is_end:
            seg_len = math.hypot(omove.segpt2.tx - omove.segpt1.tx,
                                 omove.segpt2.ty - omove.segpt1.ty)
            if seg_len < 1e-9:
                ax = omove.segpt1.tx
                ay = omove.segpt1.ty
            else:
                half = interior_len / 2.0
                ux = (omove.segpt2.tx - omove.segpt1.tx) / seg_len
                uy = (omove.segpt2.ty - omove.segpt1.ty) / seg_len
                ax = omove.segpt1.tx + ux * half
                ay = omove.segpt1.ty + uy * half
        else:
            ax = (omove.segpt1.tx + omove.segpt2.tx) / 2.0
            ay = (omove.segpt1.ty + omove.segpt2.ty) / 2.0
        return (ax, ay)

    def _normal_line_intersect(self, ma, mb, interior_len, run):
        """
        Intersect the normal-lines of two moves.
        Each normal-line passes through the move's anchor point
        in the direction of normal_angle.
        """
        ax, ay = self._anchor(ma, interior_len, run)
        bx, by = self._anchor(mb, interior_len, run)

        anx = math.cos(ma.normal)
        any_ = math.sin(ma.normal)
        bnx = math.cos(mb.normal)
        bny = math.sin(mb.normal)

        return geo.line_intersect(
            ax, ay,
            ax + anx, ay + any_,
            bx, by,
            bx + bnx, by + bny)

    # -----------------------------------------------------------------------
    # Private -- center adjustment
    # -----------------------------------------------------------------------

    def _adjust_center(self, center, p1, p2, force=False):
        """
        Move center along the bisector of p1 and p2 until
        |center-p1| == |center-p2|.
        force=False: only when the difference exceeds GRBL_RADIUS_TOL.
        force=True:  always, so the radii match exactly.
        """
        cx, cy = center
        r1 = math.hypot(p1[0] - cx, p1[1] - cy)
        r2 = math.hypot(p2[0] - cx, p2[1] - cy)
        if not force and abs(r1 - r2) <= GRBL_RADIUS_TOL:
            return center

        # Bisector direction: perpendicular to the chord p1->p2
        chord_x = p2[0] - p1[0]
        chord_y = p2[1] - p1[1]
        chord_len = math.hypot(chord_x, chord_y)
        if chord_len < 1e-9:
            return center

        # Bisector is perpendicular to chord, pointing from midpoint toward center
        mid_x = (p1[0] + p2[0]) / 2.0
        mid_y = (p1[1] + p2[1]) / 2.0
        perp_x = -chord_y / chord_len
        perp_y =  chord_x / chord_len

        # Project center onto bisector line through midpoint
        # New center: midpoint + t * perp where t gives equal distances
        # |new_center - p1|^2 = |new_center - p2|^2 is satisfied by any point
        # on the perpendicular bisector; find t to preserve average radius.
        t = (cx - mid_x) * perp_x + (cy - mid_y) * perp_y
        new_cx = mid_x + t * perp_x
        new_cy = mid_y + t * perp_y
        return (new_cx, new_cy)

    # -----------------------------------------------------------------------
    # Private -- rotation
    # -----------------------------------------------------------------------

    def _arc_rotation(self, run):
        """CW if normal delta is negative, CCW if positive."""
        delta = angle_delta(run[1].normal, run[0].normal)
        return 'CW' if delta < 0 else 'CCW'

    # -----------------------------------------------------------------------
    # Private -- move construction
    # -----------------------------------------------------------------------

    def _make_arc_move(self, run, center, radius, rotation, avg_normal, opath):
        """Build and return a new arc Move (type 'A')."""
        first = run[0]
        last  = run[-1]
        mid   = first.mid - 1

        omove = object.__new__(Move)
        omove.mid        = mid
        omove.sid        = first.sid
        omove.type       = 'A'
        omove.segpt1     = first.segpt1
        omove.segpt2     = last.segpt2
        omove.normal     = avg_normal
        omove.offpt1     = first.endpt1
        omove.offpt2     = last.endpt2
        omove.endpt1     = first.endpt1
        omove.endpt2     = last.endpt2
        omove.arc_center = center
        omove.arc_rotation = rotation
        omove.eid        = last.mid
        omove.error_flags = ''
        return omove

    def _make_hole_move(self, run, center, radius, opath):
        first = run[0]
        last = run[-1]
        mid = first.mid - 1

        correct_radius = radius - 2.0 * self.oConfig.tool_radius
        entry = (center[0] - correct_radius, center[1])
        rotation = self._arc_rotation(run)
        avg_normal = angle_mean(run[-1].normal, run[0].normal)

        tool_diameter = self.oConfig.tool_radius * 2.0
        diameter = radius * 2.0
        if abs(diameter - tool_diameter) / tool_diameter <= ARC_DRILL_TOL:
            move_type = 'D'
        else:
            move_type = 'H'

        omove = object.__new__(Move)
        omove.mid = mid
        omove.sid = first.sid
        omove.type = move_type
        omove.segpt1 = first.segpt1
        omove.segpt2 = last.segpt2
        omove.normal = avg_normal
        omove.offpt1 = entry
        omove.offpt2 = entry
        omove.endpt1 = entry
        omove.endpt2 = entry
        omove.arc_center = center
        omove.arc_rotation = rotation
        omove.arc_I = correct_radius
        omove.arc_J = 0.0
        omove.eid = last.mid
        omove.error_flags = ''
        return omove
    def __repr__(self):
        return "Arc()"

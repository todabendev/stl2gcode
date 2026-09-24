# s2g_points.py: 2026-05-31 - 1219
# Point and Points classes for CNC Router CAM Pipeline.
# No dependencies on other pipeline modules.

import math
import s2g_debug as dbg

s2g_points_stamp = "s2g_points.py: 2026-05-31 - 1219"

# ---------------------------------------------------------------------------
# Point
# ---------------------------------------------------------------------------


class Point:

    def __init__(self, pid, x, y):
        self.pid = pid
        self.ox = x
        self.oy = y
        self.tx = x      # transformed x (set by translate_rotate)
        self.ty = y      # transformed y (set by translate_rotate)
        self.seg_arr = []     # segment IDs touching this point
        self.done = False
        self.center_of = None   # sid if this is an arc center point

    def match(self, testx, testy, tolerance):
        """True if (tx, ty) is within tolerance of this point."""
        return abs(testx - self.ox) <= tolerance and abs(testy - self.oy) <= tolerance

    def add_seg_end(self, sid):
        """Record that segment sid touches this point."""
        if sid not in self.seg_arr:
            self.seg_arr.append(sid)

    def dump(self, method_name, is_start):
        """Format point state and send to debug log."""
        s = (f"P\t{method_name:<20s}"
             f"\tpid={dbg.fi(self.pid)}"
             f"\tx={dbg.ff(self.ox)}\ty={dbg.ff(self.oy)}"
             f"\tseg_arr={dbg.flist(self.seg_arr)}"
             f"\tdone={self.done}")
        dbg.log(s, is_start)

#    @dbg.trace()
    def remove_seg_end(self, sid):
        """
        Remove sid from seg_arr.
        If seg_arr becomes empty, mark done and remove from owner (Points).
        owner must be the Points instance that holds this point.
        """
        if sid in self.seg_arr:
            self.seg_arr.remove(sid)
        if not self.seg_arr:
            self.done = True

    def degree(self):
        """Number of segments currently referencing this point."""
        return len(self.seg_arr)

    def __repr__(self):
        return (f"Point(pid={self.pid}, x={self.ox:.3f}, y={self.oy:.3f}, "
                f"seg_arr={self.seg_arr}, done={self.done})")

# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------

class Points:
    """
    Collection of Point objects, indexed by pid.

    point_dict  -- dict of (int pid -> Point)
    pointct     -- monotonically increasing counter; used as next pid.
                   Never reset; provides stable IDs for debugging.

    The dictionary is an index for lookup and construction only.
    Points are removed from point_dict when consumed (seg_arr empty),
    but the Point objects live on via Segment references.
    """

    def __init__(self, config):
        self._config = config
        self.tol = config.cnc_tolerance
        self.pointct = 0
        self.point_dict = {}        # pid -> Point
        self.origMinX = 999999.0
        self.origMaxX = -999999.0
        self.origMinY = 999999.0
        self.origMaxY = -999999.0
        self.newMinX = 999999.0
        self.newMaxX = -999999.0
        self.newMinY = 999999.0
        self.newMaxY = -999999.0
        self.XboundOK = True
        self.YboundOK = True

    def findadd(self, x, y):
        """
        Find an existing point within tolerance of (x, y) and return its pid.
        If none found, create a new Point and return its pid.
        """
        for pt in self.point_dict.values():
            if pt.match(x, y, self.tol):
                return pt.pid
        self.pointct += 1
        pid = self.pointct
        self.point_dict[pid] = Point(pid, x, y)
        self.origMinX = min(self.origMinX, x)
        self.origMaxX = max(self.origMaxX, x)
        self.origMinY = min(self.origMinY, y)
        self.origMaxY = max(self.origMaxY, y)
        return pid

    def translate_rotate(self):
        translate_x = 0.0
        translate_y = 0.0
        rotcos = 1.0
        rotsin = 0.0
        rotatept = False

        if self._config.rotate_deg != 0.0:
            rotatept = True
            rotcos = math.cos(math.radians(self._config.rotate_deg))
            rotsin = math.sin(math.radians(self._config.rotate_deg))

        if self._config.translate_x is None:
            margin = self._config.tool_diameter + 0.1
            translate_x = -self.origMinX + margin
        else:
            translate_x = self._config.translate_x

        if self._config.translate_y is None:
            margin = self._config.tool_diameter + 0.1
            translate_y = -self.origMinY + margin
        else:
            translate_y = self._config.translate_y

        for pt in self.point_dict.values():
            pt.tx = ((pt.ox * rotcos) - (pt.oy * rotsin)) + translate_x
            pt.ty = ((pt.ox * rotsin) + (pt.oy * rotcos)) + translate_y
            self.newMinX = min(self.newMinX, pt.tx)
            self.newMaxX = max(self.newMaxX, pt.tx)
            self.newMinY = min(self.newMinY, pt.ty)
            self.newMaxY = max(self.newMaxY, pt.ty)

        print(f"  X: {self.newMinX:.3f} to {self.newMaxX:.3f}   Y: {self.newMinY:.3f} to {self.newMaxY:.3f} ")
        print(f"  X: {(self.newMinX/25.4):.3f} to {(self.newMaxX/25.4):.3f}   Y: {(self.newMinY/25.4):.3f} to {(self.newMaxY/25.4):.3f} ")

    def boundscheck(self):
        if (self.newMinX < 0.0
                or self.newMaxX > self._config.machine_x
                or self.newMaxX > self._config.workpiece_x):
            self.XboundOK = False
            print(f"  X: part={self.newMinX:.3f} to {self.newMaxX:.3f}  workpiece={self._config.workpiece_x:.3f}  machine={self._config.machine_x:.3f}")
        if (self.newMinY < 0.0
                or self.newMaxY > self._config.machine_y
                or self.newMaxY > self._config.workpiece_y):
            self.YboundOK = False
            print(f"  Y: part={self.newMinY:.3f} to {self.newMaxY:.3f}  workpiece={self._config.workpiece_y:.3f}  machine={self._config.machine_y:.3f}")
        return self.XboundOK and self.YboundOK

    def add_center(self, x, y, sid):
        """
        Create a center point for an arc segment.
        Center points are NOT added to point_dict -- they exist only as
        direct references on Segment.center_pt.
        Returns the new Point object.
        """
        self.pointct += 1
        pid = self.pointct
        pt = Point(pid, x, y)
        pt.center_of = sid
        return pt

    def refer(self, pid):
        """Return Point for pid, or None if not in dict."""
        return self.point_dict.get(pid)

    def count(self):
        return len(self.point_dict)

    def __repr__(self):
        return f"Points(count={self.count()}, pointct={self.pointct})"

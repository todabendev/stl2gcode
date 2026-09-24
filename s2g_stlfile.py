# s2g_stlfile.py: 2026-05-30 - 1630
# STL file reader for CNC Router CAM Pipeline.
# Parses binary STL, extracts Z=0 boundary edges,
# deduplicates points, and builds Points and Segments objects.
# No dependencies beyond s2g_points, s2g_segments, and s2g_debug.

import struct
import math
# import s2g_debug as dbg

s2g_stlfile_stamp = "s2g_stlfile.py: 2026-05-30 - 1630"


class StlFile:
    """
    Parse a binary STL file and build Points and Segments objects.

    filepath      -- path to the .stl file
    tolerance     -- coordinate snap tolerance (from config.cnc_tolerance)
    tri_count     -- number of triangles read from STL header
    seg_count     -- number of Z=0 edges extracted before deduplication
    points_obj    -- Points instance (populated after read())
    segments_obj  -- Segments instance (populated after read())

    Usage:
        stl = StlFile(filepath, tolerance)
        if stl.read():
            points_obj   = stl.points_obj
            segments_obj = stl.segments_obj
        else:
            for e in stl.errors:
                print(e)
    """

    def __init__(self, config, oPoints, oSegments):
        self._config = config
        self.filepath = config.stl_file
#        self.tolerance = config.cnc_tolerance
        self._fh = None
        self.tri_count = 0
        self.seg_count = 0
        self.points = oPoints
        self.segments = oSegments
        self._errors = []
        self.triangle = Triangle(config.cnc_tolerance)

    # ------------------------------------------------------------------
    # STL parser -- binary format only
    # ------------------------------------------------------------------
    def _open(self):
        """
        Open STL file, read and discard 80-byte header,
        read and unpack triangle count into self.tri_count.
        Stores file handle in self._fh.
        Returns True on success, False on error.
        """
        try:
            self._fh = open(self.filepath, "rb")
            self._fh.read(80)  # header, ignored
            count_bytes = self._fh.read(4)
            if len(count_bytes) < 4:
                self._errors.append(
                    f"STL file too short: {self.filepath}")
                self._fh.close()
                self._fh = None
                return False
            self.tri_count = struct.unpack("<I", count_bytes)[0]
            return True
        except OSError as exc:
            self._errors.append(f"Cannot open STL: {exc}")
            self._fh = None
            return False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def read_file(self):
        if not self._open():
            return False

        for _ in range(self.tri_count):
            if self._read_triangle():
                self._save_segment(self.triangle)
        self._fh.close()
        self._fh = None
        return len(self._errors) == 0

    def _read_triangle(self):
        """
        Read one 50-byte triangle record from self._fh.
        Returns flat tuple (nx, ny, nz, x0, y0, z0, x1, y1, z1, x2, y2, z2)
        or None at EOF or on short read.
        """
        data = self._fh.read(50)
        if len(data) < 50:
            return None
        self.triangle.reset()
        floats = struct.unpack("<12f", data[:48])
        self.triangle.a_point(floats[3], floats[4], floats[5])
        self.triangle.a_point(floats[6], floats[7], floats[8])
        self.triangle.a_point(floats[9], floats[10], floats[11])
        if self.triangle.ptct != 2:
            return False
        self.triangle.a_normal(floats[0], floats[1])
        return True

    def _save_segment(self, triangle):
        """
        Deduplicate points and build Segments from raw edge list.
        Skips zero-length edges (both endpoints the same point).
        Populates self.points_obj and self.segments_obj.
        """
        pid1 = self.points.findadd(triangle.p1x, triangle.p1y)
        pid2 = self.points.findadd(triangle.p2x, triangle.p2y)
        pt1 = self.points.refer(pid1)
        pt2 = self.points.refer(pid2)
        sid = self.segments.new_segment(pt1, pt2, triangle.ang)
        pt1.add_seg_end(sid)
        pt2.add_seg_end(sid)

    @property
    def ready(self):
        return (len(self._errors) == 0
                and self.points is not None
                and self.segments is not None)

    @property
    def errors(self):
        return list(self._errors)

    def print_errors(self):
        for e in self._errors:
            print(f"  ERROR: {e}")


class Triangle:

    def __init__(self, tol):
        self.ptct = 0
        self.p1x = 0.0
        self.p1y = 0.0
        self.p2x = 0.0
        self.p2y = 0.0
        self.ang = 0.0
        self.tol = tol

    def reset(self):
        self.ptct = 0
        self.p1x = 0.0
        self.p1y = 0.0
        self.p2x = 0.0
        self.p2y = 0.0
        self.ang = 0.0

    def a_point(self, x, y, z):
        if math.fabs(z) < self.tol:
            self.ptct += 1
            if self.ptct == 1:
                self.p1x = x
                self.p1y = y
            elif self.ptct == 2:
                self.p2x = x
                self.p2y = y

    def a_normal(self, x, y):
        self.ang = math.atan2(y, x)

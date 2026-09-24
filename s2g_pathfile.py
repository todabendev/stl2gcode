# s2g_pathfile.py: 2026-09-24 - 1133
# Path file I/O for CNC Router CAM Pipeline.
# Used by s2g_app.py (writer) and s2g_generate.py (reader).

import math
import os
from datetime import datetime
from s2g_paths import Paths

s2g_pathfile_stamp = "s2g_pathfile.py: 2026-09-24 - 1133"

if os.environ.get("dbgclaude", "").upper() == "Y":
    print(s2g_pathfile_stamp)

# ---------------------------------------------------------------------------
# PathFileWriter
# ---------------------------------------------------------------------------


class PathFileWriter:

    def __init__(self, oConfig):
        self._config = oConfig
        self.filepath = oConfig.path_file
        self.seg_source = oConfig.seg_file

    def write(self, opaths):
        ordered  = opaths.sorted_by_area()
        interior = [c for c in ordered if c.type != 'Exterior']
        exterior = [c for c in ordered if c.type == 'Exterior']
        to_write = interior + exterior

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        counter = 1

        try:
            with open(self.filepath, "w", newline="\n") as fh:
                fh.write(f"# Path file created by s2g_paths\n")
                fh.write(f"# Source : {self.seg_source}\n")
                fh.write(f"# Created: {now}\n")
                fh.write(f"# Paths  : {len(to_write)}  "
                         f"(Interior: {len(interior)}  "
                         f"Exterior: {len(exterior)})\n")
                fh.write(f"# Note   : ## comments may be added manually "
                         f"after any + marker line\n")

                for opath in to_write:
                    fh.write(f"+{opath.type} {counter}\n")
                    self._write_chain(fh, opath)
                    fh.write(f"-End {counter}\n")
                    counter += 1

        except OSError as exc:
            print(f"ERROR: cannot write path file: {exc}")
            return False
        return True

    def _write_chain(self, fh, opath):
        # Part outline: one _ line per source point, in chain order.
        # L and - moves are the original segments; A/H/D moves are added.
        for omove in opath.move_dict.values():
            if omove.type in ('L', '-'):
                fh.write(f"_\t{omove.segpt1.tx:.3f}\t{omove.segpt1.ty:.3f}\n")
        for omove in opath.move_dict.values():
            prefix = f"#{omove.error_flags}" if omove.has_error() else ""
            if omove.type == 'L':
                self._write_l(fh, omove, prefix)
            elif omove.type == 'A':
                self._write_a(fh, omove, prefix)
            elif omove.type == 'H':
                self._write_h(fh, omove, prefix)
            elif omove.type == 'D':
                self._write_d(fh, omove, prefix)
            elif omove.type == '-':
                self._write_skip(fh, omove, prefix)

    def _write_l(self, fh, omove, prefix):
        x, y = omove.segpt1.tx, omove.segpt1.ty
        nx = math.cos(omove.normal)
        ny = math.sin(omove.normal)
        ox, oy = omove.endpt1
        ex, ey = omove.endpt2
        fh.write(f"{prefix}L\t{x:.3f}\t{y:.3f}\t"
                 f"{nx:.6f}\t{ny:.6f}\t"
                 f"{ox:.3f}\t{oy:.3f}\t"
                 f"{ex:.3f}\t{ey:.3f}\n")

    def _write_a(self, fh, omove, prefix):
        sx, sy = omove.endpt1
        ex, ey = omove.endpt2
        cx, cy = omove.arc_center
        ii = cx - sx
        jj = cy - sy
        fh.write(f"{prefix}A\t{sx:.3f}\t{sy:.3f}\t"
                 f"{ex:.3f}\t{ey:.3f}\t"
                 f"{ii:.3f}\t{jj:.3f}\t"
                 f"{omove.arc_rotation}\n")

    def _write_h(self, fh, omove, prefix):
        ex, ey = omove.endpt1
        cx, cy = omove.arc_center
        fh.write(f"{prefix}H\t{ex:.3f}\t{ey:.3f}\t"
                 f"{cx:.3f}\t{cy:.3f}\t"
                 f"{omove.arc_I:.3f}\t{omove.arc_rotation}\n")

    def _write_d(self, fh, omove, prefix):
        ex, ey = omove.endpt1
        cx, cy = omove.arc_center
        fh.write(f"{prefix}D\t{ex:.3f}\t{ey:.3f}\t"
                 f"{cx:.3f}\t{cy:.3f}\t"
                 f"{omove.arc_I:.3f}\n")

    def _write_skip(self, fh, omove, prefix):
        ex, ey = omove.endpt2
        fh.write(f"{prefix}-\t{ex:.3f}\t{ey:.3f}\n")

# ---------------------------------------------------------------------------
# PathFileReader
# ---------------------------------------------------------------------------

class PathFileReader:

    def __init__(self, oConfig):
        self._config = oConfig
        self.filepath = oConfig.path_file

    def read(self):
        raise NotImplementedError("PathFileReader not yet implemented")

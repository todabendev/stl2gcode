# s2g_generate.py: 2026-09-24 - 1159
# CNC Router CAM Pipeline - GCode generator.
# Used by s2g_app.py.

import math
import os
from datetime import datetime

s2g_generate_stamp = "s2g_generate.py: 2026-09-24 - 1159"

if os.environ.get("dbgclaude", "").upper() == "Y":
    print(s2g_generate_stamp)

# GRBL rejects an arc (error 33) when the start and end radii differ by
# more than 0.005 mm and 0.1% of the radius. Checked with a margin.
ARC_RADIUS_CHECK = 0.002

# Safe height for the material check (test) GCode.
TEST_Z = 10.0


# ---------------------------------------------------------------------------
# Pass depth schedule
# ---------------------------------------------------------------------------

def pass_depths(cut_depth, max_depth):
    depths    = [cut_depth]
    remaining = max_depth - cut_depth
    if remaining <= 0:
        return depths

    count    = math.ceil(remaining / cut_depth)
    per_pass = round(remaining / count, 1)

    for i in range(count - 1):
        depths.append(depths[-1] + per_pass)

    depths.append(max_depth)
    return depths


# ---------------------------------------------------------------------------
# GCode helpers
# ---------------------------------------------------------------------------

def filter_spindle(lines):
    result = []
    for line in lines:
        upper = line.strip().upper()
        if any(cmd in upper for cmd in ("M3", "M4", "M5")):
            continue
        result.append(line)
    return result


def write_initial(fh, cfg, spindle=True):
    lines = list(cfg.initial_gcode)
    if not spindle:
        lines = filter_spindle(lines)
    for line in lines:
        fh.write(line + "\n")


def write_final(fh, cfg, spindle=True):
    lines = list(cfg.final_gcode)
    if not spindle:
        lines = filter_spindle(lines)
    for line in lines:
        fh.write(line + "\n")


def g0(fh, x=None, y=None, z=None):
    cmd = "G0"
    if x is not None: cmd += f" X{x:.4f}"
    if y is not None: cmd += f" Y{y:.4f}"
    if z is not None: cmd += f" Z{z:.4f}"
    fh.write(cmd + "\n")


def g1(fh, x=None, y=None, z=None, f=None):
    cmd = "G1"
    if x is not None: cmd += f" X{x:.4f}"
    if y is not None: cmd += f" Y{y:.4f}"
    if z is not None: cmd += f" Z{z:.4f}"
    if f is not None: cmd += f" F{f:.1f}"
    fh.write(cmd + "\n")


def g2(fh, x=None, y=None, i=None, j=None, f=None):
    cmd = "G2"
    if x is not None: cmd += f" X{x:.4f}"
    if y is not None: cmd += f" Y{y:.4f}"
    if i is not None: cmd += f" I{i:.4f}"
    if j is not None: cmd += f" J{j:.4f}"
    if f is not None: cmd += f" F{f:.1f}"
    fh.write(cmd + "\n")


def g3(fh, x=None, y=None, i=None, j=None, f=None):
    cmd = "G3"
    if x is not None: cmd += f" X{x:.4f}"
    if y is not None: cmd += f" Y{y:.4f}"
    if i is not None: cmd += f" I{i:.4f}"
    if j is not None: cmd += f" J{j:.4f}"
    if f is not None: cmd += f" F{f:.1f}"
    fh.write(cmd + "\n")


# ---------------------------------------------------------------------------
# Arc direction rule
# ---------------------------------------------------------------------------

def _point_side(px, py, ax, ay, bx, by):
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def arc_midpoint(sx, sy, ex, ey, cx, cy):
    sa  = math.atan2(sy - cy, sx - cx)
    ea  = math.atan2(ey - cy, ex - cx)
    mid = (sa + ea) / 2.0
    r   = math.hypot(sx - cx, sy - cy)
    m1x = cx + r * math.cos(mid)
    m1y = cy + r * math.sin(mid)
    m2x = cx + r * math.cos(mid + math.pi)
    m2y = cy + r * math.sin(mid + math.pi)
    d1 = math.hypot(m1x - sx, m1y - sy) + math.hypot(m1x - ex, m1y - ey)
    d2 = math.hypot(m2x - sx, m2y - sy) + math.hypot(m2x - ex, m2y - ey)
    if d1 <= d2:
        return m1x, m1y
    return m2x, m2y


def arc_gcode_direction(sx, sy, ex, ey, cx, cy, turn_angle=None):
    mx, my = arc_midpoint(sx, sy, ex, ey, cx, cy)
    side_c = _point_side(cx, cy, sx, sy, ex, ey)
    side_m = _point_side(mx, my, sx, sy, ex, ey)

    if abs(side_c) < 1e-9:
        if turn_angle is not None:
            return "G2" if turn_angle > 0 else "G3"
        side_m2 = _point_side(mx, my, sx, sy, ex, ey)
        return "G2" if side_m2 < 0 else "G3"

    chord_x = ex - sx
    chord_y = ey - sy
    sm_x    = mx - sx
    sm_y    = my - sy
    cross   = chord_x * sm_y - chord_y * sm_x

    if cross < 0:
        return "G2"
    else:
        return "G3"


# ---------------------------------------------------------------------------
# Write L-segment cut path
# ---------------------------------------------------------------------------

def write_cut_path(fh, opath, depths, cut_speed, plunge_speed, clearance, tol):
    moves = [m for m in opath.move_dict.values() if m.type != '-']
    if not moves:
        return

    start_x, start_y = moves[0].endpt1

    for pass_idx, depth in enumerate(depths):
        z_cut = -depth
        g0(fh, z=clearance)
        g0(fh, x=start_x, y=start_y)
        g1(fh, z=z_cut, f=plunge_speed)

        first_move = True
        for i, omove in enumerate(moves):
            onext = moves[(i + 1) % len(moves)]
            ex, ey = omove.endpt2
            feed = cut_speed if first_move else None
            first_move = False
            if omove.type == 'A':
                cx, cy = omove.arc_center
                sx, sy = omove.endpt1
                ii = cx - sx
                jj = cy - sy
                r1 = math.hypot(ii, jj)
                r2 = math.hypot(ex - cx, ey - cy)
                if abs(r1 - r2) > ARC_RADIUS_CHECK:
                    fh.write(f"; ARC REPLACED: radius mismatch "
                             f"{r1:.4f} / {r2:.4f}\n")
                    g1(fh, x=ex, y=ey, f=feed)
                elif omove.arc_rotation == 'CW':
                    g2(fh, x=ex, y=ey, i=ii, j=jj, f=feed)
                else:
                    g3(fh, x=ex, y=ey, i=ii, j=jj, f=feed)
            elif omove.type == 'H':
                if omove.arc_rotation == 'CW':
                    g2(fh, x=ex, y=ey, i=omove.arc_I, j=omove.arc_J, f=feed)
                else:
                    g3(fh, x=ex, y=ey, i=omove.arc_I, j=omove.arc_J, f=feed)
            else:
                g1(fh, x=ex, y=ey, f=feed)

            nx, ny = onext.endpt1
            if abs(ex - nx) > tol or abs(ey - ny) > tol:
                g1(fh, x=nx, y=ny)

        if pass_idx < len(depths) - 1:
            g0(fh, z=0.0)
        else:
            g0(fh, z=clearance)


# ---------------------------------------------------------------------------
# Generate class
# ---------------------------------------------------------------------------

class Generate:

    def __init__(self, cfg):
        self.cfg = cfg

    def write_gcode(self, oPaths):
        cfg          = self.cfg
        depths       = pass_depths(cfg.cut_depth, cfg.max_depth)
        cut_speed    = cfg.cut_speed
        plunge_speed = cfg.plunge_speed
        clearance    = cfg.clearance_height
        tol          = cfg.cnc_tolerance

        try:
            with open(cfg.gcode_file, "w", newline="\n") as fh:
                fh.write(f"; Generated by s2g_generate  "
                         f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                write_initial(fh, cfg, spindle=True)

                interior = [p for p in oPaths.sorted_by_area()
                            if p.type != 'Exterior']
                exterior = [p for p in oPaths.sorted_by_area()
                            if p.type == 'Exterior']

                for opath in interior:
                    if opath.has_errors() if hasattr(opath, 'has_errors') else False:
                        fh.write(f"; SKIPPED {opath.type} {opath.cid} -- has errors\n")
                        continue
                    fh.write(f"; {opath.type} {opath.cid}\n")
                    write_cut_path(fh, opath, depths,
                                   cut_speed, plunge_speed, clearance, tol)

                any_error = False
                for opath in exterior:
                    if any_error or (hasattr(opath, 'has_errors') and opath.has_errors()):
                        fh.write(f"; SKIPPED {opath.type} {opath.cid} -- has errors\n")
                        continue
                    fh.write(f"; {opath.type} {opath.cid}\n")
                    write_cut_path(fh, opath, depths,
                                   cut_speed, plunge_speed, clearance, tol)

                write_final(fh, cfg, spindle=True)

        except OSError as exc:
            print(f"ERROR: cannot write gcode file: {exc}")
            return False
        return True

    def write_test_gcode(self, oPaths, oPoints):
        """
        Material check: trace the exterior cut path with G0 moves at
        TEST_Z (offset line segments only, no arcs), then G0 to the part
        outline's MinX, MaxY. Spindle stays off.
        """
        cfg = self.cfg
        tol = cfg.cnc_tolerance

        exterior = [p for p in oPaths.sorted_by_area()
                    if p.type == 'Exterior']

        # Offset corner points in cut order. L and - moves are the
        # original segments; A/H/D moves are skipped (no arcs).
        pts = []
        if exterior:
            for omove in exterior[0].move_dict.values():
                if omove.type not in ('L', '-'):
                    continue
                for pt in (omove.endpt1, omove.endpt2):
                    x, y = pt[0], pt[1]
                    if pts and abs(x - pts[-1][0]) <= tol \
                            and abs(y - pts[-1][1]) <= tol:
                        continue
                    pts.append((x, y))
            if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) <= tol \
                    and abs(pts[0][1] - pts[-1][1]) <= tol:
                pts.pop()

        min_x = oPoints.newMinX
        max_y = oPoints.newMaxY

        try:
            with open(cfg.test_file, "w", newline="\n") as fh:
                fh.write(f"; Material check -- s2g_generate  "
                         f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                fh.write(f"; Traces exterior cut path at Z{TEST_Z:.1f}, "
                         f"ends at part MinX, MaxY "
                         f"({min_x:.4f},{max_y:.4f})\n")
                write_initial(fh, cfg, spindle=False)

                g0(fh, z=TEST_Z)
                if pts:
                    for x, y in pts:
                        g0(fh, x=x, y=y)
                    g0(fh, x=pts[0][0], y=pts[0][1])
                else:
                    fh.write("; no exterior path found\n")
                g0(fh, x=min_x, y=max_y)

                write_final(fh, cfg, spindle=False)

        except OSError as exc:
            print(f"ERROR: cannot write test gcode file: {exc}")
            return False
        return True

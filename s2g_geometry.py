# s2g_geometry.py: 2026-06-23 - 1900
# Geometry helpers and offset path computation for CNC Router CAM Pipeline.
# Used by s2g_paths.py.

import math
# import s2g_debug as dbg

s2g_geometry_stamp = "s2g_geometry.py: 2026-06-23 - 1900"

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def unit_vector(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-12: return (0.0, 0.0)
    return (dx / length, dy / length)


def rotate_vector(vx, vy, angle_deg):
    rad = math.radians(angle_deg)
    c = math.cos(rad)
    s = math.sin(rad)
    return (vx * c - vy * s, vx * s + vy * c)


def turn_angle(d1x, d1y, d2x, d2y):
    return (math.degrees(math.atan2(d2y, d2x)) -
            math.degrees(math.atan2(d1y, d1x)))


def normalized_turn(d1x, d1y, d2x, d2y):
    t = turn_angle(d1x, d1y, d2x, d2y)
    while t > 180.0: t -= 360.0
    while t < -180.0: t += 360.0
    return t


def line_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    d = ((x1 - x2) * (y3 - y4)) - ((y1 - y2) * (x3 - x4))
    if abs(d) < 1e-12: return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def point_side(px, py, ax, ay, bx, by):
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def arc_tangent_at(px, py, cx, cy):
    rx = px - cx
    ry = py - cy
    length = math.hypot(rx, ry)
    if length < 1e-12: return (1.0, 0.0)
    return (-ry / length, rx / length)


def arc_offset_point(px, py, cx, cy, offset):
    rx = px - cx
    ry = py - cy
    length = math.hypot(rx, ry)
    if length < 1e-12: return (px, py)
    scale = (length + offset) / length
    return (cx + rx * scale, cy + ry * scale)


def arc_tangent_line(px, py, cx, cy, offset):
    ox, oy = arc_offset_point(px, py, cx, cy, offset)
    tx, ty = arc_tangent_at(px, py, cx, cy)
    return (ox - tx, oy - ty, ox + tx, oy + ty)


def _arc_tangent_offset_line(px, py, cx, cy, tool_radius, interior):
    arc_off = -tool_radius if interior else tool_radius
    tx1, ty1, tx2, ty2 = arc_tangent_line(px, py, cx, cy, arc_off)
    tx, ty = arc_tangent_at(px, py, cx, cy)
    return tx1, ty1, tx2, ty2, tx, ty


# ---------------------------------------------------------------------------
# Corner resolution
# ---------------------------------------------------------------------------

def resolve_corner(corner_x, corner_y,
                   seg_ox1, seg_oy1, seg_ox2, seg_oy2,
                   nxt_ox1, nxt_oy1, nxt_ox2, nxt_oy2,
                   d1x, d1y, d2x, d2y, nx, ny,
                   tool_radius, tool_diameter, debug=False):
    ext_limit = 0.75 * tool_diameter
    nt = normalized_turn(d1x, d1y, d2x, d2y)

    ext_seg_x2 = seg_ox2 + ext_limit * d1x
    ext_seg_y2 = seg_oy2 + ext_limit * d1y
    ext_nxt_x1 = nxt_ox1 - ext_limit * d2x
    ext_nxt_y1 = nxt_oy1 - ext_limit * d2y

    pt = line_intersect(seg_ox1, seg_oy1, ext_seg_x2, ext_seg_y2,
                        ext_nxt_x1, ext_nxt_y1, nxt_ox2, nxt_oy2)

    if nt <= 0.0:
        if pt is None:
            pt = ((seg_ox2 + nxt_ox1) / 2.0, (seg_oy2 + nxt_oy1) / 2.0)
        return pt, pt

    if pt is not None:
        dist_seg = math.hypot(pt[0] - seg_ox2, pt[1] - seg_oy2)
        dist_nxt = math.hypot(pt[0] - nxt_ox1, pt[1] - nxt_oy1)
        if dist_seg <= ext_limit and dist_nxt <= ext_limit:
            return pt, pt

    return _bisector_corner(corner_x, corner_y, d1x, d1y, d2x, d2y,
                            nx, ny, tool_radius,
                            seg_ox1, seg_oy1, seg_ox2, seg_oy2,
                            nxt_ox1, nxt_oy1, nxt_ox2, nxt_oy2)


def _bisector_corner(corner_x, corner_y, d1x, d1y, d2x, d2y,
                     nx, ny, tool_radius,
                     seg_ox1, seg_oy1, seg_ox2, seg_oy2,
                     nxt_ox1, nxt_oy1, nxt_ox2, nxt_oy2):
    bx = d1x + d2x
    by = d1y + d2y
    blen = math.hypot(bx, by)
    if blen < 1e-12:
        bx, by = nx, ny
    else:
        bx /= blen
        by /= blen
        if bx * nx + by * ny < 0:
            bx = -bx
            by = -by

    px = corner_x + tool_radius * bx
    py = corner_y + tool_radius * by
    fx1 = px - by
    fy1 = py + bx
    fx2 = px + by
    fy2 = py - bx

    end_pt = line_intersect(seg_ox1, seg_oy1, seg_ox2, seg_oy2,
                            fx1, fy1, fx2, fy2)
    if end_pt is None:
        end_pt = (seg_ox2, seg_oy2)

    start_pt = line_intersect(nxt_ox1, nxt_oy1, nxt_ox2, nxt_oy2,
                              fx1, fy1, fx2, fy2)
    if start_pt is None:
        start_pt = (nxt_ox1, nxt_oy1)

    return end_pt, start_pt


# ---------------------------------------------------------------------------
# Process one chain into Move objects
# ---------------------------------------------------------------------------

def process_chain(chain, tool_radius, cfg, move_factory, debug=False):
    """
    Compute offset path for one closed chain.
    Returns list of Move objects with offset fields populated,
    or None if chain cannot be processed.
    Uses transformed coordinates (pt.tx, pt.ty) for all geometry.
    Normal direction derived from segment.normal_angle.
    move_factory: callable that accepts a Segment and returns a Move object.
    """
    tool_diameter = tool_radius * 2.0
    interior = chain.type in ('Interior', 'Hole', 'Drill')

    if debug:
        print(f"===== Chain {chain.cid}  type={chain.type}  "
              f"area={chain.area:.2f}")

    # Build active list of segments (L and A only)
    active = []
    cur = chain.first_seg_ref
    seen = set()
    while cur is not None and cur.sid not in seen:
        seen.add(cur.sid)
        if cur.type in ('L', 'A'):
            active.append(cur)
        cur = cur.next_seg

    n = len(active)
    if n < 2:
        return None

    def seg_pt(s):
        return (s.pt1.tx, s.pt1.ty)

    # Compute offset data for each segment
    offset_data = []

    for i in range(n):
        seg = active[i]
        x1, y1 = seg_pt(seg)
        x2, y2 = seg_pt(active[(i + 1) % n])

        if seg.type == 'L':
            ux, uy = unit_vector(x1, y1, x2, y2)
        else:
            ux, uy = arc_tangent_at(x1, y1,
                                    seg.center_pt.tx, seg.center_pt.ty)

        cur_nx = math.cos(seg.normal_angle)
        cur_ny = math.sin(seg.normal_angle)

        ox1 = x1 + tool_radius * cur_nx
        oy1 = y1 + tool_radius * cur_ny
        ox2 = x2 + tool_radius * cur_nx
        oy2 = y2 + tool_radius * cur_ny

        offset_data.append((ox1, oy1, ox2, oy2, ux, uy, cur_nx, cur_ny))
        seg.dump()

        if debug:
            print(f"  seg {seg.sid} type={seg.type} "
                  f"pt=({x1:.3f},{y1:.3f}) "
                  f"normal=({cur_nx:.4f},{cur_ny:.4f})")

    # Resolve corners
    path_starts = [None] * n
    path_ends = [None] * n

    for i in range(n):
        j = (i + 1) % n
        seg_i = active[i]
        seg_j = active[j]
        od_i = offset_data[i]
        od_j = offset_data[j]

        corner_x, corner_y = seg_pt(active[j])
        d1x, d1y = od_i[4], od_i[5]
        d2x, d2y = od_j[4], od_j[5]
        nx, ny = od_i[6], od_i[7]

        if seg_i.type == 'L':
            i_ox1, i_oy1 = od_i[0], od_i[1]
            i_ox2, i_oy2 = od_i[2], od_i[3]
        else:
            i_ox1, i_oy1, i_ox2, i_oy2, d1x, d1y = \
                _arc_tangent_offset_line(
                    corner_x, corner_y,
                    seg_i.center_pt.tx, seg_i.center_pt.ty,
                    tool_radius, interior)

        if seg_j.type == 'L':
            j_ox1, j_oy1 = od_j[0], od_j[1]
            j_ox2, j_oy2 = od_j[2], od_j[3]
        else:
            j_ox1, j_oy1, j_ox2, j_oy2, d2x, d2y = \
                _arc_tangent_offset_line(
                    corner_x, corner_y,
                    seg_j.center_pt.tx, seg_j.center_pt.ty,
                    tool_radius, interior)

        end_pt, start_pt = resolve_corner(
            corner_x, corner_y,
            i_ox1, i_oy1, i_ox2, i_oy2,
            j_ox1, j_oy1, j_ox2, j_oy2,
            d1x, d1y, d2x, d2y, nx, ny,
            tool_radius, tool_diameter, debug)

        path_ends[i] = end_pt
        path_starts[j] = start_pt

    # Build Move objects
    path_segs = []
    first_move = None
    last_move = None

    for i, seg in enumerate(active):
        move = move_factory(seg)
        od = offset_data[i]

        if seg.type == 'L':
            sx = path_starts[i][0] if path_starts[i] else None
            sy = path_starts[i][1] if path_starts[i] else None
            ex = path_ends[i][0] if path_ends[i] else None
            ey = path_ends[i][1] if path_ends[i] else None
            move.normal = (od[6], od[7])
            move.offset_pt = (sx, sy) if sx is not None else (od[0], od[1])
            move.offset_end = (ex, ey) if ex is not None else (od[2], od[3])
        else:  # 'A'
            move.arc_offset_start = (path_starts[i][0], path_starts[i][1]) \
                if path_starts[i] else None
            move.arc_offset_end = (path_ends[i][0], path_ends[i][1]) \
                if path_ends[i] else None

        if first_move is None:
            first_move = move
        else:
            last_move.oNext = move
            move.oPrev = last_move
        last_move = move
        path_segs.append(move)
        move.dump()

    # Close linked list
    if first_move and last_move:
        last_move.oNext = first_move
        first_move.oPrev = last_move

    return path_segs
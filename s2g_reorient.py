# s2g_reorient.py: 2026-06-26 - 1638
# STL reorientation tool for CNC Router CAM Pipeline.
# Translates and rotates an STL so a chosen point becomes the origin
# and the desired cross-section lies at Z=0.
# Interactive console dialog. Never overwrites an existing file.
# Usage: python3 s2g_reorient.py

import struct
import math
import os
import sys

s2g_reorient_stamp = "s2g_reorient.py: 2026-06-26 - 1638"


# ---------------------------------------------------------------------------
# STL I/O
# ---------------------------------------------------------------------------

def read_stl(filepath):
    """
    Read binary STL. Returns (triangles, header) where triangles is a list of
    dicts with keys: normal [nx,ny,nz], v1 [x,y,z], v2, v3.
    """
    with open(filepath, 'rb') as fh:
        header = fh.read(80)
        tri_count = struct.unpack('<I', fh.read(4))[0]
        triangles = []
        for _ in range(tri_count):
            data = struct.unpack('<12fH', fh.read(50))
            tri = {
                'normal': list(data[0:3]),
                'v1':     list(data[3:6]),
                'v2':     list(data[6:9]),
                'v3':     list(data[9:12]),
            }
            triangles.append(tri)
    return triangles, header


def write_stl(filepath, triangles, header):
    """Write binary STL."""
    with open(filepath, 'wb') as fh:
        fh.write(header.ljust(80, b'\x00')[:80])
        fh.write(struct.pack('<I', len(triangles)))
        for tri in triangles:
            fh.write(struct.pack('<12fH',
                tri['normal'][0], tri['normal'][1], tri['normal'][2],
                tri['v1'][0],     tri['v1'][1],     tri['v1'][2],
                tri['v2'][0],     tri['v2'][1],     tri['v2'][2],
                tri['v3'][0],     tri['v3'][1],     tri['v3'][2],
                0))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def translate_point(p, tx, ty, tz):
    return [p[0] + tx, p[1] + ty, p[2] + tz]


def rotate_x(p, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return [p[0],
            c * p[1] - s * p[2],
            s * p[1] + c * p[2]]


def rotate_y(p, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return [ c * p[0] + s * p[2],
             p[1],
            -s * p[0] + c * p[2]]


def rotate_z(p, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return [c * p[0] - s * p[1],
            s * p[0] + c * p[1],
            p[2]]


ROTATE_FN = {'X': rotate_x, 'Y': rotate_y, 'Z': rotate_z}


def apply_transform(triangles, origin, rotations):
    """
    origin   : [ox, oy, oz] -- subtracted from all points first
    rotations: list of (axis, angle_deg) applied in order
    Returns new list of transformed triangles.
    """
    ox, oy, oz = origin
    result = []
    for tri in triangles:
        verts  = [tri['v1'], tri['v2'], tri['v3']]
        normal = list(tri['normal'])

        # Translate to origin
        verts  = [translate_point(v, -ox, -oy, -oz) for v in verts]
        # Normal is a direction, no translation needed

        # Apply rotations in order
        for axis, deg in rotations:
            rad = math.radians(deg)
            fn  = ROTATE_FN[axis]
            verts  = [fn(v, rad) for v in verts]
            normal = fn(normal, rad)

        result.append({
            'normal': normal,
            'v1': verts[0],
            'v2': verts[1],
            'v3': verts[2],
        })
    return result


# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------

def bounding_box(triangles):
    """Returns dict with min/max/len for X, Y, Z."""
    xs = [v[0] for t in triangles for v in [t['v1'], t['v2'], t['v3']]]
    ys = [v[1] for t in triangles for v in [t['v1'], t['v2'], t['v3']]]
    zs = [v[2] for t in triangles for v in [t['v1'], t['v2'], t['v3']]]
    return {
        'X': (min(xs), max(xs), max(xs) - min(xs)),
        'Y': (min(ys), max(ys), max(ys) - min(ys)),
        'Z': (min(zs), max(zs), max(zs) - min(zs)),
    }


def print_bbox(label, bb):
    print(f"\n  {label}")
    print(f"  {'Axis':<6} {'Min':>10} {'Max':>10} {'Length':>10}")
    print(f"  {'-'*40}")
    for axis in ('X', 'Y', 'Z'):
        mn, mx, ln = bb[axis]
        print(f"  {axis:<6} {mn:>10.4f} {mx:>10.4f} {ln:>10.4f}")


# ---------------------------------------------------------------------------
# Console input helpers
# ---------------------------------------------------------------------------

def ask_float(prompt, default=None):
    """Ask for a float. Show default in brackets. Enter keeps default."""
    if default is not None:
        full_prompt = f"  {prompt} [{default:.4f}]: "
    else:
        full_prompt = f"  {prompt}: "
    while True:
        raw = input(full_prompt).strip()
        if raw == '' and default is not None:
            return default
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def ask_file(prompt, must_exist=True, must_not_exist=False, default=None):
    """Ask for a filename with optional existence checks."""
    if default is not None:
        full_prompt = f"  {prompt} [{default}]: "
    else:
        full_prompt = f"  {prompt}: "
    while True:
        raw = input(full_prompt).strip()
        if raw == '' and default is not None:
            raw = default
        if not raw:
            print("  Please enter a filename.")
            continue
        if must_exist and not os.path.isfile(raw):
            print(f"  File not found: {raw}")
            continue
        if must_not_exist and os.path.isfile(raw):
            print(f"  File already exists: {raw}  (choose a different name)")
            continue
        return raw


def ask_rotations(previous=None):
    """
    Ask for a sequence of axis/angle rotation pairs.
    previous: list of (axis, deg) from last run, shown as reminder.
    Returns list of (axis, deg).
    """
    if previous:
        print("  Previous rotations:")
        for axis, deg in previous:
            print(f"    {axis} {deg:.4f} deg")
        print("  Enter new rotations (or press Enter to finish).")
    else:
        print("  Enter rotations (axis then angle). Press Enter on axis to finish.")

    rotations = []
    while True:
        raw_axis = input("  Axis (X/Y/Z or Enter to finish): ").strip().upper()
        if raw_axis == '':
            break
        if raw_axis not in ('X', 'Y', 'Z'):
            print("  Please enter X, Y, or Z.")
            continue
        deg = ask_float("Angle (degrees)", default=0.0)
        rotations.append((raw_axis, deg))
    return rotations


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

def dialog(triangles, src_path):
    """
    Interactive dialog. Returns when user Quits.
    """
    origin    = [0.0, 0.0, 0.0]
    rotations = []
    result    = triangles

    print()
    print_bbox("Original", bounding_box(triangles))

    while True:
        print()
        print("  -- Origin (point that becomes 0,0,0) --")
        origin[0] = ask_float("Origin X", default=origin[0])
        origin[1] = ask_float("Origin Y", default=origin[1])
        origin[2] = ask_float("Origin Z", default=origin[2])

        print()
        print("  -- Rotations (applied in order entered) --")
        rotations = ask_rotations(previous=rotations if rotations else None)

        result = apply_transform(triangles, origin, rotations)
        bb_after = bounding_box(result)

        print()
        print_bbox("Original", bounding_box(triangles))
        print_bbox("After transform", bb_after)

        print()
        action = input("  (S)ave, (C)hange, (Q)uit: ").strip().upper()
        if not action:
            continue

        if action == 'Q':
            print("  Quit -- no file written.")
            break

        elif action == 'C':
            print()
            continue

        elif action == 'S':
            out_path = ask_file(
                f"Save as",
                must_exist=False,
                must_not_exist=True,
                default=None)
            _, header = triangles, b''
            # Re-read header from source for preservation
            with open(src_path, 'rb') as fh:
                src_header = fh.read(80)
            write_stl(out_path, result, src_header)
            print(f"  Written: {out_path}  ({len(result)} triangles)")
            break

        else:
            print("  Please enter S, C, or Q.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(s2g_reorient_stamp)
    print("STL Reorientation Tool")
    print()

    src_path = ask_file("STL input file", must_exist=True)
    triangles, header = read_stl(src_path)
    print(f"  Read: {len(triangles)} triangles from {src_path}")

    dialog(triangles, src_path)


if __name__ == "__main__":
    main()
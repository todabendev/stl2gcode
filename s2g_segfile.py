# s2g_segfile.py: 2026-05-29 - 1257
# Segment file reader and writer for CNC Router CAM Pipeline.
# Imports Points from s2g_points, Segments from s2g_segments,
# Chain and Chains from s2g_chains.
# Used by s2g_app.py.
import math
from datetime import datetime
from s2g_points import Points
from s2g_segments import Segments
from s2g_chains import Chain, Chains

s2g_segfile_stamp = "s2g_segfile.py: 2026-05-29 - 1257"


# ---------------------------------------------------------------------------
# SegFileWriter
# ---------------------------------------------------------------------------

class SegFileWriter:
    """
    Writes a segment file from a Chains object.

    Usage:
        writer = SegFileWriter(filepath, stl_source)
        writer.write(chains_obj)
    """

    def __init__(self, config):
        self._config = config
        self.filepath = config.seg_file
        self.stl_source = config.stl_file

    def write(self, chains_obj):
        """
        Write segment file. Chains must have types assigned (assign_types
        called) and arc detection complete (Phase 3) before calling.
        Interior chains written first, Exterior last.
        Returns True on success, False on error.
        """
        ordered = chains_obj.sorted_by_area()
        # Interior first, Exterior last
        interior = [c for c in ordered if c.type != 'Exterior']
        exterior = [c for c in ordered if c.type == 'Exterior']
        to_write = interior + exterior

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        counter = 1

        try:
            with open(self.filepath, "w", newline="\n") as fh:
                fh.write(f"# Segment file created by stl2gcode_ingest\n")
                fh.write(f"# Source : {self.stl_source}\n")
                fh.write(f"# Created: {now}\n")
                fh.write(f"# Paths  : {len(to_write)}  "
                         f"(Interior: {len(interior)}  "
                         f"Exterior: {len(exterior)})\n")
                fh.write(f"# Note   : ## comments may be added manually "
                         f"after any + marker line\n")

                for chain in to_write:
                    fh.write(f"+{chain.type} {counter}\n")
                    self._write_chain(fh, chain)
                    fh.write(f"-End {counter}\n")
                    counter += 1

        except OSError as exc:
            print(f"ERROR: cannot write segment file: {exc}")
            return False
        return True

    def _write_chain(self, fh, chain):
        """Walk chain linked list and write segment lines."""
        cur = chain.first_seg_ref
        seen = set()
        while cur is not None and cur.sid not in seen:
            seen.add(cur.sid)
            if cur.is_arc():
                self._write_arc_seg(fh, cur, chain.type)
            else:
                fh.write(f"L\t{cur.pt1.ox:.3f}\t{cur.pt1.oy:.3f}\t{math.degrees(cur.normal_angle):.3f}\n")
            cur = cur.next_seg

    def _write_arc_seg(self, fh, seg, chain_type):
        """
        Write arc points and arc summary line for one arc segment.
        Walk bypassed segments from arc_start to arc_end writing _ lines,
        then write the arc summary (A, H, or D line).
        """
        # Write _ points by chasing original next_seg from arc_start

        if seg.arc_chain is not None:
            byp = seg.arc_chain.first_seg_ref
            byp_seen = set()
            while byp is not None and byp.sid not in byp_seen:
                byp_seen.add(byp.sid)
                fh.write(f"_\t{byp.pt1.ox:.3f}\t{byp.pt1.oy:.3f}\n")
                if byp.pt1.pid == seg.arc_end.pid:
                    break
                byp = byp.next_seg
            # Write the arc_end point
            fh.write(f"_\t{seg.arc_end.ox:.3f}\t{seg.arc_end.oy:.3f}\n")

        cx = seg.center_pt.ox
        cy = seg.center_pt.oy

        if seg.type == 'D':
            radius = math.hypot(seg.arc_start.ox - cx,
                                seg.arc_start.oy - cy)
            fh.write(f"D\t{cx:.3f}\t{cy:.3f}\t{radius:.3f}\n")
        elif seg.type == 'H':
            px, py = seg.arc_start.ox, seg.arc_start.oy
            radius = math.hypot(px - cx, py - cy)
            fh.write(f"H\t{px:.3f}\t{py:.3f}\t"
                     f"{cx:.3f}\t{cy:.3f}\t{radius:.3f}\n")
        else:  # 'A'
            fpx, fpy = seg.arc_start.ox, seg.arc_start.oy
            fh.write(f"A\t{fpx:.3f}\t{fpy:.3f}\t{cx:.3f}\t{cy:.3f}\n")


# ---------------------------------------------------------------------------
# SegFileReader
# ---------------------------------------------------------------------------

class SegFileReader:
    """
    Reads a segment file and reconstructs Chain and Segment objects.

    Usage:
        reader = SegFileReader(filepath, tolerance)
        chains_obj, points_obj = reader.read()

    The reconstructed Chains object contains closed Chain objects with
    linked-list structure, suitable for use by stl2gcode_paths.py.
    Arc segments are reconstructed with arc_start, arc_end, center_pt.
    """

    def __init__(self, config):
        self._config = config
        self.filepath = config.seg_file
        self.tolerance = config.cnc_tolerance

    def read(self):
        """
        Parse segment file. Returns (Chains, Points) or (None, None) on error.
        """
        points_obj = Points(self._config)
        chains_obj = Chains(points_obj, None)

        try:
            with open(self.filepath, "r") as fh:
                lines = fh.readlines()
        except OSError as exc:
            print(f"ERROR: cannot read segment file: {exc}")
            return None, None

        chain = None
        seg_list = []  # flat list of parsed items per chain
        path_type = ''
        counter = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line.startswith('#'):
                continue

            if line.startswith('+'):
                # +Type N
                parts = line[1:].split()
                path_type = parts[0]
                counter = int(parts[1])
                seg_list = []
                continue

            if line.startswith('-End'):
                # Finalize chain from seg_list
                if seg_list:
                    chain = self._build_chain(
                        chains_obj, points_obj, seg_list, path_type, counter)
                seg_list = []
                path_type = ''
                continue

            seg_list.append(line)

        return chains_obj, points_obj

    @staticmethod
    def _build_chain(chains_obj, points_obj, lines, path_type, counter):
        """
        Build a Chain from a list of segment file lines.
        Returns the new Chain.
        """
        segments_obj = Segments()
        prev_pt = None
        arc_buf = []  # accumulate _ lines
        first_seg = None
        last_seg = None

        def flush_l(pt):
            """Add an L segment from prev_pt to pt."""
            nonlocal prev_pt, first_seg, last_seg
            if prev_pt is None:
                prev_pt = pt
                return
            sid = segments_obj.new_segment(prev_pt, pt, 0.0)
            seg = segments_obj.refer(sid)
            if first_seg is None:
                first_seg = seg
            else:
                last_seg.next_seg = seg
                seg.prev_seg = last_seg
            last_seg = seg
            prev_pt = pt

        def flush_arc(arc_type, cx, cy, extra):
            """Create arc segment replacing arc_buf points."""
            nonlocal prev_pt, first_seg, last_seg, arc_buf
            if not arc_buf:
                return
            arc_s = arc_buf[0]
            arc_e = arc_buf[-1]
            cpt = points_obj.add_center(cx, cy, 0)  # sid set later
            # Create arc segment from prev_pt (pre-arc) to pt after arc
            # We use arc_s as pt1 and arc_e as pt2 for the arc segment
            sid = segments_obj.new_segment(arc_s, arc_e, 0.0)
            seg = segments_obj.refer(sid)
            seg.type = arc_type
            seg.arc_start = arc_s
            seg.arc_end = arc_e
            seg.center_pt = cpt
            cpt.center_of = sid
            # Build bypassed chain among arc_buf points
            seg.arc_chain = None
            if len(arc_buf) > 1:
                # Create minimal segment objects for bypassed chain
                bp_prev = None
                bp_first = None
                for k in range(len(arc_buf) - 1):
                    bsid = segments_obj.new_segment(arc_buf[k], arc_buf[k + 1], None)
                    bseg = segments_obj.refer(bsid)
                    if bp_first is None:
                        bp_first = bseg
                    if bp_prev is not None:
                        bp_prev.next_seg = bseg
                        bseg.prev_seg = bp_prev
                    bp_prev = bseg
                seg.arc_chain = bp_first
                chains_obj.add_sub_chain(seg)
            if first_seg is None:
                first_seg = seg
            else:
                last_seg.next_seg = seg
                seg.prev_seg = last_seg
            last_seg = seg
            prev_pt = arc_e
            arc_buf = []

        for line in lines:
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]

            if tag == 'L':
                x, y = float(parts[1]), float(parts[2])
                ang = math.radians(float(parts[3]))
                pid = points_obj.findadd(x, y)
                pt = points_obj.refer(pid)
                flush_l(pt)

            elif tag == '_':
                x, y = float(parts[1]), float(parts[2])
                pid = points_obj.findadd(x, y)
                pt = points_obj.refer(pid)
                arc_buf.append(pt)

            elif tag == 'A':
                # A fpx fpy cx cy
                cx, cy = float(parts[3]), float(parts[4])
                flush_arc('A', cx, cy, None)

            elif tag == 'H':
                # H px py cx cy radius
                cx, cy = float(parts[3]), float(parts[4])
                flush_arc('H', cx, cy, None)

            elif tag == 'D':
                # D cx cy radius
                cx, cy = float(parts[1]), float(parts[2])
                flush_arc('D', cx, cy, None)

            elif tag == '#D':
                cx, cy = float(parts[1]), float(parts[2])
                flush_arc('D', cx, cy, 'error')

        # Close the chain by linking last to first
        if first_seg is not None and last_seg is not None:
            last_seg.next_seg = first_seg
            first_seg.prev_seg = last_seg

            chains_obj.chainct += 1
            cid = chains_obj.chainct
            chain = Chain(cid, first_seg)
            chain.type = path_type
            chain.closed = True
            chain.area = chain._compute_area()
            chains_obj.chain_dict[cid] = chain
            return chain

        return None

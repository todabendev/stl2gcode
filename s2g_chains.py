# s2g_chains.py:
# Chain, Chains
# Imports Point and Points from stl2gcode_points.
# Used by s2g_app.py.

# import math
# import s2g_debug as dbg

# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------
def link_segments(seg_a, seg_b):
    """
    Link seg_a (as predecessor) to seg_b (as successor).
    Precondition: seg_a.pt2.pid == seg_b.pt1.pid
    """
    seg_a.next_seg = seg_b
    seg_b.prev_seg = seg_a


def join_chains(chain_a, chain_b):
    """
    Append chain_b to chain_a.
    Precondition: chain_a.end_pt.pid == chain_b.start_pt.pid
    Updates chain_a last references and end_pt.
    Sets chain_a.closed if endpoints match after join.
    """
    link_segments(chain_a.last_seg_ref, chain_b.first_seg_ref)
    chain_a.last_seg_ref = chain_b.last_seg_ref
    chain_a.last_sid = chain_b.last_sid
    chain_a.end_pt = chain_b.end_pt
    if chain_a.start_pt.pid == chain_a.end_pt.pid:
        chain_a.closed = True


class Chain:

    def __init__(self, cid, seg):
        self.cid = cid
        seg.chainid = cid
        self.first_sid = seg.sid
        self.first_seg_ref = seg       # direct ref, independent of seg_dict
        self.last_sid = seg.sid
        self.last_seg_ref = seg       # direct ref, independent of seg_dict
        self.start_pt = seg.pt1   # Point reference
        self.end_pt = seg.pt2   # Point reference
        self.closed = False
        self.type = ''
        self.area = 0.0   # accumulated as segments are added
        self.is_subchain = False
        self.pathid = None
        seg.pt1.remove_seg_end(seg.sid)
        seg.pt2.remove_seg_end(seg.sid)

    # @classmethod
    # def from_subchain(cls, cid, first_seg, last_seg, area):
    #     chain = cls.__new__(cls)
    #     chain.cid = cid
    #     chain.first_sid = first_seg.sid
    #     chain.first_seg_ref = first_seg
    #     chain.last_sid = last_seg.sid
    #     chain.last_seg_ref = last_seg
    #     chain.start_pt = first_seg.pt1
    #     chain.end_pt = last_seg.pt2
    #     chain.closed = False
    #     chain.type = ''
    #     chain.area = 0.0
    #     chain.is_subchain = True
    #     return chain

    def extend(self, osegments):
        """
        Extend chain by one segment from an open end.
        Returns True if a segment was added, False if no extension possible.
        """
        while True:
            if self.start_pt.pid == self.end_pt.pid:
                self.closed = True
                self.first_seg_ref.prev_seg = self.last_seg_ref
                self.last_seg_ref.next_seg = self.first_seg_ref
                self.start_pt.remove_seg_end(self.last_seg_ref.sid)
                self.end_pt.remove_seg_end(self.first_seg_ref.sid)
                break
            if self.end_pt.degree() > 2:
                break
#            nextsid = self.end_pt.findnextsegid()
            nextsid = osegments.find_unchained_sid(self.end_pt)
            if nextsid is None:
                break
            nextseg = osegments.refer(nextsid)
            if nextseg.pid2 == self.end_pt.pid:
                nextseg.change_direction()
            nextseg.chainid = self.cid
            lastseg = self.last_seg_ref
            lastsid = lastseg.sid
            lastseg.next_seg = nextseg
            nextseg.prev_seg = lastseg
            self.last_seg_ref = nextseg
            self.last_sid = nextsid
            self.end_pt = nextseg.pt2
            lastseg.pt2.remove_seg_end(lastsid)
            nextseg.pt1.remove_seg_end(nextsid)

    def compute_area(self):
        self.area = 0.0
        segref = self.first_seg_ref
        firstid = segref.sid
        while segref is not None:
            self.area += segref.segarea()
            segref = segref.next_seg
            if segref.sid == firstid:
                break
        return self.area

    def reverse(self):
        """
        Reverse chain direction in place.
        Calls change_direction() on every segment, then swaps
        first/last and start/end references on the chain.
        area is recomputed via _compute_area() after reversal.
        """
        segs = self._seg_list()
        for seg in segs:
            seg.change_direction()
        if segs:
            old_first = self.first_seg_ref
            old_last = segs[-1]
            self.first_seg_ref = old_last
            self.first_sid = old_last.sid
            self.last_sid = old_first.sid
        self.start_pt, self.end_pt = self.end_pt, self.start_pt
#        self.area = self._compute_area()

    def append_chain(self, other):
        """
        Append chain 'other' to the end of self.
        Precondition: self.end_pt.pid == other.start_pt.pid
        Links last segment of self to first segment of other.
        Updates last_sid, last_seg_ref, end_pt.
        Area is recomputed after all joins are done.
        """
        self.last_seg_ref.next_seg = other.first_seg_ref
        other.first_seg_ref.prev_seg = self.last_seg_ref
        self.last_seg_ref = other.last_seg_ref
        self.last_sid = other.last_sid
        self.end_pt = other.end_pt

    def _seg_list(self):
        """Return ordered list of segments by walking next_seg."""
        segs = []
        cur = self.first_seg_ref
        seen = set()
        while cur is not None and cur.sid not in seen:
            seen.add(cur.sid)
            segs.append(cur)
            cur = cur.next_seg
        return segs

    def _last_seg(self):
        """Return last segment by walking next_seg."""
        cur = self.first_seg_ref
        seen = set()
        while cur.next_seg is not None and cur.next_seg.sid not in seen:
            seen.add(cur.sid)
            cur = cur.next_seg
        return cur

    def sign_str(self):
        if self.area > 0:
            return "CCW"
        elif self.area < 0:
            return "CW"
        return "ZERO"

    def __repr__(self):
        return (f"Chain(cid={self.cid}, type={self.type!r}, "
                f"closed={self.closed}, area={self.area:.2f})")


# ---------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------

class Chains:
    """
    Collection of Chain objects, indexed by cid.

    chain_dict  -- dict of (int cid -> Chain)
    chainct     -- monotonically increasing counter; used as next cid.
    """

    def __init__(self, opts, osegs):
        self.oPoints = opts
        self.oSegments = osegs
        self.chainct = 0
        self.chain_dict = {}    # cid -> Chain

    def build(self):
        """
        Phase 1 and 2: build closed chains from points and segments.
        Seeds chains from degree-2 points, extends, joins open fragments.
        Assigns types after all chains are closed.
        """

        while True:
            seed_seg = self.oSegments.find_seed_segment()
            if seed_seg is None:
                break
            self.chainct += 1
            chain = Chain(self.chainct, seed_seg)
            self.chain_dict[chain.cid] = chain
            chain.extend(self.oSegments)

    def refer(self, cid):
        return self.chain_dict.get(cid)

    def find_open(self):
        """Return list of open chains."""
        return [c for c in self.chain_dict.values() if not c.closed and not c.is_subchain]

    def match_open_chains(self):
        """
        Join open chain fragments into closed loops.
        Outer loop repeats until no matching pairs remain.
        """
        while True:
            open_chains = [c for c in self.chain_dict.values() if not c.closed]
            if not open_chains:
                break
            joined = False
            for chain_a in open_chains:
                for chain_b in open_chains:
                    if chain_b.cid == chain_a.cid:
                        continue
                    if chain_a.end_pt.pid == chain_b.start_pt.pid:
                        join_chains(chain_a, chain_b)
                    elif chain_a.end_pt.pid == chain_b.end_pt.pid:
                        chain_b.reverse()
                        join_chains(chain_a, chain_b)
                    elif chain_a.start_pt.pid == chain_b.end_pt.pid:
                        join_chains(chain_b, chain_a)
                        old_cid = chain_b.cid
                        chain_b.cid = chain_a.cid
                        self.chain_dict[chain_a.cid] = chain_b
                        del self.chain_dict[old_cid]
                        joined = True
                        break
                    elif chain_a.start_pt.pid == chain_b.start_pt.pid:
                        join_chains(chain_b, chain_a)
                        old_cid = chain_b.cid
                        chain_b.cid = chain_a.cid
                        self.chain_dict[chain_a.cid] = chain_b
                        del self.chain_dict[old_cid]
                        joined = True
                        break
                    else:
                        continue
                    del self.chain_dict[chain_b.cid]
                    joined = True
                    break
                if joined:
                    break
            if not joined:
                break

    def compute_all_areas(self):
        """Compute area for all chains."""
        for ochain in self.chain_dict.values():
            ochain.compute_area()
#            print(f"  Chain: {ochain.cid}  Area: {ochain.area}")

    def assign_types(self, fh=None):
        """
        Assign chain.type based on signed area.

        1. Sort closed chains descending by abs(area).
        2. Largest = 'Exterior'; all others = 'Interior' (provisional).
        3. Sanity check: largest abs(area) > sum of rest.
        4. Direction fix: reverse Exterior if CW; reverse each Interior if CCW.
        5. Type refinement (Hole/Drill) deferred to arc detection (Phase 3).
        """
        def log(msg):
            if fh is not None:
                fh.write(msg)
                fh.flush()

        closed = [c for c in self.chain_dict.values() if c.closed and not c.is_subchain]
        if not closed:
            return

        closed.sort(key=lambda c: abs(c.area), reverse=True)

        exterior = closed[0]
        interior = closed[1:]

        # Sanity check
        sum_rest = sum(abs(c.area) for c in interior)
        if sum_rest >= abs(exterior.area):
            log(f"  WARNING: exterior area {exterior.area:.2f} is not "
                f"greater than sum of others {sum_rest:.2f}\n")

        # Assign provisional types
        exterior.type = 'Exterior'
        for c in interior:
            c.type = 'Interior'

        # Direction fix: Exterior should be CCW (area > 0)
        if exterior.area < 0:
            exterior.reverse()
            log(f"  reversed Exterior chain {exterior.cid} to CCW\n")

        # Direction fix: Interior chains should be CW (area < 0)
        for c in interior:
            if c.area > 0:
                c.reverse()
                log(f"  reversed Interior chain {c.cid} to CW\n")

        log(f"  Types assigned: 1 Exterior, {len(interior)} Interior\n")

    def sorted_by_area(self):
        """Return closed chains sorted descending by abs(area)."""
        closed = [c for c in self.chain_dict.values() if c.closed and not c.is_subchain]
        closed.sort(key=lambda c: abs(c.area), reverse=True)
        return closed

    def __repr__(self):
        return (f"Chains(count={len(self.chain_dict)}, "
                f"closed={sum(1 for c in self.chain_dict.values() if c.closed)})")

    # def add_sub_chain(self, arc_seg):
    #     first_seg = arc_seg.arc_chain  # currently a Segment ref
    #
    #     area = 0.0
    #     cur = first_seg
    #     last = first_seg
    #     seen = set()
    #     while cur is not None and cur.sid not in seen:
    #         seen.add(cur.sid)
    #         area += cur.segarea
    #         last = cur
    #         cur = cur.next_seg
    #
    #     self.chainct += 1
    #     cid = self.chainct
    #     chain = Chain.from_subchain(cid, first_seg, last, area)
    #
    #     self.chain_dict[cid] = chain
    #     arc_seg.arc_chain = chain
    #     return chain

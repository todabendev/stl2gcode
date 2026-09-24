# s2g_app.py: 2026-09-24 - 1159
# CNC Router CAM Pipeline - Main application coordinator.
# Reads STL -> builds chains -> arc detection -> transform -> writes seg file.
# Computes offset paths in memory -> writes path file.

import os
import sys
import s2g_debug as dbg
from s2g_config import S2GConfig
from s2g_stlfile import StlFile
from s2g_points import Points
from s2g_segments import Segments
from s2g_chains import Chains
from s2g_arcs import Arc
from s2g_segfile import SegFileWriter
from s2g_pathfile import PathFileWriter
from s2g_paths import Paths
import s2g_preview as preview
import s2g_generate as gen

s2g_app_stamp = "s2g_app.py: 2026-09-24 - 1159"

if os.environ.get("dbgclaude", "").upper() == "Y":
    print(s2g_app_stamp)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 s2g_app.py <jobfile.s2gcfg>",
              file=sys.stderr)
        sys.exit(1)

    cfg_path = sys.argv[1]

    cfg = S2GConfig(cfg_path)
    if not cfg.ready_to_run:
        print("ERROR: config file has errors — aborting.")
        cfg.print_errors()
        sys.exit(1)
    print(f"  Settings file   : {cfg.settings_file}")
    dbg.set_debug(cfg.debug)
    print(f"  CircleSegments  : {cfg.circle_segments}  "
          f"MaxArcAngle: {cfg.max_arc_angle:.2f} deg")

    oPoints = Points(cfg)
    oSegments = Segments(oPoints)
    stl = StlFile(cfg, oPoints, oSegments)
    print(f"  Reading STL     : {cfg.stl_file}")
    if not stl.read_file():
        stl.print_errors()
        sys.exit(1)
    print(f"  Triangles       : {stl.tri_count}")
    print(f"  Points          : {oPoints.count()}  Segments: {oSegments.count()}")

    print(f"  Applying transform ...")
    oPoints.translate_rotate()
    if not oPoints.boundscheck():
        print("ERROR: part does not fit in work area — aborting.")
        sys.exit(1)

    print(f"  Building chains ...")
    oChains = Chains(oPoints, oSegments)
    oChains.build()
    oChains.match_open_chains()
    oChains.compute_all_areas()
    oChains.assign_types()

    print(f"  Writing segment file: {cfg.seg_file}")
    oWriter = SegFileWriter(cfg)
    if not oWriter.write(oChains):
        print("ERROR: segment file write failed — aborting.")
        sys.exit(1)

    oArc = Arc(cfg)

    print(f"  Computing offset paths ...")
    oPaths = Paths(oChains, cfg)
    oPaths.create_paths()
    oPaths.calc_endpoints()
    oPaths.find_arcs(oArc)

    # Console summary
#    print(f"  Path summary:")
#    for oPath in oPaths.sorted_by_area():
#        print(f"    {oPath.cid:3d}  {oPath.type:10s}  area={oPath.area:.2f}")

    print(f"  Writing path file: {cfg.path_file}")
    oWriter = PathFileWriter(cfg)
    if not oWriter.write(oPaths):
        print("ERROR: path file write failed — aborting.")
        sys.exit(1)

    print(f"Generating GCode.")

    oGen = gen.Generate(cfg)
    oGen.write_gcode(oPaths)
    if cfg.test_file:
        print(f"Generating Test GCode.")
        oGen.write_test_gcode(oPaths, oPoints)

    if cfg.html_file:
        print(f"Generating Preview.")
        preview.main()

    print(f"s2g_app complete.")


if __name__ == "__main__":
    main()

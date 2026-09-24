# s2g_preview.py: 2026-09-24 - 1133
# CNC Router CAM Pipeline - HTML preview generator.
# Reads .path file and writes a self-contained HTML preview.
# Usage: python3 s2g_preview.py <jobfile.s2gcfg>

import os
import sys
import math
from datetime import datetime

s2g_preview_stamp = "s2g_preview.py: 2026-09-24 - 1133"

if os.environ.get("dbgclaude", "").upper() == "Y":
    print(s2g_preview_stamp)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2g_config import S2GConfig


# ---------------------------------------------------------------------------
# Path file reader
# ---------------------------------------------------------------------------

def read_path_file(filepath):
    """
    Read path file. Returns list of path dicts:
    {
      "type":    str,   Interior/Exterior/Hole/Drill
      "number":  int,
      "label":   str,
      "interior": bool,
      "orig":    [(x,y), ...]        part outline points (_ lines)
      "lines":   [line_item, ...]    L-type cut segments
      "arcs":    [arc_item, ...]     A-type cut arcs
      "holes":   [hole_item, ...]    H-type full circle moves
      "drills":  [drill_item, ...]   D-type drill moves
      "has_error": bool
    }

    line_item:  {"sx":f,"sy":f,"ex":f,"ey":f,"error":str}
    arc_item:   {"cx":f,"cy":f,"sx":f,"sy":f,"ex":f,"ey":f,"ccw":bool,"error":str}
    hole_item:  {"cx":f,"cy":f,"ex":f,"ey":f,"radius":f}
    drill_item: {"cx":f,"cy":f,"radius":f}

    New path file format (tab-separated):
      L  x y nx ny endpt1x endpt1y endpt2x endpt2y
      A  sx sy ex ey I J rotation
      H  ex ey cx cy arc_I rotation
      D  ex ey cx cy arc_I
      -  ex ey                        (skip move -- ignored)
      _  x y                          (part outline point)
    """
    paths   = []
    current = None

    try:
        with open(filepath, "r") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue

                # Detect error prefixes
                error_type = ""
                while line.startswith("#L") or line.startswith("#C"):
                    if line.startswith("#L"):
                        error_type += "L"
                        parts = line.split(" ", 1)
                        line  = parts[1].strip() if len(parts) > 1 else ""
                    elif line.startswith("#C"):
                        error_type += "C"
                        parts = line.split(" ", 1)
                        line  = parts[1].strip() if len(parts) > 1 else ""

                if not line:
                    continue
                if line.startswith("#"):
                    continue

                if line.startswith("+"):
                    parts   = line[1:].split()
                    ptype   = parts[0]
                    number  = int(parts[1])
                    current = {
                        "type":      ptype,
                        "number":    number,
                        "label":     f"{ptype} {number}",
                        "interior":  ptype in ("Interior", "Hole", "Drill"),
                        "orig":      [],
                        "lines":     [],
                        "arcs":      [],
                        "holes":     [],
                        "drills":    [],
                        "has_error": False
                    }
                    continue

                if line.startswith("-End"):
                    if current is not None:
                        paths.append(current)
                        current = None
                    continue

                if current is None:
                    continue

                cols = line.split("\t")
                kind = cols[0]

                if kind == "_":
                    # Original outline points -- no longer written; keep logic
                    if len(cols) >= 3:
                        current["orig"].append(
                            (float(cols[1]), float(cols[2])))

                elif kind == "-":
                    # Skip move -- consumed into arc; ignore
                    pass

                elif kind == "L":
                    # L x y nx ny endpt1x endpt1y endpt2x endpt2y
                    if error_type:
                        current["has_error"] = True
                    if len(cols) >= 9:
                        current["lines"].append({
                            "sx":    float(cols[5]),
                            "sy":    float(cols[6]),
                            "ex":    float(cols[7]),
                            "ey":    float(cols[8]),
                            "error": error_type
                        })

                elif kind == "A":
                    # A sx sy ex ey I J rotation
                    if error_type:
                        current["has_error"] = True
                    if len(cols) >= 7:
                        sx = float(cols[1])
                        sy = float(cols[2])
                        ex = float(cols[3])
                        ey = float(cols[4])
                        ii = float(cols[5])
                        jj = float(cols[6])
                        cx = sx + ii
                        cy = sy + jj
                        rotation = cols[7].strip() if len(cols) >= 8 else "CW"
                        current["arcs"].append({
                            "cx":    cx,  "cy":    cy,
                            "sx":    sx,  "sy":    sy,
                            "ex":    ex,  "ey":    ey,
                            "ccw":   rotation == "CCW",
                            "error": error_type
                        })

                elif kind == "H":
                    # H ex ey cx cy arc_I rotation
                    if len(cols) >= 6:
                        ex     = float(cols[1])
                        ey     = float(cols[2])
                        cx     = float(cols[3])
                        cy     = float(cols[4])
                        radius = float(cols[5])
                        current["holes"].append({
                            "cx": cx, "cy": cy,
                            "ex": ex, "ey": ey,
                            "radius": radius
                        })

                elif kind == "D":
                    # D ex ey cx cy arc_I
                    if len(cols) >= 6:
                        cx     = float(cols[3])
                        cy     = float(cols[4])
                        radius = float(cols[5])
                        current["drills"].append({
                            "cx": cx, "cy": cy,
                            "radius": radius
                        })

    except OSError as exc:
        print(f"ERROR: cannot read path file: {exc}")
        return []

    return paths


# ---------------------------------------------------------------------------
# JavaScript array builders
# ---------------------------------------------------------------------------

def fmt_pt(x, y):
    return f"[{x:.3f},{y:.3f}]"


def build_js_data(cfg, paths):
    """
    Build JavaScript data constants for all path types.

    AllPoints[0][0][0..3]        board rectangle
    AllPoints[1][0..n]           part outlines (all paths, _ points)
    AllPoints[2][0..n]           Interior cut line segments [[sx,sy,ex,ey,err],...]
    AllPoints[3][0]              Exterior cut data  (same format)
    AllPoints[4][0..n]           Hole cut data  [[cx,cy,ex,ey,radius],...]
    AllPoints[5][0..n]           Drill data     [[cx,cy,radius],...]
    ArcData[0..n]                Arc cut data   [[cx,cy,sx,sy,ex,ey,err,ccw],...]
    """
    lines = []

    # AllPoints[0] board
    bx = cfg.workpiece_x
    by = cfg.workpiece_y
    board = [(0.0, 0.0), (bx, 0.0), (bx, by), (0.0, by)]
    lines.append("const AllPoints = [")
    lines.append(f"  [ [ [{','.join(fmt_pt(x, y) for x, y in board)}] ] ],")

    # AllPoints[1] part outlines (_ lines from the path file)
    lines.append("  [")
    for i, path in enumerate(paths):
        pts   = path["orig"]
        comma = "," if i < len(paths) - 1 else ""
        if pts:
            lines.append(f"    [{','.join(fmt_pt(x, y) for x, y in pts)}]{comma}")
        else:
            lines.append(f"    []{comma}")
    lines.append("  ],")

    # AllPoints[2] Interior cut line segments
    interior = [p for p in paths if p["type"] == "Interior"]
    lines.append("  [")
    for i, path in enumerate(interior):
        segs  = []
        for seg in path["lines"]:
            err = seg["error"]
            segs.append(f"[{seg['sx']:.3f},{seg['sy']:.3f},"
                        f"{seg['ex']:.3f},{seg['ey']:.3f},"
                        f"{'2' if 'C' in err else '1' if 'L' in err else '0'}]")
        comma = "," if i < len(interior) - 1 else ""
        lines.append(f"    [{','.join(segs)}]{comma}")
    lines.append("  ],")

    # AllPoints[3] Exterior cut line segments
    exterior = [p for p in paths if p["type"] == "Exterior"]
    lines.append("  [")
    if exterior:
        path = exterior[0]
        segs = []
        for seg in path["lines"]:
            err = seg["error"]
            segs.append(f"[{seg['sx']:.3f},{seg['sy']:.3f},"
                        f"{seg['ex']:.3f},{seg['ey']:.3f},"
                        f"{'2' if 'C' in err else '1' if 'L' in err else '0'}]")
        lines.append(f"    [{','.join(segs)}]")
    lines.append("  ],")

    # AllPoints[4] Hole data -- collected from H moves across all paths
    all_holes = []
    for path in paths:
        for h in path["holes"]:
            all_holes.append(
                f"[{h['cx']:.3f},{h['cy']:.3f},"
                f"{h['ex']:.3f},{h['ey']:.3f},{h['radius']:.3f}]"
            )
    lines.append("  [")
    for i, h in enumerate(all_holes):
        comma = "," if i < len(all_holes) - 1 else ""
        lines.append(f"    {h}{comma}")
    lines.append("  ],")

    # AllPoints[5] Drill data -- collected from D moves across all paths
    all_drills = []
    for path in paths:
        for d in path["drills"]:
            all_drills.append(
                f"[{d['cx']:.3f},{d['cy']:.3f},{d['radius']:.3f}]"
            )
    lines.append("  [")
    for i, d in enumerate(all_drills):
        comma = "," if i < len(all_drills) - 1 else ""
        lines.append(f"    {d}{comma}")
    lines.append("  ]")
    lines.append("];")

    # ArcData -- separate array for arc cut paths
    all_arcs = []
    for path in paths:
        for arc in path["arcs"]:
            err  = arc["error"]
            code = 2 if "C" in err else 1 if "L" in err else 0
            all_arcs.append(
                f"[{arc['cx']:.3f},{arc['cy']:.3f},"
                f"{arc['sx']:.3f},{arc['sy']:.3f},"
                f"{arc['ex']:.3f},{arc['ey']:.3f},{code},"
                f"{1 if arc['ccw'] else 0}]"
            )
    lines.append(f"const ArcData = [{','.join(all_arcs)}];")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(cfg, paths, path_filepath):
    now       = datetime.now().strftime("%Y-%m-%d %H:%M")
    src_name  = os.path.basename(path_filepath)
    board_w   = cfg.workpiece_x
    board_h   = cfg.workpiece_y
    js_data   = build_js_data(cfg, paths)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>s2g Preview - {src_name}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    background: #e0e0e0;
    font-family: monospace;
    display: flex;
    flex-direction: column;
    height: 100vh;
  }}
  #infobar {{
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 4px 10px;
    background: #333;
    color: #eee;
    font-size: 13px;
    flex-shrink: 0;
    flex-wrap: wrap;
  }}
  #infobar span {{ white-space: nowrap; }}
  #zoom-controls {{ display: flex; gap: 4px; }}
  #zoom-controls button {{
    width: 28px; height: 24px;
    font-size: 16px; font-weight: bold;
    cursor: pointer; background: #555; color: #fff;
    border: 1px solid #888; border-radius: 3px;
  }}
  #zoom-controls button:hover {{ background: #777; }}
  #legend {{
    display: flex; gap: 20px;
    padding: 4px 10px;
    background: white;
    font-size: 12px;
    flex-shrink: 0; flex-wrap: wrap;
    border-bottom: 1px solid #ccc;
  }}
  #viewport {{
    flex: 1; overflow: auto; background: #aaa;
  }}
  #workpiece {{
    display: inline-block;
    background: white;
    border: 8px solid saddlebrown;
    margin: 8px; line-height: 0;
    padding: 4px;
  }}
  #cnv {{ display: block; cursor: crosshair; }}
</style>
</head>
<body>

<div id="infobar">
  <span id="info-file">{src_name} &nbsp; {now}</span>
  <span id="info-board">Board: {board_w:.1f} x {board_h:.1f} mm</span>
  <span id="info-view">View centre: -</span>
  <div id="zoom-controls">
    <button id="btn-plus" title="Zoom in">+</button>
    <button id="btn-minus" title="Zoom out">-</button>
  </div>
  <span id="info-mag">Mag: -</span>
  <span id="info-xy">X=- Y=-</span>
</div>

<div id="legend">
  <span style="color:saddlebrown;font-weight:bold">Board outline</span>
  <span style="color:black;font-weight:bold">Part outline</span>
  <span style="color:#505050;font-weight:bold">Grid 20 mm</span>
  <span style="color:blue;font-weight:bold">Interior cut</span>
  <span style="color:green;font-weight:bold">Exterior cut</span>
  <span style="color:teal;font-weight:bold">Hole / Arc cut</span>
  <span style="color:saddlebrown;font-weight:bold">Drill (brown fill)</span>
  <span style="color:orange;font-weight:bold">Bounds error</span>
  <span style="color:red;font-weight:bold">Crossing error</span>
</div>

<div id="viewport">
  <div id="workpiece">
    <canvas id="cnv"></canvas>
  </div>
</div>

<script>
// -----------------------------------------------------------------------
// Data
// -----------------------------------------------------------------------
{js_data}

const BOARD_W   = {board_w};
const BOARD_H   = {board_h};
const MACHINE_X = {cfg.machine_x};
const MACHINE_Y = {cfg.machine_y};
const TOOL_DIA  = {cfg.tool_diameter};

var mag = 1.0;

const cnv = document.getElementById("cnv");
const ctx = cnv.getContext("2d");
const vp  = document.getElementById("viewport");

function mmToCanvasX(x) {{ return x * mag; }}
function mmToCanvasY(y) {{ return (BOARD_H - y) * mag; }}
function canvasToMmX(cx) {{ return cx / mag; }}
function canvasToMmY(cy) {{ return BOARD_H - cy / mag; }}

function initMag() {{
  var vw = vp.clientWidth  - 32;
  var vh = vp.clientHeight - 32;
  mag = Math.min(vw / Math.min(MACHINE_X, BOARD_W),
                 vh / Math.min(MACHINE_Y, BOARD_H));
  if (mag < 0.1) mag = 0.1;
}}

function resizeCanvas() {{
  cnv.width  = Math.round(BOARD_W * mag);
  cnv.height = Math.round(BOARD_H * mag);
}}

// -----------------------------------------------------------------------
// Drawing helpers
// -----------------------------------------------------------------------
function drawClosedPath(pts, color, lineWidth) {{
  if (pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(mmToCanvasX(pts[0][0]), mmToCanvasY(pts[0][1]));
  for (var i = 1; i < pts.length; i++)
    ctx.lineTo(mmToCanvasX(pts[i][0]), mmToCanvasY(pts[i][1]));
  ctx.closePath();
  ctx.strokeStyle = color; ctx.lineWidth = lineWidth;
  ctx.stroke();
}}

function errorColor(code) {{
  if (code === 2 || code === 3) return "red";
  if (code === 1)               return "orange";
  return null;
}}

// Draw line segments: each seg is [sx,sy,ex,ey,errCode]
// Wide pass (tool diameter, rounded) then thin pass on top
function drawLineSegs(segs, normalColor) {{
  if (!segs || segs.length === 0) return;
  var toolPx = TOOL_DIA * mag;

  // Wide pass
  ctx.lineCap = "round";
  for (var i = 0; i < segs.length; i++) {{
    var s = segs[i];
    ctx.beginPath();
    ctx.moveTo(mmToCanvasX(s[0]), mmToCanvasY(s[1]));
    ctx.lineTo(mmToCanvasX(s[2]), mmToCanvasY(s[3]));
    ctx.strokeStyle = s[4] > 0 ? "lightpink" : "#d4c8a0";
    ctx.lineWidth   = toolPx;
    ctx.stroke();
  }}

  // Thin pass
  ctx.lineCap = "butt";
  for (var i = 0; i < segs.length; i++) {{
    var s = segs[i];
    var ec = errorColor(s[4]);
    ctx.beginPath();
    ctx.moveTo(mmToCanvasX(s[0]), mmToCanvasY(s[1]));
    ctx.lineTo(mmToCanvasX(s[2]), mmToCanvasY(s[3]));
    ctx.strokeStyle = ec || normalColor;
    ctx.lineWidth   = ec ? 2 : 1;
    ctx.stroke();
  }}
  ctx.lineCap = "butt";
}}

// Draw arc cut: [cx,cy,sx,sy,ex,ey,errCode,ccw]
// ccw=1 draws counter-clockwise (G3), ccw=0 clockwise (G2).
function drawArcCut(arc) {{
  var cx = mmToCanvasX(arc[0]); var cy = mmToCanvasY(arc[1]);
  var sx = mmToCanvasX(arc[2]); var sy = mmToCanvasY(arc[3]);
  var ex = mmToCanvasX(arc[4]); var ey = mmToCanvasY(arc[5]);
  var r  = Math.hypot(sx - cx, sy - cy);
  var sa = Math.atan2(sy - cy, sx - cx);
  var ea = Math.atan2(ey - cy, ex - cx);
  var ec = errorColor(arc[6]);
  var ccw = (arc[7] === 1);
  var toolPx = TOOL_DIA * mag;

  // Wide pass
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.arc(cx, cy, r, sa, ea, ccw);
  ctx.strokeStyle = arc[6] > 0 ? "lightpink" : "#d4c8a0";
  ctx.lineWidth   = toolPx;
  ctx.stroke();

  // Thin pass
  ctx.beginPath();
  ctx.arc(cx, cy, r, sa, ea, ccw);
  ctx.strokeStyle = ec || "teal";
  ctx.lineWidth   = ec ? 2 : 1;
  ctx.stroke();
  ctx.lineCap = "butt";
}}

// Draw hole: [cx,cy,ex,ey,radius]
function drawHole(h) {{
  var cx = mmToCanvasX(h[0]); var cy = mmToCanvasY(h[1]);
  var r  = h[4] * mag;
  var toolPx = TOOL_DIA * mag;

  // Wide pass - light teal ring
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2*Math.PI);
  ctx.strokeStyle = "#b0dcdc";
  ctx.lineWidth   = toolPx;
  ctx.stroke();

  // Thin teal circle
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2*Math.PI);
  ctx.strokeStyle = "teal";
  ctx.lineWidth   = 1;
  ctx.stroke();
}}

// Draw drill: [cx,cy,radius] - brown filled circle
function drawDrill(d) {{
  var cx = mmToCanvasX(d[0]); var cy = mmToCanvasY(d[1]);
  var r  = d[2] * mag;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2*Math.PI);
  ctx.fillStyle   = "#b08050";
  ctx.fill();
  ctx.strokeStyle = "saddlebrown";
  ctx.lineWidth   = 1;
  ctx.stroke();
}}

// Draw 20 mm grid from 0,0 across the board
const GRID_MM = 20.0;
function drawGrid() {{
  ctx.beginPath();
  for (var x = 0.0; x <= BOARD_W; x += GRID_MM) {{
    ctx.moveTo(mmToCanvasX(x), mmToCanvasY(0.0));
    ctx.lineTo(mmToCanvasX(x), mmToCanvasY(BOARD_H));
  }}
  for (var y = 0.0; y <= BOARD_H; y += GRID_MM) {{
    ctx.moveTo(mmToCanvasX(0.0),     mmToCanvasY(y));
    ctx.lineTo(mmToCanvasX(BOARD_W), mmToCanvasY(y));
  }}
  ctx.strokeStyle = "#505050";
  ctx.lineWidth   = 0.5;
  ctx.stroke();
}}

// -----------------------------------------------------------------------
// Redraw
// -----------------------------------------------------------------------
function redraw() {{
  resizeCanvas();
  ctx.clearRect(0, 0, cnv.width, cnv.height);

  // Grid first
  drawGrid();

  // Board outline
  drawClosedPath(AllPoints[0][0], "saddlebrown", 4);

  // Part outlines (_ lines)
  for (var i = 0; i < AllPoints[1].length; i++)
    drawClosedPath(AllPoints[1][i], "black", 1);

  // Interior cut lines
  for (var i = 0; i < AllPoints[2].length; i++)
    drawLineSegs(AllPoints[2][i], "blue");

  // Exterior cut lines
  if (AllPoints[3].length > 0)
    drawLineSegs(AllPoints[3][0], "green");

  // Hole circles
  for (var i = 0; i < AllPoints[4].length; i++)
    drawHole(AllPoints[4][i]);

  // Drill circles
  for (var i = 0; i < AllPoints[5].length; i++)
    drawDrill(AllPoints[5][i]);

  // Arc cuts
  for (var i = 0; i < ArcData.length; i++)
    drawArcCut(ArcData[i]);

  updateViewInfo();
}}

// -----------------------------------------------------------------------
// Info bar / zoom / interaction
// -----------------------------------------------------------------------
function updateViewInfo() {{
  var sl=vp.scrollLeft, st=vp.scrollTop, cw=vp.clientWidth, ch=vp.clientHeight;
  document.getElementById("info-view").textContent =
    "View centre: " + canvasToMmX(sl+cw/2-16).toFixed(1) +
    ", " + canvasToMmY(st+ch/2-16).toFixed(1) + " mm";
  document.getElementById("info-mag").textContent =
    "Mag: " + mag.toFixed(2) + "x";
}}

function zoom(factor) {{
  var sl=vp.scrollLeft, st=vp.scrollTop, cw=vp.clientWidth, ch=vp.clientHeight;
  var cx_mm=canvasToMmX(sl+cw/2-16), cy_mm=canvasToMmY(st+ch/2-16);
  mag *= factor;
  if (mag < 0.05) mag = 0.05;
  redraw();
  vp.scrollLeft = mmToCanvasX(cx_mm)+16-cw/2;
  vp.scrollTop  = mmToCanvasY(cy_mm)+16-ch/2;
  updateViewInfo();
}}

document.getElementById("btn-plus").addEventListener("click",
  function() {{ zoom(1.5); }});
document.getElementById("btn-minus").addEventListener("click",
  function() {{ zoom(1.0/1.5); }});

cnv.addEventListener("click", function(e) {{
  var rect=cnv.getBoundingClientRect();
  vp.scrollLeft=(e.clientX-rect.left)+16-vp.clientWidth/2;
  vp.scrollTop =(e.clientY-rect.top) +16-vp.clientHeight/2;
  updateViewInfo();
}});

cnv.addEventListener("mousemove", function(e) {{
  var rect=cnv.getBoundingClientRect();
  document.getElementById("info-xy").textContent =
    "X="+canvasToMmX(e.clientX-rect.left).toFixed(2)+
    "  Y="+canvasToMmY(e.clientY-rect.top).toFixed(2);
}});

vp.addEventListener("scroll", updateViewInfo);

window.addEventListener("load", function() {{ initMag(); redraw(); }});
</script>
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 s2g_preview.py <jobfile.s2gcfg>",
              file=sys.stderr)
        sys.exit(1)

    cfg_path = sys.argv[1]
    print(f"s2g_preview starting  [{cfg_path}]")

    cfg = S2GConfig(cfg_path)
    if not cfg.ready_to_run:
        print("ERROR: config file has errors -- aborting.")
        cfg.print_errors()
        return

    print(f"  Settings file   : {cfg.settings_file}")

    if not cfg.html_file:
        print("ERROR: HTMLFile not specified in config -- aborting.")
        return

    print(f"  Reading path file: {cfg.path_file}")
    paths = read_path_file(cfg.path_file)
    if not paths:
        print("ERROR: no paths found in path file -- aborting.")
        return

    print(f"  Paths read      : {len(paths)}")

    print(f"  Writing HTML    : {cfg.html_file}")
    html = generate_html(cfg, paths, cfg.path_file)
    try:
        with open(cfg.html_file, "w", newline="\n") as fh:
            fh.write(html)
    except OSError as exc:
        print(f"ERROR: cannot write HTML file: {exc}")
        return

    print(f"s2g_preview complete.")


if __name__ == "__main__":
    main()
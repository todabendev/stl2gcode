# stl2gcode
Generate CNC gcode to cut out a flat part defined by an stl file
STL2GCODE
=========

Creates GCode to cut out a flat part, defined by an .stl file, on a
CNC router.


REQUIREMENTS
------------
- Python 3. Nothing else to install.
- A GRBL-type router. Tested on a FoxAlien 4040 with a 1/8" upcut bit.


QUICK START
-----------
  cd Sample
  ./MotorTooth.sh

Then open MotorTooth.html in a web browser to see the cut paths.

WINDOWS
-------
1. Install Python 3 from python.org. During setup, tick
   "Add python.exe to PATH".
2. Double-click Sample\MotorTooth.bat, or from a command window:
     cd Sample
     MotorTooth.bat
   The window stays open until you press a key.
3. Open MotorTooth.html in a web browser to see the cut paths.

On Windows the Python command is "py" rather than "python3".
PREPARING THE STL
-----------------
The surface on the XY plane at Z=0.0 defines the cut.
s2g_reorient.py can move or rotate a part so the surface you want
is on the XY plane at Z=0.0.


THE JOB FILE (.s2gcfg)
----------------------
One setting per line, "Keyword: value". Lines starting with # are
comments. Relative paths are relative to the folder you run from.

  Debug           0 = off
  STLFile         input .stl
  SegFile         output segment file
  PathFile        output path file
  HTMLFile        output preview (optional)
  GCodeFile       output cut GCode
  TestFile        output test GCode (optional)
  SettingsFile    machine/tool/material file (MTG_Settings.txt)
  Machine         name from the settings file
  Tool            name from the settings file
  Material        name from the settings file
  WorkpieceX      material size in mm; the part must fit
  WorkpieceY
  WorkpieceZ      (not used yet)
  CircleSegments  segments per full circle in the STL; used to
                  recognize arcs
  RotateDeg       rotate the part about Z, degrees
  TranslateX      shift the part, mm. Leave out to place the part
  TranslateY      one tool diameter from zero.
  ArcTolerance    (not used yet)
  SkipExterior    (not used yet)


MTG_SETTINGS.TXT
----------------
Holds Machines, Tools, Materials and GCode blocks. Add your own lines.

  Machine: "name" "GCode" WorkAreaX WorkAreaY MaxZ Tolerance ClearanceHeight
  Tool: "name" Diameter Length Flutes
  Material: "name" CutDepth MaxDepth CutSpeed PlungeSpeed

  Tolerance        mm; points closer than this are the same point
  ClearanceHeight  Z for moves between cuts
  MaxZ             (not used yet)
  CutDepth         depth of each pass
  MaxDepth         total depth; set it at or below the material thickness
  CutSpeed         mm/min
  PlungeSpeed      mm/min

The GCode block named by the Machine line holds the lines written at
the start (InitialCode) and end (FinalCode) of every GCode file.


WHAT IT PRODUCES
----------------
  .gcode       the cut. Interior cuts first, exterior last.
  Test.gcode   path test to check the setup. Spindle off, Z=10.0.
               Traces the exterior cut path with G0 moves, then goes
               to the part's MinX, MaxY.
  .html        preview of the cut paths. Grid is 20 mm.
  .seg, .path  intermediate files, useful for troubleshooting.


WORKFLOW
--------
1. Mount the material. Double-sided tape outside the exterior cut
   line and in the center of the part, none where the tool cuts.
2. Set the X, Y and Z zeros.
3. Run the Test.gcode and check by eye that the material is in the
   right place and big enough.
4. Air-cut first (bit raised or removed).
5. Run the .gcode.


LIMITS
------
Whatever shape the part has, the profile cut is its surface on the
XY plane at Z=0.0.
One tool per job. No tabs to hold the part.


MODULES
-------
  s2g_app.py          RUN THIS. Reads the job file, makes all outputs.
  s2g_reorient.py     RUN THIS. Moves/rotates an STL so the profile is
                      on the XY plane at Z=0.0.
  s2g_config.py       reads the job file
  s2g_mtgsettings.py  reads MTG_Settings.txt
  s2g_stlfile.py      reads the STL, finds the edges at Z=0.0
  s2g_points.py       points; translate and rotate
  s2g_segments.py     edge segments
  s2g_chains.py       joins segments into closed outlines
  s2g_segfile.py      writes the .seg file
  s2g_paths.py        offsets each outline by the tool radius
  s2g_geometry.py     geometry helpers
  s2g_arcs.py         finds arcs and holes in the offset paths
  s2g_pathfile.py     writes the .path file
  s2g_generate.py     writes the cut and test GCode
  s2g_preview.py      writes the .html preview
  s2g_debug.py        debug output


SAFETY
------
Use at your own risk. Always check the preview and air-cut first.
Free software with NO warranty. See LICENSE.

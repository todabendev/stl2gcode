# s2g_config.py: 2026-05-18 - 1757
# CNC Router CAM Pipeline - Job Configuration and MTG Settings Parser
import math
import os
import sys
from s2g_mtgsettings import MTGSettings

s2g_config_stamp = "s2g_config.py: 2026-05-18 - 1757"
# ---------------------------------------------------------------------------
# S2GConfig — job configuration class
# ---------------------------------------------------------------------------

class S2GConfig:
    """
    Parse a .s2gcfg job file and the referenced MTG settings file.
    Exposes all parameters as properties.
    ReadyToRun is False if any required value is missing or invalid.
    """

    def __init__(self, filepath):
        self._filepath    = filepath
        self._errors      = []
        self._raw         = {}   # keyword -> value string from config file
        self._debug = 0

        # MTG-sourced values
        self._machine_entry  = None
        self._tool_entry     = None
        self._material_entry = None
        self._gcode_entry    = None

        self._parse_config()
        if self.debug > 0:
            print(s2g_config_stamp)
        self._load_mtg()
        self._validate()

    # ------------------------------------------------------------------
    # Config file parser
    # ------------------------------------------------------------------

    def _parse_config(self):
        if not os.path.isfile(self._filepath):
            self._errors.append(f"Config file not found: {self._filepath}")
            return

        with open(self._filepath, "r") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" not in line:
                    continue
                keyword, _, value = line.partition(":")
                keyword = keyword.strip().lower()
                value   = value.strip()
                self._raw[keyword] = value

    def _get(self, key, default=None):
        return self._raw.get(key.lower(), default)

    def _get_float(self, key, default=None):
        v = self._get(key)
        if v is None:
            return default
        try:
            return float(v)
        except ValueError:
            self._errors.append(f"Config: '{key}' is not a valid number: {v}")
            return default

    def _get_int(self, key, default=None):
        v = self._get(key)
        if v is None:
            return default
        try:
            return int(v)
        except ValueError:
            self._errors.append(f"Config: '{key}' is not a valid integer: {v}")
            return default

    def _get_bool(self, key, default=False):
        v = self._get(key)
        if v is None:
            return default
        if v.upper() in ("Y", "YES"):
            return True
        if v.upper() in ("N", "NO"):
            return False
        self._errors.append(
            f"Config: '{key}' must be Y/Yes/N/No, got: {v}")
        return default

    def _unquote(self, text):
        t = text.strip() if text else ""
        if t.startswith('"') and t.endswith('"'):
            return t[1:-1]
        return t

    # ------------------------------------------------------------------
    # MTG loader
    # ------------------------------------------------------------------

    def _load_mtg(self):
        settings_file = self._get("settingsfile")
        if not settings_file:
            self._errors.append("Config: SettingsFile is required.")
            return

        mtg = MTGSettings(settings_file, self.debug)
        if mtg.errors:
            self._errors.extend(mtg.errors)
            return

        # Machine
        machine_name = self._unquote(self._get("machine", ""))
        if not machine_name:
            self._errors.append("Config: Machine name is required.")
        else:
            self._machine_entry = mtg.get_machine(machine_name)
            if self._machine_entry is None:
                self._errors.append(
                    f"Config: Machine '{machine_name}' not found in MTG settings.")
            else:
                gcode_name = self._machine_entry.get("gcode_name", "")
                self._gcode_entry = mtg.get_gcode(gcode_name)
                if self._gcode_entry is None:
                    self._errors.append(
                        f"Config: GCode profile '{gcode_name}' not found in MTG settings.")

        # Tool
        tool_name = self._unquote(self._get("tool", ""))
        if not tool_name:
            self._errors.append("Config: Tool name is required.")
        else:
            self._tool_entry = mtg.get_tool(tool_name)
            if self._tool_entry is None:
                self._errors.append(
                    f"Config: Tool '{tool_name}' not found in MTG settings.")

        # Material
        material_name = self._unquote(self._get("material", ""))
        if not material_name:
            self._errors.append("Config: Material name is required.")
        else:
            self._material_entry = mtg.get_material(material_name)
            if self._material_entry is None:
                self._errors.append(
                    f"Config: Material '{material_name}' not found in MTG settings.")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self):
        # Required file paths
        for key in ("stlfile", "segfile", "pathfile", "gcodefile"):
            if not self._get(key):
                self._errors.append(f"Config: {key} is required.")

        # Required workpiece dimensions
        if self._get_float("workpiecex") is None:
            self._errors.append("Config: WorkpieceX is required.")
        if self._get_float("workpiecey") is None:
            self._errors.append("Config: WorkpieceY is required.")
        if self._get_float("workpiecez") is None:
            self._errors.append("Config: WorkpieceZ is required.")

    # ------------------------------------------------------------------
    # File path properties
    # ------------------------------------------------------------------

    @property
    def stl_file(self):
        return self._get("stlfile", "")

    @property
    def seg_file(self):
        return self._get("segfile", "")

    @property
    def path_file(self):
        return self._get("pathfile", "")

    @property
    def gcode_file(self):
        return self._get("gcodefile", "")

    @property
    def html_file(self):
        return self._get("htmlfile", "")

    @property
    def test_file(self):
        return self._get("testfile", "")

    @property
    def settings_file(self):
        return self._get("settingsfile", "")

    # ------------------------------------------------------------------
    # Workpiece properties (per-job)
    # ------------------------------------------------------------------

    @property
    def workpiece_x(self):
        return self._get_float("workpiecex")

    @property
    def workpiece_y(self):
        return self._get_float("workpiecey")

    @property
    def workpiece_z(self):
        return self._get_float("workpiecez")

    # ------------------------------------------------------------------
    # Machine properties (from MTG)
    # ------------------------------------------------------------------

    @property
    def machine_x(self):
        return self._machine_entry["work_area_x"] \
            if self._machine_entry else None

    @property
    def machine_y(self):
        return self._machine_entry["work_area_y"] \
            if self._machine_entry else None

    @property
    def max_z(self):
        return self._machine_entry["max_z"] \
            if self._machine_entry else None

    @property
    def cnc_tolerance(self):
        return self._machine_entry["tolerance"] \
            if self._machine_entry else None

    @property
    def clearance_height(self):
        return self._machine_entry["clearance_height"] \
            if self._machine_entry else None

    # ------------------------------------------------------------------
    # Tool properties (from MTG)
    # ------------------------------------------------------------------

    @property
    def tool_diameter(self):
        return self._tool_entry["diameter"] if self._tool_entry else None

    @property
    def tool_radius(self):
        d = self.tool_diameter
        return d / 2.0 if d is not None else None

    @property
    def tool_length(self):
        return self._tool_entry["length"] if self._tool_entry else None

    @property
    def tool_flutes(self):
        return self._tool_entry["flutes"] if self._tool_entry else None

    # ------------------------------------------------------------------
    # Material / cutting properties (from MTG)
    # ------------------------------------------------------------------

    @property
    def cut_depth(self):
        return self._material_entry["cut_depth"] \
            if self._material_entry else None

    @property
    def max_depth(self):
        return self._material_entry["max_depth"] \
            if self._material_entry else None

    @property
    def cut_speed(self):
        return self._material_entry["cut_speed"] \
            if self._material_entry else None

    @property
    def plunge_speed(self):
        return self._material_entry["plunge_speed"] \
            if self._material_entry else None

    # ------------------------------------------------------------------
    # GCode block properties (from MTG via Machine)
    # ------------------------------------------------------------------

    @property
    def initial_gcode(self):
        """List of lines for the initial GCode block, or empty list."""
        if self._gcode_entry:
            return self._gcode_entry.get("initial", [])
        return []

    @property
    def final_gcode(self):
        """List of lines for the final GCode block, or empty list."""
        if self._gcode_entry:
            return self._gcode_entry.get("final", [])
        return []

    # ------------------------------------------------------------------
    # Job operation properties (per-job)
    # ------------------------------------------------------------------

    @property
    def skip_exterior(self):
        return self._get_bool("skipexterior", False)

    @property
    def arc_tolerance(self):
        return self._get_float("arctolerance", 0.01)

    @property
    def circle_segments(self):
        return self._get_int("circlesegments", 24)

    @property
    def max_arc_angle(self):
        return math.radians(360.0 / self.circle_segments + 1.0)

    @property
    def rotate_deg(self):
        return self._get_float("rotatedeg", 0.0)

    @property
    def translate_x(self):
        v = self._get("translatex", "--")
        if v == "--":
            return None
        try:
            return float(v)
        except ValueError:
            self._errors.append(
                f"Config: TranslateX is not a valid number: {v}")
            return None

    @property
    def translate_y(self):
        v = self._get("translatey", "--")
        if v == "--":
            return None
        try:
            return float(v)
        except ValueError:
            self._errors.append(
                f"Config: TranslateY is not a valid number: {v}")
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def ready_to_run(self):
        return len(self._errors) == 0

    @property
    def errors(self):
        return list(self._errors)

    @property
    def debug(self):

        return self._get_int("debug", 0)

    def print_errors(self):
        for e in self._errors:
            print(f"  ERROR: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main — test driver
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python s2g_config.py <jobfile.s2gcfg>")
        sys.exit(1)

    cfg = S2GConfig(sys.argv[1])

    print(f"Config file:      {cfg._filepath}")
    print(f"Ready to run:     {cfg.ready_to_run}")

    if not cfg.ready_to_run:
        print("Errors:")
        cfg.print_errors()
        print()

    if cfg.debug > 0:
        print(f"Debug level:  {cfg.debug}")

    print("--- File Paths ---")
    print(f"  STLFile:        {cfg.stl_file}")
    print(f"  SegFile:        {cfg.seg_file}")
    print(f"  PathFile:       {cfg.path_file}")
    print(f"  GCodeFile:      {cfg.gcode_file}")
    print(f"  HTMLFile:       {cfg.html_file}")
    print(f"  TestFile:       {cfg.test_file}")
    print(f"  SettingsFile:   {cfg.settings_file}")

    print("--- Workpiece ---")
    print(f"  WorkpieceX:     {cfg.workpiece_x}")
    print(f"  WorkpieceY:     {cfg.workpiece_y}")
    print(f"  WorkpieceZ:     {cfg.workpiece_z}")

    print("--- Machine ---")
    print(f"  MachineX:       {cfg.machine_x}")
    print(f"  MachineY:       {cfg.machine_y}")
    print(f"  MaxZ:           {cfg.max_z}")
    print(f"  CNCTolerance:   {cfg.cnc_tolerance}")
    print(f"  ClearanceH:     {cfg.clearance_height}")

    print("--- Tool ---")
    print(f"  ToolDiameter:   {cfg.tool_diameter}")
    print(f"  ToolRadius:     {cfg.tool_radius}")
    print(f"  ToolLength:     {cfg.tool_length}")
    print(f"  ToolFlutes:     {cfg.tool_flutes}")

    print("--- Material ---")
    print(f"  CutDepth:       {cfg.cut_depth}")
    print(f"  MaxDepth:       {cfg.max_depth}")
    print(f"  CutSpeed:       {cfg.cut_speed}")
    print(f"  PlungeSpeed:    {cfg.plunge_speed}")

    print("--- GCode Blocks ---")
    print(f"  InitialGCode:   {cfg.initial_gcode}")
    print(f"  FinalGCode:     {cfg.final_gcode}")

    print("--- Job Options ---")
    print(f"  SkipExterior:   {cfg.skip_exterior}")
    print(f"  ArcTolerance:   {cfg.arc_tolerance}")
    print(f"  CircleSegments: {cfg.circle_segments}")
    print(f"  MaxArcAngle:    {cfg.max_arc_angle:.4f}")
    print(f"  RotateDeg:      {cfg.rotate_deg}")
    print(f"  TranslateX:     {cfg.translate_x}")
    print(f"  TranslateY:     {cfg.translate_y}")

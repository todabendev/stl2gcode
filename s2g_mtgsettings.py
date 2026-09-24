# s2g_mtgsettings.py: 2026-05-18 - 1757
# CNC Router CAM Pipeline - Job Configuration and MTG Settings Parser

import os
# import sys

s2g_mtgsettings_stamp = "s2g_mtgsettings.py:"

# ---------------------------------------------------------------------------
# MTG Settings Parser
# Handles Machine, Tool, Material, and GCode sections from a shared
# MTG settings file (e.g. MTG_Settings.txt in the Code/ directory).
# ---------------------------------------------------------------------------

class MTGSettings:
    """Parse and hold all Machine, Tool, Material, and GCode entries."""

    def __init__(self, filepath, debug = 0):
        if debug > 0:
            print(s2g_mtgsettings_stamp)
        self._filepath = filepath
        self.debug = debug
        self._machines  = {}   # name -> dict of fields
        self._tools     = {}
        self._materials = {}
        self._gcodes    = {}   # name -> dict of code block lists
        self._errors    = []
        self._parse()

    # ------------------------------------------------------------------
    # Internal parser
    # ------------------------------------------------------------------

    def _parse(self):
        if not os.path.isfile(self._filepath):
            self._errors.append(
                f"MTG settings file not found: {self._filepath}")
            return

        current_gcode_name   = None
        current_gcode_block  = None   # e.g. "InitialCode" or "FinalCode"
        current_gcode_lines  = None

        with open(self._filepath, "r") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                stripped = line.strip()

                # Skip blank lines and comments outside a GCode block
                if current_gcode_block is None:
                    if not stripped or stripped.startswith("#"):
                        continue

                # --- GCode block content ---
                if current_gcode_block is not None:
                    end_token = current_gcode_block + "-End"
                    if stripped == end_token:
                        # Store collected lines
                        if current_gcode_name not in self._gcodes:
                            self._gcodes[current_gcode_name] = {}
                        block_key = current_gcode_block.replace("Code", "").lower()
                        # block_key: "Initial" -> "initial", "Final" -> "final"
                        self._gcodes[current_gcode_name][block_key] = \
                            list(current_gcode_lines)
                        current_gcode_block = None
                        current_gcode_lines = None
                    else:
                        current_gcode_lines.append(line)
                    continue

                # --- GCode block start ---
                if stripped.endswith("-Start"):
                    block_name = stripped[:-6]   # e.g. "InitialCode"
                    if current_gcode_name is None:
                        self._errors.append(
                            f"MTG: {block_name}-Start found outside a GCode: block")
                    else:
                        current_gcode_block = block_name
                        current_gcode_lines = []
                    continue

                # --- Keyword: value lines ---
                if ":" not in stripped:
                    continue
                keyword, _, rest = stripped.partition(":")
                keyword = keyword.strip()
                rest    = rest.strip()

                kw_lower = keyword.lower()

                if kw_lower == "machine":
                    self._parse_machine(rest)
                elif kw_lower == "tool":
                    self._parse_tool(rest)
                elif kw_lower == "material":
                    self._parse_material(rest)
                elif kw_lower == "gcode":
                    name = self._unquote(rest)
                    current_gcode_name = name
                    if name not in self._gcodes:
                        self._gcodes[name] = {}

    def _tokens(self, text):
        """Split text on whitespace, stripping quoted strings as single tokens."""
        tokens = []
        i = 0
        while i < len(text):
            if text[i] in (' ', '\t'):
                i += 1
                continue
            if text[i] == '"':
                j = text.find('"', i + 1)
                if j == -1:
                    tokens.append(text[i+1:])
                    break
                tokens.append(text[i+1:j])
                i = j + 1
            else:
                j = i
                while j < len(text) and text[j] not in (' ', '\t'):
                    j += 1
                tokens.append(text[i:j])
                i = j
        return tokens

    def _unquote(self, text):
        t = text.strip()
        if t.startswith('"') and t.endswith('"'):
            return t[1:-1]
        return t

    def _parse_machine(self, rest):
        # Machine: "name" "GCode" WorkAreaX WorkAreaY MaxZ Tolerance ClearanceHeight
        tokens = self._tokens(rest)
        if len(tokens) < 7:
            self._errors.append(
                f"MTG Machine line has too few fields: {rest}")
            return
        name = tokens[0]
        try:
            entry = {
                "gcode_name":       tokens[1],
                "work_area_x":      float(tokens[2]),
                "work_area_y":      float(tokens[3]),
                "max_z":            float(tokens[4]),
                "tolerance":        float(tokens[5]),
                "clearance_height": float(tokens[6]),
            }
        except ValueError as e:
            self._errors.append(f"MTG Machine '{name}' parse error: {e}")
            return
        self._machines[name] = entry

    def _parse_tool(self, rest):
        # Tool: "name" Diameter Length Flutes
        tokens = self._tokens(rest)
        if len(tokens) < 4:
            self._errors.append(
                f"MTG Tool line has too few fields: {rest}")
            return
        name = tokens[0]
        try:
            entry = {
                "diameter": float(tokens[1]),
                "length":   float(tokens[2]),
                "flutes":   int(tokens[3]),
            }
        except ValueError as e:
            self._errors.append(f"MTG Tool '{name}' parse error: {e}")
            return
        self._tools[name] = entry

    def _parse_material(self, rest):
        # Material: "name" CutDepth MaxDepth CutSpeed PlungeSpeed ArcTolerance
        tokens = self._tokens(rest)
        if len(tokens) < 5:
            self._errors.append(
                f"MTG Material line has too few fields: {rest}")
            return
        name = tokens[0]
        try:
            entry = {
                "cut_depth":    float(tokens[1]),
                "max_depth":    float(tokens[2]),
                "cut_speed":    float(tokens[3]),
                "plunge_speed": float(tokens[4]),
            }
        except ValueError as e:
            self._errors.append(f"MTG Material '{name}' parse error: {e}")
            return
        self._materials[name] = entry

    # ------------------------------------------------------------------
    # Lookup methods — return dict or None
    # ------------------------------------------------------------------

    def get_machine(self, name):
        return self._machines.get(name)

    def get_tool(self, name):
        return self._tools.get(name)

    def get_material(self, name):
        return self._materials.get(name)

    def get_gcode(self, name):
        return self._gcodes.get(name)

    @property
    def errors(self):
        return list(self._errors)


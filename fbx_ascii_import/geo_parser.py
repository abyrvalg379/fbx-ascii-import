# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 Maksim Kovalev
"""Houdini GEO (legacy ASCII geometry) format parser."""

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class GEOAttribute:
    """Attribute definition from a GEO attribute dictionary."""
    name: str
    size: int
    attr_type: str           # 'float', 'integer', 'string', 'index'
    default: list = field(default_factory=list)
    string_table: list = field(default_factory=list)  # for 'index' type


@dataclass
class GEOGeometry:
    """Parsed Houdini GEO geometry."""
    vertices: list = field(default_factory=list)           # [(x,y,z), ...]
    faces: list = field(default_factory=list)              # [(v0,v1,...), ...]
    open_faces: list = field(default_factory=list)         # [bool, ...] per face
    point_colors: list = field(default_factory=list)       # [(r,g,b), ...] per point
    point_normals: list = field(default_factory=list)      # [(nx,ny,nz), ...] per point
    point_uvs: list = field(default_factory=list)          # [(u,v), ...] per point
    prim_attributes: dict = field(default_factory=dict)    # name -> [values per prim]
    detail_attributes: dict = field(default_factory=dict)  # name -> value
    point_attribs: list = field(default_factory=list)      # [GEOAttribute, ...]
    prim_attribs: list = field(default_factory=list)       # [GEOAttribute, ...]
    groups: dict = field(default_factory=dict)             # name -> {type, indices}


# ─────────────────────────────────────────────────────────────────────
#  Parser
# ─────────────────────────────────────────────────────────────────────

class GEOASCIIParser:
    """Line-oriented parser for Houdini GEO ASCII files."""

    def __init__(self, text: str):
        self._lines = text.splitlines()
        self._pos = 0

    def _peek(self) -> str:
        """Return current line without advancing."""
        if self._pos < len(self._lines):
            return self._lines[self._pos]
        return ''

    def _advance(self) -> str:
        """Return current line and advance."""
        line = self._peek()
        self._pos += 1
        return line

    def _skip_empty(self):
        """Skip empty lines."""
        while self._pos < len(self._lines) and not self._lines[self._pos].strip():
            self._pos += 1

    # ── header ──────────────────────────────────────────────────

    def _parse_header(self) -> dict:
        """Parse PGEOMETRY header and counts."""
        info = {}

        # PGEOMETRY V5
        line = self._advance().strip()
        if not line.startswith('PGEOMETRY'):
            raise ValueError(f"Not a GEO file: expected 'PGEOMETRY', got '{line[:30]}'")
        parts = line.split()
        info['version'] = int(parts[1].lstrip('V')) if len(parts) > 1 else 5

        # NPoints N NPrims M ...
        line = self._advance().strip()
        parts = line.split()
        for i in range(0, len(parts) - 1, 2):
            info[parts[i]] = int(parts[i + 1])

        # NPointGroups N NPrimGroups M ...
        line = self._advance().strip()
        parts = line.split()
        for i in range(0, len(parts) - 1, 2):
            info[parts[i]] = int(parts[i + 1])

        # NPointAttrib N NVertexAttrib M NPrimAttrib K NAttrib L
        line = self._advance().strip()
        parts = line.split()
        for i in range(0, len(parts) - 1, 2):
            info[parts[i]] = int(parts[i + 1])

        return info

    # ── attribute dictionary ────────────────────────────────────

    def _parse_attrib_dict(self, keyword: str, count: int) -> list:
        """Parse an attribute dictionary block (PointAttrib, PrimAttrib, etc.)."""
        attribs = []
        if count <= 0:
            return attribs

        # Skip the keyword line (e.g., "PointAttrib")
        line = self._advance().strip()
        if line != keyword:
            # Might already be at the data — rollback
            self._pos -= 1

        for _ in range(count):
            line = self._advance().strip()
            parts = line.split()
            if len(parts) < 3:
                continue

            name = parts[0]
            size = int(parts[1])
            attr_type = parts[2]

            default = []
            string_table = []

            if attr_type == 'index':
                # Format: name 1 index N string0 string1 ...
                if len(parts) >= 4:
                    table_size = int(parts[3])
                    string_table = parts[4:4 + table_size]
                    default = [-1]
            else:
                # Format: name size type default0 default1 ...
                default = [self._parse_number(v) for v in parts[3:3 + size]]

            attribs.append(GEOAttribute(
                name=name, size=size, attr_type=attr_type,
                default=default, string_table=string_table,
            ))

        return attribs

    # ── points ──────────────────────────────────────────────────

    def _parse_points(self, count: int, point_attribs: list, geo: GEOGeometry):
        """Parse point data: x y z w (attr_vals...)"""
        for _ in range(count):
            line = self._advance().strip()
            if not line:
                continue

            # Split on '(' if point attributes exist
            if '(' in line:
                pos_part, attr_part = line.split('(', 1)
                attr_part = attr_part.rstrip(')')
            else:
                pos_part = line
                attr_part = ''

            coords = pos_part.split()
            if len(coords) < 4:
                continue

            x, y, z, w = (float(coords[0]), float(coords[1]),
                          float(coords[2]), float(coords[3]))

            # Apply w (homogeneous coordinates)
            if w != 0 and w != 1:
                x /= w
                y /= w
                z /= w

            # Houdini Y-up → Blender Z-up: (x, y, z) → (x, -z, y)
            geo.vertices.append((x, -z, y))

            # Parse point attributes
            if attr_part and point_attribs:
                vals = attr_part.split()
                vi = 0
                for attr in point_attribs:
                    if attr.name == 'Cd' and attr.size == 3:
                        if vi + 2 < len(vals):
                            geo.point_colors.append((
                                float(vals[vi]), float(vals[vi + 1]), float(vals[vi + 2])
                            ))
                        vi += 3
                    elif attr.name == 'N' and attr.size == 3:
                        if vi + 2 < len(vals):
                            nx, ny, nz = float(vals[vi]), float(vals[vi + 1]), float(vals[vi + 2])
                            # Houdini Y-up → Blender Z-up
                            geo.point_normals.append((nx, -nz, ny))
                        vi += 3
                    elif attr.name == 'uv' and attr.size == 2:
                        if vi + 1 < len(vals):
                            geo.point_uvs.append((float(vals[vi]), float(vals[vi + 1])))
                        vi += 2
                    else:
                        vi += attr.size

    # ── primitives ──────────────────────────────────────────────

    def _parse_primitives(self, info: dict, prim_attribs: list, geo: GEOGeometry):
        """Parse primitive data (Run/Poly format)."""
        n_prims = info.get('NPrims', 0)
        n_prim_attribs = info.get('NPrimAttrib', 0)

        # Check for PrimitiveAttrib keyword
        self._skip_empty()
        line = self._peek().strip()
        if line == 'PrimitiveAttrib':
            self._advance()
            prim_attrib_dict = self._parse_attrib_dict('PrimitiveAttrib', n_prim_attribs)
            # Merge into geo.prim_attribs
            geo.prim_attribs = prim_attrib_dict
        else:
            prim_attrib_dict = prim_attribs

        # Parse primitives
        prim_count = 0
        run_type = None
        run_remaining = 0

        while prim_count < n_prims and self._pos < len(self._lines):
            self._skip_empty()
            if self._pos >= len(self._lines):
                break

            line = self._advance().strip()
            if not line:
                continue

            parts = line.split()

            # Check for "Run N Type" keyword
            if parts[0] == 'Run':
                run_remaining = int(parts[1])
                run_type = parts[2] if len(parts) > 2 else 'Poly'
                continue

            # Parse a primitive line
            prim_type = run_type if run_type else parts[0]

            if prim_type == 'Poly':
                self._parse_poly_line(line, parts, run_type is not None, geo,
                                      prim_attrib_dict, n_prim_attribs)
                prim_count += 1
                if run_remaining > 0:
                    run_remaining -= 1
                    if run_remaining == 0:
                        run_type = None
            else:
                # Non-polygon primitive — skip with warning
                prim_count += 1
                if run_remaining > 0:
                    run_remaining -= 1
                    if run_remaining == 0:
                        run_type = None

    def _parse_poly_line(self, line: str, parts: list, in_run: bool,
                         geo: GEOGeometry, prim_attribs: list, n_prim_attrs: int):
        """Parse a single polygon primitive line."""
        # Format (in_run): " 4 < 0 7 17 16 [131.08844]"
        # Format (standalone): "Poly 4 < 0 7 17 16 [131.08844]"

        if in_run:
            # parts[0] = num_verts, parts[1] = '<' or ':', then indices
            idx = 0
        else:
            # parts[0] = 'Poly', parts[1] = num_verts, parts[2] = '<' or ':'
            idx = 1

        if len(parts) < idx + 3:
            return

        try:
            num_verts = int(parts[idx])
        except ValueError:
            return

        open_close = parts[idx + 1]  # '<' = closed, ':' = open
        is_open = (open_close == ':')

        # Read vertex indices
        verts = []
        idx += 2
        for i in range(num_verts):
            if idx + i < len(parts):
                v_str = parts[idx + i]
                # Stop if we hit '[' (prim attributes)
                if v_str.startswith('['):
                    break
                verts.append(int(v_str))

        geo.faces.append(tuple(verts))
        geo.open_faces.append(is_open)

        # Parse primitive attributes from [...]
        bracket_start = line.find('[')
        bracket_end = line.find(']')
        if bracket_start != -1 and bracket_end != -1:
            attr_str = line[bracket_start + 1:bracket_end]
            attr_vals = attr_str.split()
            for ai, attr in enumerate(prim_attribs):
                if ai < len(attr_vals):
                    val = self._parse_number(attr_vals[ai])
                    geo.prim_attributes.setdefault(attr.name, []).append(val)

    # ── detail attributes ───────────────────────────────────────

    def _parse_detail_attribs(self, info: dict, geo: GEOGeometry):
        """Parse DetailAttrib section."""
        n_attribs = info.get('NAttrib', 0)
        if n_attribs <= 0:
            return

        self._skip_empty()
        line = self._peek().strip()
        if line == 'DetailAttrib':
            self._advance()
        else:
            return

        for _ in range(n_attribs):
            self._skip_empty()
            if self._pos >= len(self._lines):
                break
            line = self._advance().strip()
            if not line or line in ('beginExtra', 'endExtra'):
                break

            parts = line.split()
            if len(parts) < 4:
                continue

            name = parts[0]
            size = int(parts[1])
            attr_type = parts[2]

            if attr_type == 'index':
                # Format: name 1 index N string0 string1 ... value_idx
                table_size = int(parts[3])
                table = parts[4:4 + table_size]
                value_idx = int(parts[4 + table_size]) if 4 + table_size < len(parts) else 0
                if 0 <= value_idx < len(table):
                    geo.detail_attributes[name] = table[value_idx]
                else:
                    geo.detail_attributes[name] = value_idx
            else:
                vals = [self._parse_number(v) for v in parts[3:3 + size]]
                geo.detail_attributes[name] = vals[0] if len(vals) == 1 else vals

    # ── groups ──────────────────────────────────────────────────

    def _parse_groups(self, info: dict, geo: GEOGeometry):
        """Parse point and primitive groups."""
        n_point_groups = info.get('NPointGroups', 0)
        n_prim_groups = info.get('NPrimGroups', 0)

        for _ in range(n_point_groups + n_prim_groups):
            self._skip_empty()
            if self._pos >= len(self._lines):
                break
            line = self._advance().strip()
            if not line or line in ('beginExtra', 'endExtra'):
                break

            parts = line.split()
            if len(parts) < 2:
                continue

            group_type = parts[0]  # 'PointGroup' or 'PrimitiveGroup'
            group_name = parts[1]

            # Next line: element count + bitmask
            self._skip_empty()
            if self._pos >= len(self._lines):
                break
            line = self._advance().strip()
            mask_parts = line.split()
            if not mask_parts:
                continue

            # Bitmask string
            bitmask = mask_parts[-1] if len(mask_parts) > 1 else mask_parts[0]
            indices = [i for i, c in enumerate(bitmask) if c == '1']

            geo.groups[group_name] = {
                'type': 'point' if 'Point' in group_type else 'primitive',
                'indices': indices,
            }

    # ── skip beginExtra/endExtra ────────────────────────────────

    def _skip_extra(self):
        """Skip beginExtra/endExtra block."""
        self._skip_empty()
        if self._pos < len(self._lines) and self._peek().strip() == 'beginExtra':
            self._advance()
            while self._pos < len(self._lines):
                if self._advance().strip() == 'endExtra':
                    break

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_number(s: str):
        """Parse a string as int or float."""
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return s

    # ── main entry ──────────────────────────────────────────────

    def parse(self) -> GEOGeometry:
        """Parse the full GEO file and return GEOGeometry."""
        geo = GEOGeometry()

        info = self._parse_header()

        # Attribute dictionaries
        point_attribs = self._parse_attrib_dict(
            'PointAttrib', info.get('NPointAttrib', 0)
        )
        vertex_attribs = self._parse_attrib_dict(
            'VertexAttrib', info.get('NVertexAttrib', 0)
        )
        geo.point_attribs = point_attribs

        # Points
        self._parse_points(info.get('NPoints', 0), point_attribs, geo)

        # Primitives
        self._parse_primitives(info, [], geo)

        # Detail attributes
        self._parse_detail_attribs(info, geo)

        # Groups
        self._parse_groups(info, geo)

        # Skip extra
        self._skip_extra()

        return geo


# ─────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────

def parse_geo(filepath: str) -> GEOGeometry:
    """
    Parse a Houdini GEO ASCII file and return GEOGeometry.
    This is the main entry point.
    """
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        raise ValueError(f"Cannot read file: {filepath}")

    parser = GEOASCIIParser(text)
    return parser.parse()

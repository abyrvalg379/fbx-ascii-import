# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 Maksim Kovalev
"""FBX ASCII format parser — tokenizer + recursive descent + semantic extractor."""

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class FBXNode:
    """Raw parsed node: name, flat properties list, children list."""
    name: str
    props: list
    children: list = field(default_factory=list)


@dataclass
class FBXMesh:
    uid: int
    name: str
    vertices: list = field(default_factory=list)
    polygon_vertex_index: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    normals_mapping: str = ""
    normals_reference: str = ""
    uv_layers: list = field(default_factory=list)
    material_indices: list = field(default_factory=list)
    material_per_face: bool = False
    model_translation: tuple = (0.0, 0.0, 0.0)
    model_rotation: tuple = (0.0, 0.0, 0.0)
    model_scaling: tuple = (1.0, 1.0, 1.0)


@dataclass
class FBXMaterial:
    uid: int
    name: str
    diffuse_color: tuple = (0.8, 0.8, 0.8)
    specular_color: tuple = (0.0, 0.0, 0.0)
    opacity: float = 1.0
    shininess: float = 20.0


@dataclass
class FBXLight:
    uid: int
    name: str
    light_type: int = 0          # 0=Point, 1=Directional, 2=Spot, 3=Area
    color: tuple = (1.0, 1.0, 1.0)
    intensity: float = 1.0
    decay_type: int = 0
    position: tuple = (0.0, 0.0, 0.0)


@dataclass
class FBXCamera:
    uid: int
    name: str
    fov: float = 45.0
    focal_length: float = 50.0
    aspect_ratio: float = 1.7778
    position: tuple = (0.0, 0.0, 0.0)
    up_vector: tuple = (0.0, 0.0, 1.0)
    target: tuple = (0.0, 0.0, 0.0)


@dataclass
class FBXConnection:
    conn_type: str               # "OO" | "OP"
    source_uid: int
    dest_uid: int
    prop_name: str = ""


@dataclass
class FBXScene:
    up_axis: int = 2
    up_axis_sign: int = 1
    front_axis: int = 1
    front_axis_sign: int = 1
    coord_axis: int = 0
    coord_axis_sign: int = 1
    unit_scale: float = 1.0
    custom_frame_rate: float = 30.0
    meshes: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    lights: list = field(default_factory=list)
    cameras: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    models: dict = field(default_factory=dict)   # uid -> (name, type)
    node_names: dict = field(default_factory=dict)  # uid -> name


# ─────────────────────────────────────────────────────────────────────
#  Low-level parser
# ─────────────────────────────────────────────────────────────────────

_NUM_RE = re.compile(
    r'^[+-]?('
    r'(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?'  # 1, 1.0, .5, 1e-3
    r'|inf|Inf|INF'
    r')'
)


class FBXASCIIParser:
    """Character-level recursive-descent parser for FBX ASCII files."""

    def __init__(self, text: str):
        self._text = text
        self._pos = 0
        self._len = len(text)

    # ── helpers ────────────────────────────────────────────────────

    @property
    def _ch(self) -> str:
        return self._text[self._pos] if self._pos < self._len else '\0'

    def _advance(self, n: int = 1):
        self._pos += n

    def _skip_ws(self):
        """Skip whitespace (except newlines) and comments (; ... \\n)."""
        while self._pos < self._len:
            c = self._text[self._pos]
            if c in (' ', '\t', '\r'):
                self._pos += 1
            elif c == ';':
                # skip to end of line
                nl = self._text.find('\n', self._pos)
                self._pos = nl + 1 if nl != -1 else self._len
            else:
                break

    def _skip_ws_any(self):
        """Skip whitespace including newlines and comments."""
        while self._pos < self._len:
            c = self._text[self._pos]
            if c in (' ', '\t', '\r', '\n'):
                self._pos += 1
            elif c == ';':
                nl = self._text.find('\n', self._pos)
                self._pos = nl + 1 if nl != -1 else self._len
            else:
                break

    # ── token reading ─────────────────────────────────────────────

    def _read_string(self) -> str:
        """Read a quoted string.  Entry: pos is right after the opening quote."""
        self._advance()  # skip opening "
        buf = []
        while self._pos < self._len:
            c = self._text[self._pos]
            if c == '\\':
                self._advance()
                if self._pos < self._len:
                    buf.append(self._text[self._pos])
                    self._advance()
            elif c == '"':
                self._advance()  # skip closing "
                return ''.join(buf)
            else:
                buf.append(c)
                self._advance()
        return ''.join(buf)

    def _read_number(self) -> object:
        """Read a numeric literal (int, long, float, double)."""
        start = self._pos
        has_dot = False
        has_exp = False

        # sign
        if self._ch in ('+', '-'):
            self._advance()

        # digits + dot + exponent
        while self._pos < self._len:
            c = self._text[self._pos]
            if c.isdigit():
                self._advance()
            elif c == '.' and not has_dot:
                has_dot = True
                self._advance()
            elif c in ('e', 'E') and not has_exp:
                has_exp = True
                self._advance()
                if self._pos < self._len and self._text[self._pos] in ('+', '-'):
                    self._advance()
            else:
                break

        # optional suffix: L (long), f/F (float), d/D (double)
        suffix = ''
        if self._pos < self._len and self._text[self._pos] in ('L', 'l', 'f', 'F', 'd', 'D'):
            suffix = self._text[self._pos]
            self._advance()

        raw = self._text[start:self._pos]

        # inf / -inf
        if raw.lower() in ('inf', '-inf', '+inf'):
            return float(raw)

        try:
            if has_dot or has_exp or suffix in ('f', 'F', 'd', 'D'):
                return float(raw)
            return int(raw.rstrip('Ll'))
        except ValueError:
            return float(raw) if raw else 0

    def _read_identifier(self) -> str:
        """Read an identifier (letters, digits, underscores, dots, hyphens)."""
        start = self._pos
        while self._pos < self._len:
            c = self._text[self._pos]
            if c.isalnum() or c in ('_', '.', '-', '/'):
                self._advance()
            else:
                break
        return self._text[start:self._pos]

    # ── top-level node parsing ────────────────────────────────────

    def parse_root(self) -> list:
        """Parse all top-level nodes, return list of FBXNode."""
        nodes = []
        while True:
            self._skip_ws_any()
            if self._pos >= self._len:
                break
            node = self._try_parse_node()
            if node:
                nodes.append(node)
            else:
                # stray character — advance to avoid infinite loop
                self._advance()
        return nodes

    def _try_parse_node(self) -> Optional[FBXNode]:
        """
        Try to parse:   Name : props... { children }
        Returns None if the current position doesn't start a node.
        """
        # Save position in case we need to roll back
        saved = self._pos

        # Read the node name
        if self._ch == '{' or self._ch == '}' or self._ch == '\0':
            return None

        name = self._read_identifier()
        if not name:
            self._pos = saved
            return None

        self._skip_ws()

        # Expect ':'
        if self._ch != ':':
            self._pos = saved
            return None
        self._advance()  # skip ':'

        # Read properties (comma-separated) until '{' or end-of-line then '}'
        props = self._read_properties()

        # Optional child block
        self._skip_ws()
        children = []
        if self._ch == '{':
            self._advance()  # skip '{'
            children = self._parse_children()

        return FBXNode(name=name, props=props, children=children)

    def _read_properties(self) -> list:
        """Read comma-separated properties until a '{' or newline-then-'}'."""
        props = []
        while self._pos < self._len:
            self._skip_ws()

            c = self._ch
            if c in ('{', '}', '\n', '\r', '\0'):
                break

            # Check for 'a:' marker inside an array block — handled elsewhere
            if c == 'a':
                # peek: if it's 'a:' treat as special
                peek_pos = self._pos
                ident = self._read_identifier()
                if ident == 'a':
                    self._skip_ws()
                    if self._ch == ':':
                        # This is an array-value line, not a property
                        self._pos = peek_pos
                        break
                self._pos = peek_pos

            val = self._read_one_property()
            if val is not None:
                props.append(val)
            else:
                break

            self._skip_ws()
            if self._ch == ',':
                self._advance()
            elif self._ch not in ('{', '}', '\n', '\r', '\0'):
                # no comma and not a delimiter — could be end of props
                pass

        return props

    def _read_one_property(self):
        """Read a single property value.  Returns None if nothing to read."""
        c = self._ch
        if c == '"':
            return self._read_string()
        if c in ('+', '-') or c.isdigit():
            return self._read_number()
        if c == '*':
            # Array marker: *N { a: ... }
            return self._read_array()
        if c.isalpha():
            # Boolean flags (T, U, F, Y, N) or identifiers
            ident = self._read_identifier()
            if ident in ('T', 'U', 'Y'):
                return True
            if ident in ('F', 'N'):
                return False
            # Some versions use 'n' for None
            if ident in ('n', 'none', 'None'):
                return None
            return ident
        return None

    def _read_array(self) -> list:
        """Read array: *N { a: v1, v2, ... }"""
        self._advance()  # skip '*'

        # Read count
        count_str = ''
        while self._pos < self._len and self._text[self._pos].isdigit():
            count_str += self._text[self._pos]
            self._advance()

        self._skip_ws_any()
        if self._ch != '{':
            return []
        self._advance()  # skip '{'

        # Skip optional 'a:' marker
        self._skip_ws_any()
        if self._ch == 'a':
            saved = self._pos
            ident = self._read_identifier()
            if ident == 'a':
                self._skip_ws()
                if self._ch == ':':
                    self._advance()  # skip ':'
                else:
                    self._pos = saved
            else:
                self._pos = saved

        # Read values
        values = []
        while self._pos < self._len:
            self._skip_ws_any()
            if self._ch == '}':
                self._advance()
                break
            if self._ch == ',':
                self._advance()
                continue
            val = self._read_one_property()
            if val is not None:
                values.append(float(val) if isinstance(val, (int, float)) else val)
            else:
                break

        return values

    def _parse_children(self) -> list:
        """Parse child nodes inside a '{ ... }' block."""
        children = []
        while self._pos < self._len:
            self._skip_ws_any()
            if self._ch == '}':
                self._advance()
                break
            node = self._try_parse_node()
            if node:
                children.append(node)
            else:
                self._advance()
        return children


# ─────────────────────────────────────────────────────────────────────
#  Semantic extractor
# ─────────────────────────────────────────────────────────────────────

def _get_child(root: FBXNode, name: str) -> Optional[FBXNode]:
    """Find first child node with given name."""
    for child in root.children:
        if child.name == name:
            return child
    return None


def _get_children(root: FBXNode, name: str) -> list:
    """Find all child nodes with given name."""
    return [c for c in root.children if c.name == name]


def _get_prop_value(props: list, index: int, default=None):
    """Safely get property value by index."""
    if index < len(props):
        return props[index]
    return default


def _p70(properties_node: Optional[FBXNode], name: str, default=None):
    """
    Extract a value from Properties70 by property name.
    Format: P: "PropName", "DataType", "SubType", "Label", Value...
    """
    if properties_node is None:
        return default
    for p in properties_node.children:
        if p.name == 'P' and len(p.props) >= 5:
            if p.props[0] == name:
                # Value starts at index 4
                vals = p.props[4:]
                if len(vals) == 1:
                    return vals[0]
                return tuple(vals)
    return default


def _p70_float(properties_node: Optional[FBXNode], name: str, default: float = 0.0) -> float:
    """Extract a single float from Properties70."""
    v = _p70(properties_node, name, default)
    if isinstance(v, (int, float)):
        return float(v)
    return float(default)


def _p70_color(properties_node: Optional[FBXNode], name: str, default=(1.0, 1.0, 1.0)) -> tuple:
    """Extract an RGB color tuple from Properties70."""
    v = _p70(properties_node, name, None)
    if v is None:
        return default
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        return (float(v[0]), float(v[1]), float(v[2]))
    return default


def _p70_vec3(properties_node: Optional[FBXNode], name: str, default=(0.0, 0.0, 0.0)) -> tuple:
    """Extract a Vector3D from Properties70."""
    return _p70_color(properties_node, name, default)


def extract_scene(root_nodes: list) -> FBXScene:
    """Build FBXScene from a list of top-level FBXNodes."""
    scene = FBXScene()

    # Build UID -> name lookup
    uid_name = {}
    uid_type = {}

    for root in root_nodes:
        if root.name == 'Objects':
            for child in root.children:
                if len(child.props) >= 2:
                    uid = int(child.props[0])
                    uid_name[uid] = str(child.props[1])
                    if len(child.props) >= 3:
                        uid_type[uid] = str(child.props[2])
        elif root.name == 'GlobalSettings':
            _parse_global_settings(root, scene)
        elif root.name == 'Connections':
            _parse_connections(root, scene)

    scene.node_names = uid_name
    scene.models = {uid: (name, uid_type.get(uid, '')) for uid, name in uid_name.items()}

    # Build connection index: dest_uid -> list of source_uids
    oo_children_of = {}   # dest -> [sources]
    oo_parent_of = {}     # child -> parent
    oo_materials_of = {}  # model_uid -> [material_uids]
    light_model_uids = {}  # light_uid -> model_uid
    camera_model_uids = {} # camera_uid -> model_uid

    for conn in scene.connections:
        if conn.conn_type == 'OO':
            src = conn.source_uid
            dst = conn.dest_uid
            src_type = uid_type.get(src, '')
            dst_type = uid_type.get(dst, '')

            if src_type == 'Light':
                light_model_uids[src] = dst
            elif src_type == 'Camera' or src_type == 'CameraSwitcher':
                camera_model_uids[src] = dst
            elif src_type == 'Material':
                oo_materials_of.setdefault(dst, []).append(src)
            elif dst_type in ('', 'RootNode') and src_type in ('', 'Model', 'Mesh'):
                oo_parent_of[src] = dst

    # Extract meshes
    objects_node = None
    for root in root_nodes:
        if root.name == 'Objects':
            objects_node = root
            break

    if objects_node:
        # Collect material UIDs that are referenced by models
        material_uids_in_models = set()
        for mat_list in oo_materials_of.values():
            material_uids_in_models.update(mat_list)

        # Parse materials first
        mat_by_uid = {}
        for child in objects_node.children:
            if child.name == 'Material':
                mat = _parse_material(child)
                if mat:
                    scene.materials.append(mat)
                    mat_by_uid[mat.uid] = mat

        # Parse meshes
        for child in objects_node.children:
            if child.name == 'Geometry':
                mesh = _parse_mesh(child, scene)
                if mesh:
                    # Find parent model for transform
                    geo_uid = int(child.props[0]) if child.props else 0
                    # Find model that references this geometry
                    for conn in scene.connections:
                        if conn.conn_type == 'OO' and conn.source_uid == geo_uid:
                            model_uid = conn.dest_uid
                            model_node = _find_object(objects_node, model_uid)
                            if model_node:
                                _apply_model_transform(mesh, model_node)
                            break
                    scene.meshes.append(mesh)

        # Parse lights
        for child in objects_node.children:
            if child.name == 'Light':
                light = _parse_light(child)
                if light:
                    # Find parent model
                    if light.uid in light_model_uids:
                        model_uid = light_model_uids[light.uid]
                        model_node = _find_object(objects_node, model_uid)
                        if model_node:
                            props70 = _get_child(model_node, 'Properties70')
                            light.position = _p70_vec3(props70, 'Lcl Translation')
                    scene.lights.append(light)

        # Parse cameras
        for child in objects_node.children:
            if child.name == 'Camera':
                cam = _parse_camera(child)
                if cam:
                    if cam.uid in camera_model_uids:
                        model_uid = camera_model_uids[cam.uid]
                        model_node = _find_object(objects_node, model_uid)
                        if model_node:
                            props70 = _get_child(model_node, 'Properties70')
                            cam.position = _p70_vec3(props70, 'Lcl Translation')
                    scene.cameras.append(cam)

    return scene


def _parse_global_settings(node: FBXNode, scene: FBXScene):
    """Extract global settings."""
    props70 = _get_child(node, 'Properties70')
    if props70:
        scene.up_axis = int(_p70(props70, 'UpAxis', 2))
        scene.up_axis_sign = int(_p70(props70, 'UpAxisSign', 1))
        scene.front_axis = int(_p70(props70, 'FrontAxis', 1))
        scene.front_axis_sign = int(_p70(props70, 'FrontAxisSign', 1))
        scene.coord_axis = int(_p70(props70, 'CoordAxis', 0))
        scene.coord_axis_sign = int(_p70(props70, 'CoordAxisSign', 1))
        scene.unit_scale = float(_p70(props70, 'UnitScaleFactor', 1.0))
        scene.custom_frame_rate = float(_p70(props70, 'CustomFrameRate', 30.0))


def _parse_connections(node: FBXNode, scene: FBXScene):
    """Extract all connections."""
    for child in node.children:
        if child.name == 'C' and len(child.props) >= 3:
            conn_type = str(child.props[0])
            src = int(child.props[1])
            dst = int(child.props[2])
            prop = str(child.props[3]) if len(child.props) > 3 else ''
            scene.connections.append(FBXConnection(conn_type, src, dst, prop))


def _find_object(objects_node: FBXNode, uid: int) -> Optional[FBXNode]:
    """Find an Object node by UID."""
    for child in objects_node.children:
        if child.props and int(child.props[0]) == uid:
            return child
    return None


def _parse_mesh(geo_node: FBXNode, scene: FBXScene) -> Optional[FBXMesh]:
    """Parse a Geometry node into FBXMesh."""
    if len(geo_node.props) < 2:
        return None
    uid = int(geo_node.props[0])
    name = str(geo_node.props[1]).replace('Geometry::', '')

    mesh = FBXMesh(uid=uid, name=name)

    # Vertices
    verts_node = _get_child(geo_node, 'Vertices')
    if verts_node and verts_node.props:
        raw = verts_node.props[0] if isinstance(verts_node.props[0], list) else verts_node.props
        mesh.vertices = [float(v) for v in raw]

    # Polygon indices
    poly_node = _get_child(geo_node, 'PolygonVertexIndex')
    if poly_node and poly_node.props:
        raw = poly_node.props[0] if isinstance(poly_node.props[0], list) else poly_node.props
        mesh.polygon_vertex_index = [int(v) for v in raw]

    # Normals
    normals_node = _get_child(geo_node, 'LayerElementNormal')
    if normals_node:
        version = _get_child(normals_node, 'Version')
        mapping_node = _get_child(normals_node, 'MappingInformationType')
        mesh.normals_mapping = _get_prop_value(
            mapping_node.props, 0, 'ByPolygonVertex'
        ) if mapping_node else 'ByPolygonVertex'
        ref_node = _get_child(normals_node, 'ReferenceInformationType')
        mesh.normals_reference = _get_prop_value(
            ref_node.props, 0, 'Direct'
        ) if ref_node else 'Direct'

        norms = _get_child(normals_node, 'Normals')
        if norms and norms.props:
            raw = norms.props[0] if isinstance(norms.props[0], list) else norms.props
            mesh.normals = [float(v) for v in raw]

        # Version 102: normals are in XYZW format (4 components per normal)
        ver_val = int(_get_prop_value(version.props, 0, 101)) if version else 101
        if ver_val >= 102 and mesh.normals:
            # Extract XYZ from XYZW — every 4th value is W, skip it
            extracted = []
            for i in range(0, len(mesh.normals), 4):
                extracted.extend(mesh.normals[i:i+3])
            mesh.normals = extracted

    # UV layers
    for uv_node in _get_children(geo_node, 'LayerElementUV'):
        uv_name_node = _get_child(uv_node, 'Name')
        uv_name = str(_get_prop_value(uv_name_node.props, 0, 'map1')) if uv_name_node else 'map1'
        uv_name = uv_name.strip('"')

        uv_mapping_node = _get_child(uv_node, 'MappingInformationType')
        uv_mapping = _get_prop_value(
            uv_mapping_node.props, 0, 'ByPolygonVertex'
        ) if uv_mapping_node else 'ByPolygonVertex'
        uv_ref_node = _get_child(uv_node, 'ReferenceInformationType')
        uv_reference = _get_prop_value(
            uv_ref_node.props, 0, 'IndexToDirect'
        ) if uv_ref_node else 'IndexToDirect'

        uv_data = _get_child(uv_node, 'UV')
        uv_values = []
        if uv_data and uv_data.props:
            raw = uv_data.props[0] if isinstance(uv_data.props[0], list) else uv_data.props
            uv_values = [float(v) for v in raw]

        uv_index = _get_child(uv_node, 'UVIndex')
        uv_indices = []
        if uv_index and uv_index.props:
            raw = uv_index.props[0] if isinstance(uv_index.props[0], list) else uv_index.props
            uv_indices = [int(v) for v in raw]

        mesh.uv_layers.append({
            'name': uv_name,
            'values': uv_values,
            'indices': uv_indices,
            'mapping': uv_mapping,
            'reference': uv_reference,
        })

    # Material indices
    mat_node = _get_child(geo_node, 'LayerElementMaterial')
    if mat_node:
        mat_mapping_node = _get_child(mat_node, 'MappingInformationType')
        mesh.material_per_face = _get_prop_value(
            mat_mapping_node.props, 0, 'AllSame'
        ) != 'AllSame' if mat_mapping_node else False
        mats = _get_child(mat_node, 'Materials')
        if mats and mats.props:
            raw = mats.props[0] if isinstance(mats.props[0], list) else mats.props
            mesh.material_indices = [int(v) for v in raw]

    return mesh


def _apply_model_transform(mesh: FBXMesh, model_node: FBXNode):
    """Apply Model transform to mesh data."""
    props70 = _get_child(model_node, 'Properties70')
    if not props70:
        return
    mesh.model_translation = _p70_vec3(props70, 'Lcl Translation')
    mesh.model_rotation = _p70_vec3(props70, 'Lcl Rotation')
    mesh.model_scaling = _p70_vec3(props70, 'Lcl Scaling', (1.0, 1.0, 1.0))


def _parse_material(mat_node: FBXNode) -> Optional[FBXMaterial]:
    """Parse a Material object node."""
    if len(mat_node.props) < 2:
        return None
    uid = int(mat_node.props[0])
    name = str(mat_node.props[1]).replace('Material::', '')

    props70 = _get_child(mat_node, 'Properties70')
    return FBXMaterial(
        uid=uid,
        name=name,
        diffuse_color=_p70_color(props70, 'DiffuseColor', (0.8, 0.8, 0.8)),
        specular_color=_p70_color(props70, 'SpecularColor', (0.0, 0.0, 0.0)),
        opacity=_p70_float(props70, 'Opacity', 1.0),
        shininess=_p70_float(props70, 'Shininess', 20.0),
    )


def _parse_light(light_node: FBXNode) -> Optional[FBXLight]:
    """Parse a Light object node."""
    if len(light_node.props) < 2:
        return None
    uid = int(light_node.props[0])
    name = str(light_node.props[1]).replace('Light::', '')

    props70 = _get_child(light_node, 'Properties70')
    light_type = 0
    lt = _p70(props70, 'LightType', 0)
    if isinstance(lt, (int, float)):
        light_type = int(lt)

    return FBXLight(
        uid=uid,
        name=name,
        light_type=light_type,
        color=_p70_color(props70, 'Color', (1.0, 1.0, 1.0)),
        intensity=_p70_float(props70, 'Intensity', 1.0),
        decay_type=int(_p70_float(props70, 'DecayType', 0)),
    )


def _parse_camera(cam_node: FBXNode) -> Optional[FBXCamera]:
    """Parse a Camera object node."""
    if len(cam_node.props) < 2:
        return None
    uid = int(cam_node.props[0])
    name = str(cam_node.props[1]).replace('Camera::', '')

    props70 = _get_child(cam_node, 'Properties70')
    return FBXCamera(
        uid=uid,
        name=name,
        fov=_p70_float(props70, 'FieldOfView', 45.0),
        focal_length=_p70_float(props70, 'FocalLength', 50.0),
        aspect_ratio=_p70_float(props70, 'FilmAspectRatio', 1.7778),
        up_vector=_p70_vec3(props70, 'UpVector', (0.0, 1.0, 0.0)),
        target=_p70_vec3(props70, 'InterestPosition', (0.0, 0.0, 0.0)),
    )


# ─────────────────────────────────────────────────────────────────────
#  Axis conversion
# ─────────────────────────────────────────────────────────────────────

def convert_point(scene: FBXScene, point: tuple) -> tuple:
    """
    Convert a point from FBX coordinate system to Blender Z-up.

    3ds Max default: UpAxis=2 (Z), FrontAxis=1 (Y), CoordAxis=0 (X) → Z-up
    Blender: Z-up, Y-forward, X-right

    Common case (3ds Max → Blender): both Z-up, need to negate Y.
    """
    x, y, z = point[0], point[1], point[2]
    scale = scene.unit_scale if scene.unit_scale else 1.0

    # 3ds Max Z-up: swap to Blender Z-up
    if scene.up_axis == 2:
        # Both Z-up — negate Y for handedness
        return (x * scale, -y * scale, z * scale)
    elif scene.up_axis == 1:
        # Y-up (Maya-style) → Z-up
        return (x * scale, z * scale, y * scale)
    else:
        # X-up → Z-up
        return (y * scale, z * scale, x * scale)


def convert_point_no_scale(scene: FBXScene, point: tuple) -> tuple:
    """Convert point without applying unit scale (for normals, directions)."""
    x, y, z = point[0], point[1], point[2]
    if scene.up_axis == 2:
        return (x, -y, z)
    elif scene.up_axis == 1:
        return (x, z, y)
    else:
        return (y, z, x)


# ─────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────

def parse_fbx_ascii(filepath: str) -> FBXScene:
    """
    Parse an FBX ASCII file and return an FBXScene.
    This is the main entry point for the parser.
    """
    # Read with BOM handling
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        raise ValueError(f"Cannot read file: {filepath}")

    # Parse the raw node tree
    parser = FBXASCIIParser(text)
    root_nodes = parser.parse_root()

    # Extract scene data
    scene = extract_scene(root_nodes)
    return scene

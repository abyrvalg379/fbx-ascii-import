# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 Maksim Kovalev
"""GEO/FBX Auto Import — Blender addon for importing Houdini GEO and FBX ASCII files."""

bl_info = {
    "name": "GEO/FBX Auto Import",
    "author": "Maksim Kovalev",
    "version": (2, 0, 1),
    "blender": (4, 2, 0),
    "location": "File > Import > GEO/FBX Auto (.fbx .geo)",
    "description": "Import Houdini GEO and FBX ASCII files with auto-format detection",
    "category": "Import",
}

import os
import time
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper, poll_file_object_drop


# ─────────────────────────────────────────────────────────────────────
#  Format detection
# ─────────────────────────────────────────────────────────────────────

def detect_format(filepath: str) -> str:
    """
    Detect file format by reading the first bytes.
    Returns: 'geo', 'fbx_ascii', or 'fbx_binary'.
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(64)
    except (OSError, IOError):
        return 'unknown'

    # Houdini GEO: starts with "PGEOMETRY"
    if header.startswith(b'PGEOMETRY'):
        return 'geo'

    # FBX ASCII: starts with "; FBX" (comment line)
    if header.startswith(b'; FBX'):
        return 'fbx_ascii'

    # FBX binary: starts with "Kaydara FBX Binary" magic (with spaces before null)
    if header.startswith(b'Kaydara FBX Binary'):
        return 'fbx_binary'

    # Try UTF-8 BOM + PGEOMETRY
    if header.startswith(b'\xef\xbb\xbf') and b'PGEOMETRY' in header[:30]:
        return 'geo'

    return 'unknown'


# ─────────────────────────────────────────────────────────────────────
#  Import operator
# ─────────────────────────────────────────────────────────────────────

class IMPORT_OT_geo_auto(bpy.types.Operator, ImportHelper):
    """Import Houdini GEO or FBX ASCII file with auto-detection"""
    bl_idname = "import_scene.geo_auto"
    bl_label = "Import GEO/FBX"
    bl_options = {'REGISTER', 'UNDO'}

    # File browser filter
    filename_ext = ".fbx"
    filter_glob: StringProperty(
        default="*.fbx;*.geo",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        t0 = time.time()

        filepath = self.filepath

        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}

        fmt = detect_format(filepath)
        filename = os.path.basename(filepath)

        if fmt == 'geo':
            return self._import_geo(filepath, filename, t0)
        elif fmt == 'fbx_ascii':
            return self._import_fbx_ascii(filepath, filename, t0)
        elif fmt == 'fbx_binary':
            return self._import_fbx_binary(filepath, t0)
        else:
            self.report({'ERROR'}, f"Unknown file format: {filename}")
            return {'CANCELLED'}

    def _import_geo(self, filepath, filename, t0):
        """Import Houdini GEO file."""
        from .geo_parser import parse_geo
        from .builder import build_geo_geometry

        try:
            geo = parse_geo(filepath)
        except Exception as e:
            self.report({'ERROR'}, f"GEO parse error: {e}")
            return {'CANCELLED'}

        try:
            collection = build_geo_geometry(geo, filename=filename)
        except Exception as e:
            self.report({'ERROR'}, f"GEO build error: {e}")
            return {'CANCELLED'}

        elapsed = time.time() - t0
        info = []
        if geo.vertices:
            info.append(f"{len(geo.vertices)} verts")
        if geo.faces:
            info.append(f"{len(geo.faces)} faces")
        if geo.groups:
            info.append(f"{len(geo.groups)} groups")

        self.report({'INFO'}, f"GEO imported: {', '.join(info)} ({elapsed:.2f}s)")
        return {'FINISHED'}

    def _import_fbx_ascii(self, filepath, filename, t0):
        """Import FBX ASCII file."""
        from .fbx_parser import parse_fbx_ascii
        from .builder import build_scene

        try:
            fbx_scene = parse_fbx_ascii(filepath)
        except Exception as e:
            self.report({'ERROR'}, f"FBX ASCII parse error: {e}")
            return {'CANCELLED'}

        try:
            collection = build_scene(fbx_scene)
        except Exception as e:
            self.report({'ERROR'}, f"FBX build error: {e}")
            return {'CANCELLED'}

        elapsed = time.time() - t0
        info_parts = []
        if fbx_scene.meshes:
            info_parts.append(f"{len(fbx_scene.meshes)} meshes")
        if fbx_scene.materials:
            info_parts.append(f"{len(fbx_scene.materials)} materials")
        if fbx_scene.lights:
            info_parts.append(f"{len(fbx_scene.lights)} lights")
        if fbx_scene.cameras:
            info_parts.append(f"{len(fbx_scene.cameras)} cameras")

        self.report({'INFO'}, f"FBX ASCII imported: {', '.join(info_parts)} ({elapsed:.2f}s)")
        return {'FINISHED'}

    def _import_fbx_binary(self, filepath, t0):
        """Delegate binary FBX to Blender's built-in importer."""
        try:
            result = bpy.ops.import_scene.fbx(filepath=filepath)
            if result == {'FINISHED'}:
                elapsed = time.time() - t0
                self.report({'INFO'}, f"FBX binary imported via built-in ({elapsed:.2f}s)")
            return result
        except Exception as e:
            self.report({'ERROR'}, f"FBX import failed: {e}")
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Format is auto-detected from file content")
        layout.label(text="Supports: Houdini GEO, FBX ASCII, FBX binary")


# ─────────────────────────────────────────────────────────────────────
#  FileHandler for drag-and-drop
# ─────────────────────────────────────────────────────────────────────

class IO_FH_geo_auto(bpy.types.FileHandler):
    bl_idname = "IO_FH_geo_auto"
    bl_label = "GEO/FBX Auto Import"
    bl_import_operator = "import_scene.geo_auto"
    bl_file_extensions = ".fbx;.geo"

    @classmethod
    def poll_drop(cls, context):
        return poll_file_object_drop(context)


# ─────────────────────────────────────────────────────────────────────
#  Menu integration
# ─────────────────────────────────────────────────────────────────────

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_geo_auto.bl_idname, text="GEO/FBX Auto (.fbx .geo)")


# ─────────────────────────────────────────────────────────────────────
#  Registration — override built-in FBX FileHandler
# ─────────────────────────────────────────────────────────────────────

_builtin_fbx_handler = None

classes = (
    IMPORT_OT_geo_auto,
    IO_FH_geo_auto,
)


def register():
    global _builtin_fbx_handler

    # Unregister built-in FBX FileHandler to avoid conflict
    try:
        from io_scene_fbx import IO_FH_fbx
        _builtin_fbx_handler = IO_FH_fbx
        bpy.utils.unregister_class(IO_FH_fbx)
    except Exception:
        _builtin_fbx_handler = None

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    global _builtin_fbx_handler

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Restore built-in FBX FileHandler
    if _builtin_fbx_handler is not None:
        try:
            bpy.utils.register_class(_builtin_fbx_handler)
        except Exception:
            pass
        _builtin_fbx_handler = None


if __name__ == "__main__":
    register()

# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2026 Maksim Kovalev
"""Build Blender objects from parsed geometry data (FBX + Houdini GEO)."""

import math
import bpy
import mathutils

from .fbx_parser import (
    FBXScene, FBXMesh, FBXMaterial, FBXLight, FBXCamera,
    convert_point, convert_point_no_scale,
)
from .geo_parser import GEOGeometry


# ─────────────────────────────────────────────────────────────────────
#  Mesh builder
# ─────────────────────────────────────────────────────────────────────

def _build_mesh(fbx_mesh: FBXMesh, scene: FBXScene, collection: bpy.types.Collection):
    """Create a Blender mesh + object from FBXMesh data."""
    verts = fbx_mesh.vertices
    poly_idx = fbx_mesh.polygon_vertex_index

    if not verts or not poly_idx:
        return None

    # ── vertices ───────────────────────────────────────────────
    num_verts = len(verts) // 3
    bl_verts = []
    for i in range(num_verts):
        x, y, z = verts[i*3], verts[i*3+1], verts[i*3+2]
        bl_verts.append(convert_point(scene, (x, y, z)))

    # ── polygons ───────────────────────────────────────────────
    # FBX: negative last index = end of face, real index = ~idx
    faces = []
    face = []
    for idx in poly_idx:
        if idx < 0:
            face.append(~idx)
            faces.append(tuple(face))
            face = []
        else:
            face.append(idx)

    if not faces:
        return None

    # ── create mesh ────────────────────────────────────────────
    mesh = bpy.data.meshes.new(fbx_mesh.name)
    mesh.from_pydata(bl_verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(fbx_mesh.name, mesh)
    collection.objects.link(obj)

    # ── normals ────────────────────────────────────────────────
    _apply_normals(mesh, fbx_mesh, scene, faces)

    # ── UV layers ──────────────────────────────────────────────
    _apply_uvs(mesh, fbx_mesh)

    # ── materials ──────────────────────────────────────────────
    _apply_materials(mesh, obj, fbx_mesh, scene, faces)

    # ── model transform ────────────────────────────────────────
    _apply_transform(obj, fbx_mesh, scene)

    return obj


def _apply_normals(mesh: bpy.types.Mesh, fbx_mesh: FBXMesh, scene: FBXScene, faces: list):
    """Apply custom split normals from FBX data."""
    if not fbx_mesh.normals:
        return

    normals = fbx_mesh.normals
    mapping = fbx_mesh.normals_mapping
    reference = fbx_mesh.normals_reference

    try:
        if mapping == 'ByPolygonVertex' and reference == 'Direct':
            # One normal per polygon vertex — perfect for split normals
            split_normals = []
            ni = 0
            for face in faces:
                for _ in face:
                    if ni * 3 + 2 < len(normals):
                        nx, ny, nz = normals[ni*3], normals[ni*3+1], normals[ni*3+2]
                        n = convert_point_no_scale(scene, (nx, ny, nz))
                        split_normals.append(mathutils.Vector(n))
                    ni += 1

            if split_normals:
                mesh.normals_split_custom_set(split_normals)
                mesh.use_auto_smooth = True

        elif mapping == 'ByVertex' and reference == 'Direct':
            # One normal per vertex — use as loop normals (same for all faces)
            split_normals = []
            for face in faces:
                for vi in face:
                    if vi * 3 + 2 < len(normals):
                        nx, ny, nz = normals[vi*3], normals[vi*3+1], normals[vi*3+2]
                        n = convert_point_no_scale(scene, (nx, ny, nz))
                        split_normals.append(mathutils.Vector(n))

            if split_normals:
                mesh.normals_split_custom_set(split_normals)
                mesh.use_auto_smooth = True

    except Exception:
        pass  # normals are non-critical


def _apply_uvs(mesh: bpy.types.Mesh, fbx_mesh: FBXMesh):
    """Apply UV layers from FBX data."""
    for uv_layer_data in fbx_mesh.uv_layers:
        uv_name = uv_layer_data['name']
        uv_values = uv_layer_data['values']
        uv_indices = uv_layer_data['indices']
        uv_mapping = uv_layer_data['mapping']
        uv_reference = uv_layer_data['reference']

        if not uv_values:
            continue

        uv_layer = mesh.uv_layers.new(name=uv_name)
        uv_loops = uv_layer.data

        try:
            if uv_reference == 'IndexToDirect' and uv_indices:
                # UV stored as index-to-direct
                loop_i = 0
                for poly in mesh.polygons:
                    for _ in poly.loop_indices:
                        if loop_i < len(uv_indices):
                            uv_idx = uv_indices[loop_i]
                            if uv_idx * 2 + 1 < len(uv_values):
                                u = uv_values[uv_idx * 2]
                                v = uv_values[uv_idx * 2 + 1]
                                uv_loops[loop_i].uv = (u, v)
                        loop_i += 1

            elif uv_reference == 'Direct':
                # UV values directly per polygon vertex
                loop_i = 0
                for poly in mesh.polygons:
                    for li in poly.loop_indices:
                        if loop_i * 2 + 1 < len(uv_values):
                            u = uv_values[loop_i * 2]
                            v = uv_values[loop_i * 2 + 1]
                            uv_loops[li].uv = (u, v)
                        loop_i += 1

        except (IndexError, ValueError):
            pass  # UV data inconsistency — skip


def _apply_materials(mesh: bpy.types.Mesh, obj: bpy.types.Object,
                     fbx_mesh: FBXMesh, scene: FBXScene, faces: list):
    """Apply materials to mesh polygons."""
    # Find materials connected to the parent model of this geometry
    # Connections: Material -> Model (OO)
    # We need to find the model that this geometry is connected to,
    # then find materials connected to that model

    mat_uids = []
    geo_uid = fbx_mesh.uid

    # Find model UID
    model_uid = None
    for conn in scene.connections:
        if conn.conn_type == 'OO' and conn.source_uid == geo_uid:
            model_uid = conn.dest_uid
            break

    # Find material UIDs for this model
    if model_uid is not None:
        for conn in scene.connections:
            if conn.conn_type == 'OO' and conn.dest_uid == model_uid:
                src_type = scene.models.get(conn.source_uid, ('', ''))[1]
                if src_type == 'Material':
                    mat_uids.append(conn.source_uid)

    # Create Blender materials
    mat_map = {}  # fbx_uid -> bpy_material
    for mat_uid in mat_uids:
        fbx_mat = None
        for m in scene.materials:
            if m.uid == mat_uid:
                fbx_mat = m
                break
        if fbx_mat:
            bl_mat = _create_material(fbx_mat)
            obj.data.materials.append(bl_mat)
            mat_map[mat_uid] = len(obj.data.materials) - 1

    # Assign material indices per face
    if fbx_mesh.material_per_face and fbx_mesh.material_indices:
        for face_i, poly in enumerate(mesh.polygons):
            if face_i < len(fbx_mesh.material_indices):
                mat_idx = fbx_mesh.material_indices[face_i]
                if mat_idx < len(obj.data.materials):
                    poly.material_index = mat_idx
    elif mat_map:
        # AllSame — assign first material to all faces
        first_idx = list(mat_map.values())[0]
        for poly in mesh.polygons:
            poly.material_index = first_idx


def _create_material(fbx_mat: FBXMaterial) -> bpy.types.Material:
    """Create a Blender material with Principled BSDF from FBXMaterial."""
    mat = bpy.data.materials.new(name=fbx_mat.name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Find Principled BSDF
    bsdf = None
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf = node
            break
    if bsdf is None:
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')

    # Base Color (Diffuse)
    r, g, b = fbx_mat.diffuse_color
    bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)

    # Specular
    sr, sg, sb = fbx_mat.specular_color
    specular = (sr + sg + sb) / 3.0
    bsdf.inputs['Specular IOR Level'].default_value = min(specular * 0.5, 1.0)

    # Opacity → Alpha
    if fbx_mat.opacity < 1.0:
        mat.blend_method = 'BLEND' if hasattr(mat, 'blend_method') else None
    bsdf.inputs['Alpha'].default_value = fbx_mat.opacity

    # Shininess → Roughness (inverse approximation)
    shininess = max(fbx_mat.shininess, 0.001)
    roughness = max(0.0, 1.0 - (math.log10(shininess) / math.log10(1000.0)))
    roughness = min(roughness, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness

    return mat


def _apply_transform(obj: bpy.types.Object, fbx_mesh: FBXMesh, scene: FBXScene):
    """Apply Model transform (translation, rotation, scaling)."""
    t = fbx_mesh.model_translation
    r = fbx_mesh.model_rotation
    s = fbx_mesh.model_scaling

    # Convert position
    pos = convert_point(scene, t)
    obj.location = pos

    # Rotation — convert degrees to radians, apply axis conversion
    rx = math.radians(r[0])
    ry = math.radians(r[1])
    rz = math.radians(r[2])

    if scene.up_axis == 2:
        # Z-up: negate Y rotation for handedness
        obj.rotation_euler = (rx, -ry, rz)
    elif scene.up_axis == 1:
        obj.rotation_euler = (rx, rz, ry)
    else:
        obj.rotation_euler = (ry, rz, rx)

    # Scale
    if scene.up_axis == 2:
        obj.scale = (s[0], s[1], s[2])
    else:
        obj.scale = (s[0], s[2], s[1])


# ─────────────────────────────────────────────────────────────────────
#  Light builder
# ─────────────────────────────────────────────────────────────────────

_LIGHT_TYPE_MAP = {
    0: 'POINT',
    1: 'SUN',
    2: 'SPOT',
    3: 'AREA',
}


def _build_light(fbx_light: FBXLight, scene: FBXScene,
                 collection: bpy.types.Collection):
    """Create a Blender light + object from FBXLight."""
    light_type = _LIGHT_TYPE_MAP.get(fbx_light.light_type, 'POINT')
    light = bpy.data.lights.new(name=fbx_light.name, type=light_type)

    r, g, b = fbx_light.color
    light.color = (r, g, b)
    light.energy = fbx_light.intensity * 100  # rough conversion

    # Decay
    if fbx_light.decay_type >= 2:
        light.use_shadow = True

    obj = bpy.data.objects.new(fbx_light.name, light)
    collection.objects.link(obj)

    # Position
    pos = convert_point(scene, fbx_light.position)
    obj.location = pos

    return obj


# ─────────────────────────────────────────────────────────────────────
#  Camera builder
# ─────────────────────────────────────────────────────────────────────

def _build_camera(fbx_camera: FBXCamera, scene: FBXScene,
                  collection: bpy.types.Collection):
    """Create a Blender camera + object from FBXCamera."""
    cam = bpy.data.cameras.new(name=fbx_camera.name)

    # FOV — Blender uses radians for FOV
    cam.angle = math.radians(fbx_camera.fov)

    # Focal length (if provided)
    if fbx_camera.focal_length > 0:
        cam.lens = fbx_camera.focal_length

    obj = bpy.data.objects.new(fbx_camera.name, cam)
    collection.objects.link(obj)

    # Position
    pos = convert_point(scene, fbx_camera.position)
    obj.location = pos

    # Point camera at target
    target = convert_point(scene, fbx_camera.target)
    direction = mathutils.Vector(target) - mathutils.Vector(pos)
    if direction.length > 0.001:
        rot = direction.to_track_quat('-Z', 'Y')
        obj.rotation_euler = rot.to_euler()

    return obj


# ─────────────────────────────────────────────────────────────────────
#  Hierarchy builder
# ─────────────────────────────────────────────────────────────────────

def _build_hierarchy(scene: FBXScene, obj_by_uid: dict):
    """Apply parent-child relationships from FBX Connections."""
    for conn in scene.connections:
        if conn.conn_type != 'OO':
            continue
        child_uid = conn.source_uid
        parent_uid = conn.dest_uid

        child_obj = obj_by_uid.get(child_uid)
        parent_obj = obj_by_uid.get(parent_uid)

        if child_obj and parent_obj and child_obj != parent_obj:
            child_obj.parent = parent_obj


# ─────────────────────────────────────────────────────────────────────
#  Main entry point
# ─────────────────────────────────────────────────────────────────────

def build_scene(scene: FBXScene, collection_name: str = "FBX_ASCII_Import"):
    """
    Build a complete Blender scene from an FBXScene.
    Returns the collection with imported objects.
    """
    # Create import collection
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)

    obj_by_uid = {}

    # ── meshes ─────────────────────────────────────────────
    for fbx_mesh in scene.meshes:
        obj = _build_mesh(fbx_mesh, scene, collection)
        if obj:
            obj_by_uid[fbx_mesh.uid] = obj

    # ── materials are already assigned to meshes ───────────

    # ── lights ─────────────────────────────────────────────
    for fbx_light in scene.lights:
        obj = _build_light(fbx_light, scene, collection)
        if obj:
            obj_by_uid[fbx_light.uid] = obj

    # ── cameras ────────────────────────────────────────────
    for fbx_camera in scene.cameras:
        obj = _build_camera(fbx_camera, scene, collection)
        if obj:
            obj_by_uid[fbx_camera.uid] = obj

    # ── hierarchy ──────────────────────────────────────────
    _build_hierarchy(scene, obj_by_uid)

    return collection


# ─────────────────────────────────────────────────────────────────────
#  Houdini GEO builder
# ─────────────────────────────────────────────────────────────────────

def build_geo_geometry(geo: GEOGeometry, collection_name: str = "GEO_Import",
                       filename: str = ""):
    """
    Build a Blender mesh from Houdini GEO geometry.
    Returns the collection with the imported object.
    """
    if not geo.vertices or not geo.faces:
        return None

    # Create import collection
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)

    # Object name from filename
    obj_name = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    obj_name = obj_name.rsplit('.', 1)[0] if '.' in obj_name else obj_name
    if not obj_name:
        obj_name = "GEO_Import"

    # ── create mesh ────────────────────────────────────────────
    mesh = bpy.data.meshes.new(obj_name)
    mesh.from_pydata(geo.vertices, [], geo.faces)
    mesh.update()

    obj = bpy.data.objects.new(obj_name, mesh)
    collection.objects.link(obj)

    # ── normals ────────────────────────────────────────────────
    if geo.point_normals:
        try:
            # GEO normals are per-point — expand to per-loop
            split_normals = []
            for face in geo.faces:
                for vi in face:
                    if vi < len(geo.point_normals):
                        n = geo.point_normals[vi]
                        split_normals.append(mathutils.Vector(n))
                    else:
                        split_normals.append(mathutils.Vector((0, 0, 1)))

            mesh.normals_split_custom_set(split_normals)
            mesh.use_auto_smooth = True
        except Exception:
            pass

    # ── vertex colors ──────────────────────────────────────────
    if geo.point_colors:
        try:
            color_attr = mesh.color_attributes.new(
                name='Cd', type='BYTE_COLOR', domain='POINT'
            )
            for i, (r, g, b) in enumerate(geo.point_colors):
                if i < len(color_attr.data):
                    color_attr.data[i].color = (r, g, b, 1.0)
        except Exception:
            pass

    # ── UV ─────────────────────────────────────────────────────
    if geo.point_uvs:
        try:
            uv_layer = mesh.uv_layers.new(name='uv')
            # UVs are per-point in GEO — assign to all loops referencing that point
            for poly in mesh.polygons:
                for li, vi in zip(poly.loop_indices, poly.vertices):
                    if vi < len(geo.point_uvs):
                        u, v = geo.point_uvs[vi]
                        uv_layer.data[li].uv = (u, v)
        except Exception:
            pass

    return collection

# GEO/FBX Auto Import

![GEO/FBX Auto Import](cover.png)

Blender addon for importing **ASCII FBX** (the format Houdini exports by default) and **Houdini .geo** files, with automatic format detection.

*Документация на русском: [README.ru.md](README.ru.md)*

## The problem

Houdini's FBX export ships in ASCII format by default — and Blender's built-in importer rejects it with *"ASCII FBX files are not supported"*. The usual workaround is an extra conversion step (Autodesk FBX Converter, re-export). This addon reads ASCII FBX directly in Blender.

## Features

**Auto format detection** — just drop the file, no guessing:

| Detected format | Import |
|---|---|
| Houdini GEO (ASCII) | built-in parser |
| FBX ASCII (Houdini, 3ds Max) | built-in parser |
| FBX binary | delegated to Blender's built-in importer |

**FBX ASCII:** meshes with normals and UVs, multi-materials (→ Principled BSDF), lights (Point / Sun / Spot / Area), cameras.

**Houdini GEO:** vertices, polygons (closed & open), normals, UVs, vertex colors (Cd), primitive / detail attributes, point / primitive groups.

**Drag-and-drop:** drop a `.fbx` or `.geo` file into the 3D Viewport — the format is detected from file content. Binary FBX keeps working: it is passed to the built-in importer.

## Installation

Requires Blender 4.2+

1. Download `fbx_ascii_import.zip` from the [latest release](https://github.com/abyrvalg379/fbx-ascii-import/releases/latest)
2. Blender → Edit → Preferences → Add-ons → Install…
3. Enable **Import-Export: GEO/FBX Auto Import**

## Usage

- **File → Import → GEO/FBX Auto (.fbx .geo)**
- or drag-and-drop into the 3D Viewport

## Limitations

- No bones / skin deformers / animation — meshes, lights and cameras only
- ASCII dialects tested: Houdini 20.x, 3ds Max

## License

GPL-2.0-or-later — see [LICENSE](LICENSE).

Author: **Maksim Kovalev**

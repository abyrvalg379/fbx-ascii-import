# GEO/FBX Auto Import

Blender addon for importing **ASCII FBX** (the format Houdini exports by default) and **Houdini .geo** files, with automatic format detection.

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

1. Download `fbx_ascii_import.zip` from [Releases](../../releases)
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

Author: **Maksim Kovalev** — VVERH Studio

---

## Русский

Аддон Blender для импорта **ASCII FBX** (формат по умолчанию в экспорте Houdini) и **Houdini .geo** с автоопределением формата.

## Проблема

Houdini по умолчанию экспортирует FBX в ASCII — а встроенный импортёр Blender отвечает «ASCII FBX files are not supported». Обычный обход — отдельный шаг конвертации (Autodesk FBX Converter, переэкспорт). Аддон читает ASCII FBX прямо в Blender.

## Возможности

**Автоопределение формата** — просто перетащите файл, формат определяется по содержимому:

| Формат | Импорт |
|---|---|
| Houdini GEO (ASCII) | свой парсер |
| FBX ASCII (Houdini, 3ds Max) | свой парсер |
| FBX binary | встроенный импортёр Blender |

**FBX ASCII:** меши с нормалями и UV, мультиматериалы (→ Principled BSDF), свет (Point / Sun / Spot / Area), камеры.

**Houdini GEO:** вершины, полигоны (closed/open), нормали, UV, vertex colors (Cd), primitive/detail атрибуты, point/primitive группы.

**Drag-and-drop:** перетащите `.fbx` или `.geo` в 3D Viewport. Бинарный FBX продолжает работать — уходит во встроенный импортёр.

## Установка

Требуется Blender 4.2+

1. Скачайте `fbx_ascii_import.zip` со страницы [Releases](../../releases)
2. Blender → Edit → Preferences → Add-ons → Install…
3. Включите **Import-Export: GEO/FBX Auto Import**

## Использование

- **File → Import → GEO/FBX Auto (.fbx .geo)**
- или drag-and-drop в 3D Viewport

## Ограничения

- Без костей / скина / анимации — только меши, свет и камеры
- Протестированные диалекты ASCII: Houdini 20.x, 3ds Max

## Лицензия

GPL-2.0-or-later — см. [LICENSE](LICENSE).

Автор: **Maksim Kovalev** — VVERH Studio

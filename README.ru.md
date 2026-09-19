# GEO/FBX Auto Import

Аддон Blender для импорта **ASCII FBX** (формат по умолчанию в экспорте Houdini) и **Houdini .geo** с автоопределением формата.

*English documentation: [README.md](README.md)*

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

Автор: **Maksim Kovalev**

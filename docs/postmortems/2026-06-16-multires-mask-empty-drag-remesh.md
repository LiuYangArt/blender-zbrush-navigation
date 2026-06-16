# 2026-06-16 Multires Mask Empty Drag Remesh

## Symptom

With a Multires object that already had a sculpt mask, empty-space `Ctrl+drag` cleared the mask and immediately ran voxel remesh.

Expected behavior: if a mask exists, empty-space `Ctrl+drag` should only clear the mask. If no mask exists, it should run voxel remesh.

## Root Cause

The empty-drag remesh gate only checked the base mesh `.sculpt_mask` attribute. Blender Multires sculpt masks are not exposed through that attribute or the evaluated mesh, so the add-on could misread a masked Multires object as unmasked.

The first attempted fix blocked empty-drag remesh for every Multires object, which was too broad: unmasked Multires objects still need to remesh.

## Fix

The mask operator now keeps runtime mask state for objects changed through the add-on's mask operations. Empty-drag remesh checks that runtime state first, then falls back to the mesh `.sculpt_mask` attribute for normal mesh masks.

Clearing a mask and running empty-drag remesh both clear the runtime mask state. Applying positive lasso/box masks and inverting masks mark the active object as masked.

## Regression Entry

Run:

```powershell
python scripts\validate_addon.py
git diff --check
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```
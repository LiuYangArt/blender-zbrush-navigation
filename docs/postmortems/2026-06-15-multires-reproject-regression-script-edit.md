# 2026-06-15 Multires Reproject Regression Script Edit

## Symptom

Blender background regression failed while adding the Multires detail projection test.

First failure: the test compared a live modifier wrapper by object identity. Blender can return a different Python wrapper for the same modifier, so identity comparison was too strict.

Second failure: the Windows edit command inserted a literal `\n` into Python code, causing a syntax error.

Third failure: the source-preservation assertion compared the source after projection with the pre-offset target-derived mesh positions instead of comparing source before/after operator execution.

## Root Cause

The regression assertion used wrapper identity instead of checking the modifier lookup result. The follow-up edit used a literal replacement string with escaped newlines instead of real newline content.

## Fix

The test now verifies that the `Multires` modifier still exists and has type `MULTIRES`. The malformed literal newline was replaced with actual Python lines. The source-preservation baseline is now captured after constructing the high-mesh source and before executing the operator.

## Regression Entry

Run:

```powershell
python scripts\validate_addon.py
git diff --check
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```
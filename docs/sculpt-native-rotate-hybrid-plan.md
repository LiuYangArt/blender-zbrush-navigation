# Sculpt Native Rotate Hybrid Plan

## Goal
在 Sculpt Mode 中恢复原生旋转流畅度，同时保留当前 ZBrush 风格导航体验中最关键的部分。

最终目标：

- `RMB drag`: Blender 原生 `view3d.rotate`。
- `Ctrl + RMB drag`: Blender 原生 `view3d.zoom`。
- `Alt + RMB drag`: Blender 原生 `view3d.move`。
- `Shift + RMB`: 插件自定义 ZBrush-style snap。
- 进入 Sculpt Mode 时临时开启 `Orbit Around Selection`，退出时恢复用户原设置。

## Why
当前 `RMB` 旋转由 `operators/navigation_modal.py` 的 Python modal 接管，每次 `MOUSEMOVE` 手动更新 `RegionView3D.view_rotation/view_location`。

这能实现自定义旋转中心和 Shift snap，但在 Sculpt Mode 下明显不如 Blender 原生 C 端 `view3d.rotate` 流畅。

`pan` 和 `zoom` 现在已经走原生 operator，所以没有同样的帧率问题。

## Decision
采用混合模式，不继续优化 Python rotate：

1. 普通旋转交还给 `view3d.rotate`。
2. 通过 Blender Preference 的 `Orbit Around Selection` 实现围绕当前选择/活动对象旋转。
3. `Shift + RMB` 保留插件自定义 snap，作为单独入口。
4. 不尝试在原生 rotate modal 运行中接管 Shift 并调用插件 snap。

原因：原生 `view3d.rotate` modal 内部事件不能稳定切换到插件自定义 Python snap。若插件接管 rotate modal，旋转流畅度问题会回来。

## Preference Runtime State
进入 Sculpt Mode 且插件启用时：

- 记录 `bpy.context.preferences.inputs.use_mouse_emulate_3_button` 原值。
- 记录 `bpy.context.preferences.inputs.use_rotate_around_active` 原值。
- 设置 `use_mouse_emulate_3_button = False`。
- 设置 `use_rotate_around_active = True`。

退出 Sculpt Mode、禁用插件、`unregister()`、文件加载前恢复：

- 恢复 `use_mouse_emulate_3_button` 原值。
- 恢复 `use_rotate_around_active` 原值。

注意：这是全局 Blender Preference，只能临时修改，必须和 runtime keymap 一起恢复。

## Keymap Plan
在 `functions/navigation_state.py` 的 runtime keymap 中调整：

- `RMB` 从 `zbrush_navigation.zbrush_rotate_modal` 改为 `view3d.rotate`。
- `Ctrl + RMB` 保持 `view3d.zoom`。
- `Alt + RMB` 保持 `view3d.move`。
- `Shift + RMB` 保持或改为插件自定义 snap operator/modal。

如果当前 `zbrush_navigation.zbrush_rotate_modal` 只剩 snap 用途，应后续重命名或拆分，避免名称误导。

## Snap Behavior
`Shift + RMB` 的目标仍然是 ZBrush-style snap：

- snap 到最近固定轴向视图。
- 保留当前 Perspective / Orthographic 状态。
- 支持按拖动方向切换下一个轴向视图。

不要求支持“普通 RMB 原生旋转过程中按下 Shift 后切入插件 snap”。这条不作为目标。

## Implementation Steps
1. 扩展 `_RuntimeState`，增加 `original_use_rotate_around_active`。
2. 在 `apply_zbrush_navigation()` 中记录并强制开启 `use_rotate_around_active`。
3. 在 `restore_zbrush_navigation()` 中恢复该值。
4. 修改 `_add_zbrush_keymap_items()`：普通 `RMB` 绑定 `view3d.rotate`。
5. 保留 `Shift + RMB` 绑定到插件 snap 行为。
6. 更新 `scripts/blender_regression_check.py`，覆盖 preference 记录/恢复和 keymap 目标。
7. 人工验证 Sculpt Mode 中 RMB 旋转流畅度、旋转中心、Shift snap 手感。

## Verification
最小自动验证：

```powershell
python scripts\validate_addon.py
python scripts\blender_regression_check.py
git diff --check
```

必要人工验证：

- Sculpt Mode 中 `RMB drag` 旋转接近原生流畅。
- `Orbit Around Selection` 在进入 Sculpt Mode 时开启，退出后恢复用户原状态。
- `Ctrl + RMB` zoom、`Alt + RMB` pan 不退化。
- `Shift + RMB` snap 仍符合当前 ZBrush-style 预期。

## Do Not Do
- 不要用 Python modal 继续实现普通 rotate。
- 不要永久修改用户 Preference。
- 不要粗暴修改 `keyconfigs.user`。
- 不要在原生 rotate modal 内强行调用插件 snap。
- 不要吞掉 keymap 或 preference 恢复错误。
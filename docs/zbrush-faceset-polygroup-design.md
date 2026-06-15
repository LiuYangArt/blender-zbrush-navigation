# ZBrush-style Face Set / Polygroup Visibility Design

## Goal

让 Blender Face Set 在 Sculpt Mode 中尽量接近 ZBrush Polygroup 的 `Ctrl + Shift` 可见性工作流。

重点不是重写 Face Set 数据结构，而是用插件把 Blender 原生 Face Set / Visibility operator 组织成 ZBrush 手感：

- `Ctrl + Shift + LMB click Face Set`：只显示命中的 Face Set。
- `Ctrl + Shift + LMB click 空白`：显示全部。
- `Ctrl + Shift + LMB drag 命中物体`：新增 Face Set。
- `Ctrl + Shift + LMB drag 空白区域`：反转可见性。
- `Ctrl + Shift + Alt + LMB click Face Set`：隐藏命中的 Face Set。
- `Ctrl + Shift + Alt + LMB drag 命中物体`：可选第二阶段，隐藏/切割可见性，不作为第一版核心。

## Existing Mask Code To Reuse

当前 `operators/mask.py` 已经有大量可复用代码，不应重新发明：

- modal 输入框架：`ZNAV_OT_mask_pen_input` / `ZNAV_OT_mask_lasso_input` 的 `invoke()`、`modal()`、`_cleanup()`。
- click / drag 区分：`DEFAULT_MASK_DRAG_THRESHOLD_PIXELS`、`_get_mask_drag_threshold()`。
- 鼠标命中 sculpt object：`_event_hits_active_object()`、`_screen_point_hits_active_object()`。
- 框选 / 套索命中检测：`_box_hits_active_object()`、`_lasso_hits_active_object()`、`_polygon_hits_active_object()`。
- 选区移动手感：按住 `Space` 移动 box/lasso 选区。
- overlay 绘制：`_draw_filled_polygon_overlay()`、box/lasso overlay 颜色和边框逻辑。
- native gesture 调用：mask 已经验证了“自定义 modal 收集路径，释放时调用 Blender 原生 gesture”的模式。

建议先抽公共模块：

- `functions/view3d_hit_test.py`：raycast、polygon hit test、box bounds、point-in-polygon。
- `functions/gesture_overlay.py`：box/lasso overlay 绘制。
- 或者第一版先在 `operators/faceset.py` 复制少量函数，等稳定后再抽，避免一次性重构影响 mask。

## Blender Native Operators

本方案优先使用原生 operator：

- `bpy.ops.sculpt.face_set_change_visibility(mode="TOGGLE", active_face_set=id)`
- `bpy.ops.sculpt.face_set_change_visibility(mode="SHOW_ACTIVE", active_face_set=id)`
- `bpy.ops.sculpt.face_set_change_visibility(mode="HIDE_ACTIVE", active_face_set=id)`
- `bpy.ops.paint.visibility_invert()`
- `bpy.ops.sculpt.face_set_box_gesture(xmin=..., xmax=..., ymin=..., ymax=..., wait_for_input=False, use_front_faces_only=...)`
- `bpy.ops.sculpt.face_set_lasso_gesture(path=..., use_front_faces_only=...)`
- `bpy.ops.sculpt.face_set_line_gesture(xstart=..., xend=..., ystart=..., yend=..., flip=..., use_front_faces_only=..., use_limit_to_segment=...)`
- `bpy.ops.sculpt.face_set_polyline_gesture(path=..., use_front_faces_only=...)`
- `bpy.ops.sculpt.face_sets_create(mode="VISIBLE" | "MASKED" | "ALL" | "SELECTION")` 仅作为备用，不做第一选择。

注意：`face_set_change_visibility` 文档只列出 `TOGGLE / SHOW_ACTIVE / HIDE_ACTIVE`，没有原生 `SHOW_ALL`。显示全部可能需要另找 Blender operator 或走 visibility 恢复方案，实施前必须真实验证。

## Proposed Operator

新增：`operators/faceset.py`

```python
class ZNAV_OT_faceset_polygroup_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.faceset_polygroup_input"
    bl_label = "ZBrush Face Set Polygroup Input"
    bl_options = {"REGISTER", "UNDO"}
```

Keymap：

- `Ctrl + Shift + LEFTMOUSE PRESS` -> `zbrush_navigation.faceset_polygroup_input`
- `Ctrl + Shift + Alt + LEFTMOUSE PRESS` -> 同 operator，运行时用 `event.alt` 判断 hide/subtract 语义。

必须加入 `functions/navigation_state.py` 的 runtime addon Sculpt keymap，和 mask 一样只在 Sculpt Mode 生效，退出 Sculpt Mode 删除。

## Gesture Rules

### Click Hit Face Set

流程：

1. raycast 鼠标位置，必须命中 active sculpt object。
2. 从命中的 face index 读取 Face Set id。
3. 无 Alt：只显示该 Face Set。
4. 有 Alt：隐藏该 Face Set。

实现风险：Blender Python 中如何从 hit face index 稳定读取 Face Set attribute，需要先做探针脚本确认。候选是 mesh attribute / sculpt face set layer，但不能凭空写死。

### Click Empty

流程：

1. raycast 未命中 active sculpt object。
2. 没有拖拽，释放 LMB。
3. 执行“显示全部”。

如果 Blender 没有直接 show all operator，第一版可临时采用：记录 visible 状态不可行则不实现，或通过现有 visibility operator 探索。不要 silent fallback。

### Drag Hit Object: New Face Set

这是本次新增需求。

流程：

1. `Ctrl + Shift + LMB` 按下。
2. 鼠标移动超过阈值后进入 box 或 lasso gesture。
3. 释放时，如果 box/lasso 命中 active sculpt object：新增 Face Set。
4. 如果没有命中 active sculpt object：反转 visibility。

第一版建议只做 Box，原因：Blender 已有 `sculpt.face_set_box_gesture`，参数简单、行为更容易验证。

第二阶段再做 Lasso：复用 mask lasso path，调用 `sculpt.face_set_polyline_gesture(path=...)`。

### Drag Empty: Invert Visibility

流程：

1. 拖拽结束后，命中检测为 false。
2. 执行 `bpy.ops.paint.visibility_invert()`。
3. 这对应 ZBrush 里空白拖拽反转可见性。

必须验证它是否只影响当前 Sculpt object，不能影响非当前对象或编辑模式状态。

## Overlay Rules

Face Set drag 框选/套索 overlay 必须参考现有 `Ctrl + drag` mask 工具实现：

- 复用 `operators/mask.py` 的 `SpaceView3D.draw_handler_add(..., "WINDOW", "POST_PIXEL")` 绘制路径。
- 复用 `_draw_filled_polygon_overlay()` 的半透明填充 + 白色边框模式。
- `Ctrl + Shift + drag`：绿色半透明填充，白色边框，表示新增 / show / isolate 类操作。
- `Ctrl + Alt + Shift + drag`：红色半透明填充，白色边框，表示隐藏 / subtract 类操作。
- overlay 应随 Alt 状态实时变色，和 mask 工具中 `_update_subtract_mode()` 的行为一致。
- 第一版 Box 即可；Lasso 第二阶段也使用同一套颜色规则。

建议颜色常量：

```python
FACESET_ADD_OVERLAY_FILL_COLOR = (0.0, 0.85, 0.25, 0.28)
FACESET_HIDE_OVERLAY_FILL_COLOR = (1.0, 0.05, 0.02, 0.28)
FACESET_OVERLAY_OUTLINE_COLOR = (1.0, 1.0, 1.0, 0.75)
```
## UI Settings

建议和 mask 工具一样放在 View3D Sidebar 的 `ZBrush Nav` 面板里，让用户切换当前 Face Set 手势；不要给每个工具单独占快捷键。

- `Face Set Gesture`: `BOX` / `LASSO` / `LINE` / `POLYLINE`。
- `Front Faces Only`: bool，默认 `False` 或沿用 Blender 当前工具默认值。
- `Line Limit To Segment`: bool，仅 `LINE` 模式显示，对应 `use_limit_to_segment`。

统一入口仍然是：

- `Ctrl + Shift + LMB drag`：按当前 `Face Set Gesture` 新增 Face Set，绿色半透明白边框。
- `Ctrl + Alt + Shift + LMB drag`：按当前 `Face Set Gesture` 执行 hide/subtract 语义，红色半透明白边框。

推荐默认值：`BOX`。原因是它最接近 ZBrush 常用矩形框选，参数稳定，也最容易复用现有 mask box overlay。

如果后续需要更快切换，可再加一个 operator：`zbrush_navigation.cycle_faceset_gesture`，例如绑定到面板按钮或可选快捷键；第一版不默认抢键。

## Implementation Phases

### Phase 0: Probe

写一个临时 Blender background / console 探针，确认：

- raycast hit face index 能否读到 Face Set id。
- `face_set_change_visibility(active_face_set=id)` 是否能对指定 id 生效。
- 是否存在可靠 show all visibility operator。
- `face_set_box_gesture(wait_for_input=False, xmin=..., ...)` 是否能由插件直接调用。

### Phase 1: Keymap + Empty Drag Invert

只加 operator 和 keymap，不处理 hit Face Set：

- drag 命中物体：按 Sidebar 当前 `Face Set Gesture` 调用对应 `face_set_*_gesture` 新增 Face Set。
- drag 未命中物体：调用 `paint.visibility_invert()`。
- click 先不处理或 report warning。

这一步验证 Ctrl+Shift drag 主链路和 mask/navigation 是否冲突。

### Phase 2: Click Visibility

补：

- click hit Face Set -> solo。
- Alt click hit Face Set -> hide。
- click empty -> show all。

### Phase 3: Lasso / Line / Polyline Gesture

支持 Blender 原生 Face Set 选择工具，并统一复用同一套 Ctrl+Shift modal：

- `BOX`：复用 mask box 起点/终点和 overlay，调用 `face_set_box_gesture`。
- `LASSO`：复用 mask lasso path，调用 `face_set_lasso_gesture`。
- `LINE`：记录起点/终点，调用 `face_set_line_gesture`；Alt 或拖拽方向可用于 `flip`，具体要真机验证。
- `POLYLINE`：复用 path 收集逻辑，调用 `face_set_polyline_gesture`。
- 空白 drag 统一反转 visibility。
- 支持 `Space` 移动选区。

## Verification

每阶段至少运行：

```powershell
python scripts\validate_addon.py
git diff --check
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```

真实 View3D 必测：

- 进入 Sculpt Mode 后 RMB/Ctrl RMB/Alt RMB/Shift RMB 仍正常。
- 现有 Ctrl drag mask 不退化。
- Ctrl+Shift drag 命中模型能新增 Face Set，并显示绿色半透明白边框。
- Ctrl+Shift drag 空白能 invert visibility。
- Ctrl+Shift click Face Set 能 solo。
- Ctrl+Shift Alt click Face Set 能 hide。
- Ctrl+Alt+Shift drag 显示红色半透明白边框。
- 退出 Sculpt Mode 后 runtime keymap 清理干净。

## Stop Conditions

出现以下任一情况，停止继续加功能：

- navigation keymap 丢失或优先级异常。
- mask Ctrl drag 行为退化。
- Face Set id 读取方式不稳定。
- visibility 无法恢复或 show all 无可靠方案。
- Blender crash。

## First Implementation Recommendation

先做最小可用闭环：

1. Sidebar 增加 `Face Set Gesture`，但默认先选 `BOX`。
2. `Ctrl+Shift drag hit` -> 根据当前 gesture 调用对应 `face_set_*_gesture` 新增 Face Set。
3. `Ctrl+Shift drag empty` -> `paint.visibility_invert()`。
4. 第一轮实现 `BOX`，随后补 `LASSO / LINE / POLYLINE`。
5. 保留 click visibility 到第二阶段。

原因：这条链路最贴近本次补充需求，也最大程度复用 mask 已验证的 drag / hit test / overlay 模式。
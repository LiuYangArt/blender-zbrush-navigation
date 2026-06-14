# ZBrush Sculpt Navigation Follow-up Plan

## Goal
在 Sculpt Mode 中继续靠插件临时接管导航快捷键，但行为尽量贴近 ZBrush：

- `P`: 切换 Perspective / Orthographic。
- `Shift + RMB drag`: snap viewport 到最近的固定视角。
- RMB 旋转过程中按住 Shift：也能触发同样的 snap 行为。
- snap 必须保留当前透视/正交状态，不强制切到 Orthographic。
- 退出 Sculpt Mode 时恢复用户原 keymap 和 `Emulate 3 Button Mouse`。

## Current Baseline
当前实现入口主要在：

- `functions/navigation_state.py`
- `operators/navigation.py`
- `properties/settings.py`

现有逻辑：

- 进入 Sculpt Mode 时临时修改 user keyconfig。
- 给 user `3D View` / `Sculpt` keymap 添加：
  - RMB -> `view3d.rotate`
  - Ctrl RMB -> `view3d.zoom`
  - Alt RMB -> `view3d.move`
- 退出 Sculpt Mode 时删除插件临时添加项并恢复原状态。
- 已有 keymap item 需要用签名匹配恢复，不要保存 live `KeyMapItem` 引用。

## Phase 1: Add P Perspective/Orthographic Toggle

### Expected Behavior
`P` 是 Sculpt Mode 专属 keymap 项，不需要走进入/退出 Sculpt Mode 的临时覆盖流程。

直接在插件注册时添加到 Blender user `Sculpt` keymap：

- `P` -> `view3d.view_persportho`

因为它只存在于 `Sculpt` keymap，所以不会影响 Object/Edit/Pose 等其它模式。

### Implementation Notes
不要放进 `_add_zbrush_keymap_items()`，也不要在退出 Sculpt Mode 时删除。

建议新增独立的 register/unregister keymap hook，例如：

```python
def register_static_sculpt_keymaps():
    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    sculpt_keymap = user_keyconfig.keymaps.get("Sculpt") or user_keyconfig.keymaps.new(name="Sculpt")
    keymap_item = sculpt_keymap.keymap_items.new("view3d.view_persportho", "P", "PRESS")
```

需要保存这条插件创建的 keymap item 签名；插件 `unregister()` 时删除它，避免插件卸载后残留。

### Verification
Blender background 可验证：

- 插件注册后，user `Sculpt` keymap 有 active `view3d.view_persportho` / `P`。
- 不进入 Sculpt Mode 也应该存在于 `Sculpt` keymap。
- 插件 unregister 后，该项被删除。

## Phase 2: Add One-shot Shift+RMB Snap Operator

### Expected Behavior
在 Sculpt Mode 中：

- `Shift + RMB press/drag` 触发自定义 operator。
- operator 把当前 View3D snap 到最近的固定视角。
- 保持当前 `RegionView3D.view_perspective`：
  - 当前是 `PERSP`，snap 后仍然 `PERSP`。
  - 当前是 `ORTHO`，snap 后仍然 `ORTHO`。

### Why Custom Operator Is Needed
Blender 原生 `View3D Rotate Modal -> Axis Snap` 行为和 ZBrush 不完全一致：

- 它依赖原生 rotate modal。
- snap 行为不是简单“最近固定视角”。
- 可能强制或倾向正交视图行为，不能完全模拟 ZBrush。

### Operator Location
新增文件建议：

- `operators/view_snap.py`

Class naming:

```python
class ZNAV_OT_snap_view_to_nearest_axis(bpy.types.Operator):
    bl_idname = "zbrush_navigation.snap_view_to_nearest_axis"
    bl_label = "Snap View to Nearest Axis"
    bl_options = {"REGISTER", "UNDO"}
```

### Core Algorithm
固定候选视角建议先支持 6 个轴向：

- Front
- Back
- Right
- Left
- Top
- Bottom

可选扩展：保留/清除 roll。第一版建议清除 roll，让结果稳定。

实现思路：

1. 从当前 3D View 找 `region_3d`。
2. 读取当前 view direction。
3. 和 6 个候选 direction 做 dot product。
4. 选择 dot 最大的候选。
5. 设置 `region_3d.view_rotation` 为对应 quaternion。
6. 保存进入前 `region_3d.view_perspective`，设置 rotation 后恢复该值。

注意：Blender view direction 和 object/camera direction 符号容易反，必须用真实 Blender 验证 Front/Back/Left/Right/Top/Bottom 是否符合预期。

### Keymap
进入 Sculpt Mode 时给 user `Sculpt` keymap 添加：

- `Shift + RMB` -> `zbrush_navigation.snap_view_to_nearest_axis`

如果要支持 drag，可先用 `PRESS`。若实际 ZB 手感需要拖动后触发，再改为 modal operator。

### Verification
至少验证：

- Sculpt Mode 中 keymap 存在。
- 调用 operator 后 `view_perspective` 未改变。
- 不在 Sculpt Mode 时 keymap 不存在。
- 退出 Sculpt Mode 后临时 keymap 被删除。

## Phase 3: Full ZBrush-style RMB Rotate Modal

### Expected Behavior
完整目标：

- RMB drag: rotate view。
- RMB drag + Ctrl: zoom。
- RMB drag + Alt: pan。
- RMB drag 时按住 Shift: snap 到最近固定视角。
- snap 后继续保持当前 Perspective/Orthographic 状态。

### Why This Is More Complex
如果 RMB 仍然绑定 Blender 原生 `view3d.rotate`，插件无法完全控制 rotate modal 内部事件。

要做到 ZBrush 一致，需要自定义 modal operator 接管 RMB drag：

- `ZNAV_OT_zbrush_navigation_modal`
- 监听 mouse move / modifier state。
- 根据当前 modifier 分派 rotate / zoom / pan / snap。

### Recommended Architecture
不要一开始替换全部原生导航。先确保 Phase 2 的 snap operator 行为正确，再做 modal。

建议把功能拆开：

- `functions/view_snap.py`: 纯数学逻辑，计算最近轴向和 quaternion。
- `operators/view_snap.py`: 单次 snap operator。
- `operators/navigation_modal.py`: 后续完整 RMB modal operator。

### Modal Operator Notes
Modal operator 可以通过 `context.area`, `context.region`, `context.space_data.region_3d` 操作当前视图。

风险点：

- 多窗口 / 多 View3D 区域上下文。
- 鼠标 wrap / continuous grab 行为。
- 和 Blender 原生 viewport rotate 手感一致性。
- tablet / pen input 是否按 mouse event 处理。

如果 modal 实现不稳定，应保留现有原生 `view3d.rotate` 方案作为默认，新增一个 preference 开关，例如：

- `snap_mode = "ONE_SHOT" | "CUSTOM_MODAL"`

## Do Not Do

- 不要保存 live `KeyMapItem` 引用用于退出恢复。
- 不要在退出 Sculpt Mode 时保存用户偏好。
- 不要影响 Object/Edit/Pose 等其它模式。
- 不要用 broad try/except 吞掉 keymap 恢复错误。
- 不要让 snap operator 强制切 Orthographic，除非用户明确要求。

## Minimal Verification Commands

每次实现后至少运行：

```powershell
python scripts\validate_addon.py
git diff --check
```

如果改了 Blender runtime 行为，补充 Blender background 检查：

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python-expr "..."
```

需要人工验证的部分：

- RMB / Ctrl RMB / Alt RMB / Shift RMB 在真实 View3D 中的手感。
- Shift snap 的目标视角是否和 ZBrush 预期一致。
- Perspective 和 Orthographic 下 snap 都不改变当前投影模式。
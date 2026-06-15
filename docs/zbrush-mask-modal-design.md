# ZBrush-style Sculpt Mask Design

## Status

当前代码已回滚到稳定状态。本文档只记录前一次实验中已经观察到的事实、可用片段和下一轮重做时必须验证的点。

不要把前一次实现直接恢复。那次实现最终表现为：进入 Sculpt Mode 后原本应该添加的 viewport navigation keymap 没有正常出现或没有生效，插件整体不可用。具体根因尚未定位，不能归因到某一个点。

## Target Behavior

### Alt + LMB

Sculpt Mode 中：

- `Alt + LMB`：当前 sculpt brush 临时 invert。
- 目标 operator：`sculpt.brush_stroke(mode="INVERT")`。

### Mask Input Mode

Sidebar 增加模式开关：

- `Pen`：mask 绘制使用 `sculpt.brush_stroke` + `brush_toggle="MASK"`。
- `Lasso`：mask 绘制使用 `paint.mask_lasso_gesture`。

### Ctrl + LMB

| 条件 | 行为 |
| --- | --- |
| Pen 模式，鼠标在物体上 drag | 绘制 mask |
| Pen 模式，鼠标在物体外 click | invert mask |
| Pen 模式，鼠标在物体外 drag，box 选区碰到物体 | box mask |
| Pen 模式，鼠标在物体外 drag，box 选区完全没碰到物体 | clear mask |
| Lasso 模式，lasso 选区碰到物体 | 绘制 lasso mask |
| Lasso 模式，lasso 选区完全没碰到物体 | clear mask |

### Ctrl + Alt + LMB

| 条件 | 行为 |
| --- | --- |
| Pen 模式，鼠标在物体上 drag | 减 mask |
| Lasso 模式，lasso 选区碰到物体 | 减 lasso mask |
| Lasso 模式，lasso 选区没碰到物体 | 不处理 |
### Pen Outside Drag

补充观察：ZBrush 的 mask Pen 模式下，如果 `Ctrl + LMB drag` 从物体外开始，不是立刻 clear mask，而是先进入 box select 行为。

Blender 对应 operator：

```python
bpy.ops.paint.mask_box_gesture(mode="VALUE", value=1.0)
```

目标流程：

1. `Ctrl + LMB drag`。
2. 起点 raycast。
3. 如果起点在物体上：走 Pen mask brush。
4. 如果起点在物体外：进入 box mask。
5. box 选区覆盖当前 sculpt object：执行 `mask_box_gesture(mode="VALUE", value=1.0)`。
6. box 选区完全没覆盖当前 sculpt object：执行 `mask_flood_fill(mode="VALUE", value=0.0)`。

这个 box 覆盖判定应复用 Lasso 覆盖判定思路：屏幕空间 selection polygon / rectangle 与 active object 屏幕投影相交。

## Confirmed Facts

### 1. Blender keymap 支持 click / drag 区分

已确认 `KeyMapItem.value` 支持：

- `CLICK`
- `CLICK_DRAG`
- `PRESS`

所以 `Ctrl + LMB click` 和 `Ctrl + LMB drag` 理论上可以拆成不同 keymap item。

### 2. `paint.mask_lasso_gesture(path=...)` 至少有执行记录

Crash log 中出现过：

```python
bpy.ops.paint.mask_lasso_gesture(path=[...], mode="VALUE", value=1)
```

这说明 Blender 可以记录并执行带 path 的 lasso gesture。是否适合作为插件最终方案，需要单独验证。

### 3. `mask_flood_fill` 可用于 invert / clear

已确认 API 形式：

```python
bpy.ops.paint.mask_flood_fill(mode="INVERT")
bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
```

### 4. Pen crash 现象存在，但根因未完全定位

现象：Pen 模式 `Ctrl + LMB drag` 后 Blender crash。

Crash log 关键线索：

```text
bpy.ops.zbrush_navigation.mask_ctrl_drag()
PaintStroke::modal
SculptPaintStroke::done
sculpt_paint::undo::push_end_ex
BKE_undosys_step_push
```

只能确定：crash 发生在插件 mask drag 之后，且 native stack 在 sculpt stroke/undo 结束阶段。不能进一步断言唯一根因。

### 5. 最终坏掉的现象是 navigation keymap 没正常加入或生效

用户观察：进入 Sculpt Mode 后，之前会添加的 viewport navigation keymap 全都没添加或没生效。

这说明下一轮首先要验证 `apply_zbrush_navigation()` 的前置流程，而不是直接继续做 mask 行为。

## Do Not Assume

这些不是已证实结论，不要写死为根因：

- 不要断言 viewport 失效一定是 lasso modal 吃事件导致。
- 不要断言 disable `addon/default` 一定是唯一原因。
- 不要断言 Pen crash 的唯一原因是 dispatcher 调 `sculpt.brush_stroke`。

它们都只能作为下一轮 debug 的假设。

## Chosen Empty Selection Strategy

下一轮优先采用“自定义输入/HUD + 原生 mask 应用”的混合方案。

### Why Not Run Native Gesture And Custom Modal Together

不采用“启动原生 `mask_box_gesture` / `mask_lasso_gesture` 的同时运行插件 modal”作为主方案：

- 原生 gesture modal 会接管事件流，插件 modal 不保证能完整收到 `MOUSEMOVE` / `RELEASE`。
- Lasso 必须拿到完整 path；只要漏点，空选判断就不可信。
- 原生 box/lasso operator 只返回 `FINISHED` / `CANCELLED`，不会返回“选区是否碰到模型”。

### Selected Architecture

插件自己负责拖拽输入、HUD 和空选判断；真正写入 mask 时仍调用 Blender 原生 operator。

流程：

1. 起点 raycast，只把命中当前 active sculpt object 视为“在物体上”。
2. 如果起点在物体上，继续 pass-through 给原生 sculpt mask brush。
3. 如果起点在物体外，插件进入自定义 modal。
4. Box 记录起点/终点；Lasso 记录完整鼠标 path。
5. 使用 `SpaceView3D.draw_handler_add(..., "POST_PIXEL")` 绘制 HUD 线框。
6. 松开鼠标后先做插件侧 hit test。
7. 非空选：调用原生 `mask_box_gesture(..., wait_for_input=False, mode="VALUE", value=...)` 或 `mask_lasso_gesture(path=..., mode="VALUE", value=...)`。
8. 空选：调用 `mask_flood_fill(mode="VALUE", value=0.0)`。

### Lasso Hit Test Rule

Lasso 不能用 active object bounding box 判断。第一版用屏幕空间 polygon + ray sample：

- 把 lasso path 当作屏幕空间 polygon。
- 在 polygon 内按固定步长采样屏幕点。
- 每个采样点通过 `region_2d_to_origin_3d` / `region_2d_to_vector_3d` 做 raycast。
- 只要任一点命中当前 active sculpt object，就认为选区非空。
- 没有任何命中则认为空选并 clear mask。

### First Experiment Scope

先只试 Lasso：

- 新增插件自定义 Lasso modal 和 HUD。
- 验证 `paint.mask_lasso_gesture(path=...)` 能接受插件记录的 path。
- 验证空选 clear、不空选 apply。
- Lasso 成功后，Box 复用同一套 modal/HUD/hit-test 框架实现。

## Redo Plan

### Phase 0: 先保护现有 navigation

在做任何 mask 功能前，先加或运行回归检查，确认进入 Sculpt Mode 后这些 addon keymap 存在且 active：

- RMB -> `zbrush_navigation.zbrush_rotate_modal`
- Ctrl RMB -> `view3d.zoom`
- Alt RMB -> `view3d.move`
- Shift RMB -> `zbrush_navigation.zbrush_rotate_modal`

如果这些不成立，停止 mask 实现，先修 navigation apply 流程。

### Phase 1: 只加 UI 属性，不加快捷键

先只加：

- `mask_input_mode = PEN / LASSO`
- Sidebar 显示开关

验证：

- 进入 Sculpt Mode 后 navigation keymap 仍正常。
- 退出 Sculpt Mode 后恢复正常。

### Phase 2: 只加 `Alt + LMB` invert brush

只添加：

```python
sculpt.brush_stroke(mode="INVERT")
```

验证 navigation 不受影响。

### Phase 3: 只加 mask flood fill click

添加 `Ctrl + LMB CLICK` dispatcher：

- 鼠标在物体外：`mask_flood_fill(mode="INVERT")`
- 鼠标在物体上：不处理或 pass-through

验证 navigation 不受影响。

### Phase 4: 再分别实验 Pen / Lasso drag

每次只做一种模式，不要同时改 Pen 和 Lasso：

- Pen 起点在物体上：优先直接绑定原生 `sculpt.brush_stroke` keymap。
- Pen 起点在物体外：实验 box mask，目标 operator 是 `paint.mask_box_gesture(mode="VALUE", value=1.0)`；box 完全没覆盖 object 时 clear mask。
- Lasso drag：优先直接绑定原生 `paint.mask_lasso_gesture` keymap。

每一步都必须真实 View3D 测试后再继续。

## Conflict Handling Rules

如果需要禁用冲突快捷键：

- 第一版只碰 `keyconfigs.user`。
- 不碰 `keyconfigs.addon`。
- 不碰 `keyconfigs.default`。
- 不 bulk clear / rebuild keymap。
- 只处理明确冲突项，例如 `Sculpt` keymap 中 active 的 `Ctrl/Alt + LEFTMOUSE`。
- 记录 signature 和原 active 状态。
- 退出 Sculpt Mode 时按 signature 恢复。

## Hit Test Notes

### 鼠标是否在物体上

可用 View3D raycast：

```python
region_2d_to_origin_3d(region, rv3d, mouse)
region_2d_to_vector_3d(region, rv3d, mouse)
context.scene.ray_cast(depsgraph, origin, direction)
```

只把命中当前 active sculpt mesh 视为“在物体上”。

### Box / Lasso 是否覆盖物体

尚未验证。可作为后续方案：

1. active object bound box 投影到屏幕。
2. box rectangle 或 lasso path 构成屏幕空间 polygon。
3. 判断两个 polygon 是否相交。

这是近似方案，不等价于真实 mesh selection。

## Required Verification

每一步至少运行：

```powershell
python scripts\validate_addon.py
git diff --check
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```

真实 View3D 必测：

- 进入 Sculpt Mode 后 RMB rotate 可用。
- Ctrl RMB zoom 可用。
- Alt RMB pan 可用。
- Shift RMB snap 可用。
- 退出 Sculpt Mode 后恢复。
- 新增 mask 行为不影响上述 navigation。

## Stop Conditions

出现以下任一情况，立刻停止并回滚当前步骤：

- 进入 Sculpt Mode 后 navigation keymap 没添加或不 active。
- viewport 输入失效。
- Blender crash。
- keymap 状态无法解释。
- background regression 通过但真实 View3D 失效。
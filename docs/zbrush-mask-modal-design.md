# ZBrush-style Sculpt Mask Design

## Status

当前代码已经回滚到稳定状态；本文档记录前一次 mask 功能实验的结论，供下一次从零重做使用。

不要直接恢复前一次实现。前一次实现曾导致：

- 进入 Sculpt Mode 后 viewport navigation keymap 没有按预期生效。
- Lasso 自定义 modal 吃事件，导致 viewport 操作失效。
- Pen mask 从自定义 dispatcher 调 `sculpt.brush_stroke` 时触发 Blender crash。

## Target Behavior

### Alt + LMB

Sculpt Mode 中：

- `Alt + LMB`：当前 sculpt brush 临时 invert。
- 对应 Blender operator：`sculpt.brush_stroke(mode="INVERT")`。

### Mask Input Mode

Sidebar 增加开关：

- `Pen`：mask 绘制使用 `sculpt.brush_stroke` + `brush_toggle="MASK"`。
- `Lasso`：mask 绘制使用 `paint.mask_lasso_gesture`。

### Ctrl + LMB

ZBrush 目标行为：

| 条件 | 行为 |
| --- | --- |
| Pen 模式，鼠标在物体上 drag | 绘制 mask |
| Pen 模式，鼠标在物体外 click | invert mask |
| Pen 模式，鼠标在物体外 drag | clear mask |
| Lasso 模式，lasso 选区碰到物体 | 绘制 lasso mask |
| Lasso 模式，lasso 选区完全没碰到物体 | clear mask |

### Ctrl + Alt + LMB

| 条件 | 行为 |
| --- | --- |
| Pen 模式，鼠标在物体上 drag | 减 mask |
| Lasso 模式，lasso 选区碰到物体 | 减 lasso mask |
| Lasso 模式，lasso 选区没碰到物体 | 不处理 |

## What Worked

### 1. Blender keymap 支持 click / drag 区分

`KeyMapItem.value` 可用：

- `CLICK`
- `CLICK_DRAG`
- `PRESS`

因此 `Ctrl + LMB click` 和 `Ctrl + LMB drag` 可以拆成不同 keymap item。

### 2. `paint.mask_lasso_gesture(path=...)` 可执行

Crash log 里出现过成功执行记录：

```python
bpy.ops.paint.mask_lasso_gesture(path=[...], mode="VALUE", value=1)
```

说明 lasso operator 支持传入完成后的 path。

### 3. `mask_flood_fill` 可用于 invert / clear

可用调用：

```python
bpy.ops.paint.mask_flood_fill(mode="INVERT")
bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
```

### 4. Pen mask 必须尽量走原生 keymap

Pen 模式下，直接让 Blender 原生 `sculpt.brush_stroke` 接管 drag 是目前最安全方向。

## Failed Attempts

### 1. 不要从自定义 operator 里 invoke Pen stroke

失败做法：

```python
bpy.ops.sculpt.brush_stroke(
    "INVOKE_DEFAULT",
    mode="NORMAL",
    brush_toggle="MASK",
)
```

从自定义 `CLICK_DRAG` operator 内启动它，Blender 5.1.2 在 stroke 结束 push sculpt undo 时 crash。

Crash 栈关键位置：

```text
PaintStroke::modal
SculptPaintStroke::done
sculpt_paint::undo::push_end_ex
BKE_undosys_step_push
```

结论：Pen mask 不能用 dispatcher 再转调 `sculpt.brush_stroke`。

### 2. 不要用 `CLICK_DRAG` 启动自定义 long-running lasso modal

失败做法：

- `Ctrl + LMB CLICK_DRAG` 触发插件 operator。
- operator `modal_handler_add()` 后返回 `RUNNING_MODAL`。
- modal 内记录路径，等待 `LEFTMOUSE RELEASE`。

问题：`CLICK_DRAG` 触发时 Blender 事件流已经进入 drag 状态，自定义 modal 容易错过 release 或吃掉后续输入，导致 viewport 操作整体失效。

结论：Lasso 自定义 modal 如果要做，不能从 `CLICK_DRAG` 事件开始；必须从 `PRESS` 开始完整接管 press/move/release，或者避免自定义 modal。

### 3. 不要 disable `addon` / `default` keyconfig

失败做法：

- 进入 Sculpt Mode 时扫描 `user` / `addon` / `default`。
- disable 所有 `Ctrl/Alt + LEFTMOUSE` 冲突项。

问题：会误伤插件自己刚添加或 Blender 默认依赖的 keymap 行为，表现为进入 Sculpt Mode 后导航 keymap 丢失或不生效。

结论：冲突处理只能碰 `keyconfigs.user`，且必须先添加明确签名和回归检查。

## Recommended Redo Plan

### Phase 1: 只做最小稳定版本

实现范围：

- Sidebar `mask_input_mode`。
- `Alt + LMB PRESS` -> `sculpt.brush_stroke(mode="INVERT")`。
- `Ctrl + LMB CLICK` -> 插件 operator：物体外 invert，物体上 pass-through。
- Pen 模式：`Ctrl + LMB CLICK_DRAG` / `Ctrl + Alt + LMB CLICK_DRAG` 直接绑定原生 `sculpt.brush_stroke`。
- Lasso 模式：先直接绑定原生 `paint.mask_lasso_gesture`，不要做 ZBrush 外部 clear 逻辑。

目标是先确认不会破坏 navigation。

### Phase 2: narrow conflict handling

只处理 `keyconfigs.user`。

仅 disable：

- keymap name: `Sculpt` 和必要时 `3D View Tool: Sculpt*`。
- event type: `LEFTMOUSE`。
- modifier: `Ctrl` 或 `Alt`。
- 排除：`zbrush_navigation.*`。

必须记录：

- keyconfig name。
- keymap name。
- keymap item signature。
- 原 active 状态。

退出 Sculpt Mode 时只恢复这些签名。

### Phase 3: ZBrush-style lasso clear

不要用 `CLICK_DRAG` 启动自定义 modal。

可选方案 A：`PRESS` modal 完整接管 Lasso

- `Ctrl + LMB PRESS` 进入插件 modal。
- modal 记录 `MOUSEMOVE` path。
- `LEFTMOUSE RELEASE` 时判断 lasso 是否覆盖 object。
- 覆盖则调用 `paint.mask_lasso_gesture(path=...)`。
- 未覆盖则 clear mask。

风险：`PRESS` modal 会和 Pen 原生 stroke 冲突，所以只在 Lasso 模式启用。

可选方案 B：保留原生 lasso，放弃“完全没选中才 clear”

- 这是更稳定的折中方案。
- 外部 clear 只通过额外独立操作实现。

## Hit Test Design

### Pen 起点判断

可用 View3D raycast：

```python
region_2d_to_origin_3d(region, rv3d, mouse)
region_2d_to_vector_3d(region, rv3d, mouse)
context.scene.ray_cast(depsgraph, origin, direction)
```

只把命中当前 active sculpt mesh 视为“在物体上”。

### Lasso 覆盖判断

第一版不要追求完美面级判断。建议用屏幕空间近似：

1. active object bound box 8 个点投影到屏幕。
2. 计算 convex hull。
3. 判断 lasso polygon 与 object hull 是否相交：
   - lasso 点在 hull 内。
   - hull 点在 lasso 内。
   - polygon 边相交。

这只能判断 object 屏幕包围范围，不等价于真实 mesh selection，但足够先接近 ZBrush 行为。

## Keymap Safety Rules

必须遵守：

- 默认写 `keyconfigs.addon`。
- 不创建 user keymap override，除非用户明确要求。
- 不 bulk clear / rebuild user keymap。
- 不碰 `keyconfigs.default`。
- 不 disable `addon` keyconfig。
- 不保存 live `KeyMapItem` 引用。
- 恢复时用 signature 重新查找。
- 任何 conflict disable 必须有 Blender background regression。

## Required Verification

每次实现后至少运行：

```powershell
python scripts\validate_addon.py
git diff --check
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```

如果改 keymap，background regression 必须检查：

- add-on `Sculpt` keymap 中 navigation RMB 项仍存在。
- add-on `Sculpt` keymap 中 mask LMB 项存在。
- user keymap 中 unrelated LMB/RMB 项未被删除。
- 被 disable 的 user conflict 项退出 Sculpt Mode 后恢复 active 状态。
- 插件 unregister 后 add-on keymap 清理干净。

## Manual Verification Checklist

真实 View3D 必测：

- 进入 Sculpt Mode 后 RMB rotate 可用。
- Ctrl RMB zoom 可用。
- Alt RMB pan 可用。
- Shift RMB snap 可用。
- 退出 Sculpt Mode 后原 navigation 恢复。
- Pen 模式 Ctrl LMB drag 不 crash。
- Lasso 模式 Ctrl LMB drag 能正常 lasso。
- Ctrl LMB click 只在物体外 invert mask。
- 物体外 clear 行为不会吞掉后续 viewport 输入。

## Stop Conditions

出现以下任一情况，立刻 revert 当前 mask 实现，不继续叠补丁：

- 进入 Sculpt Mode 后 RMB navigation 丢失。
- viewport 输入被 modal 吞掉。
- Blender crash。
- user/default/addon keymap 状态无法解释。
- background regression 通过但真实 View3D 失效。
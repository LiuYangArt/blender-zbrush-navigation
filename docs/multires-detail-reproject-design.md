# Multires Detail Reproject Design

## Goal

实现一个最小的 ZBrush-style 投射辅助工具：

- 用户自己准备高模 source。
- 用户自己准备低模 target。
- target 已经有 Multires。
- target 的 Multires 层级由用户自己决定。
- 插件只负责把 source 表面细节投射到 target 当前 Multires 层。

这个功能不负责 remesh、retopo、自动 subdivide、自动猜层级。

## User Workflow

1. 用户准备高模。
2. 用户准备低模，并添加 Multires。
3. 用户自己把 Multires 调到目标 `sculpt_levels`。
4. 用户选中高模和低模。
5. active object 必须是低模 target。
6. 执行 `Project Details From Selected High Mesh`。
7. 插件从非 active mesh source 投射细节到 active target 当前 Multires 层。

## Scope

第一版只做：

- 单个 active target。
- 一个或多个 selected source mesh。
- 不创建 Multires。
- 不修改 Multires 层级。
- 不 apply modifier。
- 不改 target 拓扑。
- 不隐藏、不删除、不复制 source。
- 投射完成后报告结果。

## Required Checks

执行前必须检查：

- 当前 active object 是 mesh。
- active object 有 Multires modifier。
- Multires `sculpt_levels > 0`。
- 当前目标层级就是用户想投射的层级。
- 至少存在一个非 active 的 selected mesh source。
- source 不能等于 target。
- target 不应处于无法写入 Multires 当前层的状态。

检查失败直接报错，不做 silent fallback。

## Expected Behavior

插件应该只修改 active target 当前 Multires 层的几何细节。

投射完成后：

- target 仍然保留 Multires modifier。
- target 低层级仍可切换。
- source 保持不变。
- 用户可以继续在 Multires 高层雕刻。

## Non-Goals

第一版明确不做：

- 自动 Voxel Remesh。
- 自动 Quad Remesh。
- 自动添加 Multires。
- 自动 subdivide。
- 自动推荐层级。
- 自动判断最佳 source。
- 多 source 智能融合。
- 自动修复投射 artifact。
- UV、材质、Face Sets 转移。

## Technical Unknown

核心风险是 Blender Python 是否能稳定把任意 source 表面投射结果写入 target 的当前 Multires 层。

需要先做技术验证：

- 是否能直接通过 Blender operator/API 完成。
- 是否需要临时 high-level mesh，再通过 Multires reshape 类流程写回。
- 是否能在 background check 中验证 target 顶层顶点发生变化且 Multires 保留。

如果 API 不稳定，第一版应停止在技术验证阶段，不继续包装 UI。

## Projection Strategy Candidates

候选方案按优先级验证：

1. 使用 Blender 原生 Multires reshape/project 相关能力。
2. 临时生成 target 当前最高层评估网格，投射到 source，再尝试写回 Multires。
3. 使用 Shrinkwrap/nearest surface 作为中间计算，但不能把最终结果退化成普通 applied mesh。

任何方案都不能破坏 target 的 Multires 层级结构。

## Failure Reporting

失败时应给出可读原因：

- 没有 active target。
- target 没有 Multires。
- 当前 Multires 层级为 0。
- 没有 selected source。
- Blender API 无法写入当前 Multires 层。
- 投射过程中出现异常。

调试阶段应尽量输出：

- target 名称。
- source 名称。
- Multires 当前层级。
- modifier 名称。
- 操作路径。

## Validation

最小验证：

```powershell
python scripts\validate_addon.py
git diff --check
```

实现投射后需要 Blender background 验证：

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py
```

真实 View3D 必测：

- 高模 source 不变化。
- 低模 target Multires 仍存在。
- target 可切换低/高层级。
- 高层级能看到投射细节。
- 失败时错误信息明确。

## Implementation Entry Points

建议文件：

- `operators/reproject.py`
- `functions/reproject.py`
- `panels/view3d_panel.py`
- `scripts/blender_regression_check.py`

Operator 命名：

- class: `ZNAV_OT_project_details_from_selected_high_mesh`
- `bl_idname`: `zbrush_navigation.project_details_from_selected_high_mesh`
- `bl_options`: `{ "REGISTER", "UNDO" }`

## Decision

当前设计采用半自动流程。

用户负责准备正确的 target/source 和 Multires 层级；插件只负责执行投射和报告结果。
这样范围最小、风险最低，也最符合 Blender 的实际能力边界。
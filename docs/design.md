# ZBrush Navigation 设计文档

## 目标
- 为 Blender 5.0+ 搭建 ZBrush-style navigation 插件基础结构。
- 使用 `auto_load.py` 自动发现并注册模块，避免维护手写注册列表。
- 保持 operator、panel、property、preferences 命名符合 Blender 规范和项目约定。
- 暴露可机器读取的验证与打包命令，方便 agent 后续迭代。

## 当前脚手架
- `properties/settings.py`：WindowManager 级设置。
- `properties/addon_preferences.py`：插件偏好设置。
- `operators/navigation.py`：最小 smoke-test operator。
- `panels/view3d_panel.py`：View3D Sidebar 入口。
- `scripts/validate_addon.py`：语法、版本、Blender 类名前缀和 operator id 校验。
- `scripts/build_release_package.py`：生成发布 zip。

## 后续实现入口
- ZBrush 导航行为放在 `operators/`。
- 纯计算、状态格式化、keymap 工具函数放在 `functions/`。
- 需要挂载到 `WindowManager` 或 `Scene` 的参数放在 `properties/`，并保持 register/unregister 对称。
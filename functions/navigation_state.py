from __future__ import annotations


def format_settings_summary(settings) -> str:
    enabled = "enabled" if settings.enable_zbrush_navigation else "disabled"
    return f"ZBrush Navigation is {enabled}; orbit mode: {settings.orbit_mode}"
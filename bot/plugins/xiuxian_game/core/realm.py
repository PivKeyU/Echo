"""境界相关纯函数 — 无数据库依赖，可被任何模块安全导入。"""

from __future__ import annotations

from bot.sql_helper.sql_xiuxian import (
    FIRST_REALM_STAGE,
    REALM_ORDER,
    cultivation_threshold,
    normalize_realm_stage,
)


def realm_index(stage: str | None) -> int:
    """返回境界在 REALM_ORDER 中的索引，用于数值计算。"""
    normalized = normalize_realm_stage(stage or FIRST_REALM_STAGE)
    if normalized in REALM_ORDER:
        return REALM_ORDER.index(normalized)
    return 0


def apply_cultivation_gain(stage: str, layer: int, cultivation: int, gain: int) -> tuple[int, int, list[int], int]:
    """将修为增益应用到当前层，自动处理升级。返回 (新层, 新修为, 升级的层列表, 剩余需求)。"""
    current_layer = max(int(layer or 1), 1)
    current_cultivation = max(int(cultivation or 0), 0) + max(int(gain or 0), 0)
    upgraded_layers: list[int] = []
    threshold = cultivation_threshold(stage, current_layer)

    while current_layer < 9 and current_cultivation >= threshold:
        current_cultivation -= threshold
        current_layer += 1
        upgraded_layers.append(current_layer)
        threshold = cultivation_threshold(stage, current_layer)

    if current_layer >= 9:
        current_cultivation = min(current_cultivation, threshold)

    remaining = max(threshold - current_cultivation, 0)
    return current_layer, current_cultivation, upgraded_layers, remaining


def seclusion_cultivation_efficiency_percent(gap: int) -> int:
    """根据境界差返回闭关修炼效率百分比。"""
    if gap >= 6:
        return 150
    if gap >= 4:
        return 130
    if gap >= 2:
        return 115
    if gap >= 1:
        return 105
    if gap == 0:
        return 100
    if gap >= -1:
        return 80
    if gap >= -2:
        return 55
    return 25

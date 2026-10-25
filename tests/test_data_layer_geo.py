"""Regression tests for wt_geo.grid_cell axis orientation."""

from __future__ import annotations

import pytest

from wt_geo import grid_cell
from wt_telemetry import MapInfo


def _map_info(**overrides) -> MapInfo:
    # 取自真实录像 rec_20260722_153043 的 /map_info.json
    data = {
        "valid": True,
        "grid_size": (32768.0, 32768.0),
        "grid_steps": (3200.0, 3200.0),
        "grid_zero": (-16384.0, 16384.0),
        "map_min": (-16384.0, -16384.0),
        "map_max": (16384.0, 16384.0),
    }
    data.update(overrides)
    return MapInfo(**data)


@pytest.mark.parametrize(
    ("nx", "ny", "expected"),
    [
        (0.0, 0.0, "A1"),  # 左上角（西北）
        (0.05, 0.05, "A1"),
        (0.15, 0.05, "A2"),  # 向东一格 -> 列号 +1
        (0.05, 0.15, "B1"),  # 向南一格 -> 字母 +1
        (0.5, 0.5, "F6"),  # 地图中心
        (0.999, 0.999, "K11"),  # 右下角的最后一格（32768 / 3200 向上取整为 11 格）
    ],
)
def test_grid_cell_letters_rows_from_top_numbers_columns_from_left(nx, ny, expected):
    assert grid_cell(nx, ny, _map_info()) == expected


def test_grid_cell_with_offset_grid_origin():
    # 小地图：网格区域比地图小，grid_zero 不在地图边角（真实录像中的 grid_steps=250 样本）
    info = _map_info(
        grid_size=(1250.0, 1250.0),
        grid_steps=(250.0, 250.0),
        grid_zero=(-592.95, 894.55),
        map_min=(-2048.0, -2048.0),
        map_max=(2048.0, 2048.0),
    )
    span = 4096.0
    # 网格左上角往东南各进半格 -> A1
    nx = (-592.95 + 125.0 + 2048.0) / span
    ny = (2048.0 - (894.55 - 125.0)) / span
    assert grid_cell(nx, ny, info) == "A1"
    # 往东两格、往南一格 -> B3
    assert grid_cell(nx + 500.0 / span, ny + 250.0 / span, info) == "B3"


@pytest.mark.parametrize(
    ("nx", "ny"),
    [
        (0.0, 0.0),  # 网格区域西北外侧
        (0.99, 0.99),  # 网格区域东南外侧
    ],
)
def test_grid_cell_outside_grid_area_returns_none(nx, ny):
    info = _map_info(
        grid_size=(1250.0, 1250.0),
        grid_steps=(250.0, 250.0),
        grid_zero=(-592.95, 894.55),
        map_min=(-2048.0, -2048.0),
        map_max=(2048.0, 2048.0),
    )
    assert grid_cell(nx, ny, info) is None


def test_grid_cell_missing_parameters_returns_none():
    assert grid_cell(0.5, 0.5, MapInfo()) is None
    assert grid_cell(0.5, 0.5, _map_info(grid_steps=(0.0, 3200.0))) is None


def test_grid_cell_rejects_rows_beyond_alphabet():
    info = _map_info(grid_size=None, grid_steps=(100.0, 100.0))
    assert grid_cell(0.0, 0.9, info) is None

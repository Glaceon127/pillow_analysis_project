"""Shared plotting style for the project.

Centralizes matplotlib rcParams and common colors so that all visualizations
(main PlotGenerator + standalone visualizers) look consistent.
"""

from __future__ import annotations

import logging
import sys
from typing import Dict

import matplotlib.pyplot as plt

# Silence noisy font fallback logs
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

# ========== Global palette ==========
COLOR_COMMIT = '#2E86AB'    # commit-related (blue)
COLOR_FIX = '#A23B72'       # fix-related (purple)
COLOR_BUG = '#F18F01'       # bug-related (orange)
COLOR_CVE = '#C73E1D'       # vulnerability-related (red)
COLOR_MEAN = '#3F88C5'      # mean line
COLOR_P90 = '#90A959'       # p90 line
COLOR_AST = '#6F4E7C'       # AST-danger signal (deep purple)


def apply_style() -> None:
    """Apply a consistent matplotlib style and Chinese font fallbacks."""

    platform = sys.platform.lower()
    if platform.startswith('darwin'):
        families = [
            'PingFang SC',
            'Hiragino Sans GB',
            'Heiti SC',
            'STHeiti',
            'Arial Unicode MS',
            'Noto Sans CJK SC',
            'DejaVu Sans',
        ]
    elif platform.startswith('win'):
        families = [
            'Microsoft YaHei',
            'SimHei',
            'Arial Unicode MS',
            'Noto Sans CJK SC',
            'DejaVu Sans',
        ]
    else:
        families = [
            'Noto Sans CJK SC',
            'WenQuanYi Micro Hei',
            'WenQuanYi Zen Hei',
            'Arial Unicode MS',
            'DejaVu Sans',
        ]

    plt.rcParams['font.family'] = families
    plt.rcParams['axes.unicode_minus'] = False

    # unified look
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = 'white'
    plt.rcParams['axes.grid'] = True
    plt.rcParams['grid.linestyle'] = '--'
    plt.rcParams['grid.alpha'] = 0.5
    plt.rcParams['lines.markersize'] = 4
    plt.rcParams['lines.linewidth'] = 1.5
    plt.rcParams['legend.fontsize'] = 10
    plt.rcParams['axes.titlesize'] = 12
    plt.rcParams['axes.labelsize'] = 10
    plt.rcParams['xtick.labelsize'] = 9
    plt.rcParams['ytick.labelsize'] = 9


def colors() -> Dict[str, str]:
    """Expose palette as a mapping (optional helper)."""

    return {
        'commit': COLOR_COMMIT,
        'fix': COLOR_FIX,
        'bug': COLOR_BUG,
        'cve': COLOR_CVE,
        'mean': COLOR_MEAN,
        'p90': COLOR_P90,
        'ast': COLOR_AST,
    }

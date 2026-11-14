# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The explanation record shared by the explanation tables."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Explanation:
    title: str
    meaning: str
    action: str


def _e(title: str, meaning: str, action: str) -> Explanation:
    return Explanation(title, meaning, action)

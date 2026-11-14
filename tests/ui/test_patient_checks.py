# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI checks wait for slow background work (seen on a slow Windows PC)."""

import pytest
from nicegui import ui
from nicegui.testing import User

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


async def test_text_that_arrives_after_a_second_is_still_seen(user: User) -> None:
    @ui.page("/slow-test-page")
    def slow() -> None:
        box = ui.column()

        def arrive() -> None:
            with box:
                ui.label("finally here")

        ui.timer(1.0, arrive, once=True)

    await user.open("/slow-test-page")
    await user.should_see("finally here")  # NiceGUI alone gives up after 0.3 s

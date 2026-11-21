"""Headless proof for the Pine Harvester TUI."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ["TV_TUI_NO_SCAN"] = "1"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

from textual.widgets import Button  # noqa: E402

from harvester_tui import HarvesterTUI  # noqa: E402
from screens import (  # noqa: E402
    ConfigureScreen,
    DangerScreen,
    DetailsScreen,
    HelpScreen,
    HistoryScreen,
    MaintenanceScreen,
    PaletteScreen,
    SearchScreen,
)

CARDS = ("card-enumerated", "card-downloaded", "card-protected", "card-index")


async def render(size: tuple[int, int], name: str) -> None:
    app = HarvesterTUI()
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.5)
        for card in CARDS:
            widget = app.query_one("#" + card)
            assert widget.size.width > 0 and widget.size.height > 0, card
        assert app.query_one("#log").size.height >= 3
        assert app.query_one("#progbar")
        assert app.query_one("#badge")
        assert app.query_one("#status-left")
        assert app.query_one("#status-right")
        assert app.query_one("#btn-maint")
        assert app._wide_toolbar == (size[0] >= 100)
        assert app._wide_sidebar == (size[0] >= 120)
        shots = HERE / "_screens"
        shots.mkdir(exist_ok=True)
        try:
            svg = app.export_screenshot()
            (shots / ("%s.svg" % name)).write_text(svg, encoding="utf-8")
        except Exception as exc:
            print("screenshot skipped:", exc)

        if name == "80x24":
            await pilot.click("#card-enumerated")
            await pilot.pause(0.3)
            assert isinstance(app.screen, DetailsScreen)
            try:
                (shots / "80x24-details.svg").write_text(
                    app.export_screenshot(), encoding="utf-8"
                )
            except Exception:
                pass
            await pilot.press("escape")
            await pilot.pause(0.2)

            await pilot.press("question_mark")
            await pilot.pause(0.3)
            assert isinstance(app.screen, HelpScreen)
            try:
                (shots / "80x24-help.svg").write_text(
                    app.export_screenshot(), encoding="utf-8"
                )
            except Exception:
                pass
            await pilot.press("escape")
            await pilot.pause(0.2)

            await pilot.press("slash")
            await pilot.pause(0.2)
            for key in ("p", "r", "o", "g"):
                await pilot.press(key)
            await pilot.press("enter")
            await pilot.pause(0.2)
            try:
                (shots / "80x24-filter.svg").write_text(
                    app.export_screenshot(), encoding="utf-8"
                )
            except Exception:
                pass
            await pilot.press("escape")
            await pilot.pause(0.2)
    print("rendered", name)


async def interactions() -> None:
    app = HarvesterTUI()
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause(0.2)

        snippet = (
            "import time; print('PROG task|demo|5|10|0.4'); "
            "time.sleep(0.2); print('smoke done')"
        )
        app._start("Smoke A", ["-c", snippet])
        app._start("Smoke B", ["-c", snippet])
        assert len(app.queue) == 1, app.queue
        await pilot.pause(2.6)
        assert app.job is None, "job did not finish"
        assert app.queue == [], app.queue
        assert app._session_jobs == 2, app._session_jobs
        assert app._state == "done", app._state
        assert len(app._history) == 2, app._history

        await pilot.press("slash")
        await pilot.pause(0.2)
        assert app.query_one("#logfilter").display
        for key in ("p", "r", "o", "g"):
            await pilot.press(key)
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app._log_filter.lower() == "prog", app._log_filter
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert app._log_filter == ""
        assert not app.query_one("#logfilter").display

        await pilot.press("j")
        await pilot.pause(0.25)
        assert isinstance(app.screen, HistoryScreen)
        try:
            (HERE / "_screens" / "110x34-history.svg").write_text(
                app.export_screenshot(), encoding="utf-8"
            )
        except Exception:
            pass
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("ctrl+p")
        await pilot.pause(0.25)
        assert isinstance(app.screen, PaletteScreen)
        for key in ("h", "e", "l", "p"):
            await pilot.press(key)
        await pilot.pause(0.15)
        await pilot.press("enter")
        await pilot.pause(0.35)
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("f")
        await pilot.pause(0.25)
        assert isinstance(app.screen, SearchScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.click("#card-enumerated")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DetailsScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("t")
        await pilot.pause(0.1)
        assert app.motion.enabled is False
        await pilot.press("t")
        await pilot.pause(0.1)
        assert app.motion.enabled is True

        await pilot.press("g")
        await pilot.pause(0.1)
        assert app._ascii is True

        await pilot.press("end")
        await pilot.pause(0.1)

        await pilot.press("ctrl+p")
        await pilot.pause(0.2)
        for key in ("c", "o", "n", "f", "i", "g", "u", "r", "e"):
            await pilot.press(key)
        await pilot.pause(0.15)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfigureScreen)
        try:
            (HERE / "_screens" / "110x34-configure.svg").write_text(
                app.export_screenshot(), encoding="utf-8"
            )
        except Exception:
            pass
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("shift+d")
        await pilot.pause(0.35)
        assert isinstance(app.screen, MaintenanceScreen)
        try:
            (HERE / "_screens" / "110x34-maintenance.svg").write_text(
                app.export_screenshot(), encoding="utf-8"
            )
        except Exception:
            pass
        await pilot.press("escape")
        await pilot.pause(0.2)

        await pilot.press("shift+d")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DangerScreen)
        await pilot.click("#delete")
        await pilot.pause(0.3)
        assert len(app._history) == 0
        assert app._session_jobs == 0

        await pilot.press("shift+d")
        await pilot.pause(0.3)
        for _ in range(3):
            await pilot.press("down")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DangerScreen)
        delete_button = app.screen.query_one("#delete", Button)
        assert delete_button.disabled
        try:
            (HERE / "_screens" / "110x34-danger.svg").write_text(
                app.export_screenshot(), encoding="utf-8"
            )
        except Exception:
            pass
        for key in ("c", "l", "e", "a", "r"):
            await pilot.press(key)
        await pilot.pause(0.2)
        assert not delete_button.disabled
        await pilot.press("escape")
        await pilot.pause(0.2)
    print("interactions OK")


async def stop_queue() -> None:
    app = HarvesterTUI()
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause(0.2)
        app._start("Smoke A", ["-c", "import time; time.sleep(5)"])
        app._start("Smoke B", ["-c", "print('B done')"])
        assert app.job is not None
        assert len(app.queue) == 1
        app.action_stop_job()
        assert app.job is None
        await pilot.pause(1.6)
        assert app.job is None
        assert app.queue == []
        assert app._session_jobs == 2, app._session_jobs
        assert len(app._history) == 2, app._history
        assert app._history[0]["rc"] == -1
        assert app._history[1]["rc"] == 0
    print("stop/queue OK")


async def live_scan() -> None:
    os.environ.pop("TV_TUI_NO_SCAN", None)
    app = HarvesterTUI()
    async with app.run_test(size=(130, 40)) as pilot:
        for _ in range(60):
            await pilot.pause(0.1)
            if app._stats:
                break
        assert app._stats, "status scan produced nothing"
        assert "manifest" in app._stats and "downloaded" in app._stats
        await pilot.pause(0.9)
        shot = HERE / "_screens" / "130x40-live.svg"
        shot.parent.mkdir(exist_ok=True)
        try:
            shot.write_text(app.export_screenshot(), encoding="utf-8")
        except Exception:
            pass
    print("live scan OK", app._stats)


async def main() -> None:
    await render((80, 24), "80x24")
    await render((120, 40), "120x40")
    await render((160, 50), "160x50")
    await interactions()
    await stop_queue()
    await live_scan()
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())

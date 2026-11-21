"""KPI card widget for the Pine Harvester dashboard."""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from theme import P


def fmt_count(value: float) -> str:
    return "{:,.0f}".format(value)


def fmt_mb(value: float) -> str:
    return "{:.1f} MB".format(value)


class KpiCard(Static):
    def __init__(self, label: str, card_id: str, formatter) -> None:
        super().__init__("", id=card_id, classes="card")
        self._label = label
        self._format = formatter
        self._value = 0.0
        self._delta = 0.0

    @property
    def value(self) -> float:
        return self._value

    def on_mount(self) -> None:
        self.border_title = self._label
        self.render_value()

    def set_value(self, value: float) -> None:
        self._value = float(value)
        self.render_value()

    def set_data(self, value: float, delta: float = 0.0) -> None:
        self._value = float(value)
        self._delta = float(delta)
        self.render_value()

    def render_value(self) -> None:
        if abs(self._delta) < 0.5:
            delta = "·"
            color = P["muted"]
        else:
            delta = ("+" if self._delta > 0 else "") + self._format(self._delta)
            color = P["success"] if self._delta > 0 else P["danger"]
        self.update(
            Text.assemble(
                (self._format(self._value), "bold " + P["accent"]),
                ("\n", ""),
                (delta, color),
            )
        )

    def flash(self) -> None:
        self.add_class("flash")
        self.set_timer(0.45, lambda: self.remove_class("flash"))

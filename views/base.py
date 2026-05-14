"""Abstract base for display views."""

from abc import ABC, abstractmethod
from typing import Optional

from usage_client import UsageData


class View(ABC):
    """A display surface. Owns its UI lifecycle; receives usage updates via on_update."""

    def __init__(self, manager):
        # ModeManager reference; views call back via manager.request_switch / .request_refresh / .request_quit
        self.manager = manager

    @abstractmethod
    def start(self, initial: Optional[UsageData]) -> None:
        """Build UI. If `initial` is provided, render it immediately."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down UI. Idempotent."""

    @abstractmethod
    def on_update(self, data: UsageData) -> None:
        """Fresh data arrived. Tk views get this on the main thread; cli/tray on the Poller thread."""

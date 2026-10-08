import pytest

from hf_gguf_downloader import app as gui
from hf_gguf_downloader.app import DownloaderApp, format_bytes


class Recorder:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def configure(self, **values: object) -> None:
        self.values.update(values)

    def set(self, value: str) -> None:
        self.values["value"] = value


def test_format_bytes_uses_decimal_units() -> None:
    assert format_bytes(999) == "999 B"
    assert format_bytes(1_500_000) == "1.5 MB"
    assert format_bytes(49_400_000_000) == "49.4 GB"


def test_cancel_terminates_active_worker() -> None:
    class FakeProcess:
        terminated = False

        def is_alive(self) -> bool:
            return True

        def terminate(self) -> None:
            self.terminated = True

    app = DownloaderApp.__new__(DownloaderApp)
    app._process = FakeProcess()
    app._cancel_requested = False
    app.start_button = Recorder()
    app.status = Recorder()

    app._cancel()

    assert app._cancel_requested is True
    assert app._process.terminated is True
    assert app.start_button.values["text"] == "CANCELING…"
    assert app.status.values["value"] == "Canceling download…"


def test_speed_uses_rolling_window_and_refreshes_once_per_second(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(gui.time, "monotonic", lambda: clock["now"])
    app = DownloaderApp.__new__(DownloaderApp)
    app.speed = Recorder()
    app._reset_speed()

    for now, transferred, expected in (
        (1.0, 1_000_000, "1.0"),
        (1.5, 2_000_000, "1.0"),
        (2.0, 3_000_000, "1.5"),
        (3.0, 6_000_000, "2.0"),
        (4.0, 6_000_000, "1.7"),
        (5.0, 6_000_000, "1.0"),
        (6.0, 6_000_000, "0.0"),
    ):
        clock["now"] = now
        app._network_bytes = transferred
        app._refresh_speed()
        assert app.speed.values["value"] == f"{expected} MB/s"

    app._reset_speed()
    assert app._network_bytes == 0
    assert len(app._speed_samples) == 1
    assert app.speed.values["value"] == "0.0 MB/s"


@pytest.mark.parametrize("pid, expected_joins", [(None, 0), (42, 1)])
def test_cleanup_joins_only_started_processes(pid: int | None, expected_joins: int) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = pid
            self.joins = 0

        def join(self, timeout: int) -> None:
            assert timeout == 0
            self.joins += 1

    app = DownloaderApp.__new__(DownloaderApp)
    process = FakeProcess()
    app._process = process
    app._event_queue = None
    app._cancel_requested = True
    app._dead_poll_count = 7

    app._cleanup_process()

    assert process.joins == expected_joins
    assert app._process is None
    assert app._cancel_requested is False
    assert app._dead_poll_count == 0

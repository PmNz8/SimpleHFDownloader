from hf_gguf_downloader.app import DownloaderApp, format_bytes


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

    class Recorder:
        values: dict[str, object]

        def __init__(self) -> None:
            self.values = {}

        def configure(self, **values: object) -> None:
            self.values.update(values)

        def set(self, value: str) -> None:
            self.values["value"] = value

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

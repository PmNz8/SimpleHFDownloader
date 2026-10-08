import os
from queue import Queue
from typing import Any

import pytest
from hf_xet import XetConfig

from hf_gguf_downloader import worker
from hf_gguf_downloader.worker import _progress_tqdm_factory


@pytest.mark.parametrize(
    "overrides, minimum, maximum, telemetry",
    [({}, 64, 128, False), ({"fixed": "8", "maximum": "32", "telemetry": "1"}, 8, 32, True)],
)
def test_worker_configures_xet_before_download(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str], minimum: int, maximum: int, telemetry: bool
) -> None:
    for name in (
        "HF_XET_FIXED_DOWNLOAD_CONCURRENCY",
        "HF_XET_CLIENT_AC_INITIAL_DOWNLOAD_CONCURRENCY",
        "HF_XET_CLIENT_AC_MIN_DOWNLOAD_CONCURRENCY",
        "HF_XET_CLIENT_AC_MAX_DOWNLOAD_CONCURRENCY",
        "HF_XET_CLIENT_ENABLE_ADAPTIVE_CONCURRENCY",
        "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_SIZE",
        "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_PERFILE_SIZE",
        "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_LIMIT",
        "HF_XET_DISABLE_MEMORY_DERIVED_DOWNLOAD_BUFFERS",
        "HF_XET_TELEMETRY_ENABLED",
        "HF_HUB_DISABLE_TELEMETRY",
        "DISABLE_TELEMETRY",
        "DO_NOT_TRACK",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    ):
        monkeypatch.delenv(name, raising=False)
    for option, name in (
        ("fixed", "HF_XET_FIXED_DOWNLOAD_CONCURRENCY"),
        ("maximum", "HF_XET_CLIENT_AC_MAX_DOWNLOAD_CONCURRENCY"),
        ("telemetry", "HF_XET_TELEMETRY_ENABLED"),
    ):
        if option in overrides:
            monkeypatch.setenv(name, overrides[option])
    monkeypatch.setenv("HF_XET_HIGH_PERFORMANCE", "0")
    monkeypatch.setenv("HF_XET_HP", "0")
    standard_config = XetConfig()
    monkeypatch.setenv("HF_XET_HIGH_PERFORMANCE", "1")
    monkeypatch.setenv("HF_XET_HP", "1")
    events: Queue[dict[str, Any]] = Queue()

    def fake_download(_payload: dict[str, Any], emit: worker.EventEmitter) -> None:
        config = XetConfig()
        emit(
            {
                "type": "configuration",
                "initial": config.get("client.ac_initial_download_concurrency"),
                "minimum": config.get("client.ac_min_download_concurrency"),
                "maximum": config.get("client.ac_max_download_concurrency"),
                "adaptive": config.get("client.enable_adaptive_concurrency"),
                "buffer": config.get("reconstruction.download_buffer_size"),
                "perfile_buffer": config.get("reconstruction.download_buffer_perfile_size"),
                "buffer_limit": config.get("reconstruction.download_buffer_limit"),
                "telemetry": config.get("telemetry.enabled"),
            }
        )

    monkeypatch.setattr(worker, "_download", fake_download)
    worker.run_download_worker({}, events)

    assert events.get_nowait() == {
        "type": "configuration",
        "initial": minimum,
        "minimum": minimum,
        "maximum": maximum,
        "adaptive": True,
        "buffer": standard_config.get("reconstruction.download_buffer_size"),
        "perfile_buffer": standard_config.get("reconstruction.download_buffer_perfile_size"),
        "buffer_limit": standard_config.get("reconstruction.download_buffer_limit"),
        "telemetry": telemetry,
    }
    assert os.environ["HF_XET_HIGH_PERFORMANCE"] == "0"
    assert os.environ["HF_XET_HP"] == "0"


def test_progress_class_emits_aggregate_progress() -> None:
    events: list[dict[str, object]] = []
    progress_class = _progress_tqdm_factory(
        emit=events.append,
        filename="model-00002-of-00003.gguf",
        file_index=2,
        file_count=3,
        completed_before=100,
        overall_total=400,
        expected_file_size=200,
    )

    progress = progress_class(total=200)
    progress.update(50)
    progress.update_transfer(20)
    progress.close()

    assert events[-1]["file_completed"] == 50
    assert events[-1]["completed_bytes"] == 150
    assert events[-1]["total_bytes"] == 400
    assert events[-1]["transferred_bytes"] == 20


def test_network_bytes_exclude_resume_and_continue_across_files() -> None:
    events: list[dict[str, object]] = []
    first_class = _progress_tqdm_factory(
        emit=events.append,
        filename="first.gguf",
        file_index=1,
        file_count=2,
        completed_before=0,
        overall_total=200,
        expected_file_size=100,
    )
    first = first_class(total=100, initial=40)
    first.update(10)
    first.update_transfer(25)
    first.update_transfer(-40)
    first.close()

    assert first_class.transferred_bytes == 25
    assert events[-1]["file_completed"] == 50
    assert events[-1]["transferred_bytes"] == 25

    second_class = _progress_tqdm_factory(
        emit=events.append,
        filename="second.gguf",
        file_index=2,
        file_count=2,
        completed_before=100,
        overall_total=200,
        expected_file_size=100,
        transferred_before=first_class.transferred_bytes,
    )
    second = second_class(total=100)
    second.update_transfer(30)
    second.close()

    assert events[-1]["transferred_bytes"] == 55

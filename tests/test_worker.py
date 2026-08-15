from hf_gguf_downloader.worker import _progress_tqdm_factory


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
    progress.close()

    assert events[-1]["file_completed"] == 50
    assert events[-1]["completed_bytes"] == 150
    assert events[-1]["total_bytes"] == 400

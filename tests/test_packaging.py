import importlib.metadata
import runpy
from pathlib import Path
from types import SimpleNamespace


def test_exe_includes_metadata_used_to_detect_xet() -> None:
    analysis_options = {}

    def capture_analysis(*_args, **kwargs):
        analysis_options.update(kwargs)
        return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "hf_gguf_downloader.spec"),
        init_globals={
            "Analysis": capture_analysis,
            "PYZ": lambda *_args: None,
            "EXE": lambda *_args, **_kwargs: None,
        },
    )
    metadata_paths = [
        Path(source) / "METADATA"
        for source, destination in analysis_options["datas"]
        if destination.startswith("hf_xet-") and destination.endswith(".dist-info")
    ]
    assert len(metadata_paths) == 1, "Hub detects Xet through distribution metadata, not just its .pyd"
    assert f"Version: {importlib.metadata.version('hf-xet')}\n" in metadata_paths[0].read_text("utf-8")

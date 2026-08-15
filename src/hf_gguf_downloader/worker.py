from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download
from huggingface_hub.errors import (
    EntryNotFoundError,
    GatedRepoError,
    HfHubHTTPError,
    RemoteEntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from tqdm.auto import tqdm

EventEmitter = Callable[[dict[str, Any]], None]


class _NullWriter:
    def write(self, _value: str) -> int:
        return 0

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


_NULL_WRITER = _NullWriter()


def run_download_worker(payload: dict[str, Any], event_queue: Any) -> None:
    """Run in a child process so cancellation can safely stop active network work."""

    def emit(event: dict[str, Any]) -> None:
        event_queue.put(event)

    try:
        _download(payload, emit)
    except BaseException as error:  # The child must always return a useful terminal event.
        emit({"type": "error", "message": _friendly_error(error)})


def _download(payload: dict[str, Any], emit: EventEmitter) -> None:
    repo_id = str(payload["repo_id"])
    revision = str(payload["revision"])
    files = tuple(str(filename) for filename in payload["files"])
    local_dir = Path(str(payload["local_dir"]))
    local_dir.mkdir(parents=True, exist_ok=True)

    emit({"type": "planning", "file_count": len(files)})
    dry_run_infos = [
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            local_dir=local_dir,
            library_name="huggingface-cli",
            dry_run=True,
        )
        for filename in files
    ]

    commit_hashes = {info.commit_hash for info in dry_run_infos}
    if len(commit_hashes) != 1:
        raise RuntimeError(
            "The repository changed while the shards were being checked. Start the download again."
        )
    resolved_revision = commit_hashes.pop()
    total_bytes = sum(info.file_size for info in dry_run_infos)
    completed_bytes = sum(info.file_size for info in dry_run_infos if not info.will_download)

    emit(
        {
            "type": "plan",
            "file_count": len(files),
            "total_bytes": total_bytes,
            "completed_bytes": completed_bytes,
        }
    )

    for index, info in enumerate(dry_run_infos, start=1):
        if not info.will_download:
            emit(
                {
                    "type": "file_complete",
                    "file_index": index,
                    "file_count": len(files),
                    "filename": info.filename,
                    "cached": True,
                    "completed_bytes": completed_bytes,
                    "total_bytes": total_bytes,
                }
            )
            continue

        emit(
            {
                "type": "file_start",
                "file_index": index,
                "file_count": len(files),
                "filename": info.filename,
                "file_size": info.file_size,
            }
        )
        progress_class = _progress_tqdm_factory(
            emit=emit,
            filename=info.filename,
            file_index=index,
            file_count=len(files),
            completed_before=completed_bytes,
            overall_total=total_bytes,
            expected_file_size=info.file_size,
        )
        hf_hub_download(
            repo_id=repo_id,
            filename=info.filename,
            revision=resolved_revision,
            local_dir=local_dir,
            library_name="huggingface-cli",
            tqdm_class=progress_class,
        )
        completed_bytes += info.file_size
        emit(
            {
                "type": "file_complete",
                "file_index": index,
                "file_count": len(files),
                "filename": info.filename,
                "cached": False,
                "completed_bytes": completed_bytes,
                "total_bytes": total_bytes,
            }
        )

    emit(
        {
            "type": "complete",
            "file_count": len(files),
            "total_bytes": total_bytes,
            "local_dir": str(local_dir),
        }
    )


def _progress_tqdm_factory(
    *,
    emit: EventEmitter,
    filename: str,
    file_index: int,
    file_count: int,
    completed_before: int,
    overall_total: int,
    expected_file_size: int,
) -> type[tqdm]:
    class EventTqdm(tqdm):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["file"] = _NULL_WRITER
            kwargs["disable"] = False
            kwargs["mininterval"] = 0.1
            self._event_lock = threading.Lock()
            self._last_event_at = 0.0
            self._closed_event_sent = False
            self.transfer_n = 0
            super().__init__(*args, **kwargs)
            self._emit_progress(force=True)

        def display(self, msg: str | None = None, pos: int | None = None) -> None:
            return None

        def update(self, amount: int | float = 1) -> bool | None:
            with self._event_lock:
                result = super().update(amount)
                self._emit_progress()
                return result

        def update_transfer(self, amount: int | float = 1) -> None:
            with self._event_lock:
                self.transfer_n += amount
                self._emit_progress()

        def set_transfer_postfix_str(self, _value: str, refresh: bool = True) -> None:
            return None

        def close(self) -> None:
            if not self._closed_event_sent:
                self._emit_progress(force=True)
                self._closed_event_sent = True
            super().close()

        def _emit_progress(self, *, force: bool = False) -> None:
            now = time.monotonic()
            if not force and now - self._last_event_at < 0.1:
                return
            self._last_event_at = now
            file_total = int(self.total or expected_file_size)
            file_completed = min(max(int(self.n), 0), file_total)
            emit(
                {
                    "type": "progress",
                    "file_index": file_index,
                    "file_count": file_count,
                    "filename": filename,
                    "file_completed": file_completed,
                    "file_total": file_total,
                    "completed_bytes": min(completed_before + file_completed, overall_total),
                    "total_bytes": overall_total,
                }
            )

    return EventTqdm


def _friendly_error(error: BaseException) -> str:
    if isinstance(error, GatedRepoError):
        return "The repository requires approved access. Log in with `hf auth login`."
    if isinstance(error, RepositoryNotFoundError):
        return "The repository was not found, or you do not have access to it."
    if isinstance(error, RevisionNotFoundError):
        return "The revision referenced by the link was not found."
    if isinstance(error, (EntryNotFoundError, RemoteEntryNotFoundError)):
        return "One of the calculated GGUF shards was not found in the repository."
    if isinstance(error, HfHubHTTPError):
        return f"Hugging Face returned a network error: {error}"
    if isinstance(error, KeyboardInterrupt):
        return "The download was interrupted."
    message = str(error).strip()
    return message or error.__class__.__name__

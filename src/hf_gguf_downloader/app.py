from __future__ import annotations

import multiprocessing as mp
import queue
import tkinter as tk
from contextlib import suppress
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config import load_download_directory, save_download_directory
from .links import LinkParseError, parse_huggingface_url
from .worker import run_download_worker

_POLL_INTERVAL_MS = 100


class DownloaderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("HF GGUF Downloader")
        self.root.geometry("820x215")
        self.root.minsize(640, 215)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.url = tk.StringVar()
        self.directory = tk.StringVar(value=load_download_directory())
        self.status = tk.StringVar(value="Ready")
        self.percentage = tk.StringVar(value="0%")

        self._context = mp.get_context("spawn")
        self._event_queue: Any | None = None
        self._process: mp.Process | None = None
        self._terminal_event_seen = False
        self._cancel_requested = False
        self._dead_poll_count = 0
        self._build_ui()

    def _build_ui(self) -> None:
        self.root.columnconfigure(1, weight=1)

        ttk.Label(self.root, text="URL:").grid(row=0, column=0, padx=(12, 8), pady=(14, 6), sticky="w")
        self.url_entry = ttk.Entry(self.root, textvariable=self.url)
        self.url_entry.grid(row=0, column=1, columnspan=2, padx=(0, 12), pady=(14, 6), sticky="ew")

        ttk.Label(self.root, text="Directory:").grid(row=1, column=0, padx=(12, 8), pady=6, sticky="w")
        self.directory_entry = ttk.Entry(self.root, textvariable=self.directory)
        self.directory_entry.grid(row=1, column=1, padx=(0, 6), pady=6, sticky="ew")
        self.browse_button = ttk.Button(self.root, text="...", width=4, command=self._choose_directory)
        self.browse_button.grid(row=1, column=2, padx=(0, 12), pady=6, sticky="e")

        ttk.Label(self.root, text="Progress:").grid(row=2, column=0, padx=(12, 8), pady=6, sticky="w")
        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.grid(row=2, column=1, padx=(0, 6), pady=6, sticky="ew")
        ttk.Label(self.root, textvariable=self.percentage, width=7, anchor="e").grid(
            row=2, column=2, padx=(0, 12), pady=6, sticky="e"
        )

        self.status_label = ttk.Label(self.root, textvariable=self.status, anchor="w")
        self.status_label.grid(row=3, column=0, columnspan=3, padx=12, pady=(4, 8), sticky="ew")

        self.start_button = ttk.Button(self.root, text="START", command=self._start)
        self.start_button.grid(row=4, column=0, columnspan=3, padx=12, pady=(2, 12), sticky="ew")

        self.root.bind("<Return>", lambda _event: self._start() if self._process is None else None)
        self.root.bind("<Escape>", lambda _event: self._cancel() if self._process is not None else None)
        self.url_entry.focus_set()

    def _choose_directory(self) -> None:
        selected = filedialog.askdirectory(
            title="Select download directory",
            initialdir=self.directory.get() or None,
        )
        if selected:
            self.directory.set(selected)

    def _start(self) -> None:
        if self._process is not None:
            return
        try:
            spec = parse_huggingface_url(self.url.get())
            download_root = _prepare_download_root(self.directory.get())
        except (LinkParseError, OSError, ValueError) as error:
            messagebox.showerror("Cannot start download", str(error), parent=self.root)
            return

        with suppress(OSError):
            save_download_directory(str(download_root))
        self.directory.set(str(download_root))
        self._event_queue = self._context.Queue()
        self._terminal_event_seen = False
        self._cancel_requested = False
        self._dead_poll_count = 0
        self._process = self._context.Process(
            target=run_download_worker,
            args=(spec.to_worker_payload(download_root), self._event_queue),
            name="hf-gguf-download-worker",
            daemon=True,
        )
        try:
            self._process.start()
        except Exception as error:
            self._cleanup_process()
            messagebox.showerror("Cannot start download", str(error), parent=self.root)
            return

        self._set_running(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.percentage.set("—")
        self.status.set(f"Checking {_format_file_count(len(spec.files))} in the repository…")
        self.root.after(_POLL_INTERVAL_MS, self._poll_worker)

    def _cancel(self) -> None:
        if self._process is None or self._cancel_requested:
            return
        self._cancel_requested = True
        self.start_button.configure(text="CANCELING…", state=tk.DISABLED)
        self.status.set("Canceling download…")
        if self._process.is_alive():
            self._process.terminate()

    def _poll_worker(self) -> None:
        process = self._process
        event_queue = self._event_queue
        if process is None or event_queue is None:
            return

        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)

        if self._process is None:
            return
        if process.is_alive():
            self._dead_poll_count = 0
            self.root.after(_POLL_INTERVAL_MS, self._poll_worker)
            return

        process.join(timeout=0)
        self._dead_poll_count += 1
        if self._dead_poll_count < 2:
            self.root.after(_POLL_INTERVAL_MS, self._poll_worker)
            return
        if not self._terminal_event_seen:
            if self._cancel_requested:
                self._finish("Canceled. Starting again will resume incomplete files.")
            else:
                self._finish(
                    f"The download process exited unexpectedly (code {process.exitcode}).",
                    error=True,
                )

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "planning":
            self.status.set(f"Checking availability of {_format_file_count(event['file_count'])}…")
            return
        if event_type == "plan":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
            self._set_progress(event["completed_bytes"], event["total_bytes"])
            return
        if event_type == "file_start":
            self.status.set(
                f"Downloading {event['file_index']}/{event['file_count']}: {Path(event['filename']).name}"
            )
            return
        if event_type == "progress":
            self._set_progress(event["completed_bytes"], event["total_bytes"])
            self.status.set(
                f"Downloading {event['file_index']}/{event['file_count']}: "
                f"{Path(event['filename']).name} — "
                f"{format_bytes(event['file_completed'])} / {format_bytes(event['file_total'])}"
            )
            return
        if event_type == "file_complete" and event.get("cached"):
            self._set_progress(event["completed_bytes"], event["total_bytes"])
            self.status.set(f"Already available: {Path(event['filename']).name}")
            return
        if event_type == "complete":
            self._terminal_event_seen = True
            self._set_progress(event["total_bytes"], event["total_bytes"])
            self._finish(f"Download complete. Saved to: {event['local_dir']}")
            return
        if event_type == "error":
            self._terminal_event_seen = True
            self._finish(str(event["message"]), error=True)

    def _set_progress(self, completed: int, total: int) -> None:
        percent = 100.0 if total <= 0 else min(max(completed / total * 100.0, 0.0), 100.0)
        self.progress.configure(value=percent)
        self.percentage.set(f"{percent:.1f}%")

    def _set_running(self, running: bool) -> None:
        entry_state = tk.DISABLED if running else tk.NORMAL
        self.url_entry.configure(state=entry_state)
        self.directory_entry.configure(state=entry_state)
        self.browse_button.configure(state=entry_state)
        self.start_button.configure(
            text="CANCEL" if running else "START",
            command=self._cancel if running else self._start,
            state=tk.NORMAL,
        )

    def _finish(self, message: str, *, error: bool = False) -> None:
        self.progress.stop()
        self.status.set(message)
        self._cleanup_process()
        self._set_running(False)
        if error:
            messagebox.showerror("Download error", message, parent=self.root)

    def _cleanup_process(self) -> None:
        if self._process is not None:
            self._process.join(timeout=0)
        if self._event_queue is not None:
            self._event_queue.close()
            self._event_queue.cancel_join_thread()
        self._process = None
        self._event_queue = None
        self._cancel_requested = False
        self._dead_poll_count = 0

    def _on_close(self) -> None:
        if self._process is not None and self._process.is_alive():
            should_close = messagebox.askyesno(
                "Download in progress",
                "Cancel the active download and close the application?",
                parent=self.root,
            )
            if not should_close:
                return
            self._process.terminate()
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.kill()
        self._cleanup_process()
        self.root.destroy()


def _prepare_download_root(raw_directory: str) -> Path:
    value = raw_directory.strip()
    if not value:
        raise ValueError("Select a download directory.")
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError("The selected path is not a directory.")
    return path


def _format_file_count(count: int) -> str:
    return f"{count} {'file' if count == 1 else 'files'}"


def format_bytes(value: int | float) -> str:
    size = float(max(value, 0))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1000 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"


def run_app() -> None:
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()

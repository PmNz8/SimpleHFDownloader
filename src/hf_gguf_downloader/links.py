from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

_SHARD_PATTERN = re.compile(
    r"^(?P<prefix>.+)-(?P<part>\d+)-of-(?P<total>\d+)(?P<extension>\.gguf)$",
    re.IGNORECASE,
)
_ALLOWED_HOSTS = {"huggingface.co", "www.huggingface.co"}
_MAX_SHARDS = 10_000


class LinkParseError(ValueError):
    """Raised when a pasted Hugging Face link cannot describe a GGUF download."""


@dataclass(frozen=True, slots=True)
class DownloadSpec:
    repo_id: str
    owner: str
    repo_name: str
    revision: str
    files: tuple[str, ...]

    def local_repo_dir(self, download_root: str | Path) -> Path:
        return Path(download_root) / self.owner / self.repo_name

    def to_worker_payload(self, download_root: str | Path) -> dict[str, object]:
        return {
            "repo_id": self.repo_id,
            "revision": self.revision,
            "files": list(self.files),
            "local_dir": str(self.local_repo_dir(download_root)),
        }


def parse_huggingface_url(url: str) -> DownloadSpec:
    value = url.strip()
    if not value:
        raise LinkParseError("Paste a link to a GGUF file on Hugging Face.")

    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise LinkParseError("The link must point to https://huggingface.co/.")

    raw_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(raw_segments) < 5:
        raise LinkParseError("Expected a file link in the format owner/repo/resolve/revision/file.gguf.")

    owner = _decode_safe_segment(raw_segments[0], "repository owner")
    repo_name = _decode_safe_segment(raw_segments[1], "repository name")
    action = raw_segments[2].lower()
    if action not in {"resolve", "blob"}:
        raise LinkParseError("The link must reference a file using a /resolve/ or /blob/ segment.")

    revision = unquote(raw_segments[3])
    if not revision or revision in {".", ".."} or "\\" in revision:
        raise LinkParseError("The link contains an invalid revision.")

    remote_segments = tuple(_decode_safe_segment(segment, "file path") for segment in raw_segments[4:])
    remote_path = PurePosixPath(*remote_segments)
    filename = remote_path.name
    if not filename.lower().endswith(".gguf"):
        raise LinkParseError("The link must point to a file with the .gguf extension.")

    files = _expand_shards(remote_path)
    return DownloadSpec(
        repo_id=f"{owner}/{repo_name}",
        owner=owner,
        repo_name=repo_name,
        revision=revision,
        files=files,
    )


def _decode_safe_segment(raw_segment: str, label: str) -> str:
    segment = unquote(raw_segment)
    if not segment or segment in {".", ".."} or "/" in segment or "\\" in segment:
        raise LinkParseError(f"Invalid {label} segment.")
    return segment


def _expand_shards(remote_path: PurePosixPath) -> tuple[str, ...]:
    match = _SHARD_PATTERN.fullmatch(remote_path.name)
    if match is None:
        return (remote_path.as_posix(),)

    part_text = match.group("part")
    total_text = match.group("total")
    part = int(part_text)
    total = int(total_text)
    if total < 1 or part < 1 or part > total:
        raise LinkParseError("The GGUF part number does not match the shard count.")
    if total > _MAX_SHARDS:
        raise LinkParseError(f"The link declares more than {_MAX_SHARDS} shards.")

    parent = "" if remote_path.parent == PurePosixPath(".") else f"{remote_path.parent.as_posix()}/"
    prefix = match.group("prefix")
    extension = match.group("extension")
    width = len(part_text)
    return tuple(
        f"{parent}{prefix}-{index:0{width}d}-of-{total_text}{extension}" for index in range(1, total + 1)
    )

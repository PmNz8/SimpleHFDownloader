# HF GGUF Downloader

> Unofficial project, not affiliated with Hugging Face.

A minimal Windows desktop application for downloading complete GGUF models from Hugging Face.
Paste a link to any GGUF shard, choose a destination directory, and select **START**. For a filename
such as `model-00001-of-00003.gguf`, the application automatically discovers and downloads all three
parts.

![HF GGUF Downloader](gui.png)

## Features

- accepts a Hugging Face `resolve` URL for any `.gguf` shard,
- automatically expands sharded filenames and verifies every expected part,
- shows per-file and total byte progress,
- supports cancellation while preserving resumable partial downloads,
- reuses the Hugging Face cache and credentials,
- works with public, private, and gated repositories,
- builds as a single Windows EXE with PyInstaller.

## How downloads work

The current successor to `huggingface-cli` is the `hf` command. Both are interfaces to the official
`huggingface_hub` Python package. This application calls the same download backend directly because
redirected CLI output does not provide a stable machine-readable progress stream.

Direct integration lets the GUI report byte-level progress, cancel an active worker process, and keep
the partial cache needed to resume a transfer. It also allows the runtime to be packaged without a
separate CLI installation.

See the official [Hugging Face CLI documentation](https://huggingface.co/docs/huggingface_hub/en/guides/cli)
for authentication details.

## Run from source

Requirements:

- Windows,
- Python 3.11, 3.12, or 3.13,
- [`uv`](https://docs.astral.sh/uv/).

```powershell
uv sync --group dev
uv run hf-gguf-downloader
```

Public repositories do not require authentication. For private or gated repositories, authenticate
with the standard CLI first, or provide an `HF_TOKEN` environment variable:

```powershell
uv run hf auth login
```

## Destination layout

For a base directory of `E:\LLMs` and the repository `unsloth/Model-GGUF`, downloaded files are stored
under:

```text
E:\LLMs\unsloth\Model-GGUF\<repository subdirectory>\file.gguf
```

The hidden `.cache\huggingface` directory inside the repository folder contains metadata used to skip
completed files and resume interrupted transfers. Do not remove it during a download.

## Tests and checks

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check src tests scripts
```

## Build the Windows EXE

```powershell
.\build.ps1
```

The build output is written to `dist\HF-GGUF-Downloader.exe`. The script only builds locally; it does
not publish anything.

When distributing the binary, include all three files from `dist`:

- `HF-GGUF-Downloader.exe`,
- `LICENSE.txt`,
- `THIRD_PARTY_NOTICES.txt`.

The executable is not digitally signed.

## License

The current implementation is available under the [MIT License](LICENSE). Notices and license texts
for components bundled into the EXE are listed in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
Legacy versions in this repository remain subject to the license included with those versions.

This application does not grant a license to downloaded models. Each model remains subject to the
terms chosen by the author or owner of its Hugging Face repository.

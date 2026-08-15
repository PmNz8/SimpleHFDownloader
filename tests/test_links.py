import pytest

from hf_gguf_downloader.links import LinkParseError, parse_huggingface_url

EXAMPLE_URL = (
    "https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF/resolve/main/"
    "UD-Q2_K_XL/DeepSeek-V4-Flash-0731-UD-Q2_K_XL-00001-of-00003.gguf"
)


def test_expands_all_shards_from_example() -> None:
    spec = parse_huggingface_url(EXAMPLE_URL)

    assert spec.repo_id == "unsloth/DeepSeek-V4-Flash-0731-GGUF"
    assert spec.revision == "main"
    assert spec.files == (
        "UD-Q2_K_XL/DeepSeek-V4-Flash-0731-UD-Q2_K_XL-00001-of-00003.gguf",
        "UD-Q2_K_XL/DeepSeek-V4-Flash-0731-UD-Q2_K_XL-00002-of-00003.gguf",
        "UD-Q2_K_XL/DeepSeek-V4-Flash-0731-UD-Q2_K_XL-00003-of-00003.gguf",
    )


def test_expands_from_any_shard_and_keeps_width() -> None:
    spec = parse_huggingface_url(
        "https://huggingface.co/acme/model/resolve/v1/sub/model-02-of-12.GGUF?download=true"
    )

    assert len(spec.files) == 12
    assert spec.files[0] == "sub/model-01-of-12.GGUF"
    assert spec.files[-1] == "sub/model-12-of-12.GGUF"


def test_accepts_browser_blob_link_and_unsharded_file() -> None:
    spec = parse_huggingface_url("https://huggingface.co/acme/model/blob/main/quantizations/model%20q4.gguf")

    assert spec.files == ("quantizations/model q4.gguf",)


def test_accepts_unsharded_file_at_repository_root() -> None:
    spec = parse_huggingface_url("https://huggingface.co/acme/model/resolve/main/model.gguf")

    assert spec.files == ("model.gguf",)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/acme/model/resolve/main/model.gguf",
        "https://huggingface.co/acme/model/tree/main/model.gguf",
        "https://huggingface.co/acme/model/resolve/main/model.bin",
        "https://huggingface.co/acme/model/resolve/main/model-00000-of-00003.gguf",
        "https://huggingface.co/acme/model/resolve/main/model-00004-of-00003.gguf",
        "https://huggingface.co/acme/model/resolve/main/%2E%2E/model.gguf",
    ],
)
def test_rejects_invalid_links(url: str) -> None:
    with pytest.raises(LinkParseError):
        parse_huggingface_url(url)

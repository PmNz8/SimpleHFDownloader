$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    uv sync --group dev
    uv run python scripts/generate_third_party_notices.py
    uv run pyinstaller --clean --noconfirm hf_gguf_downloader.spec
    Copy-Item -LiteralPath "LICENSE" -Destination "dist\LICENSE.txt" -Force
    Copy-Item -LiteralPath "THIRD_PARTY_NOTICES.txt" -Destination "dist\THIRD_PARTY_NOTICES.txt" -Force
}
finally {
    Pop-Location
}

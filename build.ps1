$ErrorActionPreference = "Stop"

Push-Location $PSScriptRoot
try {
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) { throw "Dependency synchronization failed." }
    uv run python scripts/generate_third_party_notices.py
    if ($LASTEXITCODE -ne 0) { throw "License notice generation failed." }
    uv run pyinstaller --clean --noconfirm hf_gguf_downloader.spec
    if ($LASTEXITCODE -ne 0) { throw "EXE build failed." }
    Copy-Item -LiteralPath "LICENSE" -Destination "dist\LICENSE.txt" -Force
    Copy-Item -LiteralPath "THIRD_PARTY_NOTICES.txt" -Destination "dist\THIRD_PARTY_NOTICES.txt" -Force
}
finally {
    Pop-Location
}

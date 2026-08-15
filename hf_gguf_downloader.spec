# -*- mode: python ; coding: utf-8 -*-

# huggingface_hub exposes hf_hub_download through a lazy import. Name that
# implementation module and the native hf_xet extension explicitly, without
# collecting unrelated CLI and development modules from either package.
hiddenimports = ["huggingface_hub.file_download", "hf_xet"]

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "pygments", "setuptools"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HF-GGUF-Downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

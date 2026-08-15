from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()

    from hf_gguf_downloader.__main__ import main

    main()

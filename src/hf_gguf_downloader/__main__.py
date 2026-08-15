from multiprocessing import freeze_support


def main() -> None:
    freeze_support()

    from .app import run_app

    run_app()


if __name__ == "__main__":
    main()

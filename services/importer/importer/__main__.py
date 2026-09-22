from .config import load_settings
from .run import run_import


def main() -> None:
    run_import(load_settings())


if __name__ == "__main__":
    main()

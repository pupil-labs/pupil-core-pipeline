import pathlib
from importlib.metadata import PackageNotFoundError, version

__version__: str = version("core")


def _default_shared_modules_loc():
    return str(
        pathlib.Path(__file__).parent / "_core_plugins" / "pupil_src" / "shared_modules"
    )


__all__ = ["__version__"]

if __package__:
    from .cli import main
else:
    # The source launchers run this file with -I -S. Register just this package
    # so unrelated files beside the checkout never enter Python's import path.
    import importlib.util
    from pathlib import Path
    import sys

    package_init = Path(__file__).resolve().with_name('__init__.py')
    spec = importlib.util.spec_from_file_location('open_fire_toolkit', package_init)
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    from open_fire_toolkit.cli import main

if __name__ == '__main__':
    raise SystemExit(main())

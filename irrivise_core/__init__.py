# Shim package for irrivise_core.
# Extends this package's __path__ to the real implementation in packages/irrivise_core/irrivise_core.

from pathlib import Path

_impl_path = Path(__file__).parent / "packages" / "irrivise_core" / "irrivise_core"
if not _impl_path.is_dir():
    raise ImportError(f"irrivise_core implementation not found at {_impl_path}")
# Add the implementation directory to the package search path for submodule imports.
__path__.append(str(_impl_path))


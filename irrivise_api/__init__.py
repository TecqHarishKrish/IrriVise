# Shim package for irrivise_api.
# Extends this package's __path__ to the real implementation in services/api/irrivise_api.

from pathlib import Path

_impl_path = Path(__file__).parent / "services" / "api" / "irrivise_api"
if not _impl_path.is_dir():
    raise ImportError(f"irrivise_api implementation not found at {_impl_path}")
# Add the implementation directory to the package search path.
__path__.append(str(_impl_path))

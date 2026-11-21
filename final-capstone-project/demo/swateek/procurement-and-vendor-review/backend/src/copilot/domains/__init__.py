"""Domain-pack loading. The core never hard-codes a domain; it reads domains/<name>/."""

from copilot.domains.loader import DomainConfig, load_domain
from copilot.domains.manifest import Manifest, ManifestLock, Source, load_manifest

__all__ = ["DomainConfig", "Manifest", "ManifestLock", "Source", "load_domain", "load_manifest"]

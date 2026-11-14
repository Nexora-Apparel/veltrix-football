"""Environment-driven runtime wiring for the shared V2 website/Telegram bundle.

No verifier or source is inferred. Both dependencies must be explicitly supplied
by deployment configuration; absent or invalid configuration remains fail-closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
import re
from typing import Callable, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from veltrix_v2.reporting.artifact_bundle import PORTABLE_BUNDLE_MAX_BYTES


_REPOSITORY = "Nexora-Apparel/veltrix-football"
_FIXED_BUNDLE_PATH = (
    "/Nexora-Apparel/veltrix-football/command-data/public-data/v2_report_bundle.json"
)
_VERSIONED_BUNDLE_PREFIX = (
    "/Nexora-Apparel/veltrix-football/command-data/public-data/bundles/"
)
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


@dataclass(frozen=True, slots=True)
class RuntimePublicationDependencies:
    verifier: Callable
    bundle_url: str
    bundle_reader: Callable[[], bytes]


def validate_public_bundle_url(url: str) -> str:
    parsed = urlsplit(url)
    fixed_path = parsed.path == _FIXED_BUNDLE_PATH
    versioned_path = (
        parsed.path.startswith(_VERSIONED_BUNDLE_PREFIX)
        and parsed.path.endswith(".bundle.json")
        and _SAFE_REPORT_ID.fullmatch(
            parsed.path[len(_VERSIONED_BUNDLE_PREFIX):-len(".bundle.json")]
        ) is not None
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != "raw.githubusercontent.com"
        or not (fixed_path or versioned_path)
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("PORTABLE_REPORT_BUNDLE_URL_NOT_ALLOWLISTED")
    return url


def _load_verifier_factory(spec: str) -> Callable[[], Callable]:
    if not isinstance(spec, str) or ":" not in spec:
        raise RuntimeError("AUTHORITATIVE_PUBLICATION_VERIFIER_FACTORY_REQUIRED")
    module_name, attribute = spec.split(":", 1)
    if (
        not module_name.startswith("veltrix_v2.")
        or not attribute.isidentifier()
    ):
        raise RuntimeError("PUBLICATION_VERIFIER_FACTORY_NOT_ALLOWLISTED")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise RuntimeError("PUBLICATION_VERIFIER_FACTORY_NOT_CALLABLE")
    return factory


def _build_bundle_reader(url: str) -> Callable[[], bytes]:
    def reader() -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "VELTRIX-FOOTBALL/2.0",
                "Cache-Control": "no-cache",
            },
            method="GET",
        )
        with urlopen(request, timeout=8) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read(PORTABLE_BUNDLE_MAX_BYTES + 1)
        if status != 200:
            raise RuntimeError("PORTABLE_REPORT_BUNDLE_FETCH_FAILED")
        if not raw or len(raw) > PORTABLE_BUNDLE_MAX_BYTES:
            raise ValueError("PORTABLE_REPORT_BUNDLE_SIZE_INVALID")
        return raw
    return reader


def load_runtime_publication_dependencies(
    environ: Mapping[str, str] | None = None,
) -> RuntimePublicationDependencies | None:
    env = os.environ if environ is None else environ
    factory_spec = env.get("VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY", "").strip()
    bundle_url = env.get("VELTRIX_V2_REPORT_BUNDLE_URL", "").strip()
    if not factory_spec and not bundle_url:
        return None
    if not factory_spec or not bundle_url:
        raise RuntimeError("V2_PUBLICATION_RUNTIME_CONFIGURATION_INCOMPLETE")

    allowed_url = validate_public_bundle_url(bundle_url)
    factory = _load_verifier_factory(factory_spec)
    verifier = factory()
    if not callable(verifier):
        raise RuntimeError("AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED")
    return RuntimePublicationDependencies(
        verifier=verifier,
        bundle_url=allowed_url,
        bundle_reader=_build_bundle_reader(allowed_url),
    )

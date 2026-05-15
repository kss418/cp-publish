#!/usr/bin/env python3
"""Shared HTTPS helpers for cp-publish network scripts."""

from __future__ import annotations

import os
import ssl
import sys
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any


CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
COMMON_CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/ssl/cert.pem",
    "/usr/local/etc/openssl/cert.pem",
    "/opt/homebrew/etc/openssl@3/cert.pem",
    "/opt/homebrew/etc/openssl@1.1/cert.pem",
)


def _path_or_none(value: str | None) -> Path | None:
    if not value:
        return None
    try:
        return Path(value).expanduser()
    except (OSError, RuntimeError):
        return None


def _existing_file(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path.resolve()
    except OSError:
        return None
    return None


def _certifi_bundle() -> Path | None:
    try:
        import certifi  # type: ignore[import-not-found]
    except Exception:
        return None
    return _existing_file(_path_or_none(certifi.where()))


def _msys2_root(prefix: Path) -> Path | None:
    parts = {part.lower() for part in prefix.parts}
    if "msys64" not in parts:
        return None
    for parent in (prefix, *prefix.parents):
        if parent.name.lower() == "msys64":
            return parent
    return None


def candidate_ca_bundles() -> list[tuple[str, Path]]:
    paths = ssl.get_default_verify_paths()
    candidates: list[tuple[str, Path | None]] = []

    for name in CA_ENV_VARS:
        candidates.append((name, _path_or_none(os.environ.get(name))))

    candidates.append(("certifi", _certifi_bundle()))
    candidates.append(("python-default-cafile", _path_or_none(paths.cafile)))
    candidates.append(("openssl-default-cafile", _path_or_none(paths.openssl_cafile)))

    prefixes = {Path(sys.prefix), Path(sys.base_prefix), Path(sys.exec_prefix)}
    for prefix in prefixes:
        candidates.append((f"{prefix}-etc-ssl-cert.pem", prefix / "etc" / "ssl" / "cert.pem"))
        msys_root = _msys2_root(prefix)
        if msys_root is not None:
            candidates.append(("msys2-usr-ssl-cert.pem", msys_root / "usr" / "ssl" / "cert.pem"))
            candidates.append(
                ("msys2-usr-ssl-ca-bundle.crt", msys_root / "usr" / "ssl" / "certs" / "ca-bundle.crt")
            )

    for path in COMMON_CA_FILES:
        candidates.append(("common-ca-file", Path(path)))

    result: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, path in candidates:
        existing = _existing_file(path)
        if existing is None:
            continue
        key = str(existing).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append((source, existing))
    return result


@lru_cache(maxsize=1)
def selected_ca_bundle() -> Path | None:
    for source, bundle in candidate_ca_bundles():
        if source in CA_ENV_VARS or source == "certifi":
            return bundle

    paths = ssl.get_default_verify_paths()
    default_cafile = _existing_file(_path_or_none(paths.cafile))
    if default_cafile is not None:
        return None

    default_openssl_cafile = _existing_file(_path_or_none(paths.openssl_cafile))
    if default_openssl_cafile is not None:
        return None

    for _source, bundle in candidate_ca_bundles():
        return bundle
    return None


@lru_cache(maxsize=1)
def verified_ssl_context() -> ssl.SSLContext:
    bundle = selected_ca_bundle()
    if bundle is None:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=str(bundle))


def open_url(
    request: urllib.request.Request | str,
    *,
    timeout: int,
) -> Any:
    return urllib.request.urlopen(request, timeout=timeout, context=verified_ssl_context())


def is_cert_verification_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return True
        return "CERTIFICATE_VERIFY_FAILED" in str(reason)
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _exists_text(path: str | None) -> str:
    if not path:
        return "(unset)"
    candidate = Path(path)
    return f"{path} ({'exists' if candidate.exists() else 'missing'})"


def https_diagnostics() -> dict[str, Any]:
    paths = ssl.get_default_verify_paths()
    return {
        "python": sys.executable,
        "openssl": ssl.OPENSSL_VERSION,
        "environment": {name: os.environ.get(name) for name in CA_ENV_VARS},
        "default_verify_paths": {
            "cafile": paths.cafile,
            "capath": paths.capath,
            "openssl_cafile": paths.openssl_cafile,
            "openssl_capath": paths.openssl_capath,
        },
        "selected_ca_bundle": str(selected_ca_bundle()) if selected_ca_bundle() else None,
        "candidate_ca_bundles": [
            {"source": source, "path": str(path)} for source, path in candidate_ca_bundles()
        ],
    }


def format_url_error(exc: urllib.error.URLError) -> str:
    reason = exc.reason
    if not is_cert_verification_error(exc):
        return str(reason)

    paths = ssl.get_default_verify_paths()
    bundle = selected_ca_bundle()
    lines = [
        f"TLS certificate verification failed: {reason}",
        f"Python: {sys.executable}",
        f"OpenSSL: {ssl.OPENSSL_VERSION}",
        f"default cafile: {_exists_text(paths.cafile)}",
        f"default OpenSSL cafile: {_exists_text(paths.openssl_cafile)}",
    ]
    if bundle:
        lines.append(f"selected CA bundle: {bundle}")
        lines.append(f"try setting SSL_CERT_FILE={bundle}")
    else:
        lines.append("no usable CA bundle was found")
        lines.append("install/update CA certificates or set SSL_CERT_FILE to a valid CA bundle")
    return "\n".join(lines)


def probe_https(url: str, *, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "cp-publish/0.1"})
    try:
        with open_url(request, timeout=timeout) as response:
            response.read(1)
            return {
                "url": url,
                "ok": True,
                "status": getattr(response, "status", None),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"url": url, "ok": True, "status": exc.code, "error": None}
    except urllib.error.URLError as exc:
        return {"url": url, "ok": False, "status": None, "error": format_url_error(exc)}
    except TimeoutError as exc:
        return {"url": url, "ok": False, "status": None, "error": str(exc)}

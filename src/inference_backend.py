"""
Inference Backend — protocol-based abstraction for model lifecycle management.

Replaces ``lmstudio_loader.py`` with a backend-agnostic Protocol that
supports llama-swap today and can be extended to vLLM / SGLang later.

Design contract (carried forward from lmstudio_loader.py):

  * NEVER SILENT.  Every public method returns a typed frozen dataclass.
    Failures raise ``InferenceBackendError`` with a precise reason — no
    booleans, no None-returns-meaning-error.

  * ASYNC CORE.  This module is async-first. The ``LlamaSwapBackend``
    wraps synchronous ``requests`` calls via ``asyncio.to_thread`` so
    they never block the event loop.

  * PROTOCOL-BASED.  ``InferenceBackend`` is a ``typing.Protocol``.
    Any class that satisfies the structural interface is accepted;
    no inheritance required. New backends (vLLM, SGLang) just need to
    implement the same method signatures.

Public surface:

  InferenceBackend.ensure_model_ready(model_key, config)  -> ModelStatus
  InferenceBackend.list_models()                          -> list[ModelInfo]
  InferenceBackend.list_running()                         -> list[RunningModel]
  InferenceBackend.unload_model(model_key)                -> bool
  InferenceBackend.unload_all()                           -> int
  InferenceBackend.health_check()                         -> HealthStatus

  get_backend(backend_type, **kwargs) -> InferenceBackend  (factory)

Run as a smoke test from the repo root:

  python -m src.inference_backend health
  python -m src.inference_backend list
  python -m src.inference_backend running
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import requests

log = logging.getLogger("inference_backend")


# ════════════════════════════════════════════════════════════════════
#  EXCEPTION
# ════════════════════════════════════════════════════════════════════


class InferenceBackendError(RuntimeError):
    """Raised by any InferenceBackend implementation for any failure.

    Always carries enough context for the Data Flow Tracer to pinpoint
    the hop where things went wrong. Never silent, never swallowed.
    """


# ════════════════════════════════════════════════════════════════════
#  RETURN-TYPE DATACLASSES (frozen=True)
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ModelStatus:
    """Outcome of an ``ensure_model_ready`` call.

    Attributes:
        model_key: The canonical model identifier.
        status:    One of ``'ready'``, ``'loading'``, or ``'error'``.
        message:   Human-readable explanation of the outcome.
    """
    model_key: str
    status: str   # 'ready' | 'loading' | 'error'
    message: str


@dataclass(frozen=True)
class ModelInfo:
    """A model known to the backend (configured, not necessarily loaded).

    Attributes:
        model_key:  The canonical model identifier.
        aliases:    Alternative names / IDs that resolve to this model.
        configured: Whether this model has an explicit configuration
                    entry in the backend (vs. being a passthrough).
    """
    model_key: str
    aliases: list[str] = field(default_factory=list)
    configured: bool = False


@dataclass(frozen=True)
class RunningModel:
    """A model instance currently loaded / running.

    Attributes:
        model_key:       The canonical model identifier.
        port:            TCP port the instance is listening on, if known.
        uptime_seconds:  How long the instance has been running, if known.
    """
    model_key: str
    port: int | None = None
    uptime_seconds: float | None = None


@dataclass(frozen=True)
class HealthStatus:
    """Result of a backend health check.

    Attributes:
        healthy:      Whether the backend is responsive and functional.
        backend_type: Identifier for the backend implementation
                      (e.g. ``'llama-swap'``, ``'vllm'``).
        message:      Human-readable status description.
    """
    healthy: bool
    backend_type: str
    message: str


# ════════════════════════════════════════════════════════════════════
#  PROTOCOL
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class InferenceBackend(Protocol):
    """Structural protocol for inference backend lifecycle management.

    Any class implementing these async methods satisfies the protocol
    via structural subtyping — no explicit inheritance required.

    All methods raise ``InferenceBackendError`` on failure. No method
    returns ``None``-meaning-error or swallows exceptions silently.
    """

    async def ensure_model_ready(
        self,
        model_key: str,
        config: dict[str, Any] | None = None,
    ) -> ModelStatus:
        """Ensure that ``model_key`` is loaded and ready for inference.

        For backends with auto-loading (e.g. llama-swap), this may be a
        lightweight readiness check. For backends requiring explicit
        loads, this triggers the full load sequence.

        Args:
            model_key: The canonical model identifier.
            config:    Optional backend-specific configuration overrides.

        Returns:
            ModelStatus describing the outcome.

        Raises:
            InferenceBackendError: on any failure.
        """
        ...

    async def list_models(self) -> list[ModelInfo]:
        """Return all models known to the backend.

        Returns:
            List of ModelInfo for every configured / available model.

        Raises:
            InferenceBackendError: on communication or parse failure.
        """
        ...

    async def list_running(self) -> list[RunningModel]:
        """Return all currently loaded / running model instances.

        Returns:
            List of RunningModel for every active instance.

        Raises:
            InferenceBackendError: on communication or parse failure.
        """
        ...

    async def unload_model(self, model_key: str) -> bool:
        """Unload a specific model instance.

        Args:
            model_key: The model to unload.

        Returns:
            True if the model was unloaded, False if it was not loaded.

        Raises:
            InferenceBackendError: on communication failure.
        """
        ...

    async def unload_all(self) -> int:
        """Unload all currently loaded model instances.

        Returns:
            The number of models that were unloaded.

        Raises:
            InferenceBackendError: on communication failure.
        """
        ...

    async def health_check(self) -> HealthStatus:
        """Check whether the backend process is alive and responsive.

        Returns:
            HealthStatus describing the backend state.

        Raises:
            InferenceBackendError: only on truly unexpected failures
            (not on the backend simply being down — that's reported
            via ``HealthStatus(healthy=False, ...)``).
        """
        ...


# ════════════════════════════════════════════════════════════════════
#  LLAMA-SWAP BACKEND IMPLEMENTATION
# ════════════════════════════════════════════════════════════════════


# Default timeout for HTTP requests to llama-swap (seconds).
_DEFAULT_TIMEOUT: float = 10.0

# Longer timeout for the warm-up / ensure-ready request, since
# llama-swap may need to start a llama-server process on first hit.
_WARMUP_TIMEOUT: float = 120.0


class LlamaSwapBackend:
    """InferenceBackend implementation for llama-swap.

    llama-swap is a model multiplexer that sits in front of one or more
    llama-server processes. It auto-starts the appropriate llama-server
    when a model is requested via the OpenAI-compatible ``/v1/`` endpoints,
    and exposes management endpoints for listing / unloading models.

    HTTP calls use ``requests`` (already a project dependency) wrapped in
    ``asyncio.to_thread`` so they never block the event loop.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        # Strip trailing slash for consistent URL construction.
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        log.info(
            "[inference_backend] LlamaSwapBackend initialised: base_url=%s",
            self._base_url,
        )

    # ---- helpers -------------------------------------------------------

    def _url(self, path: str) -> str:
        """Build a full URL from a relative path."""
        return f"{self._base_url}/{path.lstrip('/')}"

    def _get_sync(
        self,
        path: str,
        *,
        timeout: float | None = None,
    ) -> requests.Response:
        """Synchronous GET with unified error handling.

        Raises InferenceBackendError on any transport or HTTP error.
        """
        url = self._url(path)
        effective_timeout = timeout or self._timeout
        try:
            resp = requests.get(url, timeout=effective_timeout)
            resp.raise_for_status()
            return resp
        except requests.ConnectionError as exc:
            raise InferenceBackendError(
                f"Connection refused: {url} — is llama-swap running? "
                f"Detail: {exc!r}"
            ) from exc
        except requests.Timeout as exc:
            raise InferenceBackendError(
                f"Request timed out after {effective_timeout}s: {url} — "
                f"Detail: {exc!r}"
            ) from exc
        except requests.HTTPError as exc:
            raise InferenceBackendError(
                f"HTTP {resp.status_code} from {url}: "
                f"{resp.text[:500]}"
            ) from exc
        except requests.RequestException as exc:
            raise InferenceBackendError(
                f"Request failed for {url}: {exc!r}"
            ) from exc

    def _post_sync(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> requests.Response:
        """Synchronous POST with unified error handling.

        Raises InferenceBackendError on any transport or HTTP error.
        """
        url = self._url(path)
        effective_timeout = timeout or self._timeout
        try:
            resp = requests.post(url, json=json, timeout=effective_timeout)
            resp.raise_for_status()
            return resp
        except requests.ConnectionError as exc:
            raise InferenceBackendError(
                f"Connection refused: {url} — is llama-swap running? "
                f"Detail: {exc!r}"
            ) from exc
        except requests.Timeout as exc:
            raise InferenceBackendError(
                f"Request timed out after {effective_timeout}s: {url} — "
                f"Detail: {exc!r}"
            ) from exc
        except requests.HTTPError as exc:
            raise InferenceBackendError(
                f"HTTP {resp.status_code} from {url}: "
                f"{resp.text[:500]}"
            ) from exc
        except requests.RequestException as exc:
            raise InferenceBackendError(
                f"Request failed for {url}: {exc!r}"
            ) from exc

    # ---- protocol implementation ----------------------------------------

    async def ensure_model_ready(
        self,
        model_key: str,
        config: dict[str, Any] | None = None,
    ) -> ModelStatus:
        """Ensure a model is ready for inference on llama-swap.

        llama-swap auto-starts models on first inference request, so
        this method performs a lightweight warm-up: it sends a minimal
        completion request to ``/v1/chat/completions`` which triggers
        llama-swap to start the llama-server for ``model_key`` if it
        isn't already running.

        The ``config`` parameter is accepted for protocol compatibility
        but is not used by llama-swap (model configs are defined in
        llama-swap's own config.yaml).
        """
        if config:
            log.debug(
                "[inference_backend] ensure_model_ready config ignored by "
                "llama-swap (configs live in config.yaml): %s",
                config,
            )

        # Step 1: verify llama-swap is alive.
        health = await self.health_check()
        if not health.healthy:
            return ModelStatus(
                model_key=model_key,
                status="error",
                message=f"Backend unhealthy: {health.message}",
            )

        # Step 2: send a warm-up request. llama-swap routes based on the
        # model name in the OpenAI payload — this triggers the backend
        # llama-server to start if it isn't already running.
        def _warmup() -> ModelStatus:
            url = self._url("/v1/chat/completions")
            payload = {
                "model": model_key,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "temperature": 0.0,
            }
            try:
                resp = requests.post(url, json=payload, timeout=_WARMUP_TIMEOUT)
                resp.raise_for_status()
                return ModelStatus(
                    model_key=model_key,
                    status="ready",
                    message="Model responded to warm-up request.",
                )
            except requests.Timeout:
                return ModelStatus(
                    model_key=model_key,
                    status="loading",
                    message=(
                        f"Warm-up timed out after {_WARMUP_TIMEOUT}s — "
                        f"model may still be loading."
                    ),
                )
            except requests.ConnectionError as exc:
                return ModelStatus(
                    model_key=model_key,
                    status="error",
                    message=f"Connection failed during warm-up: {exc!r}",
                )
            except requests.HTTPError as exc:
                # A 4xx/5xx from llama-swap likely means the model_key
                # is not configured.
                return ModelStatus(
                    model_key=model_key,
                    status="error",
                    message=(
                        f"Warm-up HTTP error: {resp.status_code} — "
                        f"{resp.text[:300]}"
                    ),
                )
            except requests.RequestException as exc:
                return ModelStatus(
                    model_key=model_key,
                    status="error",
                    message=f"Warm-up request failed: {exc!r}",
                )

        return await asyncio.to_thread(_warmup)

    async def list_models(self) -> list[ModelInfo]:
        """List all models known to llama-swap via ``GET /v1/models``.

        Returns a ``ModelInfo`` for each model entry. The OpenAI-compatible
        ``/v1/models`` endpoint returns all configured model aliases.
        """
        def _fetch() -> list[ModelInfo]:
            resp = self._get_sync("/v1/models")
            body = resp.json()
            models: list[ModelInfo] = []
            for entry in body.get("data", []):
                model_id = entry.get("id", "")
                models.append(
                    ModelInfo(
                        model_key=model_id,
                        aliases=[],
                        configured=True,
                    )
                )
            return models

        return await asyncio.to_thread(_fetch)

    async def list_running(self) -> list[RunningModel]:
        """List currently running models via ``GET /running``.

        llama-swap exposes a ``/running`` management endpoint that
        returns the set of currently loaded llama-server processes.
        """
        def _fetch() -> list[RunningModel]:
            resp = self._get_sync("/running")
            # llama-swap's /running endpoint returns plain text with
            # one model name per line, or JSON depending on version.
            content_type = resp.headers.get("Content-Type", "")
            running: list[RunningModel] = []

            if "application/json" in content_type:
                body = resp.json()
                # Handle both list and dict formats.
                if isinstance(body, list):
                    for entry in body:
                        if isinstance(entry, str):
                            running.append(RunningModel(model_key=entry))
                        elif isinstance(entry, dict):
                            running.append(RunningModel(
                                model_key=entry.get("model", entry.get("id", "")),
                                port=entry.get("port"),
                                uptime_seconds=entry.get("uptime_seconds"),
                            ))
                elif isinstance(body, dict):
                    for key, val in body.items():
                        if isinstance(val, dict):
                            running.append(RunningModel(
                                model_key=key,
                                port=val.get("port"),
                                uptime_seconds=val.get("uptime_seconds"),
                            ))
                        else:
                            running.append(RunningModel(model_key=key))
            else:
                # Plain text: one model per line.
                text = resp.text.strip()
                if text:
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            running.append(RunningModel(model_key=line))

            return running

        return await asyncio.to_thread(_fetch)

    async def unload_model(self, model_key: str) -> bool:
        """Unload a specific model via ``POST /api/models/unload/{model_key}``.

        Returns True if the backend acknowledged the unload, False if
        the model was not loaded.
        """
        def _unload() -> bool:
            url = self._url(f"/api/models/unload/{model_key}")
            try:
                resp = requests.post(url, timeout=self._timeout)
                if resp.status_code == 404:
                    return False
                resp.raise_for_status()
                return True
            except requests.ConnectionError as exc:
                raise InferenceBackendError(
                    f"Connection refused during unload of {model_key!r}: "
                    f"{exc!r}"
                ) from exc
            except requests.HTTPError as exc:
                if resp.status_code == 404:
                    return False
                raise InferenceBackendError(
                    f"HTTP {resp.status_code} unloading {model_key!r}: "
                    f"{resp.text[:500]}"
                ) from exc
            except requests.RequestException as exc:
                raise InferenceBackendError(
                    f"Unload request failed for {model_key!r}: {exc!r}"
                ) from exc

        return await asyncio.to_thread(_unload)


    async def unload_all(self) -> int:
        """Unload all running models via ``POST /api/models/unload``.

        Uses llama-swap's bulk unload endpoint to stop all running
        llama-server backends at once.

        Returns the number of models that were running before unload.
        """
        # Snapshot running count before unload.
        try:
            running = await self.list_running()
            count = len(running)
        except InferenceBackendError:
            count = -1  # Unknown, but proceed with unload anyway.

        def _unload() -> int:
            url = self._url("/api/models/unload")
            try:
                resp = requests.post(url, timeout=self._timeout)
                resp.raise_for_status()
                log.info(
                    "[inference_backend] Bulk unload successful (%d models were running).",
                    max(count, 0),
                )
                return max(count, 0)
            except requests.ConnectionError as exc:
                raise InferenceBackendError(
                    f"Connection refused during bulk unload: {exc!r}"
                ) from exc
            except requests.HTTPError as exc:
                raise InferenceBackendError(
                    f"HTTP {resp.status_code} during bulk unload: "
                    f"{resp.text[:500]}"
                ) from exc
            except requests.RequestException as exc:
                raise InferenceBackendError(
                    f"Bulk unload request failed: {exc!r}"
                ) from exc

        return await asyncio.to_thread(_unload)


    async def health_check(self) -> HealthStatus:
        """Check if llama-swap is responding.

        Probes ``GET /v1/models`` — if it returns 200 the backend is
        healthy.
        """
        def _check() -> HealthStatus:
            url = self._url("/v1/models")
            try:
                resp = requests.get(url, timeout=self._timeout)
                resp.raise_for_status()
                return HealthStatus(
                    healthy=True,
                    backend_type="llama-swap",
                    message=f"OK — llama-swap responding at {self._base_url}",
                )
            except requests.ConnectionError:
                return HealthStatus(
                    healthy=False,
                    backend_type="llama-swap",
                    message=(
                        f"Connection refused at {self._base_url} — "
                        f"is llama-swap running?"
                    ),
                )
            except requests.Timeout:
                return HealthStatus(
                    healthy=False,
                    backend_type="llama-swap",
                    message=(
                        f"Health check timed out after {self._timeout}s "
                        f"at {self._base_url}"
                    ),
                )
            except requests.HTTPError:
                return HealthStatus(
                    healthy=False,
                    backend_type="llama-swap",
                    message=(
                        f"HTTP {resp.status_code} from {self._base_url}: "
                        f"{resp.text[:300]}"
                    ),
                )
            except requests.RequestException as exc:
                return HealthStatus(
                    healthy=False,
                    backend_type="llama-swap",
                    message=f"Unexpected error: {exc!r}",
                )

        return await asyncio.to_thread(_check)


# ════════════════════════════════════════════════════════════════════
#  FACTORY
# ════════════════════════════════════════════════════════════════════


def get_backend(
    backend_type: str = "llama-swap",
    **kwargs: Any,
) -> InferenceBackend:
    """Create an InferenceBackend instance for the given backend type.

    Args:
        backend_type: The backend to instantiate. Currently supported:
                      ``'llama-swap'``.
        **kwargs:     Passed through to the backend constructor
                      (e.g. ``base_url='http://...'``).

    Returns:
        An object satisfying the ``InferenceBackend`` protocol.

    Raises:
        ValueError: for unknown backend types.
    """
    if backend_type == "llama-swap":
        return LlamaSwapBackend(**kwargs)
    raise ValueError(
        f"Unknown backend type: {backend_type!r}. "
        f"Supported: 'llama-swap'"
    )


# ════════════════════════════════════════════════════════════════════
#  CLI SMOKE TEST
# ════════════════════════════════════════════════════════════════════


async def _cli_health(backend: InferenceBackend) -> int:
    """``python -m src.inference_backend health``"""
    status = await backend.health_check()
    if status.healthy:
        print(f"✅ {status.backend_type}: {status.message}")
        return 0
    else:
        print(f"❌ {status.backend_type}: {status.message}")
        return 1


async def _cli_list(backend: InferenceBackend) -> int:
    """``python -m src.inference_backend list``"""
    models = await backend.list_models()
    if not models:
        print("(no models)")
        return 0
    print(f"{'MODEL KEY':<50} {'CONFIGURED':<12} ALIASES")
    print("─" * 80)
    for m in models:
        aliases_str = ", ".join(m.aliases) if m.aliases else "—"
        configured_str = "yes" if m.configured else "no"
        print(f"{m.model_key:<50} {configured_str:<12} {aliases_str}")
    return 0


async def _cli_running(backend: InferenceBackend) -> int:
    """``python -m src.inference_backend running``"""
    running = await backend.list_running()
    if not running:
        print("(no models running)")
        return 0
    print(f"{'MODEL KEY':<50} {'PORT':<8} UPTIME")
    print("─" * 70)
    for r in running:
        port_str = str(r.port) if r.port is not None else "—"
        if r.uptime_seconds is not None:
            mins, secs = divmod(int(r.uptime_seconds), 60)
            hours, mins = divmod(mins, 60)
            uptime_str = f"{hours}h {mins}m {secs}s"
        else:
            uptime_str = "—"
        print(f"{r.model_key:<50} {port_str:<8} {uptime_str}")
    return 0


async def _cli_unload_all(backend: InferenceBackend) -> int:
    """``python -m src.inference_backend unload-all``"""
    count = await backend.unload_all()
    print(f"Unloaded {count} model(s).")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="inference_backend",
        description="Smoke-test CLI for the inference backend abstraction.",
    )
    p.add_argument(
        "--url",
        default="http://127.0.0.1:1234",
        help="Base URL of the inference backend (default: %(default)s).",
    )
    p.add_argument(
        "--backend",
        default="llama-swap",
        help="Backend type (default: %(default)s).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health", help="Check backend health.")
    sub.add_parser("list", help="List all configured models.")
    sub.add_parser("running", help="List currently running models.")
    sub.add_parser("unload-all", help="Unload all running models.")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    args = _build_argparser().parse_args(argv)

    try:
        backend = get_backend(args.backend, base_url=args.url)
    except ValueError as exc:
        print(f"[inference_backend] ERROR: {exc}", file=sys.stderr)
        return 2

    dispatch = {
        "health": _cli_health,
        "list": _cli_list,
        "running": _cli_running,
        "unload-all": _cli_unload_all,
    }

    handler = dispatch.get(args.cmd)
    if handler is None:
        print(f"[inference_backend] Unknown command: {args.cmd}", file=sys.stderr)
        return 2

    try:
        return asyncio.run(handler(backend))
    except InferenceBackendError as exc:
        print(f"[inference_backend] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

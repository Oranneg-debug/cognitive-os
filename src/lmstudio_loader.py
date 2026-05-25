"""
LMStudioLoader — programmatic lifecycle control over LM Studio runtime.

Part of DEV-20260521-001000-B5D5C0DE: replaces the silent-no-op
`POST /api/v1/models/load` in legacy `llm_client.py` with calls against
the official `lmstudio-python` SDK (verified 1.5.0, see requirements.txt).

Two-path load strategy
======================
The SDK's ``LlmLoadModelConfig`` (verified empirically on 2026-05-21)
**has no slot for max-parallel-predictions / n_parallel / n_seq_max**.
Probed paths A/B (extra dict keys) and D (private `_kv_config`) all
silently drop the value. Path C (`lms.llm()` factory) cannot force a
fresh load.

The **only working back-channel** is the `lms` CLI's ``--parallel``
flag, verified to produce ``n_parallel=1`` in the LM Studio runtime
debug log. So:

  - When ``n_parallel`` is set in the load config, the loader
    delegates to ``lms load`` subprocess (slow path, ~15-20s).
  - When ``n_parallel`` is not set, the loader uses the SDK directly
    (fast path, ~2-5s) — gets every other knob (context, FA, KV quant,
    GPU offload) typed and validated.

Both paths return the same ``LoadResult`` shape; callers don't care.

Design contract (per Boardroom Chairman verdict 2026-05-20):

  * SYNCHRONOUS CORE.  This module is purely synchronous. Async callers
    (FastAPI handlers) MUST wrap each call in ``asyncio.to_thread`` or
    ``loop.run_in_executor`` — see Task 7 + 8 of the action plan. The
    Chairman's CRITICAL veto: do NOT call these methods directly from
    an async handler.

  * IDEMPOTENT.  ``ensure_loaded(model_key, config)`` is the main entry
    point. It checks whether a matching instance is already loaded
    (same key, same effective config) and skips the reload if so.

  * SNAPSHOT BEFORE OVERRIDE.  The first call into the loader triggers
    one ``lmstudio_snapshot.snapshot()`` to back up the user's LM Studio
    GUI preferences. Subsequent calls within the reuse window are
    no-ops at snapshot time. Strategist's veto-override authority is
    satisfied: GUI prefs are always captured before this code overrides
    them.

  * NEVER SILENT.  Every public method returns a typed result dataclass.
    Failures raise ``LoaderError`` with a precise reason — no booleans,
    no None-returns-meaning-error. The previous regime's worst sin was
    silent-drop, and the Data Flow Tracer agent's bug catalog is full
    of evidence; we don't repeat it.

Public surface:

  LMStudioLoader.ensure_loaded(model_key, config)         -> LoadResult
  LMStudioLoader.unload(identifier)                       -> bool
  LMStudioLoader.list_loaded()                            -> list[LoadedInstance]
  LMStudioLoader.list_downloaded()                        -> list[DownloadedModel]
  LMStudioLoader.get_effective_config(identifier)         -> dict
  LMStudioLoader.normalize_config(raw_dict)               -> LlmLoadModelConfigDict

Run as a smoke test from the repo root:

  python -m src.lmstudio_loader list                   # show downloaded + loaded
  python -m src.lmstudio_loader ensure <model_key>     # idempotent load with defaults
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    import lmstudio as lms
    from lmstudio import (
        LlmLoadModelConfig,
        LMStudioModelNotFoundError,
        LMStudioServerError,
        LMStudioTimeoutError,
    )
except ImportError as exc:  # pragma: no cover — fast import error
    raise ImportError(
        "lmstudio>=1.5.0 is required for LMStudioLoader. "
        "Install with: pip install lmstudio==1.5.0"
    ) from exc

# Snapshot is part of this same package — relative import only works when
# imported as cognitive-os.src.lmstudio_loader; defer to a plain import.
try:
    from src.lmstudio_snapshot import snapshot as _snapshot_lmstudio_prefs
    from src.lmstudio_snapshot import SnapshotResult
except ImportError:  # pragma: no cover — fallback if cwd differs
    from lmstudio_snapshot import snapshot as _snapshot_lmstudio_prefs  # type: ignore[no-redef]
    from lmstudio_snapshot import SnapshotResult  # type: ignore[no-redef]


log = logging.getLogger("lmstudio_loader")


# ---------------------------------------------------------------------------
# Result + exception types
# ---------------------------------------------------------------------------

class LoaderError(RuntimeError):
    """Raised by LMStudioLoader for any failure during load/unload/query.

    Always carries enough context for the Data Flow Tracer to pinpoint
    the hop where things went wrong.
    """


@dataclass(frozen=True)
class LoadResult:
    """Outcome of a single ``ensure_loaded`` call."""

    model_key: str
    identifier: str
    action: str  # "loaded" | "reused" | "reloaded"
    config_applied: dict[str, Any]
    duration_seconds: float
    snapshot: SnapshotResult | None = None

    def __str__(self) -> str:  # pragma: no cover — display
        return (
            f"[loader] {self.action}: {self.model_key} "
            f"(identifier={self.identifier}, {self.duration_seconds:.2f}s)"
        )


@dataclass(frozen=True)
class LoadedInstance:
    """One running model instance, as reported by ``list_loaded``."""

    identifier: str
    model_key: str
    raw: Any = field(repr=False)  # the underlying SyncModelHandle


@dataclass(frozen=True)
class DownloadedModel:
    """One model present in LM Studio's downloaded catalog."""

    model_key: str
    path: str
    raw: Any = field(repr=False)  # the underlying DownloadedLlm


# ---------------------------------------------------------------------------
# Config normalisation
# ---------------------------------------------------------------------------

# The dotted-key form used inside LM Studio's on-disk per-model JSON
# (e.g. `llm.load.llama.acceleration.offloadRatio`) maps cleanly to the
# snake_case SDK struct fields below. We accept BOTH forms in callers
# (master_config.md historically uses snake_case) and dispatch to the
# SDK shape.

# Source-of-truth mapping. LEFT = canonical SDK snake_case kwarg.
# RIGHT-side aliases are accepted but normalised away.
_LOAD_CONFIG_ALIASES: dict[str, str] = {
    # Legacy names from the broken llm_client.py POST payload (so old
    # master_config.md entries keep working during the migration).
    "contextLength": "context_length",
    "context_window": "context_length",          # historical alias
    "flashAttention": "flash_attention",
    "cacheTypeK": "llama_k_cache_quantization_type",
    "cache_type_k": "llama_k_cache_quantization_type",
    "cacheTypeV": "llama_v_cache_quantization_type",
    "cache_type_v": "llama_v_cache_quantization_type",
    # GPU offload — see _build_gpu_setting below for the nested form.
    # We accept both a top-level float (legacy) and a {ratio: …} dict.
}

# Known SDK fields (introspected from lmstudio 1.5.0). Anything not in
# this set (and not in aliases) is rejected by normalize_config.
_SDK_LOAD_FIELDS: frozenset[str] = frozenset({
    "gpu",
    "gpu_strict_vram_cap",
    "offload_kv_cache_to_gpu",
    "context_length",
    "rope_frequency_base",
    "rope_frequency_scale",
    "eval_batch_size",
    "flash_attention",
    "keep_model_in_memory",
    "seed",
    "use_fp16_for_kv_cache",
    "try_mmap",
    "num_experts",
    "llama_k_cache_quantization_type",
    "llama_v_cache_quantization_type",
})


def _build_gpu_setting(value: Any) -> dict[str, Any] | None:
    """Accept a few shapes for GPU offload and produce the SDK ``gpu`` dict.

    Accepted shapes:
        - None  -> None (no override)
        - "max" -> {"ratio": "max"}
        - 0.85  -> {"ratio": 0.85}
        - {"ratio": …, "split": [...], "main_gpu": …}  -> passed through
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return {"ratio": value}
    if isinstance(value, Mapping):
        # Pass-through; the SDK will validate.
        return dict(value)
    raise LoaderError(f"Unsupported `gpu` config shape: {value!r}")


def normalize_config(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Translate the heterogeneous master_config.md / legacy / SDK forms
    into a single canonical dict shaped for ``LlmLoadModelConfig``.

    Anything we can't map raises ``LoaderError`` — silently dropping a
    user-supplied knob is exactly the bug we're paying off.
    """
    if not raw:
        return {}
    normalised: dict[str, Any] = {}
    leftover: dict[str, Any] = {}
    for key, value in raw.items():
        canonical = _LOAD_CONFIG_ALIASES.get(key, key)
        if canonical == "gpu":
            normalised["gpu"] = _build_gpu_setting(value)
            continue
        # Legacy convenience: gpu_offload_ratio (float) -> gpu.ratio
        if canonical in ("gpu_offload_ratio", "gpuOffloadRatio"):
            normalised["gpu"] = _build_gpu_setting(value)
            continue
        # Quietly tolerate `n_parallel` / `maxParallelPredictions` / etc.
        # — the SDK's LlmLoadModelConfig doesn't have a slot for this, but
        # we don't want to reject it because callers (and master_config.md)
        # legitimately set it. Stash it for the loader to handle via a
        # secondary path or to surface as a warning.
        if canonical in (
            "n_parallel", "nParallel", "maxParallelPredictions",
            "numParallelSessions", "parallel",
        ):
            leftover["max_parallel_predictions"] = int(value)
            continue
        if canonical in _SDK_LOAD_FIELDS:
            normalised[canonical] = value
            continue
        # Unknown — raise loudly so callers see typos/old keys.
        raise LoaderError(
            f"Unknown load-config key {key!r} (canonical: {canonical!r}). "
            f"Known SDK fields: {sorted(_SDK_LOAD_FIELDS)}; "
            f"known aliases: {sorted(_LOAD_CONFIG_ALIASES)}"
        )

    if leftover:
        # Attach as a private side-band; the loader pops it before
        # constructing the SDK config object.
        normalised["__loader_extras__"] = leftover
    return normalised


# ---------------------------------------------------------------------------
# Effective-config drift detection
# ---------------------------------------------------------------------------

# Field aliases LM Studio's SDK reports back vs the snake-case canonical
# names we normalise to. Probed empirically against lmstudio-python 1.5.0
# — the SDK info struct uses camelCase keys and sometimes nests them.
_LIVE_CONFIG_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "context_length": ("contextLength", "context_length", "n_ctx"),
    "flash_attention": ("flashAttention", "flash_attention"),
    "llama_k_cache_quantization_type": (
        "llamaKCacheQuantizationType",
        "kCacheQuant",
        "cache_type_k",
    ),
    "llama_v_cache_quantization_type": (
        "llamaVCacheQuantizationType",
        "vCacheQuant",
        "cache_type_v",
    ),
}


def _extract_live_value(live: Mapping[str, Any], canonical_key: str) -> Any:
    """Return the first non-None value in ``live`` for any alias of
    ``canonical_key``. Walks nested dicts one level deep.
    """
    aliases = _LIVE_CONFIG_FIELD_ALIASES.get(canonical_key, (canonical_key,))
    # flat probe
    for alias in aliases:
        if alias in live and live[alias] is not None:
            return live[alias]
    # one-level-nested probe (e.g. live["loadConfig"]["contextLength"])
    for key, val in live.items():
        if isinstance(val, Mapping):
            for alias in aliases:
                if alias in val and val[alias] is not None:
                    return val[alias]
    return None


def _diff_effective_vs_requested(
    live: Mapping[str, Any],
    requested: Mapping[str, Any],
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare LM Studio's reported live config against what was requested.

    Returns a dict of ``{field: {"live": ..., "requested": ...}}`` for every
    field that differs. Empty dict means "matches, safe to reuse".

    Only checks the fields that actually affect VRAM / generation behaviour
    (context_length, flash_attention, KV-cache quant, GPU offload, parallel).
    Differences on cosmetic / unknown fields are ignored.
    """
    diff: dict[str, Any] = {}
    extras = extras or {}

    # 1. Direct canonical fields.
    for key, want in requested.items():
        if key == "__loader_extras__":
            continue
        live_val = _extract_live_value(live, key)
        if live_val is None:
            # The SDK didn't report this field. Be conservative: only flag
            # drift for the high-impact knobs (context_length / FA).
            if key in {"context_length", "flash_attention"}:
                diff[key] = {"live": "<unreported>", "requested": want}
            continue
        # Normalise types for comparison (the SDK sometimes wraps numbers).
        if isinstance(want, bool):
            if bool(live_val) != want:
                diff[key] = {"live": live_val, "requested": want}
        elif isinstance(want, (int, float)):
            try:
                if int(live_val) != int(want):
                    diff[key] = {"live": live_val, "requested": want}
            except (TypeError, ValueError):
                diff[key] = {"live": live_val, "requested": want}
        elif isinstance(want, Mapping):
            # e.g. {"ratio": "max"} for gpu — compare the ratio field.
            live_ratio = live_val.get("ratio") if isinstance(live_val, Mapping) else None
            want_ratio = want.get("ratio")
            if str(live_ratio) != str(want_ratio):
                diff[key] = {"live": live_val, "requested": want}
        else:
            if str(live_val) != str(want):
                diff[key] = {"live": live_val, "requested": want}

    # 2. The CLI-only `n_parallel` lives in extras. If it's set, the live
    # instance MUST have been loaded via the CLI path — there's no way to
    # know from the SDK info struct, so a parallelism request always forces
    # a reload (safe default).
    if "max_parallel_predictions" in extras or "n_parallel" in extras:
        want_parallel = extras.get("max_parallel_predictions") or extras.get("n_parallel")
        live_parallel = _extract_live_value(live, "max_parallel_predictions")
        if live_parallel is None or int(live_parallel) != int(want_parallel):
            diff["max_parallel_predictions"] = {
                "live": live_parallel if live_parallel is not None else "<unreported>",
                "requested": want_parallel,
            }

    return diff


# ---------------------------------------------------------------------------
# The loader
# ---------------------------------------------------------------------------

class LMStudioLoader:
    """Sync-only orchestrator of LM Studio model lifecycle calls.

    A single instance can be shared across the process; the SDK module
    keeps its own connection pool internally.
    """

    def __init__(
        self,
        *,
        snapshot_before_overrides: bool = True,
        snapshot_reuse_window_seconds: int = 3600,
        load_timeout_seconds: float = 180.0,
    ) -> None:
        self._snapshot_enabled = snapshot_before_overrides
        self._snapshot_reuse_window = snapshot_reuse_window_seconds
        self._load_timeout = load_timeout_seconds
        self._snapshot_done_for_session: SnapshotResult | None = None

        # Catalog cache: model_key -> DownloadedLlm. Cleared per-session;
        # callers can manually call `refresh_catalog()` after a model is
        # downloaded outside our control.
        self._downloaded_cache: dict[str, Any] | None = None

    # ---- snapshot ------------------------------------------------------

    def _ensure_snapshot(self) -> SnapshotResult | None:
        """First touch in a session: take a snapshot of GUI prefs.

        Returns the SnapshotResult so callers can attach it to LoadResult.
        Subsequent calls in the same session are no-ops (the snapshot
        utility itself is also idempotent within its reuse window).
        """
        if not self._snapshot_enabled:
            return None
        if self._snapshot_done_for_session is not None:
            return self._snapshot_done_for_session
        try:
            result = _snapshot_lmstudio_prefs(
                reuse_window_seconds=self._snapshot_reuse_window,
            )
        except FileNotFoundError as exc:
            # LM Studio not installed in the expected location — log and
            # carry on; the loader can still talk to a remote LM Studio.
            log.warning("[loader] snapshot skipped: %s", exc)
            return None
        log.info("[loader] %s", result)
        self._snapshot_done_for_session = result
        return result

    # ---- catalog -------------------------------------------------------

    def refresh_catalog(self) -> dict[str, Any]:
        """Reload the downloaded-model catalog from LM Studio."""
        try:
            downloaded = lms.list_downloaded_models()
        except Exception as exc:
            raise LoaderError(f"list_downloaded_models() failed: {exc!r}") from exc
        self._downloaded_cache = {m.model_key: m for m in downloaded}
        return self._downloaded_cache

    def list_downloaded(self) -> list[DownloadedModel]:
        if self._downloaded_cache is None:
            self.refresh_catalog()
        assert self._downloaded_cache is not None
        return [
            DownloadedModel(model_key=k, path=getattr(m, "path", ""), raw=m)
            for k, m in self._downloaded_cache.items()
        ]

    def list_loaded(self) -> list[LoadedInstance]:
        """Return every currently-loaded LLM instance."""
        try:
            handles = lms.list_loaded_models()
        except Exception as exc:
            raise LoaderError(f"list_loaded_models() failed: {exc!r}") from exc
        out: list[LoadedInstance] = []
        for h in handles:
            ident = getattr(h, "identifier", "") or getattr(h, "model_identifier", "")
            mkey = getattr(h, "model_key", "") or getattr(h, "info", None)
            if hasattr(mkey, "model_key"):
                mkey = mkey.model_key
            out.append(LoadedInstance(identifier=str(ident), model_key=str(mkey or ""), raw=h))
        return out

    def get_effective_config(self, identifier: str) -> dict[str, Any]:
        """Return whatever load-config LM Studio reports for the loaded
        instance with the given identifier. Best-effort — the SDK
        exposes this via the handle's info struct, which varies between
        versions.
        """
        for inst in self.list_loaded():
            if inst.identifier != identifier:
                continue
            raw = inst.raw
            info = getattr(raw, "info", None)
            if info is None:
                return {}
            # info is a msgspec.Struct — convert to dict where possible.
            try:
                import msgspec
                return msgspec.to_builtins(info)
            except Exception:
                return {k: getattr(info, k) for k in dir(info)
                        if not k.startswith("_") and not callable(getattr(info, k, None))}
        raise LoaderError(f"No loaded instance with identifier={identifier!r}")

    # ---- ensure_loaded -------------------------------------------------

    def ensure_loaded(
        self,
        model_key: str,
        config: Mapping[str, Any] | None = None,
        *,
        ttl: int | None = None,
        instance_identifier: str | None = None,
        on_progress: Callable[[float], Any] | None = None,
        force_reload: bool = False,
    ) -> LoadResult:
        """Load ``model_key`` if not already loaded with matching config.

        Args:
            model_key:    The catalog key (e.g. ``"hermes-4.3-36b"``).
            config:       Load configuration in any accepted shape (see
                          :func:`normalize_config`). ``None`` uses SDK defaults.
            ttl:          Auto-unload TTL in seconds. ``None`` disables
                          auto-unload (recommended for orchestrator use).
            instance_identifier: Explicit identifier for the loaded
                          instance. Defaults to ``model_key`` so subsequent
                          ``list_loaded()`` calls find it deterministically.
            on_progress:  Optional callback ``(fraction: float) -> None``.
            force_reload: If True, unload any existing instance first.

        Returns:
            LoadResult describing what happened.

        Raises:
            LoaderError for any failure. Never returns silently on error.
        """
        snap = self._ensure_snapshot()
        identifier = instance_identifier or model_key
        norm = normalize_config(config)
        extras = norm.pop("__loader_extras__", {})

        # Idempotency: check if an instance with this identifier is already
        # loaded WITH MATCHING CONFIG. If the live config differs from the
        # requested config on any key field, unload + reload — never silently
        # reuse a stale instance. (Fix landed during bootstrap of the
        # governance proposal stack 2026-05-23; see
        # dev/decisions/_bootstrap_approvals_2026-05-22.md "DIAGNOSTIC
        # INCIDENT #2" for the symptom and rationale.)
        existing = next(
            (i for i in self.list_loaded() if i.identifier == identifier),
            None,
        )
        config_diff: dict[str, Any] = {}
        if existing and not force_reload:
            try:
                live = self.get_effective_config(identifier)
                config_diff = _diff_effective_vs_requested(live, norm, extras)
            except Exception as exc:  # never silently swallow; log + force reload
                print(
                    f"[LOADER] effective-config probe failed for "
                    f"identifier={identifier!r}: {exc!r} — forcing reload",
                    file=sys.stderr,
                )
                config_diff = {"__probe_failed__": repr(exc)}

            if not config_diff:
                return LoadResult(
                    model_key=model_key,
                    identifier=identifier,
                    action="reused",
                    config_applied=norm,
                    duration_seconds=0.0,
                    snapshot=snap,
                )
            # Config drift detected — log loudly so the dashboard / logs
            # show which field forced the reload. No silent drops.
            print(
                f"[LOADER] config drift on identifier={identifier!r} "
                f"-> reloading. diff={config_diff}",
                file=sys.stderr,
            )
            self.unload(identifier)
        elif existing and force_reload:
            self.unload(identifier)

        # Look up the downloaded handle.
        if self._downloaded_cache is None:
            self.refresh_catalog()
        assert self._downloaded_cache is not None
        downloaded = self._downloaded_cache.get(model_key)
        if downloaded is None:
            raise LoaderError(
                f"Model {model_key!r} not in downloaded catalog. "
                f"Available: {sorted(self._downloaded_cache)[:10]}…"
            )

        # ----- Dispatch: CLI back-channel if parallelism set, SDK otherwise.
        parallel = extras.get("max_parallel_predictions")
        if parallel is not None:
            return self._load_via_cli(
                model_key=model_key,
                identifier=identifier,
                norm=norm,
                parallel=int(parallel),
                ttl=ttl,
                snap=snap,
            )
        return self._load_via_sdk(
            model_key=model_key,
            identifier=identifier,
            downloaded=downloaded,
            norm=norm,
            ttl=ttl,
            on_progress=on_progress,
            snap=snap,
        )

    # ---- load paths ----------------------------------------------------

    def _load_via_sdk(
        self,
        *,
        model_key: str,
        identifier: str,
        downloaded: Any,
        norm: dict[str, Any],
        ttl: int | None,
        on_progress: Callable[[float], Any] | None,
        snap: SnapshotResult | None,
    ) -> LoadResult:
        """Fast path: typed SDK call, every knob except parallelism."""
        sdk_config: LlmLoadModelConfig | None
        if norm:
            try:
                sdk_config = LlmLoadModelConfig(**norm)
            except TypeError as exc:
                raise LoaderError(
                    f"normalize_config returned shape rejected by "
                    f"LlmLoadModelConfig: {exc!r}; payload was {norm!r}"
                ) from exc
        else:
            sdk_config = None

        t0 = time.monotonic()
        try:
            handle = downloaded.load_new_instance(
                ttl=ttl,
                instance_identifier=identifier,
                config=sdk_config,
                on_load_progress=on_progress,
            )
        except (LMStudioModelNotFoundError, LMStudioServerError,
                LMStudioTimeoutError) as exc:
            raise LoaderError(
                f"load_new_instance({model_key!r}) failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except Exception as exc:
            raise LoaderError(
                f"load_new_instance({model_key!r}) raised unexpected "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        elapsed = time.monotonic() - t0

        actual_identifier = (
            getattr(handle, "identifier", None)
            or getattr(handle, "model_identifier", None)
            or identifier
        )
        return LoadResult(
            model_key=model_key,
            identifier=str(actual_identifier),
            action="loaded",
            config_applied=norm,
            duration_seconds=elapsed,
            snapshot=snap,
        )

    def _load_via_cli(
        self,
        *,
        model_key: str,
        identifier: str,
        norm: dict[str, Any],
        parallel: int,
        ttl: int | None,
        snap: SnapshotResult | None,
    ) -> LoadResult:
        """Slow path: shell out to ``lms load`` for parallelism control.

        The CLI is the only verified back-channel (probed 2026-05-21)
        for setting ``n_parallel`` on the underlying llama.cpp runtime.
        Verified to produce ``n_parallel=1`` and ``n_seq_max=1`` in the
        LM Studio debug log, with pipeline parallelism preserved.

        Side-effects:
            - Spawns a child process: ``lms load <args> <model_key>``.
            - Times out after ``self._load_timeout`` seconds.
            - Does NOT support on_progress (CLI doesn't stream progress
              to our stdout — that's a future enhancement).
        """
        lms_bin = shutil.which("lms")
        if not lms_bin:
            raise LoaderError(
                "max_parallel_predictions was requested but the `lms` CLI "
                "is not on PATH. Install LM Studio's CLI bridge or unset "
                "n_parallel in master_config.md to fall back to the SDK."
            )

        args: list[str] = [
            lms_bin, "load",
            "--identifier", identifier,
            "--parallel", str(parallel),
            "--yes",  # don't prompt for unloads
        ]
        # GPU offload — translate the SDK `gpu` block back to a CLI flag.
        gpu_block = norm.get("gpu")
        if isinstance(gpu_block, dict):
            ratio = gpu_block.get("ratio")
            if ratio is not None:
                args.extend(["--gpu", str(ratio)])
        # Context length — first-class CLI flag.
        ctx = norm.get("context_length")
        if ctx is not None:
            args.extend(["--context-length", str(int(ctx))])
        # TTL — pass through if explicit.
        if ttl is not None:
            args.extend(["--ttl", str(int(ttl))])
        # Final positional arg: model key.
        args.append(model_key)

        # NB: any normalised field not representable as a CLI flag
        # (flash_attention, KV quant, eval_batch_size, ...) is silently
        # *not applied by the CLI* — but the model's persisted per-model
        # GUI config still governs those, and the snapshot we took before
        # this call ensures user-tuned defaults are recoverable. We
        # surface a warning so callers know which knobs the CLI dropped.
        unmapped = [
            k for k in norm.keys()
            if k not in ("gpu", "context_length")
        ]
        if unmapped:
            log.warning(
                "[loader] CLI path can't set these knobs (using GUI prefs "
                "for them instead): %s. Set n_parallel=None to use the "
                "typed SDK path which supports them all.",
                unmapped,
            )

        log.info("[loader] CLI load: %s", " ".join(args[1:]))
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                # Force UTF-8 with replacement so cp1252-default Windows
                # consoles don't blow up on lms-CLI's progress glyphs.
                encoding="utf-8",
                errors="replace",
                timeout=self._load_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LoaderError(
                f"lms load {model_key!r} timed out after "
                f"{self._load_timeout}s"
            ) from exc
        except OSError as exc:
            raise LoaderError(
                f"lms load {model_key!r} failed to start: {exc!r}"
            ) from exc
        elapsed = time.monotonic() - t0

        if result.returncode != 0:
            raise LoaderError(
                f"lms load {model_key!r} exited {result.returncode}. "
                f"stderr: {result.stderr.strip()[:500]} | "
                f"stdout: {result.stdout.strip()[:500]}"
            )

        # Verify it actually landed.
        loaded = next(
            (i for i in self.list_loaded() if i.identifier == identifier),
            None,
        )
        if loaded is None:
            raise LoaderError(
                f"lms load {model_key!r} returned 0 but no instance with "
                f"identifier={identifier!r} appears in list_loaded(). "
                f"stdout: {result.stdout.strip()[:300]}"
            )

        applied = dict(norm)
        applied["max_parallel_predictions"] = parallel  # echo it back
        return LoadResult(
            model_key=model_key,
            identifier=identifier,
            action="loaded",
            config_applied=applied,
            duration_seconds=elapsed,
            snapshot=snap,
        )

    # ---- unload --------------------------------------------------------

    def unload(self, identifier: str) -> bool:
        """Unload the instance with the given identifier. Returns True on
        success, raises LoaderError otherwise (never silent)."""
        target = next(
            (i for i in self.list_loaded() if i.identifier == identifier),
            None,
        )
        if target is None:
            return False  # already absent — not an error
        try:
            target.raw.unload()
        except Exception as exc:
            raise LoaderError(
                f"unload({identifier!r}) failed: {type(exc).__name__}: {exc}"
            ) from exc
        return True


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def _cli_list(loader: LMStudioLoader) -> int:
    print("== downloaded ==")
    for m in loader.list_downloaded():
        print(f"  {m.model_key}")
    print()
    print("== loaded ==")
    for inst in loader.list_loaded():
        print(f"  {inst.identifier:<40} <- {inst.model_key}")
    return 0


def _cli_ensure(loader: LMStudioLoader, model_key: str) -> int:
    def progress(fraction: float) -> None:
        bar = "=" * int(fraction * 20)
        pad = " " * (20 - len(bar))
        print(f"\r  [{bar}{pad}] {fraction * 100:5.1f}%", end="", flush=True)

    result = loader.ensure_loaded(model_key, on_progress=progress)
    print()  # close the progress line
    print(result)
    if result.snapshot:
        print(f"  snapshot: {result.snapshot}")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lmstudio_loader")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Show downloaded + loaded models.")
    en = sub.add_parser("ensure", help="Idempotently load a model.")
    en.add_argument("model_key")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_argparser().parse_args(argv)
    loader = LMStudioLoader()
    try:
        if args.cmd == "list":
            return _cli_list(loader)
        if args.cmd == "ensure":
            return _cli_ensure(loader, args.model_key)
    except LoaderError as exc:
        print(f"[loader] ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

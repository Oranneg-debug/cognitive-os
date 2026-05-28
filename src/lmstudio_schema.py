"""
Pydantic input schemas for the LM Studio load API.

These are the **public** validation models — what the dashboard's
"Load Settings" panel POSTs, what FastAPI validates before it ever
reaches the LMStudioLoader.

We keep validation here (not inside the loader) because:

  * The loader's ``normalize_config`` does the canonical mapping from
    legacy aliases to SDK kwargs. It cares about *correctness*.
  * These Pydantic models care about *user-supplied input*: type
    coercion, range bounds, enums, descriptive error messages. The
    Boardroom Critic + Overseer both insisted on this layer.

Together they satisfy the chairman's veto:

  > Data Integrity: Allowing unvalidated or partial load configs to
  > reach LM Studio runtime (silent drift).
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Canonical KV quant types accepted by llama.cpp — matches the SDK's
# LlmLoadModelConfig.llama_k_cache_quantization_type literal exactly.
KvQuant = Literal[
    "f32", "f16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1",
]

# GPU offload accepts either a string sentinel or a numeric ratio.
GpuRatio = Union[Literal["max", "off"], Annotated[float, Field(ge=0.0, le=1.0)]]


class GpuSettingIn(BaseModel):
    """Optional nested GPU control. Maps to SDK's ``gpu`` field."""

    model_config = ConfigDict(extra="forbid")

    ratio: Optional[GpuRatio] = Field(
        default=None,
        description="GPU offload ratio. 'max' = use as much VRAM as fits; "
                    "0.0–1.0 = explicit fraction; 'off' = CPU-only.",
    )
    main_gpu: Optional[int] = Field(
        default=None, ge=0,
        description="Index of the GPU to prefer for single-GPU workloads.",
    )
    split_strategy: Optional[Literal["evenly", "favorMainGpu"]] = Field(
        default=None,
        description="Strategy for splitting the model across multiple GPUs.",
    )
    disabled_gpus: Optional[list[int]] = Field(
        default=None,
        description="List of GPU indices to ignore.",
    )


class LoadConfigIn(BaseModel):
    """User-facing load configuration. Accepts both the canonical
    snake_case form and the historical camelCase / aliases that
    master_config.md has used. ``LMStudioLoader.normalize_config``
    does the final mapping before the SDK call.
    """

    model_config = ConfigDict(
        extra="forbid",          # No silently-dropped unknown fields.
        populate_by_name=True,   # Allow camelCase alias use via Field(alias=...).
    )

    # ---- typed knobs (SDK-controlled) ----------------------------------
    context_length: Optional[int] = Field(
        default=None, ge=512, le=1_048_576,
        alias="context_window",  # historical name
        description="Context window in tokens. 512–1,048,576.",
    )
    flash_attention: Optional[bool] = Field(
        default=None,
        alias="flashAttention",
        description="Enable llama.cpp flash attention. Recommended on for KV quant.",
    )
    llama_k_cache_quantization_type: Optional[KvQuant] = Field(
        default=None,
        alias="cache_type_k",
        description="K-cache quantization type. f16 = full precision.",
    )
    llama_v_cache_quantization_type: Optional[KvQuant] = Field(
        default=None,
        alias="cache_type_v",
        description="V-cache quantization type. Requires flash_attention for non-f16.",
    )
    eval_batch_size: Optional[int] = Field(
        default=None, ge=1, le=8192,
        description="Prompt-processing batch size.",
    )
    keep_model_in_memory: Optional[bool] = Field(default=None)
    use_fp16_for_kv_cache: Optional[bool] = Field(default=None)
    try_mmap: Optional[bool] = Field(default=None)
    seed: Optional[int] = Field(default=None)
    rope_frequency_base: Optional[float] = Field(default=None)
    rope_frequency_scale: Optional[float] = Field(default=None, gt=0)
    gpu_strict_vram_cap: Optional[bool] = Field(default=None)
    offload_kv_cache_to_gpu: Optional[bool] = Field(default=None)
    num_experts: Optional[int] = Field(default=None, ge=1)

    # ---- GPU control ---------------------------------------------------
    gpu: Optional[GpuSettingIn] = Field(default=None)
    gpu_offload_ratio: Optional[GpuRatio] = Field(
        default=None,
        alias="gpuOffloadRatio",
        description="Shortcut for gpu.ratio. Either this OR gpu, not both.",
    )

    # ---- CLI back-channel (not in SDK LlmLoadModelConfig) --------------
    n_parallel: Optional[int] = Field(
        default=None, ge=1, le=32,
        alias="maxParallelPredictions",
        description="Max parallel predictions. Forces the loader to use the "
                    "`lms` CLI back-channel (SDK 1.5.0 cannot set this).",
    )

    # ---- validators ----------------------------------------------------

    @field_validator("llama_v_cache_quantization_type")
    @classmethod
    def _v_requires_flash_attention(
        cls, v: KvQuant | None, info: object
    ) -> KvQuant | None:
        # NB: in pydantic v2, sibling-field access is awkward; we do a
        # *soft* check at the model level via @model_validator below.
        return v

    def model_post_init(self, __ctx: object) -> None:  # noqa: D401
        # Cross-field rules.
        if self.gpu is not None and self.gpu_offload_ratio is not None:
            raise ValueError(
                "Set either `gpu` (full nested settings) or "
                "`gpu_offload_ratio` (shortcut), not both."
            )
        v = self.llama_v_cache_quantization_type
        if v is not None and v != "f16" and self.flash_attention is False:
            raise ValueError(
                f"V-cache quantization {v!r} requires flash_attention=True "
                f"(llama.cpp limitation). Either set flash_attention=True "
                f"or use 'f16' for V."
            )

    def to_loader_dict(self) -> dict[str, object]:
        """Emit the dict shape that ``LMStudioLoader.normalize_config``
        expects (canonical SDK snake_case + the CLI extras).
        """
        out: dict[str, object] = {}
        # Pull every non-None field as-is; aliases were resolved by Pydantic.
        for name, value in self.model_dump(exclude_none=True).items():
            out[name] = value
        # If the user supplied `gpu_offload_ratio`, lift it into `gpu`
        # so the loader's normalize_config sees the canonical shape.
        if "gpu_offload_ratio" in out and "gpu" not in out:
            out["gpu"] = {"ratio": out.pop("gpu_offload_ratio")}
        elif "gpu_offload_ratio" in out:
            out.pop("gpu_offload_ratio")
        return out


class LoadRequest(BaseModel):
    """Top-level body for ``POST /api/load``."""

    model_config = ConfigDict(extra="forbid")

    model_key: str = Field(
        ...,
        description="The catalog key (e.g. 'hermes-4.3-36b'). Must match "
                    "an entry from `GET /api/loaded` or the SDK catalog.",
    )
    identifier: Optional[str] = Field(
        default=None,
        description="Instance identifier. Defaults to model_key.",
    )
    config: LoadConfigIn = Field(default_factory=LoadConfigIn)
    ttl: Optional[int] = Field(
        default=None, ge=1,
        description="Auto-unload TTL in seconds. None = no auto-unload.",
    )
    force_reload: bool = Field(
        default=False,
        description="If true, unload any existing instance with the same "
                    "identifier before loading.",
    )


class LoadResponse(BaseModel):
    """Mirrors :class:`LMStudioLoader.LoadResult` for the HTTP layer."""

    model_config = ConfigDict(extra="forbid")

    model_key: str
    identifier: str
    action: Literal["loaded", "reused", "reloaded"]
    config_applied: dict[str, object]
    duration_seconds: float
    snapshot_dir: Optional[str] = None
    snapshot_reused: Optional[bool] = None


class LoadedInstanceOut(BaseModel):
    """One row of ``GET /api/loaded``."""

    model_config = ConfigDict(extra="forbid")

    identifier: str
    model_key: str


class LoadedListResponse(BaseModel):
    """Top-level body of ``GET /api/loaded``."""

    model_config = ConfigDict(extra="forbid")

    loaded: list[LoadedInstanceOut]
    downloaded: list[str]  # just the model_keys, full info would be too big

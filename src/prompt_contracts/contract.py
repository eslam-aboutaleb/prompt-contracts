"""Immutable runtime Contract facade for rendering prompts and validating outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from prompt_contracts.errors import ErrorCode, ResourceLimitError
from prompt_contracts.rendering.renderer import render_prompt_messages
from prompt_contracts.types import (
    BUNDLE_DIGEST_ALGORITHM,
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    MessageTemplate,
    OutputSpec,
    RenderedPrompt,
    RuntimePolicy,
    thaw_json_value,
)
from prompt_contracts.validation.inputs import validate_contract_inputs
from prompt_contracts.validation.outputs import validate_contract_output
from prompt_contracts.validation.profile import CompiledSchema

__all__ = ["Contract"]


def _resolve_effective_policy(
    contract_policy: RuntimePolicy,
    override_policy: RuntimePolicy | None,
    *,
    contract_ref: str,
) -> RuntimePolicy:
    """Ensure a per-call override policy tightens or matches the contract's policy, never relaxing
    it.
    """
    if override_policy is None:
        return contract_policy
    if not isinstance(override_policy, RuntimePolicy):
        raise ResourceLimitError(
            "policy must be a RuntimePolicy instance",
            code=ErrorCode.POLICY_LIMIT_INVALID,
            contract_ref=contract_ref,
        )
    contract_limits = contract_policy.to_dict()
    override_limits = override_policy.to_dict()
    for key, c_val in contract_limits.items():
        o_val = override_limits[key]
        if o_val > c_val:
            raise ResourceLimitError(
                f"Override RuntimePolicy.{key} ({o_val}) "
                f"cannot relax contract policy limit ({c_val})",
                code=ErrorCode.POLICY_LIMIT_INVALID,
                contract_ref=contract_ref,
            )
    return override_policy


@dataclass(frozen=True, slots=True)
class Contract:
    """Verified, immutable in-memory prompt contract snapshot."""

    ref: ContractRef
    format_version: int
    description: str | None
    renderer: str
    bundle_digest: str
    policy: RuntimePolicy
    messages: tuple[MessageTemplate, ...]
    output_spec: OutputSpec
    _compiled_input_schema: CompiledSchema
    _compiled_output_schema: CompiledSchema | None
    _asset_bytes: Mapping[str, bytes]
    digest_algorithm: str = BUNDLE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "_asset_bytes", MappingProxyType(dict(self._asset_bytes)))

    @property
    def name(self) -> str:
        return self.ref.name

    @property
    def version(self) -> str:
        return self.ref.version

    @property
    def input_schema(self) -> dict[str, Any]:
        """Return a defensive deep copy of the input JSON Schema."""
        return self._compiled_input_schema.to_dict()

    @property
    def output_schema(self) -> dict[str, Any] | None:
        """Return a defensive deep copy of the output JSON Schema, or ``None`` for text mode."""
        if self._compiled_output_schema is None:
            return None
        return self._compiled_output_schema.to_dict()

    @property
    def asset_bytes(self) -> Mapping[str, bytes]:
        """Return an immutable mapping of logical asset paths to snapshot bytes."""
        return self._asset_bytes

    def validate_inputs(
        self,
        inputs: Mapping[str, Any],
        *,
        policy: RuntimePolicy | None = None,
    ) -> dict[str, Any]:
        """Validate ``inputs`` against this contract's input schema and return a fresh copy."""
        effective_policy = _resolve_effective_policy(
            self.policy, policy, contract_ref=str(self.ref)
        )
        frozen = validate_contract_inputs(
            inputs,
            self._compiled_input_schema,
            policy=effective_policy,
            contract_ref=str(self.ref),
        )
        res = thaw_json_value(frozen)
        assert isinstance(res, dict)
        return res

    def render(
        self,
        inputs: Mapping[str, Any],
        *,
        policy: RuntimePolicy | None = None,
    ) -> RenderedPrompt:
        """Validate ``inputs`` and render ordered messages in a single pass."""
        effective_policy = _resolve_effective_policy(
            self.policy, policy, contract_ref=str(self.ref)
        )
        validated_inputs = validate_contract_inputs(
            inputs,
            self._compiled_input_schema,
            policy=effective_policy,
            contract_ref=str(self.ref),
        )
        return render_prompt_messages(
            contract_ref=self.ref,
            bundle_digest=self.bundle_digest,
            renderer=self.renderer,
            templates=self.messages,
            validated_inputs=validated_inputs,
            policy=effective_policy,
        )

    def validate_output(
        self,
        raw_output: str,
        *,
        policy: RuntimePolicy | None = None,
    ) -> Any:
        """Validate a model response string against this contract's output specification."""
        effective_policy = _resolve_effective_policy(
            self.policy, policy, contract_ref=str(self.ref)
        )
        return validate_contract_output(
            raw_output,
            self.output_spec,
            self._compiled_output_schema,
            policy=effective_policy,
            contract_ref=str(self.ref),
        )

    @classmethod
    def from_directory(
        cls,
        bundle_dir: Path | str,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> Contract:
        """Load and verify a single contract bundle from a filesystem directory."""
        from prompt_contracts.loading.loader import load_contract_from_directory

        return load_contract_from_directory(Path(bundle_dir), policy=policy)

    @classmethod
    def from_package_resource(
        cls,
        package: str,
        resource_path: str = "",
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> Contract:
        """Load and verify a single contract bundle from an installed Python package resource."""
        from prompt_contracts.loading.loader import load_contract_from_package

        return load_contract_from_package(package, resource_path, policy=policy)

"""Request/response adapter for ``llm-gateway-sdk``.

Maps a verified :class:`RenderedPrompt` and :class:`Contract` into detached kwargs for
``GatewayClient.complete`` / ``AsyncGatewayClient.complete`` (or ``chat.completions.create``),
and normalizes completion status before validating the output. Owns no client, model
alias, credentials, or retry loop.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from prompt_contracts.contract import Contract
from prompt_contracts.errors import (
    ErrorCode,
    IncompleteCompletionError,
    PromptContractError,
    ProviderCapabilityError,
)
from prompt_contracts.types import (
    ContractRef,
    ExecutionMetadata,
    JSONPrimitive,
    OutputMode,
    RenderedMessage,
    RenderedPrompt,
    RuntimePolicy,
    freeze_json_value,
    thaw_json_value,
)
from prompt_contracts.validation.profile import SUPPORTED_SCHEMA_KEYWORDS, expand_schema_node

__all__ = [
    "GatewayCapabilities",
    "GatewayRequest",
    "GatewaySchemaMode",
    "build_execution_metadata",
    "ensure_gateway_sdk_available",
    "to_gateway_request",
    "validate_gateway_response",
]

_SAFE_SCHEMA_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def ensure_gateway_sdk_available() -> str:
    """Verify ``llm_gateway_sdk`` is installed and return its version string.

    Raises a helpful :class:`ImportError` instructing the user to install
    ``prompt-contracts[gateway]`` if the extra is not present.
    """
    if importlib.util.find_spec("llm_gateway_sdk") is None:
        raise ImportError(
            "Optional dependency 'llm-gateway-sdk' is not installed. "
            "Install it with: pip install 'prompt-contracts[gateway]'"
        )
    import llm_gateway_sdk

    return str(getattr(llm_gateway_sdk, "__version__", "unknown"))


class GatewaySchemaMode(StrEnum):
    """Explicit JSON schema enforcement policy for gateway requests."""

    STRICT_JSON_SCHEMA = "strict_json_schema"
    LOCAL_VALIDATION = "local_validation"


@dataclass(frozen=True, slots=True)
class GatewayCapabilities:
    """Provider capability profile governing how JSON contracts map to ``response_format``."""

    mode: GatewaySchemaMode
    require_closed_objects: bool = True
    require_all_properties_required: bool = True
    supported_keywords: frozenset[str] = SUPPORTED_SCHEMA_KEYWORDS

    @classmethod
    def strict_json_schema(
        cls,
        *,
        supported_keywords: frozenset[str] = SUPPORTED_SCHEMA_KEYWORDS,
        require_closed_objects: bool = True,
        require_all_properties_required: bool = True,
    ) -> GatewayCapabilities:
        """Strict provider-enforced JSON schema mode.

        By default requires every object schema to declare ``additionalProperties: false``
        and list all declared properties in ``required``.
        """
        return cls(
            mode=GatewaySchemaMode.STRICT_JSON_SCHEMA,
            require_closed_objects=require_closed_objects,
            require_all_properties_required=require_all_properties_required,
            supported_keywords=frozenset(supported_keywords),
        )

    @classmethod
    def local_validation(cls) -> GatewayCapabilities:
        """Explicit local-only validation mode: sends no ``response_format`` and validates
        locally.
        """
        return cls(
            mode=GatewaySchemaMode.LOCAL_VALIDATION,
            require_closed_objects=False,
            require_all_properties_required=False,
            supported_keywords=SUPPORTED_SCHEMA_KEYWORDS,
        )


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """Detached, immutable gateway request parameters (``messages`` and optional
    ``response_format``).

    Contains no ``model``, credentials, timeout, or retry parameters so the host retains
    complete transport ownership.
    """

    contract_ref: ContractRef
    bundle_digest: str
    schema_mode: GatewaySchemaMode
    _messages: tuple[RenderedMessage, ...]
    _response_format: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_messages", tuple(self._messages))
        if self._response_format is not None:
            object.__setattr__(
                self,
                "_response_format",
                freeze_json_value(self._response_format),
            )

    @property
    def messages(self) -> list[dict[str, str]]:
        """Return a fresh list of message dicts."""
        return [m.to_dict() for m in self._messages]

    @property
    def response_format(self) -> dict[str, Any] | None:
        """Return a fresh deep copy of ``response_format``, or ``None``."""
        if self._response_format is None:
            return None
        res = thaw_json_value(self._response_format)
        assert isinstance(res, dict)
        return res

    def to_kwargs(self) -> dict[str, Any]:
        """Return fresh keyword arguments suitable for ``client.complete(model=...,
        **request.to_kwargs())``.
        """
        kwargs: dict[str, Any] = {
            "messages": self.messages,
        }
        if self._response_format is not None:
            kwargs["response_format"] = self.response_format
        return kwargs


def _format_strict_schema_name(ref: ContractRef) -> str:
    raw = f"{ref.name}_{ref.version}"
    cleaned = _SAFE_SCHEMA_NAME_RE.sub("_", raw).strip("_")
    return (cleaned or "contract_schema")[:64]


def _verify_strict_capability(
    contract: Contract,
    capabilities: GatewayCapabilities,
) -> None:
    assert contract._compiled_output_schema is not None
    raw_schema = contract._compiled_output_schema.raw_schema
    ref_str = str(contract.ref)

    expanded, _ = expand_schema_node(
        raw_schema,
        policy=contract.policy,
        contract_ref=ref_str,
    )

    def _walk(node: Mapping[str, Any], path: str) -> None:
        for key in node:
            if key not in capabilities.supported_keywords:
                raise ProviderCapabilityError(
                    f"Output schema keyword {key!r} at {path} is not supported "
                    "by the selected strict gateway capability profile",
                    code=ErrorCode.CAPABILITY_UNSUPPORTED,
                    contract_ref=ref_str,
                )

        node_type = node.get("type")
        is_object = (
            node_type == "object"
            or (isinstance(node_type, (list, tuple)) and "object" in node_type)
            or "properties" in node
        )

        if is_object:
            if (
                capabilities.require_closed_objects
                and node.get("additionalProperties") is not False
            ):
                raise ProviderCapabilityError(
                    "Strict JSON schema profile requires "
                    f"'additionalProperties': false on object at {path}",
                    code=ErrorCode.CAPABILITY_UNSUPPORTED,
                    contract_ref=ref_str,
                )
            props = node.get("properties", {})
            if isinstance(props, Mapping):
                req = set(node.get("required", ()))
                prop_keys = set(props.keys())
                if capabilities.require_all_properties_required and prop_keys != req:
                    missing_req = sorted(prop_keys - req)
                    raise ProviderCapabilityError(
                        "Strict JSON schema profile requires all object properties to "
                        f"be required at {path}; optional properties: {missing_req}",
                        code=ErrorCode.CAPABILITY_UNSUPPORTED,
                        contract_ref=ref_str,
                    )
                for p_name, p_node in props.items():
                    if isinstance(p_node, Mapping):
                        _walk(p_node, f"{path}.properties.{p_name}")

        if "items" in node and isinstance(node["items"], Mapping):
            _walk(node["items"], f"{path}.items")

    _walk(expanded, "$")


def to_gateway_request(
    rendered: RenderedPrompt,
    *,
    contract: Contract,
    capabilities: GatewayCapabilities | None = None,
) -> GatewayRequest:
    """Map a :class:`RenderedPrompt` and :class:`Contract` into a detached :class:`GatewayRequest`.

    Verifies that ``rendered`` was produced by ``contract`` (matching reference and
    bundle digest). Never silently downgrades a failed strict schema check to local
    validation.
    """
    if rendered.contract_ref != contract.ref or rendered.bundle_digest != contract.bundle_digest:
        raise PromptContractError(
            f"RenderedPrompt identity ({rendered.contract_ref}, {rendered.bundle_digest}) "
            f"does not match Contract ({contract.ref}, {contract.bundle_digest})",
            code=ErrorCode.ADAPTER_CONTRACT_MISMATCH,
            contract_ref=str(contract.ref),
        )

    effective_caps = (
        capabilities if capabilities is not None else GatewayCapabilities.strict_json_schema()
    )

    if contract.output_spec.mode == OutputMode.TEXT:
        return GatewayRequest(
            contract_ref=contract.ref,
            bundle_digest=contract.bundle_digest,
            schema_mode=GatewaySchemaMode.LOCAL_VALIDATION,
            _messages=rendered.messages,
            _response_format=None,
        )

    if effective_caps.mode == GatewaySchemaMode.LOCAL_VALIDATION:
        return GatewayRequest(
            contract_ref=contract.ref,
            bundle_digest=contract.bundle_digest,
            schema_mode=GatewaySchemaMode.LOCAL_VALIDATION,
            _messages=rendered.messages,
            _response_format=None,
        )

    _verify_strict_capability(contract, effective_caps)
    out_schema = contract.output_schema
    assert out_schema is not None
    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": _format_strict_schema_name(contract.ref),
            "strict": True,
            "schema": out_schema,
        },
    }
    return GatewayRequest(
        contract_ref=contract.ref,
        bundle_digest=contract.bundle_digest,
        schema_mode=GatewaySchemaMode.STRICT_JSON_SCHEMA,
        _messages=rendered.messages,
        _response_format=response_format,
    )


def _unwrap_sdk_response(response: Any) -> Any:
    """Unwrap ``RawGatewayResponse`` if passed, returning the inner ``ChatResponse``."""
    if hasattr(response, "parse") and callable(response.parse) and hasattr(response, "status_code"):
        return response.parse()
    return response


def _get_field(obj: Any, name: str) -> Any:
    """Retrieve ``name`` from an SDK model instance or a mapping."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def validate_gateway_response(
    contract: Contract,
    response: Any,
    *,
    policy: RuntimePolicy | None = None,
) -> Any:
    """Check gateway completion choice count and status, then validate the output against
    ``contract``.

    Distinguishes missing/multiple choices, length truncation, refusal/content filter,
    unexpected tool calls, and empty content before delegating to ``contract.validate_output``.
    """
    unwrapped = _unwrap_sdk_response(response)
    ref_str = str(contract.ref)

    choices = _get_field(unwrapped, "choices")
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        count = len(choices) if isinstance(choices, (list, tuple)) else 0
        raise IncompleteCompletionError(
            f"Expected exactly 1 completion choice from gateway response, got {count}",
            code=ErrorCode.COMPLETION_CHOICE_COUNT,
            contract_ref=ref_str,
        )

    choice = choices[0]
    finish_reason = _get_field(choice, "finish_reason")
    message = _get_field(choice, "message")
    if message is None:
        raise IncompleteCompletionError(
            "Completion choice is missing a message object",
            code=ErrorCode.COMPLETION_EMPTY_CONTENT,
            contract_ref=ref_str,
        )

    if finish_reason == "length":
        raise IncompleteCompletionError(
            "Model completion was truncated due to max_tokens ('finish_reason': 'length')",
            code=ErrorCode.COMPLETION_TRUNCATED,
            contract_ref=ref_str,
        )

    if finish_reason in ("content_filter", "refusal", "safety"):
        raise IncompleteCompletionError(
            f"Model completion was blocked or refused ('finish_reason': {finish_reason!r})",
            code=ErrorCode.COMPLETION_REFUSED_OR_FILTERED,
            contract_ref=ref_str,
        )

    refusal_field = _get_field(message, "refusal")
    if refusal_field:
        raise IncompleteCompletionError(
            "Model completion returned an explicit refusal metadata field",
            code=ErrorCode.COMPLETION_REFUSED_OR_FILTERED,
            contract_ref=ref_str,
        )

    tool_calls = _get_field(message, "tool_calls")
    if finish_reason == "tool_calls" or (
        isinstance(tool_calls, (list, tuple)) and len(tool_calls) > 0
    ):
        raise IncompleteCompletionError(
            "Model completion returned unexpected tool calls for a non-tool contract",
            code=ErrorCode.COMPLETION_UNEXPECTED_TOOL_CALL,
            contract_ref=ref_str,
        )

    if finish_reason not in (None, "stop"):
        raise IncompleteCompletionError(
            "Model completion returned an unsupported finish reason",
            code=ErrorCode.COMPLETION_REFUSED_OR_FILTERED,
            contract_ref=ref_str,
        )

    content = _get_field(message, "content")
    if type(content) is not str or content == "":
        raise IncompleteCompletionError(
            "Model completion returned empty or null message content",
            code=ErrorCode.COMPLETION_EMPTY_CONTENT,
            contract_ref=ref_str,
        )

    return contract.validate_output(content, policy=policy)


def build_execution_metadata(
    contract: Contract,
    rendered: RenderedPrompt,
    *,
    response: Any = None,
    model_alias: str | None = None,
    correlation_id: str | None = None,
    dataset_revision: str | None = None,
    input_valid: bool = True,
    output_valid: bool | None = None,
    render_duration_ms: float | None = None,
    validation_duration_ms: float | None = None,
    generation_options: Mapping[str, JSONPrimitive] | None = None,
) -> ExecutionMetadata:
    """Assemble a sanitized :class:`ExecutionMetadata` record from contract and gateway metadata."""
    from prompt_contracts import __version__

    if rendered.contract_ref != contract.ref or rendered.bundle_digest != contract.bundle_digest:
        raise PromptContractError(
            "RenderedPrompt does not match Contract when building ExecutionMetadata",
            code=ErrorCode.ADAPTER_CONTRACT_MISMATCH,
            contract_ref=str(contract.ref),
        )

    served_model: str | None = None
    request_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    if response is not None:
        raw_req_id = getattr(response, "request_id", None)
        unwrapped = _unwrap_sdk_response(response)
        request_id = str(raw_req_id or getattr(unwrapped, "request_id", None) or "") or None
        raw_model = getattr(unwrapped, "model", None)
        served_model = str(raw_model) if raw_model else None
        usage = getattr(unwrapped, "usage", None)
        if usage is not None:
            pt = getattr(usage, "prompt_tokens", None)
            ct = getattr(usage, "completion_tokens", None)
            tt = getattr(usage, "total_tokens", None)
            if type(pt) is int:
                prompt_tokens = pt
            if type(ct) is int:
                completion_tokens = ct
            if type(tt) is int:
                total_tokens = tt

    return ExecutionMetadata(
        contract_name=contract.name,
        contract_version=contract.version,
        bundle_digest=contract.bundle_digest,
        digest_algorithm=contract.digest_algorithm,
        renderer=contract.renderer,
        library_version=__version__,
        policy_id=rendered.policy_id,
        model_alias=model_alias,
        served_model=served_model,
        request_id=request_id,
        correlation_id=correlation_id,
        dataset_revision=dataset_revision,
        input_valid=input_valid,
        output_valid=output_valid,
        render_duration_ms=render_duration_ms,
        validation_duration_ms=validation_duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        generation_options=generation_options or MappingProxyType({}),
    )

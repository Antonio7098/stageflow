"""Contract utilities for typed outputs and schema management."""

from .errors import ContractErrorInfo
from .registry import ContractCompatibilityReport, ContractMetadata, ContractRegistry, registry
from .suggestions import ContractSuggestion as _ContractSuggestion
from .suggestions import get_contract_suggestion, register_suggestion
from .typed_output import TypedStageOutput

__all__ = [
    "ContractCompatibilityReport",
    "ContractErrorInfo",
    "ContractMetadata",
    "ContractRegistry",
    "ContractSuggestion",
    "TypedStageOutput",
    "get_contract_suggestion",
    "register_suggestion",
    "registry",
]

ContractSuggestion = _ContractSuggestion

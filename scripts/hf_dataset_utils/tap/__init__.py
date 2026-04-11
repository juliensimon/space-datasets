"""TAP clients for astronomical data services."""

from hf_dataset_utils.tap.vizier import vizier_query
from hf_dataset_utils.tap.heasarc import heasarc_query

__all__ = ["vizier_query", "heasarc_query"]

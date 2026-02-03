# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Command log entity (audit trail)."""

from .endpoint import CommandLogEndpoint
from .table import CommandLogTable

__all__ = ["CommandLogEndpoint", "CommandLogTable"]

# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Tenant entity (multi-tenancy)."""

from .endpoint import TenantEndpoint
from .table import TenantsTable

__all__ = ["TenantEndpoint", "TenantsTable"]

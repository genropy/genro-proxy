# Copyright 2025 Softwell S.r.l. - SPDX-License-Identifier: Apache-2.0
"""Sphinx configuration for genro-proxy documentation."""

import os
import sys

# Add source directory to path for autodoc
sys.path.insert(0, os.path.abspath("../src"))

# Project information
project = "genro-proxy"
copyright = "2025, Softwell S.r.l."
author = "Genropy Team"
release = "0.1.0"

# Extensions
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

# Napoleon settings (Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}
autodoc_typehints = "description"

# MyST settings (for .md files)
myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
}

# HTML output
html_theme = "furo"
html_static_path = ["_static"]
html_title = "genro-proxy"

# Source settings
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"

# Exclude patterns
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

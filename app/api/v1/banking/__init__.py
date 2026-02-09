# -*- coding: utf-8 -*-
"""Banking API v1 module."""

from .connections import router as connections_router
from .routes import *  # noqa: F401,F403 - re-export all route functions
from .routes import router  # noqa: F811 - explicit re-export of router

__all__ = ["router", "connections_router"]

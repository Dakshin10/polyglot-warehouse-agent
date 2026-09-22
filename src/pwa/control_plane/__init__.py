"""Control plane package for PWA.

Provides run lifecycle tracking, task execution logging, watermark management,
and quality result persistence.
"""

from pwa.control_plane.metadata import ControlPlaneManager

__all__ = ["ControlPlaneManager"]

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from ..api.models import EasyEdaFootprint


logger = logging.getLogger(__name__)


class Model3DConfig:
    """Manages 3D model positioning with automatic heuristics and manual overrides."""

    OVERRIDE_FILE = "model_overrides.json"

    def __init__(self, library_path: Path):
        self.library_path = library_path
        self.override_path = library_path / self.OVERRIDE_FILE
        self.overrides: Dict[str, Dict[str, Any]] = {}
        self._load_overrides()

    def _load_overrides(self):
        if self.override_path.exists():
            try:
                with open(self.override_path, "r", encoding="utf-8") as f:
                    self.overrides = json.load(f)
                logger.info(f"Loaded {len(self.overrides)} model overrides")
            except Exception as e:
                logger.warning(f"Failed to load model overrides: {e}")
                self.overrides = {}

    def save_overrides(self):
        try:
            with open(self.override_path, "w", encoding="utf-8") as f:
                json.dump(self.overrides, f, indent=2)
            logger.info(f"Saved {len(self.overrides)} model overrides")
        except Exception as e:
            logger.error(f"Failed to save model overrides: {e}")

    def set_override(
        self,
        lcsc_id: str,
        offset: Optional[Tuple[float, float, float]] = None,
        rotation: Optional[Tuple[float, float, float]] = None,
        scale: Optional[Tuple[float, float, float]] = None
    ):
        """Set manual override for a component's 3D model positioning."""
        lcsc_id = lcsc_id.upper()

        if lcsc_id not in self.overrides:
            self.overrides[lcsc_id] = {}

        if offset is not None:
            self.overrides[lcsc_id]["offset"] = list(offset)
        if rotation is not None:
            self.overrides[lcsc_id]["rotation"] = list(rotation)
        if scale is not None:
            self.overrides[lcsc_id]["scale"] = list(scale)

        self.save_overrides()

    def get_override(self, lcsc_id: str) -> Optional[Dict[str, Any]]:
        """Get manual override if exists."""
        return self.overrides.get(lcsc_id.upper())

    def remove_override(self, lcsc_id: str):
        """Remove manual override for a component."""
        lcsc_id = lcsc_id.upper()
        if lcsc_id in self.overrides:
            del self.overrides[lcsc_id]
            self.save_overrides()

    def calculate_transform(
        self,
        lcsc_id: str,
        footprint: EasyEdaFootprint
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Calculate 3D model transform (offset, rotation, scale).
        Uses manual override if available, otherwise applies heuristics.
        """
        override = self.get_override(lcsc_id)

        if override:
            offset = tuple(override.get("offset", [0, 0, 0]))
            rotation = tuple(override.get("rotation", [0, 0, 0]))
            scale = tuple(override.get("scale", [1, 1, 1]))
            logger.debug(f"Using override for {lcsc_id}: offset={offset}, rotation={rotation}")
            return offset, rotation, scale

        return self._calculate_heuristic_transform(footprint)

    def _calculate_heuristic_transform(
        self,
        footprint: EasyEdaFootprint
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Calculate transform using heuristics based on footprint geometry.

        Heuristics applied:
        1. Z offset: Place model on top of PCB (z=0)
        2. XY offset: Center model on footprint centroid
        3. Rotation: Try to align based on pin 1 position
        """
        offset_x = 0.0
        offset_y = 0.0
        offset_z = 0.0
        rotation_x = 0.0
        rotation_y = 0.0
        rotation_z = 0.0
        scale = (1.0, 1.0, 1.0)

        if not footprint.pads:
            return (offset_x, offset_y, offset_z), (rotation_x, rotation_y, rotation_z), scale

        pad_positions = [(p.x, p.y) for p in footprint.pads]

        min_x = min(p[0] for p in pad_positions)
        max_x = max(p[0] for p in pad_positions)
        min_y = min(p[1] for p in pad_positions)
        max_y = max(p[1] for p in pad_positions)

        centroid_x = (min_x + max_x) / 2
        centroid_y = (min_y + max_y) / 2

        offset_x = -centroid_x
        offset_y = -centroid_y

        pin1 = self._find_pin1(footprint)
        if pin1:
            rotation_z = self._calculate_rotation_from_pin1(
                pin1, centroid_x, centroid_y, min_x, max_x, min_y, max_y
            )

        offset = (offset_x, offset_y, offset_z)
        rotation = (rotation_x, rotation_y, rotation_z)

        logger.debug(
            f"Heuristic transform: offset={offset}, rotation={rotation}"
        )

        return offset, rotation, scale

    def _find_pin1(self, footprint: EasyEdaFootprint):
        """Find pin 1 or first numbered pin."""
        for pad in footprint.pads:
            if pad.number in ("1", "A1", "A", "P1"):
                return pad

        numbered_pads = [p for p in footprint.pads if p.number.isdigit()]
        if numbered_pads:
            numbered_pads.sort(key=lambda p: int(p.number))
            return numbered_pads[0]

        return footprint.pads[0] if footprint.pads else None

    def _calculate_rotation_from_pin1(
        self,
        pin1,
        centroid_x: float,
        centroid_y: float,
        min_x: float,
        max_x: float,
        min_y: float,
        max_y: float
    ) -> float:
        """
        Calculate Z rotation based on pin 1 position relative to centroid.
        Standard convention: pin 1 at top-left or marked corner.
        """
        rel_x = pin1.x - centroid_x
        rel_y = pin1.y - centroid_y

        width = max_x - min_x
        height = max_y - min_y

        if width < 0.1 or height < 0.1:
            return 0.0

        threshold = 0.3

        if rel_x < -width * threshold and rel_y < -height * threshold:
            return 0.0
        elif rel_x > width * threshold and rel_y < -height * threshold:
            return 90.0
        elif rel_x > width * threshold and rel_y > height * threshold:
            return 180.0
        elif rel_x < -width * threshold and rel_y > height * threshold:
            return 270.0

        return 0.0

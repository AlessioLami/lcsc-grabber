"""
Wrapper module for easyeda2kicad library integration.

This module provides a clean interface to use easyeda2kicad for converting
EasyEDA component data to KiCad format while maintaining compatibility with
the existing plugin architecture.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import easyeda2kicad components
try:
    from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
    from easyeda2kicad.easyeda.easyeda_importer import (
        EasyedaSymbolImporter,
        EasyedaFootprintImporter,
        Easyeda3dModelImporter
    )
    from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad
    from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
    from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
    from easyeda2kicad.kicad.parameters_kicad_symbol import KicadVersion
    EASYEDA2KICAD_AVAILABLE = True
except ImportError as e:
    logger.warning(f"easyeda2kicad not available: {e}")
    EASYEDA2KICAD_AVAILABLE = False


class Easyeda2KicadWrapper:
    """
    Wrapper class for easyeda2kicad library.

    Provides methods to convert EasyEDA component data to KiCad format
    using the easyeda2kicad library.
    """

    def __init__(self):
        if not EASYEDA2KICAD_AVAILABLE:
            raise ImportError("easyeda2kicad library is not installed. "
                            "Install it with: pip install easyeda2kicad")
        self.api = EasyedaApi()
        self.kicad_version = KicadVersion.KI6

    def get_component_cad_data(self, lcsc_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch component CAD data from EasyEDA API.

        Args:
            lcsc_id: LCSC component ID (e.g., "C2040")

        Returns:
            Raw CAD data dictionary or None if not found
        """
        try:
            return self.api.get_cad_data_of_component(lcsc_id=lcsc_id)
        except Exception as e:
            logger.error(f"Failed to fetch CAD data for {lcsc_id}: {e}")
            return None

    def convert_symbol(
        self,
        cad_data: Dict[str, Any],
        component_name: str,
        footprint_lib: str = "lcsc_grabber",
        footprint_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Convert EasyEDA symbol data to KiCad symbol format.

        Args:
            cad_data: Raw CAD data from EasyEDA API
            component_name: Name for the symbol
            footprint_lib: Name of the footprint library
            footprint_name: Name of the footprint (defaults to component_name)

        Returns:
            KiCad symbol content as string, or None on failure
        """
        try:
            importer = EasyedaSymbolImporter(cad_data)
            ee_symbol = importer.get_symbol()

            if ee_symbol is None:
                logger.warning("No symbol data found in CAD data")
                return None

            exporter = ExporterSymbolKicad(ee_symbol, self.kicad_version)

            # Update footprint reference in the symbol
            fp_name = footprint_name or component_name
            exporter.output.info.fp_lib_name = footprint_lib

            return exporter.export(footprint_lib)

        except Exception as e:
            logger.error(f"Failed to convert symbol: {e}", exc_info=True)
            return None

    def convert_footprint(
        self,
        cad_data: Dict[str, Any],
        component_name: str,
        output_path: str,
        model_path: Optional[str] = None,
        model_offset: Tuple[float, float, float] = (0, 0, 0),
        model_rotation: Tuple[float, float, float] = (0, 0, 0),
        model_scale: Tuple[float, float, float] = (1, 1, 1)
    ) -> bool:
        """
        Convert EasyEDA footprint data to KiCad footprint format and save to file.

        Args:
            cad_data: Raw CAD data from EasyEDA API
            component_name: Name for the footprint
            output_path: Path to save the .kicad_mod file
            model_path: Optional path to 3D model
            model_offset: 3D model offset (x, y, z)
            model_rotation: 3D model rotation (x, y, z)
            model_scale: 3D model scale (x, y, z)

        Returns:
            True if conversion succeeded, False otherwise
        """
        try:
            importer = EasyedaFootprintImporter(cad_data)
            ee_footprint = importer.get_footprint()

            if ee_footprint is None:
                logger.warning("No footprint data found in CAD data")
                return False

            exporter = ExporterFootprintKicad(ee_footprint)

            # Set 3D model info if available
            if model_path:
                # The exporter expects model info in the footprint
                if hasattr(exporter, 'output') and hasattr(exporter.output, 'model_3d'):
                    exporter.output.model_3d = {
                        'path': model_path,
                        'offset': {'x': model_offset[0], 'y': model_offset[1], 'z': model_offset[2]},
                        'rotation': {'x': model_rotation[0], 'y': model_rotation[1], 'z': model_rotation[2]},
                        'scale': {'x': model_scale[0], 'y': model_scale[1], 'z': model_scale[2]}
                    }

            exporter.export(output_path)
            return True

        except Exception as e:
            logger.error(f"Failed to convert footprint: {e}", exc_info=True)
            return False

    def download_3d_model(
        self,
        cad_data: Dict[str, Any],
        output_dir: str,
        lcsc_id: str
    ) -> Optional[str]:
        """
        Download 3D model for a component.

        Args:
            cad_data: Raw CAD data from EasyEDA API
            output_dir: Directory to save the 3D model
            lcsc_id: LCSC ID for naming the file

        Returns:
            Path to the downloaded model file, or None if unavailable
        """
        try:
            importer = Easyeda3dModelImporter(
                easyeda_cp_cad_data=cad_data,
                download_raw_3d_model=True
            )

            if not importer.output:
                logger.info(f"No 3D model available for {lcsc_id}")
                return None

            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            exporter = Exporter3dModelKicad(importer.output)

            # Try STEP format first, then WRL
            step_path = output_path / f"{lcsc_id.upper()}.step"
            wrl_path = output_path / f"{lcsc_id.upper()}.wrl"

            if exporter.export_step(str(step_path)):
                return str(step_path)
            elif exporter.export_wrl(str(wrl_path)):
                return str(wrl_path)
            else:
                logger.warning(f"Failed to export 3D model for {lcsc_id}")
                return None

        except Exception as e:
            logger.error(f"Failed to download 3D model: {e}", exc_info=True)
            return None


def is_available() -> bool:
    """Check if easyeda2kicad library is available."""
    return EASYEDA2KICAD_AVAILABLE


def get_wrapper() -> Optional[Easyeda2KicadWrapper]:
    """
    Get an instance of the easyeda2kicad wrapper.

    Returns:
        Wrapper instance or None if easyeda2kicad is not available
    """
    if not EASYEDA2KICAD_AVAILABLE:
        return None
    try:
        return Easyeda2KicadWrapper()
    except Exception as e:
        logger.error(f"Failed to create easyeda2kicad wrapper: {e}")
        return None

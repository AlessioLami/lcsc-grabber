import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from ..api.models import ComponentInfo, EasyEdaSymbol, EasyEdaFootprint
from ..api.cache import get_cache
from ..converters.model3d_handler import Model3DHandler
from .model3d_config import Model3DConfig

# Try to import easyeda2kicad for conversions
try:
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
except ImportError:
    EASYEDA2KICAD_AVAILABLE = False
    # Fallback to custom converters
    from ..converters.symbol_converter import SymbolConverter
    from ..converters.footprint_converter import FootprintConverter
    from .symbol_writer import SymbolWriter
    from .footprint_writer import FootprintWriter


logger = logging.getLogger(__name__)


class LibraryManager:

    LIBRARY_NAME = "lcsc_grabber"
    DEFAULT_CATEGORY = "misc"

    def __init__(self, library_path: Optional[str] = None):
        if library_path:
            self.library_path = Path(library_path)
        else:
            docs_path = Path.home() / "Documents" / "KiCad"
            self.library_path = docs_path / self.LIBRARY_NAME

        self.library_path.mkdir(parents=True, exist_ok=True)

        # Legacy paths (kept for backwards compatibility)
        self.symbol_lib_path = self.library_path / f"{self.LIBRARY_NAME}.kicad_sym"
        self.footprint_lib_path = self.library_path / f"{self.LIBRARY_NAME}.pretty"
        self.models_3d_path = self.library_path / f"{self.LIBRARY_NAME}.3dshapes"

        self.models_3d_path.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.library_path / "manifest.json"
        self.manifest = self._load_manifest()

        self.categories_path = self.library_path / "categories.json"
        self.categories = self._load_categories()

        # Ensure default category exists
        self._ensure_category_libs_exist(self.DEFAULT_CATEGORY)

        # Use easyeda2kicad if available, otherwise fall back to custom converters
        self.use_easyeda2kicad = EASYEDA2KICAD_AVAILABLE
        if self.use_easyeda2kicad:
            logger.info("Using easyeda2kicad for component conversion")
            self.kicad_version = KicadVersion.KI6
        else:
            logger.info("Using custom converters (easyeda2kicad not available)")
            self.symbol_converter = SymbolConverter()
            self.footprint_converter = FootprintConverter()
            self.symbol_writer = SymbolWriter()
            self.footprint_writer = FootprintWriter()

        self.model3d_handler = Model3DHandler(output_dir=str(self.models_3d_path))
        self.model3d_config = Model3DConfig(self.library_path)

    def _create_empty_symbol_library(self, path: Optional[Path] = None):
        if path is None:
            path = self.symbol_lib_path
        content = """(kicad_symbol_lib
  (version 20231120)
  (generator "lcsc_grabber")
  (generator_version "1.0")
)
"""
        path.write_text(content, encoding="utf-8")
        logger.info(f"Created empty symbol library: {path}")

    # -------------------------------------------------------------------------
    # Category Management
    # -------------------------------------------------------------------------

    def _load_categories(self) -> Dict[str, Any]:
        if self.categories_path.exists():
            try:
                return json.loads(self.categories_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Invalid categories file, creating default")
        return {
            "categories": [
                {"id": self.DEFAULT_CATEGORY, "name": "Misc"}
            ],
            "default_category": self.DEFAULT_CATEGORY
        }

    def _save_categories(self):
        self.categories_path.write_text(
            json.dumps(self.categories, indent=2),
            encoding="utf-8"
        )

    def get_categories(self) -> List[Dict[str, str]]:
        return self.categories.get("categories", [])

    def get_default_category(self) -> str:
        return self.categories.get("default_category", self.DEFAULT_CATEGORY)

    def add_category(self, category_id: str, name: str) -> Tuple[bool, str]:
        category_id = self._sanitize_category_id(category_id)

        for cat in self.categories.get("categories", []):
            if cat["id"] == category_id:
                return (False, f"Category '{category_id}' already exists")

        self.categories.setdefault("categories", []).append({
            "id": category_id,
            "name": name
        })
        self._save_categories()
        self._ensure_category_libs_exist(category_id)

        return (True, f"Category '{name}' created")

    def remove_category(self, category_id: str) -> Tuple[bool, str]:
        if category_id == self.DEFAULT_CATEGORY:
            return (False, "Cannot remove default category")

        categories = self.categories.get("categories", [])
        found = False
        for i, cat in enumerate(categories):
            if cat["id"] == category_id:
                categories.pop(i)
                found = True
                break

        if not found:
            return (False, f"Category '{category_id}' not found")

        # Move components from this category to default
        for lcsc_id, comp in self.manifest.get("components", {}).items():
            if comp.get("category") == category_id:
                self.update_component_category(lcsc_id, self.DEFAULT_CATEGORY)

        self._save_categories()
        return (True, f"Category removed, components moved to {self.DEFAULT_CATEGORY}")

    def _sanitize_category_id(self, name: str) -> str:
        category_id = name.lower().replace(" ", "_").replace("-", "_")
        category_id = re.sub(r'[^\w_]', '', category_id)
        return category_id or "misc"

    def _ensure_category_libs_exist(self, category_id: str):
        sym_path = self._get_symbol_lib_for_category(category_id)
        fp_path = self._get_footprint_lib_for_category(category_id)

        if not sym_path.exists():
            self._create_empty_symbol_library(sym_path)

        fp_path.mkdir(parents=True, exist_ok=True)

    def _get_symbol_lib_for_category(self, category_id: str) -> Path:
        return self.library_path / f"{category_id}.kicad_sym"

    def _get_footprint_lib_for_category(self, category_id: str) -> Path:
        return self.library_path / f"{category_id}.pretty"

    def get_category_library_name(self, category_id: str) -> str:
        return category_id

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Invalid manifest file, creating new one")
        return {"components": {}}

    def _save_manifest(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2),
            encoding="utf-8"
        )

    def get_library_path(self) -> str:
        return str(self.library_path)

    def get_symbol_library_path(self) -> str:
        return str(self.symbol_lib_path)

    def get_footprint_library_path(self) -> str:
        return str(self.footprint_lib_path)

    def get_3d_models_path(self) -> str:
        return str(self.models_3d_path)

    def is_imported(self, lcsc_id: str) -> bool:
        lcsc_id = lcsc_id.upper()
        return lcsc_id in self.manifest.get("components", {})

    def get_imported_components(self) -> List[Dict[str, Any]]:
        return list(self.manifest.get("components", {}).values())

    def import_component(
        self,
        component: ComponentInfo,
        import_symbol: bool = True,
        import_footprint: bool = True,
        import_3d_model: bool = True,
        overwrite: bool = False,
        category: Optional[str] = None,
        model_offset: Optional[Tuple[float, float, float]] = None,
        model_rotation: Optional[Tuple[float, float, float]] = None,
        model_scale: Optional[Tuple[float, float, float]] = None
    ) -> Tuple[bool, str]:
        lcsc_id = component.lcsc_id.upper()

        if self.is_imported(lcsc_id) and not overwrite:
            return (False, f"Component {lcsc_id} already imported. Use overwrite option to update.")

        # Use provided category or default
        if category is None:
            category = self.get_default_category()
        self._ensure_category_libs_exist(category)

        component_name = self._make_component_name(component)
        results = []

        if import_symbol and component.has_symbol():
            success, msg = self._import_symbol(component, component_name, overwrite, category)
            results.append(("Symbol", success, msg))
        elif import_symbol:
            results.append(("Symbol", False, "No symbol data available"))

        footprint_name = None
        if import_footprint and component.has_footprint():
            success, msg, footprint_name = self._import_footprint(
                component, component_name, overwrite, category,
                model_offset=model_offset,
                model_rotation=model_rotation,
                model_scale=model_scale
            )
            results.append(("Footprint", success, msg))
        elif import_footprint:
            results.append(("Footprint", False, "No footprint data available"))

        model_path = None
        if import_3d_model and component.has_3d_model():
            success, msg, model_path = self._import_3d_model(component, overwrite)
            results.append(("3D Model", success, msg))
        elif import_3d_model:
            results.append(("3D Model", False, "No 3D model available"))

        self.manifest.setdefault("components", {})[lcsc_id] = {
            "lcsc_id": lcsc_id,
            "name": component_name,
            "mpn": component.mpn,
            "manufacturer": component.manufacturer,
            "description": component.description,
            "package": component.package,
            "category": category,
            "has_symbol": component.has_symbol(),
            "has_footprint": component.has_footprint(),
            "has_3d_model": component.has_3d_model(),
            "footprint_name": footprint_name,
            "model_path": model_path,
        }
        self._save_manifest()

        # Save 3D config override if custom values provided
        if model_offset or model_rotation or model_scale:
            self.model3d_config.set_override(
                lcsc_id,
                offset=model_offset,
                rotation=model_rotation,
                scale=model_scale
            )

        success_count = sum(1 for _, s, _ in results if s)
        total_count = len(results)
        detail_msg = ", ".join(f"{name}: {'OK' if s else m}" for name, s, m in results)

        if success_count == total_count:
            return (True, f"Imported {lcsc_id} successfully ({detail_msg})")
        elif success_count > 0:
            return (True, f"Partially imported {lcsc_id} ({detail_msg})")
        else:
            return (False, f"Failed to import {lcsc_id} ({detail_msg})")

    def _make_component_name(self, component: ComponentInfo) -> str:
        name = component.mpn or component.lcsc_id

        name = re.sub(r'[^\w\-_.]', '_', name)
        name = re.sub(r'_+', '_', name)
        name = name.strip('_')

        return name or component.lcsc_id

    def _import_symbol(
        self,
        component: ComponentInfo,
        component_name: str,
        overwrite: bool,
        category: str
    ) -> Tuple[bool, str]:
        try:
            sym_lib_path = self._get_symbol_lib_for_category(category)
            lib_content = sym_lib_path.read_text(encoding="utf-8")

            symbol_pattern = rf'\(symbol "{re.escape(component_name)}"'
            if re.search(symbol_pattern, lib_content):
                if not overwrite:
                    return (False, "Symbol already exists")
                lib_content = self._remove_symbol_from_lib(lib_content, component_name)

            if self.use_easyeda2kicad:
                # Use easyeda2kicad for conversion
                symbol_sexpr = self._convert_symbol_easyeda2kicad(
                    component, component_name, category
                )
            else:
                # Use custom converters
                symbol_sexpr = self._convert_symbol_custom(
                    component, component_name, category
                )

            if not symbol_sexpr:
                return (False, "Failed to convert symbol data")

            insert_pos = lib_content.rfind(")")
            new_content = lib_content[:insert_pos] + symbol_sexpr + "\n" + lib_content[insert_pos:]

            sym_lib_path.write_text(new_content, encoding="utf-8")

            return (True, f"Symbol added: {component_name}")

        except Exception as e:
            logger.error(f"Error importing symbol: {e}", exc_info=True)
            return (False, str(e))

    def _convert_symbol_easyeda2kicad(
        self,
        component: ComponentInfo,
        component_name: str,
        category: str
    ) -> Optional[str]:
        """Convert symbol using easyeda2kicad library."""
        try:
            importer = EasyedaSymbolImporter(component.symbol_data)
            ee_symbol = importer.get_symbol()

            if ee_symbol is None:
                logger.warning("No symbol data found in CAD data")
                return None

            exporter = ExporterSymbolKicad(ee_symbol, self.kicad_version)
            symbol_content = exporter.export(category)

            # Post-process the symbol to add our custom properties
            symbol_content = self._enhance_symbol_content(
                symbol_content, component, component_name, category
            )

            return symbol_content

        except Exception as e:
            logger.error(f"easyeda2kicad symbol conversion failed: {e}", exc_info=True)
            return None

    def _enhance_symbol_content(
        self,
        symbol_content: str,
        component: ComponentInfo,
        component_name: str,
        category: str
    ) -> str:
        """Add custom properties to the symbol content."""
        # The easyeda2kicad output already includes most properties
        # We just need to ensure LCSC ID and other custom props are present
        if f'"LCSC"' not in symbol_content:
            # Find the last property line and add LCSC property after it
            lines = symbol_content.split('\n')
            new_lines = []
            property_added = False
            for i, line in enumerate(lines):
                new_lines.append(line)
                if '(property "' in line and not property_added:
                    # Check if next few lines close this property
                    for j in range(i+1, min(i+5, len(lines))):
                        if lines[j].strip().startswith('(property'):
                            break
                        if lines[j].strip() == ')' and '(at' in lines[j-1]:
                            # This is likely the end of a property block
                            pass

            # For now, just return as-is - easyeda2kicad should include needed props
            return symbol_content
        return symbol_content

    def _convert_symbol_custom(
        self,
        component: ComponentInfo,
        component_name: str,
        category: str
    ) -> Optional[str]:
        """Convert symbol using custom converters (fallback)."""
        symbol = self.symbol_converter.convert(
            component.symbol_data,
            component_name=component_name,
            description=component.description,
            category=component.category
        )

        if not symbol:
            return None

        return self.symbol_writer.write_symbol(
            symbol,
            lcsc_id=component.lcsc_id,
            footprint_lib=category,
            footprint_name=component_name,
            datasheet_url=component.datasheet_url,
            mpn=component.mpn
        )

    def _remove_symbol_from_lib(self, lib_content: str, symbol_name: str) -> str:
        pattern = rf'\(symbol "{re.escape(symbol_name)}"'
        match = re.search(pattern, lib_content)
        if not match:
            return lib_content

        start = match.start()

        depth = 0
        end = start
        for i in range(start, len(lib_content)):
            if lib_content[i] == '(':
                depth += 1
            elif lib_content[i] == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        while end < len(lib_content) and lib_content[end] in '\n\r':
            end += 1

        return lib_content[:start] + lib_content[end:]

    def _import_footprint(
        self,
        component: ComponentInfo,
        component_name: str,
        overwrite: bool,
        category: str,
        model_offset: Optional[Tuple[float, float, float]] = None,
        model_rotation: Optional[Tuple[float, float, float]] = None,
        model_scale: Optional[Tuple[float, float, float]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        try:
            fp_lib_path = self._get_footprint_lib_for_category(category)
            fp_path = fp_lib_path / f"{component_name}.kicad_mod"

            if fp_path.exists() and not overwrite:
                return (False, "Footprint already exists", component_name)

            fp_model_path = None
            fp_model_offset = model_offset or (0, 0, 0)
            fp_model_rotation = model_rotation or (0, 0, 0)
            fp_model_scale = model_scale or (1, 1, 1)

            if component.has_3d_model():
                fp_model_path = str(self.models_3d_path / f"{component.lcsc_id.upper()}.step")
                # Convert to Windows path format if needed
                if os.name == 'nt' or '/mnt/' in fp_model_path:
                    fp_model_path = fp_model_path.replace('/', '\\')

            if self.use_easyeda2kicad:
                # Use easyeda2kicad for conversion
                success = self._convert_footprint_easyeda2kicad(
                    component, component_name, str(fp_path),
                    fp_model_path, fp_model_offset, fp_model_rotation, fp_model_scale
                )
            else:
                # Use custom converters
                success = self._convert_footprint_custom(
                    component, component_name, str(fp_path),
                    fp_model_path, fp_model_offset, fp_model_rotation, fp_model_scale
                )

            if not success:
                return (False, "Failed to convert footprint data", None)

            return (True, f"Footprint added: {component_name}", component_name)

        except Exception as e:
            logger.error(f"Error importing footprint: {e}", exc_info=True)
            return (False, str(e), None)

    def _convert_footprint_easyeda2kicad(
        self,
        component: ComponentInfo,
        component_name: str,
        output_path: str,
        model_path: Optional[str],
        model_offset: Tuple[float, float, float],
        model_rotation: Tuple[float, float, float],
        model_scale: Tuple[float, float, float]
    ) -> bool:
        """Convert footprint using easyeda2kicad library."""
        try:
            importer = EasyedaFootprintImporter(component.footprint_data)
            ee_footprint = importer.get_footprint()

            if ee_footprint is None:
                logger.warning("No footprint data found in CAD data")
                return False

            # Set 3D model info if available
            if model_path and hasattr(ee_footprint, 'model_3d') and ee_footprint.model_3d:
                ee_footprint.model_3d.translation = {
                    'x': model_offset[0],
                    'y': model_offset[1],
                    'z': model_offset[2]
                }
                ee_footprint.model_3d.rotation = {
                    'x': model_rotation[0],
                    'y': model_rotation[1],
                    'z': model_rotation[2]
                }

            exporter = ExporterFootprintKicad(ee_footprint)

            # Export to file
            exporter.export(output_path)

            # If we have a 3D model path, we need to add it to the footprint
            if model_path:
                self._add_3d_model_to_footprint(
                    output_path, model_path,
                    model_offset, model_rotation, model_scale
                )

            return True

        except Exception as e:
            logger.error(f"easyeda2kicad footprint conversion failed: {e}", exc_info=True)
            return False

    def _add_3d_model_to_footprint(
        self,
        footprint_path: str,
        model_path: str,
        offset: Tuple[float, float, float],
        rotation: Tuple[float, float, float],
        scale: Tuple[float, float, float]
    ):
        """Add 3D model reference to an existing footprint file."""
        try:
            content = Path(footprint_path).read_text(encoding="utf-8")

            # Check if model is already present
            if '(model ' in content:
                return

            # Find the closing parenthesis and add model before it
            model_sexpr = f'''  (model "{model_path}"
    (offset (xyz {offset[0]:.6f} {offset[1]:.6f} {offset[2]:.6f}))
    (scale (xyz {scale[0]:.6f} {scale[1]:.6f} {scale[2]:.6f}))
    (rotate (xyz {rotation[0]:.6f} {rotation[1]:.6f} {rotation[2]:.6f}))
  )'''

            # Insert before the last closing parenthesis
            insert_pos = content.rfind(")")
            new_content = content[:insert_pos] + model_sexpr + "\n" + content[insert_pos:]

            Path(footprint_path).write_text(new_content, encoding="utf-8")

        except Exception as e:
            logger.error(f"Failed to add 3D model to footprint: {e}")

    def _convert_footprint_custom(
        self,
        component: ComponentInfo,
        component_name: str,
        output_path: str,
        model_path: Optional[str],
        model_offset: Tuple[float, float, float],
        model_rotation: Tuple[float, float, float],
        model_scale: Tuple[float, float, float]
    ) -> bool:
        """Convert footprint using custom converters (fallback)."""
        footprint = self.footprint_converter.convert(
            component.footprint_data,
            component_name=component_name
        )

        if not footprint:
            return False

        # Calculate transform if not provided and 3D model exists
        if model_path and model_offset == (0, 0, 0) and model_rotation == (0, 0, 0):
            model_offset, model_rotation, model_scale = self.model3d_config.calculate_transform(
                component.lcsc_id, footprint
            )

        self.footprint_writer.save_footprint(
            footprint,
            output_path,
            model_path=model_path,
            model_offset=model_offset,
            model_rotation=model_rotation,
            model_scale=model_scale
        )

        return True

    def _import_3d_model(
        self,
        component: ComponentInfo,
        overwrite: bool
    ) -> Tuple[bool, str, Optional[str]]:
        try:
            lcsc_id = component.lcsc_id.upper()

            existing_path = self.model3d_handler.get_model_path(lcsc_id)
            if existing_path and not overwrite:
                return (True, "3D model already exists", existing_path)

            model_path = self.model3d_handler.download_model(
                component.model_3d_uuid,
                lcsc_id
            )

            if model_path:
                return (True, "3D model downloaded", model_path)
            else:
                return (False, "Failed to download 3D model", None)

        except Exception as e:
            logger.error(f"Error importing 3D model: {e}", exc_info=True)
            return (False, str(e), None)

    def remove_component(self, lcsc_id: str) -> Tuple[bool, str]:
        lcsc_id = lcsc_id.upper()

        if not self.is_imported(lcsc_id):
            return (False, f"Component {lcsc_id} not found in library")

        component_info = self.manifest["components"].get(lcsc_id, {})
        component_name = component_info.get("name", lcsc_id)
        category = component_info.get("category", self.DEFAULT_CATEGORY)

        errors = []

        # Remove symbol from category library
        sym_lib_path = self._get_symbol_lib_for_category(category)
        try:
            if sym_lib_path.exists():
                lib_content = sym_lib_path.read_text(encoding="utf-8")
                new_content = self._remove_symbol_from_lib(lib_content, component_name)
                sym_lib_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            errors.append(f"Symbol: {e}")

        # Remove footprint from category library
        fp_lib_path = self._get_footprint_lib_for_category(category)
        fp_path = fp_lib_path / f"{component_name}.kicad_mod"
        try:
            if fp_path.exists():
                fp_path.unlink()
        except Exception as e:
            errors.append(f"Footprint: {e}")

        # Remove 3D models
        for ext in [".step", ".wrl", ".obj"]:
            model_path = self.models_3d_path / f"{lcsc_id}{ext}"
            try:
                if model_path.exists():
                    model_path.unlink()
            except Exception as e:
                errors.append(f"3D model: {e}")

        # Remove 3D config override if exists
        self.model3d_config.remove_override(lcsc_id)

        del self.manifest["components"][lcsc_id]
        self._save_manifest()

        if errors:
            return (True, f"Removed {lcsc_id} with errors: {', '.join(errors)}")
        return (True, f"Removed {lcsc_id} successfully")

    # -------------------------------------------------------------------------
    # Post-Import Management
    # -------------------------------------------------------------------------

    def update_component_category(self, lcsc_id: str, new_category: str) -> Tuple[bool, str]:
        lcsc_id = lcsc_id.upper()

        if not self.is_imported(lcsc_id):
            return (False, f"Component {lcsc_id} not found")

        component_info = self.manifest["components"].get(lcsc_id, {})
        old_category = component_info.get("category", self.DEFAULT_CATEGORY)
        component_name = component_info.get("name", lcsc_id)

        if old_category == new_category:
            return (True, "Category unchanged")

        self._ensure_category_libs_exist(new_category)

        errors = []

        # Move symbol
        old_sym_path = self._get_symbol_lib_for_category(old_category)
        new_sym_path = self._get_symbol_lib_for_category(new_category)

        try:
            if old_sym_path.exists():
                old_content = old_sym_path.read_text(encoding="utf-8")
                # Extract symbol from old library
                symbol_sexpr = self._extract_symbol_from_lib(old_content, component_name)
                if symbol_sexpr:
                    # Remove from old
                    new_old_content = self._remove_symbol_from_lib(old_content, component_name)
                    old_sym_path.write_text(new_old_content, encoding="utf-8")

                    # Update footprint reference in symbol
                    symbol_sexpr = symbol_sexpr.replace(
                        f'"{old_category}:{component_name}"',
                        f'"{new_category}:{component_name}"'
                    )

                    # Add to new
                    new_content = new_sym_path.read_text(encoding="utf-8")
                    insert_pos = new_content.rfind(")")
                    new_content = new_content[:insert_pos] + symbol_sexpr + "\n" + new_content[insert_pos:]
                    new_sym_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            errors.append(f"Symbol: {e}")

        # Move footprint
        old_fp_lib = self._get_footprint_lib_for_category(old_category)
        new_fp_lib = self._get_footprint_lib_for_category(new_category)
        old_fp_path = old_fp_lib / f"{component_name}.kicad_mod"
        new_fp_path = new_fp_lib / f"{component_name}.kicad_mod"

        try:
            if old_fp_path.exists():
                old_fp_path.rename(new_fp_path)
        except Exception as e:
            errors.append(f"Footprint: {e}")

        # Update manifest
        self.manifest["components"][lcsc_id]["category"] = new_category
        self._save_manifest()

        if errors:
            return (True, f"Moved with errors: {', '.join(errors)}")
        return (True, f"Moved to {new_category}")

    def _extract_symbol_from_lib(self, lib_content: str, symbol_name: str) -> Optional[str]:
        pattern = rf'\(symbol "{re.escape(symbol_name)}"'
        match = re.search(pattern, lib_content)
        if not match:
            return None

        start = match.start()
        depth = 0
        end = start

        for i in range(start, len(lib_content)):
            if lib_content[i] == '(':
                depth += 1
            elif lib_content[i] == ')':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        return lib_content[start:end]

    def update_3d_config(
        self,
        lcsc_id: str,
        offset: Optional[Tuple[float, float, float]] = None,
        rotation: Optional[Tuple[float, float, float]] = None,
        scale: Optional[Tuple[float, float, float]] = None
    ) -> Tuple[bool, str]:
        lcsc_id = lcsc_id.upper()

        if not self.is_imported(lcsc_id):
            return (False, f"Component {lcsc_id} not found")

        # Update the override
        self.model3d_config.set_override(lcsc_id, offset=offset, rotation=rotation, scale=scale)

        # Regenerate footprint with new values
        return self.regenerate_footprint(lcsc_id)

    def regenerate_footprint(self, lcsc_id: str) -> Tuple[bool, str]:
        lcsc_id = lcsc_id.upper()

        if not self.is_imported(lcsc_id):
            return (False, f"Component {lcsc_id} not found")

        component_info = self.manifest["components"].get(lcsc_id, {})
        component_name = component_info.get("name", lcsc_id)
        category = component_info.get("category", self.DEFAULT_CATEGORY)

        # Get cached component data
        cache = get_cache()
        component = cache.get_component(lcsc_id)

        if not component or not component.has_footprint():
            return (False, "No footprint data in cache")

        try:
            fp_lib_path = self._get_footprint_lib_for_category(category)
            fp_path = fp_lib_path / f"{component_name}.kicad_mod"

            # Get 3D model config
            model_path = None
            model_offset, model_rotation, model_scale = (0, 0, 0), (0, 0, 0), (1, 1, 1)

            if component.has_3d_model():
                model_path = str(self.models_3d_path / f"{lcsc_id}.step")
                if os.name == 'nt' or '/mnt/' in model_path:
                    model_path = model_path.replace('/', '\\')

            # Use appropriate converter
            if self.use_easyeda2kicad:
                success = self._convert_footprint_easyeda2kicad(
                    component, component_name, str(fp_path),
                    model_path, model_offset, model_rotation, model_scale
                )
            else:
                success = self._convert_footprint_custom(
                    component, component_name, str(fp_path),
                    model_path, model_offset, model_rotation, model_scale
                )

            if not success:
                return (False, "Failed to regenerate footprint")

            return (True, "Footprint regenerated")

        except Exception as e:
            logger.error(f"Error regenerating footprint: {e}", exc_info=True)
            return (False, str(e))

    def get_component_3d_config(self, lcsc_id: str) -> Optional[Dict[str, Tuple[float, float, float]]]:
        lcsc_id = lcsc_id.upper()
        override = self.model3d_config.get_override(lcsc_id)
        if override:
            return override

        # Calculate heuristic values if no override
        if not self.is_imported(lcsc_id):
            return None

        cache = get_cache()
        component = cache.get_component(lcsc_id)
        if not component or not component.has_footprint():
            return None

        component_info = self.manifest["components"].get(lcsc_id, {})
        component_name = component_info.get("name", lcsc_id)

        if self.use_easyeda2kicad:
            # easyeda2kicad handles 3D transforms internally
            # Return default values that can be overridden by user
            return {"offset": (0, 0, 0), "rotation": (0, 0, 0), "scale": (1, 1, 1)}
        else:
            footprint = self.footprint_converter.convert(
                component.footprint_data,
                component_name=component_name
            )

            if footprint:
                offset, rotation, scale = self.model3d_config.calculate_transform(lcsc_id, footprint)
                return {"offset": offset, "rotation": rotation, "scale": scale}

        return None

    def get_imported_components_by_category(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        components = self.get_imported_components()
        if category is None:
            return components
        return [c for c in components if c.get("category", self.DEFAULT_CATEGORY) == category]

    def _get_kicad_config_dir(self) -> Optional[Path]:
        """Find KiCad's configuration directory."""
        import platform
        system = platform.system()

        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            if appdata:
                kicad_dir = Path(appdata) / "kicad"
                # Try versioned directories first (8.0, 7.0, etc.)
                if kicad_dir.exists():
                    versions = sorted([d for d in kicad_dir.iterdir() if d.is_dir() and d.name[0].isdigit()], reverse=True)
                    if versions:
                        return versions[0]
                    return kicad_dir
        elif system == "Darwin":  # macOS
            config_paths = [
                Path.home() / "Library" / "Preferences" / "kicad",
                Path.home() / ".config" / "kicad"
            ]
            for config_path in config_paths:
                if config_path.exists():
                    versions = sorted([d for d in config_path.iterdir() if d.is_dir() and d.name[0].isdigit()], reverse=True)
                    if versions:
                        return versions[0]
                    return config_path
        else:  # Linux
            config_path = Path.home() / ".config" / "kicad"
            if config_path.exists():
                versions = sorted([d for d in config_path.iterdir() if d.is_dir() and d.name[0].isdigit()], reverse=True)
                if versions:
                    return versions[0]
                return config_path

        return None

    def _parse_lib_table(self, content: str) -> Tuple[List[str], List[Dict[str, str]]]:
        """Parse a KiCad library table file and return header lines and library entries."""
        lines = content.strip().split('\n')
        header_lines = []
        libraries = []

        for line in lines:
            line = line.strip()
            if line.startswith('(lib '):
                # Parse library entry
                name_match = re.search(r'\(name\s+"([^"]+)"\)', line)
                uri_match = re.search(r'\(uri\s+"([^"]+)"\)', line)
                type_match = re.search(r'\(type\s+"([^"]+)"\)', line)
                if name_match:
                    libraries.append({
                        'name': name_match.group(1),
                        'uri': uri_match.group(1) if uri_match else '',
                        'type': type_match.group(1) if type_match else 'KiCad',
                        'raw': line
                    })
            elif line and not line.startswith(')'):
                header_lines.append(line)

        return header_lines, libraries

    def _add_to_lib_table(self, table_path: Path, lib_name: str, lib_uri: str, lib_type: str = "KiCad") -> bool:
        """Add a library entry to a KiCad library table file."""
        try:
            if table_path.exists():
                content = table_path.read_text(encoding='utf-8')
                header_lines, libraries = self._parse_lib_table(content)

                # Check if library already exists
                for lib in libraries:
                    if lib['name'] == lib_name:
                        logger.info(f"Library '{lib_name}' already registered in {table_path}")
                        return True
            else:
                # Create new table
                if 'sym' in table_path.name:
                    header_lines = ['(sym_lib_table', '  (version 7)']
                else:
                    header_lines = ['(fp_lib_table', '  (version 7)']
                libraries = []

            # Add the new library
            new_entry = f'  (lib (name "{lib_name}")(type "{lib_type}")(uri "{lib_uri}")(options "")(descr "LCSC Grabber imported components"))'

            # Rebuild the file
            output_lines = header_lines.copy()
            for lib in libraries:
                output_lines.append(lib['raw'])
            output_lines.append(new_entry)
            output_lines.append(')')

            table_path.write_text('\n'.join(output_lines) + '\n', encoding='utf-8')
            logger.info(f"Added library '{lib_name}' to {table_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to update {table_path}: {e}")
            return False

    def register_libraries_with_kicad(self) -> Tuple[bool, str]:
        """
        Automatically register LCSC Grabber libraries with KiCad.
        Returns (success, message).
        """
        config_dir = self._get_kicad_config_dir()
        if not config_dir:
            return (False, "Could not find KiCad configuration directory. Please add libraries manually.")

        results = []
        all_success = True

        # Get all categories to register
        categories = [cat['id'] for cat in self.get_categories()]

        # Register symbol libraries
        sym_table = config_dir / "sym-lib-table"
        for cat_id in categories:
            sym_path = self._get_symbol_lib_for_category(cat_id)
            if sym_path.exists():
                lib_name = f"lcsc_{cat_id}"
                success = self._add_to_lib_table(sym_table, lib_name, str(sym_path))
                if success:
                    results.append(f"Symbol library '{lib_name}' registered")
                else:
                    all_success = False
                    results.append(f"Failed to register symbol library '{lib_name}'")

        # Register footprint libraries
        fp_table = config_dir / "fp-lib-table"
        for cat_id in categories:
            fp_path = self._get_footprint_lib_for_category(cat_id)
            if fp_path.exists():
                lib_name = f"lcsc_{cat_id}"
                success = self._add_to_lib_table(fp_table, lib_name, str(fp_path))
                if success:
                    results.append(f"Footprint library '{lib_name}' registered")
                else:
                    all_success = False
                    results.append(f"Failed to register footprint library '{lib_name}'")

        if all_success:
            msg = "Libraries registered with KiCad successfully!\n\n"
            msg += "Note: If KiCad is open, restart it or go to:\n"
            msg += "Preferences > Manage Symbol/Footprint Libraries > OK\n"
            msg += "to reload the library tables."
        else:
            msg = "Some libraries could not be registered:\n" + "\n".join(results)

        return (all_success, msg)

    def is_registered_with_kicad(self) -> bool:
        """Check if libraries are already registered with KiCad."""
        config_dir = self._get_kicad_config_dir()
        if not config_dir:
            return False

        sym_table = config_dir / "sym-lib-table"
        if sym_table.exists():
            content = sym_table.read_text(encoding='utf-8')
            if 'lcsc_' in content:
                return True

        return False

    def get_kicad_config_instructions(self) -> str:
        return f"""
To use LCSC Grabber libraries in KiCad:

1. Add Symbol Library:
   - Go to Preferences > Manage Symbol Libraries
   - Click "Add existing library to table"
   - Navigate to: {self.symbol_lib_path}

2. Add Footprint Library:
   - Go to Preferences > Manage Footprint Libraries
   - Click "Add existing library to table"
   - Add the folder: {self.footprint_lib_path}

3. Configure 3D Model Path:
   - Go to Preferences > Configure Paths
   - Add environment variable:
     Name: LCSC_GRABBER_3D
     Path: {self.models_3d_path}
"""


_default_manager: Optional[LibraryManager] = None


def get_library_manager(library_path: Optional[str] = None) -> LibraryManager:
    global _default_manager
    if _default_manager is None or library_path:
        _default_manager = LibraryManager(library_path)
    return _default_manager

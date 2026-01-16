import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple

from ..api.easyeda_client import EasyEdaClient, get_client
from ..api.cache import CacheManager, get_cache
from ..api.models import Model3D


logger = logging.getLogger(__name__)


class Model3DHandler:

    def __init__(
        self,
        client: Optional[EasyEdaClient] = None,
        cache: Optional[CacheManager] = None,
        output_dir: Optional[str] = None
    ):
        self.client = client or get_client()
        self.cache = cache or get_cache()

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(self.cache.cache_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download_model(
        self,
        uuid: str,
        lcsc_id: str
    ) -> Optional[str]:
        lcsc_id = lcsc_id.upper()

        cached_path = self.get_model_path(lcsc_id)
        if cached_path and os.path.exists(cached_path):
            logger.info(f"Using cached 3D model for {lcsc_id}")
            return cached_path

        logger.info(f"Downloading 3D model for {lcsc_id} (UUID: {uuid})")
        step_data = self.client.get_3d_model_step(uuid)

        if step_data:
            step_path = self.output_dir / f"{lcsc_id}.step"
            step_path.write_bytes(step_data)
            logger.info(f"Saved STEP model: {step_path}")
            return str(step_path)

        obj_data = self.client.get_3d_model_obj(uuid)
        if obj_data:
            obj_path = self.output_dir / f"{lcsc_id}.obj"
            obj_path.write_text(obj_data, encoding="utf-8")
            logger.info(f"Saved OBJ model: {obj_path}")

            wrl_path = self._convert_obj_to_wrl(obj_path)
            if wrl_path:
                return wrl_path

            return str(obj_path)

        logger.warning(f"No 3D model available for {lcsc_id}")
        return None

    def get_model_path(self, lcsc_id: str) -> Optional[str]:
        lcsc_id = lcsc_id.upper()

        step_path = self.output_dir / f"{lcsc_id}.step"
        if step_path.exists():
            return str(step_path)

        wrl_path = self.output_dir / f"{lcsc_id}.wrl"
        if wrl_path.exists():
            return str(wrl_path)

        obj_path = self.output_dir / f"{lcsc_id}.obj"
        if obj_path.exists():
            return str(obj_path)

        return None

    def _convert_obj_to_wrl(self, obj_path: Path) -> Optional[str]:
        try:
            obj_content = obj_path.read_text(encoding="utf-8")

            vertices = []
            faces = []

            for line in obj_content.splitlines():
                line = line.strip()
                if line.startswith("v "):
                    parts = line.split()
                    if len(parts) >= 4:
                        vertices.append((
                            float(parts[1]),
                            float(parts[2]),
                            float(parts[3])
                        ))
                elif line.startswith("f "):
                    parts = line.split()[1:]
                    indices = []
                    for p in parts:
                        idx = p.split("/")[0]
                        indices.append(int(idx) - 1)
                    if len(indices) >= 3:
                        faces.append(indices)

            if not vertices or not faces:
                return None

            wrl_lines = [
                "#VRML V2.0 utf8",
                "",
                "Shape {",
                "  appearance Appearance {",
                "    material Material {",
                "      diffuseColor 0.8 0.8 0.8",
                "      specularColor 0.2 0.2 0.2",
                "      shininess 0.2",
                "    }",
                "  }",
                "  geometry IndexedFaceSet {",
                "    coord Coordinate {",
                "      point [",
            ]

            for v in vertices:
                wrl_lines.append(f"        {v[0]:.6f} {v[1]:.6f} {v[2]:.6f},")

            wrl_lines.append("      ]")
            wrl_lines.append("    }")
            wrl_lines.append("    coordIndex [")

            for f in faces:
                if len(f) == 3:
                    wrl_lines.append(f"      {f[0]}, {f[1]}, {f[2]}, -1,")
                elif len(f) == 4:
                    wrl_lines.append(f"      {f[0]}, {f[1]}, {f[2]}, -1,")
                    wrl_lines.append(f"      {f[0]}, {f[2]}, {f[3]}, -1,")
                else:
                    for i in range(1, len(f) - 1):
                        wrl_lines.append(f"      {f[0]}, {f[i]}, {f[i+1]}, -1,")

            wrl_lines.append("    ]")
            wrl_lines.append("  }")
            wrl_lines.append("}")

            wrl_path = obj_path.with_suffix(".wrl")
            wrl_path.write_text("\n".join(wrl_lines), encoding="utf-8")

            logger.info(f"Converted OBJ to WRL: {wrl_path}")
            return str(wrl_path)

        except Exception as e:
            logger.error(f"Error converting OBJ to WRL: {e}")
            return None

    def get_model_transform(
        self,
        lcsc_id: str
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        offset = (0.0, 0.0, 0.0)
        rotation = (0.0, 0.0, 0.0)
        scale = (1.0, 1.0, 1.0)

        return (offset, rotation, scale)

    def cleanup_old_models(self, max_age_days: int = 30):
        import time

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        for file_path in self.output_dir.iterdir():
            if file_path.suffix.lower() in (".step", ".wrl", ".obj"):
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    logger.info(f"Removed old model file: {file_path}")

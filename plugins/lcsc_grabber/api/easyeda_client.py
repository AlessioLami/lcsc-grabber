import json
import time
import logging
from typing import Optional, Dict, Any, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

from .models import ComponentInfo, Model3D


logger = logging.getLogger(__name__)


class EasyEdaApiError(Exception):
    pass


class EasyEdaClient:

    COMPONENT_API_URL = "https://easyeda.com/api/products/{lcsc_id}/components?version=6.4.19.5"
    MODEL_3D_OBJ_URL = "https://modules.easyeda.com/3dmodel/{uuid}"
    MODEL_3D_STEP_URL = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}"

    MIN_REQUEST_INTERVAL = 0.6

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._last_request_time = 0.0
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://easyeda.com",
            "Referer": "https://easyeda.com/",
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _make_request(
        self,
        url: str,
        binary: bool = False
    ) -> Tuple[bool, Any]:
        self._rate_limit()

        try:
            request = Request(url, headers=self._headers)
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()

                if response.info().get('Content-Encoding') == 'gzip':
                    import gzip
                    data = gzip.decompress(data)

                if binary:
                    return (True, data)
                else:
                    return (True, data.decode('utf-8'))

        except HTTPError as e:
            logger.error(f"HTTP error {e.code} for {url}: {e.reason}")
            return (False, f"HTTP error {e.code}: {e.reason}")

        except URLError as e:
            logger.error(f"URL error for {url}: {e.reason}")
            return (False, f"Network error: {e.reason}")

        except TimeoutError:
            logger.error(f"Timeout for {url}")
            return (False, "Request timed out")

        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            return (False, str(e))

    def _normalize_lcsc_id(self, lcsc_id: str) -> str:
        lcsc_id = lcsc_id.strip().upper()

        if lcsc_id.startswith("LCSC"):
            lcsc_id = lcsc_id[4:].strip()

        if not lcsc_id.startswith("C"):
            lcsc_id = "C" + lcsc_id

        return lcsc_id

    def get_component(self, lcsc_id: str) -> Optional[ComponentInfo]:
        lcsc_id = self._normalize_lcsc_id(lcsc_id)
        url = self.COMPONENT_API_URL.format(lcsc_id=quote(lcsc_id))

        logger.info(f"Fetching component data for {lcsc_id}")

        success, data = self._make_request(url)
        if not success:
            raise EasyEdaApiError(f"Failed to fetch component {lcsc_id}: {data}")

        try:
            response = json.loads(data)
        except json.JSONDecodeError as e:
            raise EasyEdaApiError(f"Invalid JSON response for {lcsc_id}: {e}")

        if not response.get("success", False):
            error_msg = response.get("message", "Unknown error")
            logger.warning(f"API error for {lcsc_id}: {error_msg}")
            return None

        result = response.get("result")
        if not result:
            logger.warning(f"No result data for {lcsc_id}")
            return None

        return self._parse_component_response(lcsc_id, result)

    def _parse_component_response(
        self,
        lcsc_id: str,
        result: Dict[str, Any]
    ) -> ComponentInfo:
        component = ComponentInfo(lcsc_id=lcsc_id)

        component.mpn = result.get("title", "")
        component.description = result.get("description", "")
        component.datasheet_url = result.get("datasheet", "")

        attributes = result.get("attributes", {})
        component.package = attributes.get("Package", "")
        component.manufacturer = attributes.get("Manufacturer", "")

        pkg_detail = result.get("packageDetail", {})
        if pkg_detail and not component.package:
            component.package = pkg_detail.get("title", "")

        cad_data = result.get("dataStr", {})

        if isinstance(cad_data, str):
            try:
                cad_data = json.loads(cad_data)
            except json.JSONDecodeError:
                cad_data = {}

        head = cad_data.get("head", {})
        doc_type = str(head.get("docType", ""))

        if doc_type == "2":
            component.symbol_data = cad_data
            logger.debug(f"Found symbol data (docType=2) for {lcsc_id}")
        elif doc_type in ("3", "4"):
            component.footprint_data = cad_data
            logger.debug(f"Found footprint data (docType={doc_type}) for {lcsc_id}")
        else:
            shapes = cad_data.get("shape", [])
            has_pins = any(s.startswith("P~") if isinstance(s, str) else False for s in shapes)
            has_pads = any(s.startswith("PAD~") if isinstance(s, str) else False for s in shapes)

            if has_pins and not has_pads:
                component.symbol_data = cad_data
            elif has_pads:
                component.footprint_data = cad_data
            else:
                for key, value in cad_data.items():
                    if key.lower().startswith("symbol") or key.lower() == "schlib":
                        component.symbol_data = value
                    elif key.lower().startswith("footprint") or key.lower().startswith("package") or key.lower() == "pcblib":
                        component.footprint_data = value

        pkg_detail = result.get("packageDetail")
        if pkg_detail and isinstance(pkg_detail, dict) and not component.footprint_data:
            pkg_data_str = pkg_detail.get("dataStr")
            if pkg_data_str:
                if isinstance(pkg_data_str, str):
                    try:
                        pkg_data_str = json.loads(pkg_data_str)
                    except json.JSONDecodeError:
                        pkg_data_str = None

                if isinstance(pkg_data_str, dict):
                    pkg_head = pkg_data_str.get("head", {})
                    pkg_doc_type = str(pkg_head.get("docType", ""))
                    if pkg_doc_type in ("3", "4"):
                        component.footprint_data = pkg_data_str
                        logger.debug(f"Found footprint in packageDetail for {lcsc_id}")

        model_uuid = self._extract_3d_model_uuid(cad_data)
        if not model_uuid and component.footprint_data:
            model_uuid = self._extract_3d_model_uuid(component.footprint_data)
        if model_uuid:
            component.model_3d_uuid = model_uuid

        logger.info(
            f"Parsed {lcsc_id}: "
            f"symbol={'yes' if component.has_symbol() else 'no'}, "
            f"footprint={'yes' if component.has_footprint() else 'no'}, "
            f"3d={'yes' if component.has_3d_model() else 'no'}"
        )

        return component

    def _extract_3d_model_uuid(self, cad_data: Dict[str, Any]) -> Optional[str]:
        if "3d_model_uuid" in cad_data:
            return cad_data["3d_model_uuid"]

        def extract_from_shapes(shapes):
            if not isinstance(shapes, list):
                return None
            for shape in shapes:
                if isinstance(shape, str) and shape.startswith("SVGNODE~"):
                    parts = shape.split("~", 1)
                    if len(parts) > 1:
                        json_str = parts[1]
                        if json_str.startswith("{"):
                            try:
                                svg_data = json.loads(json_str)
                                if "uuid" in svg_data:
                                    return svg_data["uuid"]
                                attrs = svg_data.get("attrs", {})
                                if "uuid" in attrs:
                                    return attrs["uuid"]
                            except json.JSONDecodeError:
                                import re
                                match = re.search(r'"uuid"\s*:\s*"([a-f0-9]+)"', json_str)
                                if match:
                                    return match.group(1)
            return None

        shapes = cad_data.get("shape", [])
        uuid = extract_from_shapes(shapes)
        if uuid:
            return uuid

        for key in ["footprint", "package", "pcblib"]:
            if key in cad_data:
                pkg_data = cad_data[key]
                if isinstance(pkg_data, dict):
                    if "3DModel" in pkg_data:
                        model = pkg_data["3DModel"]
                        if isinstance(model, dict):
                            return model.get("uuid")
                        elif isinstance(model, str):
                            return model

                    uuid = extract_from_shapes(pkg_data.get("shape", []))
                    if uuid:
                        return uuid

        return None

    def get_3d_model_obj(self, uuid: str) -> Optional[str]:
        url = self.MODEL_3D_OBJ_URL.format(uuid=quote(uuid))
        logger.info(f"Fetching OBJ 3D model: {uuid}")

        success, data = self._make_request(url)
        if not success:
            logger.warning(f"Failed to fetch OBJ model {uuid}: {data}")
            return None

        return data

    def get_3d_model_step(self, uuid: str) -> Optional[bytes]:
        url = self.MODEL_3D_STEP_URL.format(uuid=quote(uuid))
        logger.info(f"Fetching STEP 3D model: {uuid}")

        success, data = self._make_request(url, binary=True)
        if not success:
            logger.warning(f"Failed to fetch STEP model {uuid}: {data}")
            return None

        return data

    def get_3d_model(self, uuid: str) -> Model3D:
        model = Model3D(uuid=uuid)

        model.step_data = self.get_3d_model_step(uuid)

        model.obj_data = self.get_3d_model_obj(uuid)

        return model


_default_client: Optional[EasyEdaClient] = None


def get_client() -> EasyEdaClient:
    global _default_client
    if _default_client is None:
        _default_client = EasyEdaClient()
    return _default_client

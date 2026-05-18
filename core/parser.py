"""
parser.py — Lee el Swagger y extrae el contrato de APIs
Soporta: archivo .yaml/.json local o URL de Swagger UI
"""

import yaml
import json
import requests
from urllib.parse import urlparse


class SwaggerParser:
    def __init__(self, source: str):
        self.source = source
        self.spec = None

    def _load_from_file(self) -> dict:
        with open(self.source, "r") as f:
            if self.source.endswith(".json"):
                return json.load(f)
            return yaml.safe_load(f)

    def _load_from_url(self) -> dict:
        url = self.source
        if not url.endswith(".json") and not url.endswith(".yaml"):
            url = url.rstrip("/") + "/swagger.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def _is_url(self) -> bool:
        parsed = urlparse(self.source)
        return parsed.scheme in ("http", "https")

    def parse(self) -> dict:
        raw = self._load_from_url() if self._is_url() else self._load_from_file()
        self.spec = raw
        return self._extract_contract(raw)

    def _extract_contract(self, spec: dict) -> dict:
        endpoints = []
        base_path = spec.get("basePath", "")
        paths = spec.get("paths", {})

        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    endpoint = {
                        "path": base_path + path,
                        "method": method.upper(),
                        "operation_id": details.get("operationId", ""),
                        "parameters": details.get("parameters", []),
                        "request_body": details.get("requestBody", {}),
                        "responses": details.get("responses", {}),
                        "required_headers": self._extract_required_headers(details),
                        "tags": details.get("tags", []),
                    }
                    endpoints.append(endpoint)

        return {
            "title": spec.get("info", {}).get("title", "API"),
            "version": spec.get("info", {}).get("version", "1.0"),
            "base_url": self._extract_base_url(spec),
            "endpoints": endpoints,
        }

    def _extract_required_headers(self, details: dict) -> list:
        headers = []
        for param in details.get("parameters", []):
            if param.get("in") == "header" and param.get("required", False):
                headers.append(param["name"])
        return headers

    def _extract_base_url(self, spec: dict) -> str:
        servers = spec.get("servers", [])
        if servers:
            return servers[0].get("url", "")
        host = spec.get("host", "")
        scheme = spec.get("schemes", ["https"])[0]
        return f"{scheme}://{host}" if host else ""

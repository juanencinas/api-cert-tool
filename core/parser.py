"""
parser.py — Lee el Swagger y extrae el contrato de APIs
Soporta: archivo .yaml/.json local o URL de Swagger UI
Maneja JSONs con descripciones mal escapadas (generados por .NET)
"""

import re
import yaml
import json
import requests
from urllib.parse import urlparse


class SwaggerParser:
    def __init__(self, source: str):
        self.source = source
        self.spec = None

    def _load_from_file(self) -> dict:
        with open(self.source, "r", encoding="utf-8") as f:
            content = f.read()
        if self.source.endswith(".json"):
            return self._safe_json_load(content)
        return yaml.safe_load(content)

    def _load_from_url(self) -> dict:
        url = self.source
        if not url.endswith(".json") and not url.endswith(".yaml"):
            url = url.rstrip("/") + "/swagger.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return self._safe_json_load(response.text)

    def _safe_json_load(self, content: str) -> dict:
        """Intenta cargar el JSON, si falla repara comillas mal escapadas"""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            fixed = self._fix_unescaped_quotes(content)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                # Fallback: extraer endpoints con regex directo
                return self._extract_via_regex(content)

    def _fix_unescaped_quotes(self, content: str) -> str:
        """Repara comillas sin escapar dentro de valores de string JSON"""
        result = []
        i = 0
        while i < len(content):
            found = False
            for field in ['"description": "', '"summary": "', '"description":"', '"summary":"']:
                if content[i:i+len(field)] == field:
                    result.append(field)
                    i += len(field)
                    value_chars = []
                    while i < len(content):
                        ch = content[i]
                        if ch == '\\' and i + 1 < len(content):
                            value_chars.append(ch)
                            value_chars.append(content[i + 1])
                            i += 2
                            continue
                        if ch == '"':
                            next_part = content[i + 1:i + 5].lstrip()
                            if next_part and next_part[0] in (',', '\n', '\r', '}', ']'):
                                result.append('"')
                                i += 1
                                break
                            else:
                                value_chars.append('\\"')
                                i += 1
                                continue
                        value_chars.append(ch)
                        i += 1
                    result.extend(value_chars)
                    found = True
                    break
            if not found:
                result.append(content[i])
                i += 1
        return ''.join(result)

    def _extract_via_regex(self, content: str) -> dict:
        """Extrae endpoints directamente con regex sin parsear JSON completo"""
        print("⚠️  JSON con formato irregular — extrayendo endpoints con regex")
        paths = {}
        pattern = r'"(/[A-Za-z0-9/_{}]+)":\s*\{\s*"(get|post|put|patch|delete)"'
        for match in re.finditer(pattern, content, re.IGNORECASE):
            path, method = match.group(1), match.group(2).lower()
            if path not in paths:
                paths[path] = {}
            # Buscar tags cercanas
            snippet = content[match.start():match.start()+500]
            tag_match = re.search(r'"tags":\s*\[\s*"([^"]+)"', snippet)
            tag = tag_match.group(1) if tag_match else "General"
            paths[path][method] = {"tags": [tag], "parameters": [], "responses": {}}

        return {
            "openapi": "3.0.1",
            "info": {"title": "Netactica API", "version": "v1"},
            "servers": [{"url": "/netcoreapi"}],
            "paths": paths,
            "components": {}
        }

    def _is_url(self) -> bool:
        parsed = urlparse(self.source)
        return parsed.scheme in ("http", "https")

    def parse(self) -> dict:
        raw = self._load_from_url() if self._is_url() else self._load_from_file()
        self.spec = raw
        return self._extract_contract(raw)

    def _extract_contract(self, spec: dict) -> dict:
        endpoints = []
        paths = spec.get("paths", {})
        servers = spec.get("servers", [])
        base_path = servers[0].get("url", "") if servers else spec.get("basePath", "")

        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    endpoints.append({
                        "path": path,
                        "method": method.upper(),
                        "operation_id": details.get("operationId", ""),
                        "parameters": details.get("parameters", []),
                        "request_body": details.get("requestBody", {}),
                        "responses": details.get("responses", {}),
                        "required_headers": self._extract_required_headers(details),
                        "tags": details.get("tags", []),
                    })

        return {
            "title": spec.get("info", {}).get("title", "API"),
            "version": spec.get("info", {}).get("version", "1.0"),
            "base_url": base_path,
            "endpoints": endpoints,
        }

    def _extract_required_headers(self, details: dict) -> list:
        return [
            p["name"] for p in details.get("parameters", [])
            if p.get("in") == "header" and p.get("required", False)
        ]

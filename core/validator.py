"""
validator.py — Compara cada request capturado vs el contrato Swagger
"""

from urllib.parse import urlparse
import re


class ContractValidator:
    def __init__(self, contract: dict):
        self.contract = contract
        self.endpoints = contract["endpoints"]

    def validate_all(self, captured_requests: list) -> list:
        results = []
        for req in captured_requests:
            result = self._validate_request(req)
            results.append(result)
        return results

    def _validate_request(self, req: dict) -> dict:
        url = req["url"]
        method = req["method"].upper()
        path = urlparse(url).path

        matched = self._match_endpoint(path, method)

        if not matched:
            return {
                "url": url,
                "method": method,
                "path": path,
                "status": "FAIL",
                "issues": [f"Endpoint {method} {path} no existe en el contrato Swagger"],
            }

        issues = []

        for required_header in matched.get("required_headers", []):
            if required_header.lower() not in {k.lower() for k in req["headers"]}:
                issues.append(f"Header requerido ausente: {required_header}")

        if method in ("POST", "PUT", "PATCH"):
            content_type = req["headers"].get("content-type", "")
            if not content_type:
                issues.append("Content-Type no enviado en request con body")

        return {
            "url": url,
            "method": method,
            "path": path,
            "matched_endpoint": matched.get("operation_id", path),
            "status": "PASS" if not issues else "FAIL",
            "issues": issues,
        }

    def _match_endpoint(self, path: str, method: str):
        for endpoint in self.endpoints:
            if endpoint["method"] != method:
                continue
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", endpoint["path"])
            if re.fullmatch(pattern, path):
                return endpoint
        return None

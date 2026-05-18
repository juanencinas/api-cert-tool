"""
Herramienta de Certificación de APIs
Punto de entrada principal
"""

import asyncio
import yaml
import json
from pathlib import Path
from core.parser import SwaggerParser
from core.navigator import SandboxNavigator
from core.validator import ContractValidator
from reports.generator import ReportGenerator


def load_config(client_config_path: str) -> dict:
    with open(client_config_path, "r") as f:
        return yaml.safe_load(f)


async def run_certification(client_config_path: str, swagger_path: str):
    print("🚀 Iniciando certificación...")

    # 1. Cargar configuración del cliente y contrato Swagger
    config = load_config(client_config_path)
    parser = SwaggerParser(swagger_path)
    contract = parser.parse()
    print(f"✅ Contrato cargado: {len(contract['endpoints'])} endpoints encontrados")

    # 2. Navegar el sandbox e interceptar requests
    navigator = SandboxNavigator(config)
    captured_requests = await navigator.run()
    print(f"✅ Requests capturados: {len(captured_requests)}")

    # 3. Validar cada request contra el contrato
    validator = ContractValidator(contract)
    results = validator.validate_all(captured_requests)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"✅ Validación completa: {passed} PASS / {failed} FAIL")

    # 4. Generar reporte
    generator = ReportGenerator(config, results, contract)
    report_path = generator.generate()
    print(f"📄 Certificado generado: {report_path}")

    return results


if __name__ == "__main__":
    import sys
    client_cfg = sys.argv[1] if len(sys.argv) > 1 else "config/cliente_001.yaml"
    swagger_cfg = sys.argv[2] if len(sys.argv) > 2 else "swagger/api_contrato.yaml"
    asyncio.run(run_certification(client_cfg, swagger_cfg))

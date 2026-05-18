"""
har_validator.py — Valida un archivo HAR contra el contrato Swagger
y el flujo obligatorio definido en el config del cliente

Uso:
    python har_validator.py config/skybooker.yaml swagger/api_contrato.json archivo.har
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Template


# ─── Flujos obligatorios por tipo de certificación ───────────────────────────

FLOWS = {
    "convergence_air": [
        {"step": 1, "name": "Session",                    "path": "/Session"},
        {"step": 2, "name": "Air Search",                 "path": "/Air/Search"},
        {"step": 3, "name": "Air Results",                "path": "/Air/Results"},
        {"step": 4, "name": "Air Validation",             "path": "/Air/Validation"},
        {"step": 5, "name": "Air Book",                   "path": "/Air/Book"},
        {"step": 6, "name": "Air Issue",                  "path": "/Air/Issue"},
        {"step": 7, "name": "Ancillary Search by Option", "path": "/Air/Ancillary/SearchByOption"},
        {"step": 8, "name": "Seatmap",                    "path": "/Air/Seatmap"},
        {"step": 9, "name": "Air Ancillary Book",         "path": "/Air/Ancillary/Book"},
    ],
    "convergence_hotel": [
        {"step": 1, "name": "Session",                    "path": "/Session"},
        {"step": 2, "name": "Hotel Search",               "path": "/Hotel/Search"},
        {"step": 3, "name": "Hotel Results",              "path": "/Hotel/Results"},
        {"step": 4, "name": "Hotel Detail",               "path": "/Hotel/Detail"},
        {"step": 5, "name": "Hotel Book",                 "path": "/Hotel/Book"},
    ],
}


# ─── Parser del HAR ───────────────────────────────────────────────────────────

def load_har(har_path: str, api_base_urls: list) -> tuple[list, set]:
    with open(har_path, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har["log"]["entries"]

    # Filtrar solo calls a tus APIs (ignorar OPTIONS/preflight)
    api_calls = [
        e for e in entries
        if any(base in e["request"]["url"] for base in api_base_urls)
        and e["request"]["method"] != "OPTIONS"
    ]

    # Endpoints únicos llamados
    called = set()
    for e in api_calls:
        url = e["request"]["url"]
        path = re.sub(r"^.*/NetCoreApi", "", urlparse(url).path, flags=re.IGNORECASE)
        if path:
            called.add(path)

    return api_calls, called


# ─── Validación contra Swagger ────────────────────────────────────────────────

def load_swagger_endpoints(swagger_path: str) -> list:
    with open(swagger_path, "r", encoding="utf-8") as f:
        content = f.read()

    endpoints = []
    pattern = r'"(/[A-Za-z0-9/_{}]+)":\s*\{\s*"(get|post|put|patch|delete)"'
    for match in re.finditer(pattern, content, re.IGNORECASE):
        path, method = match.group(1), match.group(2).upper()
        tag_match = re.search(r'"tags":\s*\[\s*"([^"]+)"', content[match.start():match.start() + 500])
        tag = tag_match.group(1) if tag_match else "General"
        endpoints.append({"path": path, "method": method, "tag": tag})

    return endpoints


def match_endpoint(path: str, method: str, endpoints: list) -> dict | None:
    for ep in endpoints:
        if ep["method"] != method:
            continue
        pattern = re.sub(r"\{[^}]+\}", "[^/]+", ep["path"])
        if re.fullmatch(pattern, path, re.IGNORECASE):
            return ep
    return None


def validate_calls(api_calls: list, swagger_endpoints: list) -> list:
    results = []
    for e in api_calls:
        req = e["request"]
        res = e["response"]
        url = req["url"]
        method = req["method"]
        path = re.sub(r"^.*/NetCoreApi", "", urlparse(url).path, flags=re.IGNORECASE) or urlparse(url).path

        matched = match_endpoint(path, method, swagger_endpoints)
        issues = []

        if not matched:
            issues.append("Endpoint no existe en el contrato Swagger")
            status = "FAIL"
        else:
            if res["status"] >= 400:
                issues.append(f"Respuesta con error HTTP {res['status']}")
            headers = {h["name"].lower(): h["value"] for h in req["headers"]}
            if method == "POST" and "content-type" not in headers:
                issues.append("Content-Type ausente en POST")
            status = "FAIL" if issues else "PASS"

        results.append({
            "method": method,
            "path": path,
            "tag": matched["tag"] if matched else "—",
            "http_status": res["status"],
            "status": status,
            "issues": issues,
        })

    return results


# ─── Validación del flujo obligatorio ────────────────────────────────────────

def validate_flow(called: set, flow_name: str) -> list:
    flow = FLOWS.get(flow_name, [])
    results = []
    for step in flow:
        found = any(step["path"].lower() in c.lower() for c in called)
        # Caso especial: seatmap con path dinámico
        if not found and "seatmap" in step["path"].lower():
            found = any("seatmap" in c.lower() for c in called)
            status = "WARN" if found else "FAIL"
            called_as = next((c for c in called if "seatmap" in c.lower()), "No llamado")
        else:
            status = "PASS" if found else "FAIL"
            called_as = step["path"] if found else "No llamado"

        results.append({
            **step,
            "status": status,
            "called_as": called_as,
        })

    return results


# ─── Generador de reporte ─────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Certificado — {{ client_name }}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',sans-serif;background:#f0f4f8;color:#1a1a2e}
  .header{background:linear-gradient(135deg,#0f3460,#1a5276);color:white;padding:40px}
  .header h1{font-size:24px;margin-bottom:6px}
  .header p{opacity:.8;font-size:13px}
  .container{max-width:960px;margin:30px auto;padding:0 20px}
  .banner{padding:24px;border-radius:10px;text-align:center;margin-bottom:20px;color:white;background:{{ banner_color }}}
  .banner h2{font-size:20px;margin-bottom:6px}
  .card{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
  .card h2{color:#0f3460;font-size:15px;margin-bottom:16px;border-bottom:2px solid #e94560;padding-bottom:8px}
  .summary{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
  .stat{text-align:center;padding:20px;border-radius:10px}
  .stat .num{font-size:32px;font-weight:700}
  .stat .label{font-size:12px;margin-top:4px;opacity:.7}
  .s-total{background:#eaf4fb;color:#1a5276}
  .s-pass{background:#eafaf1;color:#1e8449}
  .s-warn{background:#fef9e7;color:#b7950b}
  .s-fail{background:#fdedec;color:#c0392b}
  .info-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .info-item{font-size:13px}
  .info-item strong{color:#0f3460;display:block;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{background:#0f3460;color:white;padding:10px 12px;text-align:left}
  td{padding:10px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
  .progress-bar{background:#f0f0f0;border-radius:10px;height:14px;margin-top:16px;overflow:hidden}
  .progress-fill{background:linear-gradient(90deg,#27ae60,#f39c12);height:14px;border-radius:10px}
  code{background:#f0f0f0;padding:2px 6px;border-radius:4px;font-size:11px}
  .actions li{margin-bottom:8px;font-size:13px;padding:8px 12px;background:#fff8f0;border-left:3px solid #e67e22;border-radius:0 6px 6px 0;list-style:none}
  .footer{text-align:center;padding:24px;color:#999;font-size:12px}
</style>
</head>
<body>
<div class="header">
  <h1>🔐 Certificado de Integración — {{ flow_label }}</h1>
  <p>Herramienta de Certificación Automática — Netactica</p>
</div>
<div class="container">
  <div class="banner">
    <h2>{{ banner_title }}</h2>
    <p>{{ banner_desc }}</p>
  </div>
  <div class="card">
    <h2>Información del cliente</h2>
    <div class="info-grid">
      <div class="info-item"><strong>Cliente</strong>{{ client_name }}</div>
      <div class="info-item"><strong>Sandbox</strong>{{ sandbox_url }}</div>
      <div class="info-item"><strong>API certificada</strong>Netactica.Net.Core.Api v1</div>
      <div class="info-item"><strong>Flujo evaluado</strong>{{ flow_label }}</div>
      <div class="info-item"><strong>Fecha de evaluación</strong>{{ date }}</div>
      <div class="info-item"><strong>Total calls capturados</strong>{{ total_calls }}</div>
    </div>
  </div>
  <div class="card">
    <h2>Resumen</h2>
    <div class="summary">
      <div class="stat s-total"><div class="num">{{ total_steps }}</div><div class="label">Pasos requeridos</div></div>
      <div class="stat s-pass"><div class="num">{{ passed }}</div><div class="label">✅ Correctos</div></div>
      <div class="stat s-warn"><div class="num">{{ warnings }}</div><div class="label">⚠️ Observaciones</div></div>
      <div class="stat s-fail"><div class="num">{{ failed }}</div><div class="label">❌ Faltantes</div></div>
    </div>
    <div class="progress-bar">
      <div class="progress-fill" style="width:{{ coverage }}%"></div>
    </div>
    <p style="font-size:12px;color:#999;margin-top:6px;text-align:right">{{ coverage }}% completado — {{ passed + warnings }}/{{ total_steps }} pasos</p>
  </div>
  <div class="card">
    <h2>Detalle del flujo obligatorio</h2>
    <table>
      <tr><th>#</th><th>Paso</th><th>Endpoint contrato</th><th>Estado</th><th>Observación</th></tr>
      {% for r in flow_results %}
      <tr style="{{ 'background:#fffef0;' if r.status=='WARN' else ('background:#fffaf9;' if r.status=='FAIL' else '') }}">
        <td style="text-align:center;color:#999">{{ r.step }}</td>
        <td><strong>{{ r.name }}</strong></td>
        <td style="font-family:monospace;font-size:12px;color:#0f3460">{{ r.path }}</td>
        <td>
          {% if r.status == 'PASS' %}<span style="background:#eafaf1;color:#1e8449;padding:3px 12px;border-radius:10px;font-weight:bold;font-size:12px">✅ PASS</span>
          {% elif r.status == 'WARN' %}<span style="background:#fef9e7;color:#b7950b;padding:3px 12px;border-radius:10px;font-weight:bold;font-size:12px">⚠️ REVISAR</span>
          {% else %}<span style="background:#fdedec;color:#c0392b;padding:3px 12px;border-radius:10px;font-weight:bold;font-size:12px">❌ FALTANTE</span>{% endif %}
        </td>
        <td style="font-size:12px;color:#666">
          {% if r.status == 'PASS' %}—
          {% elif r.status == 'WARN' %}Llamado como <code>{{ r.called_as }}</code> — verificar si coincide con el contrato
          {% else %}Endpoint no fue llamado en el flujo certificado{% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% if actions %}
  <div class="card" style="border-left:4px solid #e67e22">
    <h2>⚠️ Acciones requeridas</h2>
    <ul class="actions" style="margin-top:8px">
      {% for a in actions %}<li>{{ a }}</li>{% endfor %}
    </ul>
  </div>
  {% endif %}
</div>
<div class="footer">
  Generado automáticamente · Herramienta de Certificación de APIs · Netactica · {{ date }}
</div>
</body>
</html>"""


def generate_report(config, flow_results, call_results, flow_name):
    passed   = sum(1 for r in flow_results if r["status"] == "PASS")
    warnings = sum(1 for r in flow_results if r["status"] == "WARN")
    failed   = sum(1 for r in flow_results if r["status"] == "FAIL")
    total    = len(flow_results)
    coverage = round((passed + warnings) / total * 100) if total else 0

    if failed == 0 and warnings == 0:
        banner_color = "#27ae60"
        banner_title = "✅ INTEGRACIÓN CERTIFICADA"
        banner_desc  = "Todos los pasos del flujo obligatorio fueron implementados correctamente."
    elif failed == 0:
        banner_color = "#e67e22"
        banner_title = "⚠️ CERTIFICACIÓN PENDIENTE — Revisión requerida"
        banner_desc  = f"Se encontraron {warnings} observación(es). Verificar antes de certificar."
    else:
        banner_color = "#c0392b"
        banner_title = "⚠️ CERTIFICACIÓN PENDIENTE"
        banner_desc  = f"Faltan {failed} endpoint(s) y hay {warnings} observación(es)."

    actions = []
    for r in flow_results:
        if r["status"] == "WARN":
            actions.append(f"<strong>Paso {r['step']} — {r['name']}:</strong> Llamado como <code>{r['called_as']}</code> pero el contrato define <code>{r['path']}</code>. Verificar implementación.")
        elif r["status"] == "FAIL":
            actions.append(f"<strong>Paso {r['step']} — {r['name']}:</strong> Endpoint <code>{r['path']}</code> no fue llamado. El cliente debe implementar este paso.")

    flow_labels = {
        "convergence_air":   "Convergence — APIs Aéreos",
        "convergence_hotel": "Convergence — APIs Hotel",
    }

    html = Template(TEMPLATE).render(
        client_name=config.get("client_name", "Cliente"),
        sandbox_url=config.get("login", {}).get("url", ""),
        flow_label=flow_labels.get(flow_name, flow_name),
        date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        total_calls=len(call_results),
        total_steps=total,
        passed=passed,
        warnings=warnings,
        failed=failed,
        coverage=coverage,
        banner_color=banner_color,
        banner_title=banner_title,
        banner_desc=banner_desc,
        flow_results=flow_results,
        actions=actions,
    )

    output_dir = Path("reports/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = config.get("client_name", "cliente").replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = output_dir / f"certificado_{client}_{timestamp}.html"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(path)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import yaml

    if len(sys.argv) < 4:
        print("Uso: python har_validator.py <config.yaml> <swagger.json> <archivo.har> [flow_name]")
        print("Flows disponibles:", ", ".join(FLOWS.keys()))
        sys.exit(1)

    config_path  = sys.argv[1]
    swagger_path = sys.argv[2]
    har_path     = sys.argv[3]
    flow_name    = sys.argv[4] if len(sys.argv) > 4 else "convergence_air"

    print("🚀 Iniciando validación HAR...")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    api_base_urls = config.get("api_base_urls", [])

    # 1. Cargar y filtrar HAR
    api_calls, called = load_har(har_path, api_base_urls)
    print(f"✅ HAR cargado: {len(api_calls)} calls a tus APIs")
    print(f"✅ Endpoints únicos llamados: {len(called)}")

    # 2. Validar contra Swagger
    swagger_endpoints = load_swagger_endpoints(swagger_path)
    call_results = validate_calls(api_calls, swagger_endpoints)
    contract_pass = sum(1 for r in call_results if r["status"] == "PASS")
    contract_fail = sum(1 for r in call_results if r["status"] == "FAIL")
    print(f"✅ Validación contrato: {contract_pass} PASS / {contract_fail} FAIL")

    # 3. Validar flujo obligatorio
    flow_results = validate_flow(called, flow_name)
    flow_pass    = sum(1 for r in flow_results if r["status"] == "PASS")
    flow_warn    = sum(1 for r in flow_results if r["status"] == "WARN")
    flow_fail    = sum(1 for r in flow_results if r["status"] == "FAIL")
    coverage     = round((flow_pass + flow_warn) / len(flow_results) * 100)
    print(f"✅ Flujo obligatorio: {flow_pass} PASS / {flow_warn} WARN / {flow_fail} FAIL — {coverage}%")

    # 4. Generar reporte
    report_path = generate_report(config, flow_results, call_results, flow_name)
    print(f"📄 Certificado generado: {report_path}")
    print(f"   Abre con: open {report_path}")


if __name__ == "__main__":
    main()

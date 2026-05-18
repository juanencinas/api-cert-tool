"""
har_validator.py — Valida un archivo HAR contra el contrato Swagger
y el flujo obligatorio definido en el config del cliente

Uso:
    python har_validator.py config/skybooker.yaml swagger/api_contrato.json hars/skybooker.har
    python har_validator.py config/skybooker.yaml swagger/api_contrato.json hars/skybooker.har convergence_hotel
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Template


# ─── Flujos obligatorios ──────────────────────────────────────────────────────

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
        {"step": 1, "name": "Session",       "path": "/Session"},
        {"step": 2, "name": "Hotel Search",  "path": "/Hotel/Search"},
        {"step": 3, "name": "Hotel Results", "path": "/Hotel/Results"},
        {"step": 4, "name": "Hotel Detail",  "path": "/Hotel/Detail"},
        {"step": 5, "name": "Hotel Book",    "path": "/Hotel/Book"},
    ],
}

FLOW_LABELS = {
    "convergence_air":   "Convergence — APIs Aéreos",
    "convergence_hotel": "Convergence — APIs Hotel",
}


# ─── HAR ─────────────────────────────────────────────────────────────────────

def load_har(har_path: str, api_base_urls: list) -> tuple:
    with open(har_path, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har["log"]["entries"]
    api_calls = [
        e for e in entries
        if any(base in e["request"]["url"] for base in api_base_urls)
        and e["request"]["method"] != "OPTIONS"
    ]

    called = set()
    for e in api_calls:
        path = re.sub(r"^.*/NetCoreApi", "", urlparse(e["request"]["url"]).path, flags=re.IGNORECASE)
        if path:
            called.add(path)

    return api_calls, called


# ─── Swagger ──────────────────────────────────────────────────────────────────

def load_swagger_endpoints(swagger_path: str) -> list:
    with open(swagger_path, "r", encoding="utf-8") as f:
        content = f.read()

    endpoints = []
    pattern = r'"(/[A-Za-z0-9/_{}]+)":\s*\{\s*"(get|post|put|patch|delete)"'
    for match in re.finditer(pattern, content, re.IGNORECASE):
        path, method = match.group(1), match.group(2).upper()
        tag_match = re.search(r'"tags":\s*\[\s*"([^"]+)"', content[match.start():match.start() + 500])
        endpoints.append({
            "path": path,
            "method": method,
            "tag": tag_match.group(1) if tag_match else "General"
        })
    return endpoints


def match_endpoint(path: str, method: str, endpoints: list):
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
        req, res = e["request"], e["response"]
        method = req["method"]
        path = re.sub(r"^.*/NetCoreApi", "", urlparse(req["url"]).path, flags=re.IGNORECASE) or urlparse(req["url"]).path
        matched = match_endpoint(path, method, swagger_endpoints)
        issues = []

        if not matched:
            issues.append("Endpoint no existe en el contrato Swagger")
        else:
            if res["status"] >= 400:
                issues.append(f"HTTP {res['status']}")
            headers = {h["name"].lower(): h["value"] for h in req["headers"]}
            if method == "POST" and "content-type" not in headers:
                issues.append("Content-Type ausente")

        results.append({
            "method": method,
            "path": path,
            "tag": matched["tag"] if matched else "—",
            "http_status": res["status"],
            "status": "FAIL" if issues else "PASS",
            "issues": issues,
        })
    return results


# ─── Flujo obligatorio ────────────────────────────────────────────────────────

def validate_flow(called: set, flow_name: str) -> list:
    results = []
    for step in FLOWS.get(flow_name, []):
        found = any(step["path"].lower() in c.lower() for c in called)
        if not found and "seatmap" in step["path"].lower():
            found = any("seatmap" in c.lower() for c in called)
            status = "WARN" if found else "FAIL"
            called_as = next((c for c in called if "seatmap" in c.lower()), "No llamado")
        else:
            status = "PASS" if found else "FAIL"
            called_as = step["path"] if found else "No llamado"
        results.append({**step, "status": status, "called_as": called_as})
    return results


# ─── Template HTML paleta Netactica ──────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Certificado — {{ client_name }} · Netactica</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  :root {
    --yellow:    #F5C518;
    --yellow-lt: #FFFBEE;
    --yellow-md: #EDD96A;
    --gray-dk:   #636363;
    --gray-xdk:  #2e2e2e;
    --black:     #1a1a1a;
    --white:     #ffffff;
    --border:    #e8e8e8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', sans-serif; background: #f7f7f5; color: var(--black); }

  .header { background: var(--gray-xdk); border-bottom: 4px solid var(--yellow); }
  .header-inner { max-width: 960px; margin: 0 auto; padding: 32px 40px; display: flex; align-items: center; justify-content: space-between; }
  .logo h1 { font-size: 22px; font-weight: 800; color: var(--white); }
  .logo h1 span { color: var(--yellow); }
  .logo p { color: #aaa; font-size: 12px; margin-top: 3px; }
  .header-badge { background: var(--yellow); color: var(--black); font-weight: 700; font-size: 11px; padding: 8px 18px; border-radius: 20px; letter-spacing: .3px; }

  .container { max-width: 960px; margin: 28px auto; padding: 0 24px; }

  .banner { background: var(--gray-xdk); border-left: 6px solid {{ banner_color }}; border-radius: 10px; padding: 22px 28px; margin-bottom: 22px; display: flex; align-items: center; gap: 18px; }
  .banner-icon { font-size: 32px; flex-shrink: 0; }
  .banner h2 { color: var(--white); font-size: 17px; font-weight: 700; margin-bottom: 4px; }
  .banner p { color: #bbb; font-size: 13px; }

  .card { background: var(--white); border-radius: 12px; padding: 22px 26px; margin-bottom: 18px; border: 1px solid var(--border); }
  .card-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .8px; color: var(--gray-dk); margin-bottom: 16px; padding-bottom: 10px; border-bottom: 2px solid var(--yellow); display: flex; align-items: center; gap: 8px; }
  .card-title::before { content: ''; display: inline-block; width: 4px; height: 14px; background: var(--yellow); border-radius: 2px; }

  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .info-item label { display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px; color: var(--gray-dk); margin-bottom: 2px; }
  .info-item span { font-size: 13px; font-weight: 500; }

  .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 18px; }
  .stat { background: var(--gray-xdk); border-radius: 10px; padding: 18px; text-align: center; border-bottom: 3px solid transparent; }
  .stat.total { border-color: var(--yellow); }
  .stat.s-pass { border-color: #4CAF50; }
  .stat.s-warn { border-color: #FF9800; }
  .stat.s-fail { border-color: #f44336; }
  .stat .num { font-size: 34px; font-weight: 800; color: var(--white); line-height: 1; }
  .stat .lbl { font-size: 10px; color: #aaa; margin-top: 5px; text-transform: uppercase; letter-spacing: .5px; }
  .stat.total .num { color: var(--yellow); }
  .stat.s-pass .num { color: #81C784; }
  .stat.s-warn .num { color: #FFB74D; }
  .stat.s-fail .num { color: #e57373; }

  .progress-bar { background: #eee; border-radius: 8px; height: 10px; overflow: hidden; }
  .progress-fill { height: 10px; border-radius: 8px; background: linear-gradient(90deg, var(--yellow), var(--yellow-md)); }
  .progress-label { display: flex; justify-content: space-between; font-size: 11px; color: var(--gray-dk); margin-top: 6px; }

  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  thead tr { background: var(--gray-xdk); }
  thead th { padding: 11px 14px; text-align: left; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; color: var(--yellow); }
  tbody tr { border-bottom: 1px solid #f0f0f0; }
  tbody tr:hover td { background: #fafafa; }
  tbody td { padding: 10px 14px; vertical-align: middle; }
  .row-warn td { background: var(--yellow-lt) !important; }
  .row-fail td { background: #fff5f5 !important; }
  .num-col { text-align: center; color: var(--gray-dk); font-weight: 600; width: 40px; }
  .mono { font-family: 'Courier New', monospace; font-size: 12px; color: var(--gray-xdk); }
  .obs { font-size: 12px; color: var(--gray-dk); }
  code { background: var(--yellow-lt); border: 1px solid var(--yellow-md); padding: 1px 6px; border-radius: 4px; font-size: 11px; font-family: 'Courier New', monospace; }

  .badge { padding: 3px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; white-space: nowrap; }
  .badge.pass { background: #E8F5E9; color: #2E7D32; }
  .badge.warn { background: var(--yellow-lt); color: #8B6914; border: 1px solid var(--yellow-md); }
  .badge.fail { background: #FFEBEE; color: #C62828; }

  .actions-list { list-style: none; display: flex; flex-direction: column; gap: 10px; }
  .actions-list li { background: var(--yellow-lt); border-left: 4px solid var(--yellow); padding: 12px 16px; border-radius: 0 8px 8px 0; font-size: 13px; line-height: 1.5; }

  .footer { background: var(--gray-dk); color: #ccc; text-align: center; padding: 18px; font-size: 12px; margin-top: 28px; border-top: 3px solid var(--yellow); }
  .footer strong { color: var(--yellow); }
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div class="logo">
      <h1>neta<span>ctica</span></h1>
      <p>Plataforma de Certificación de Integraciones API</p>
    </div>
    <div class="header-badge">🔐 CERTIFICACIÓN {{ flow_label | upper }}</div>
  </div>
</div>

<div class="container">

  <div class="banner">
    <div class="banner-icon">{{ banner_icon }}</div>
    <div>
      <h2>{{ banner_title }}</h2>
      <p>{{ banner_desc }}</p>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Información del cliente</div>
    <div class="info-grid">
      <div class="info-item"><label>Cliente</label><span>{{ client_name }}</span></div>
      <div class="info-item"><label>Sandbox</label><span>{{ sandbox_url }}</span></div>
      <div class="info-item"><label>API Certificada</label><span>Netactica.Net.Core.Api v1</span></div>
      <div class="info-item"><label>API Base URL</label><span>{{ api_base }}</span></div>
      <div class="info-item"><label>Flujo Evaluado</label><span>{{ flow_label }}</span></div>
      <div class="info-item"><label>Fecha de Evaluación</label><span>{{ date }}</span></div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Resumen</div>
    <div class="stats">
      <div class="stat total"><div class="num">{{ total_steps }}</div><div class="lbl">Requeridos</div></div>
      <div class="stat s-pass"><div class="num">{{ passed }}</div><div class="lbl">Correctos</div></div>
      <div class="stat s-warn"><div class="num">{{ warnings }}</div><div class="lbl">Observaciones</div></div>
      <div class="stat s-fail"><div class="num">{{ failed }}</div><div class="lbl">Faltantes</div></div>
    </div>
    <div class="progress-bar"><div class="progress-fill" style="width:{{ coverage }}%"></div></div>
    <div class="progress-label">
      <span>Cobertura del flujo obligatorio</span>
      <span><strong>{{ coverage }}%</strong> — {{ passed + warnings }}/{{ total_steps }} pasos</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Detalle del flujo obligatorio</div>
    <table>
      <thead><tr><th>#</th><th>Paso</th><th>Endpoint contrato</th><th>Estado</th><th>Observación</th></tr></thead>
      <tbody>
        {% for r in flow_results %}
        <tr class="{{ 'row-warn' if r.status=='WARN' else ('row-fail' if r.status=='FAIL' else '') }}">
          <td class="num-col">{{ r.step }}</td>
          <td><strong>{{ r.name }}</strong></td>
          <td class="mono">{{ r.path }}</td>
          <td>
            {% if r.status == 'PASS' %}<span class="badge pass">✅ PASS</span>
            {% elif r.status == 'WARN' %}<span class="badge warn">⚠️ REVISAR</span>
            {% else %}<span class="badge fail">❌ FALTANTE</span>{% endif %}
          </td>
          <td class="obs">
            {% if r.status == 'PASS' %}—
            {% elif r.status == 'WARN' %}Llamado como <code>{{ r.called_as }}</code> — verificar path vs contrato
            {% else %}Endpoint no fue llamado en el flujo certificado{% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  {% if actions %}
  <div class="card">
    <div class="card-title">Acciones requeridas</div>
    <ul class="actions-list">
      {% for a in actions %}<li>{{ a | safe }}</li>{% endfor %}
    </ul>
  </div>
  {% endif %}

</div>

<div class="footer">
  Generado automáticamente por la <strong>Herramienta de Certificación de APIs · Netactica</strong> · {{ date }}
</div>
</body>
</html>"""


# ─── Reporte ──────────────────────────────────────────────────────────────────

def generate_report(config: dict, flow_results: list, call_results: list, flow_name: str) -> str:
    passed   = sum(1 for r in flow_results if r["status"] == "PASS")
    warnings = sum(1 for r in flow_results if r["status"] == "WARN")
    failed   = sum(1 for r in flow_results if r["status"] == "FAIL")
    total    = len(flow_results)
    coverage = round((passed + warnings) / total * 100) if total else 0

    if failed == 0 and warnings == 0:
        banner_color = "#F5C518"
        banner_icon  = "✅"
        banner_title = "INTEGRACIÓN CERTIFICADA"
        banner_desc  = "Todos los pasos del flujo obligatorio fueron implementados correctamente."
    elif failed == 0:
        banner_color = "#FF9800"
        banner_icon  = "⚠️"
        banner_title = "Certificación Pendiente — Revisión Requerida"
        banner_desc  = f"Se encontraron {warnings} observación(es). Verificar antes de emitir el certificado final."
    else:
        banner_color = "#f44336"
        banner_icon  = "⚠️"
        banner_title = "Certificación Pendiente"
        banner_desc  = f"Faltan {failed} endpoint(s) y hay {warnings} observación(es). El cliente debe completar su implementación."

    actions = []
    for r in flow_results:
        if r["status"] == "WARN":
            actions.append(f'<strong>Paso {r["step"]} — {r["name"]}:</strong> Llamado como <code>{r["called_as"]}</code> pero el contrato define <code>{r["path"]}</code>. Verificar implementación.')
        elif r["status"] == "FAIL":
            actions.append(f'<strong>Paso {r["step"]} — {r["name"]}:</strong> Endpoint <code>{r["path"]}</code> no fue llamado. El cliente debe implementar este paso.')

    html = Template(TEMPLATE).render(
        client_name  = config.get("client_name", "Cliente"),
        sandbox_url  = config.get("login", {}).get("url", ""),
        api_base     = f"https://{config.get('api_base_urls', [''])[0]}/NetCoreApi",
        flow_label   = FLOW_LABELS.get(flow_name, flow_name),
        date         = datetime.now().strftime("%d/%m/%Y %H:%M"),
        total_steps  = total,
        passed       = passed,
        warnings     = warnings,
        failed       = failed,
        coverage     = coverage,
        banner_color = banner_color,
        banner_icon  = banner_icon,
        banner_title = banner_title,
        banner_desc  = banner_desc,
        flow_results = flow_results,
        actions      = actions,
    )

    output_dir = Path("reports/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    client    = config.get("client_name", "cliente").replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    path      = output_dir / f"certificado_{client}_{timestamp}.html"

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(path)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import yaml

    if len(sys.argv) < 4:
        print("Uso: python har_validator.py <config.yaml> <swagger.json> <archivo.har> [flow]")
        print("Flows:", ", ".join(FLOWS.keys()))
        sys.exit(1)

    config_path  = sys.argv[1]
    swagger_path = sys.argv[2]
    har_path     = sys.argv[3]
    flow_name    = sys.argv[4] if len(sys.argv) > 4 else "convergence_air"

    print("🚀 Iniciando certificación HAR...")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    api_base_urls = config.get("api_base_urls", [])

    api_calls, called = load_har(har_path, api_base_urls)
    print(f"✅ HAR cargado: {len(api_calls)} calls | {len(called)} endpoints únicos")

    swagger_endpoints = load_swagger_endpoints(swagger_path)
    call_results      = validate_calls(api_calls, swagger_endpoints)
    print(f"✅ Contrato: {sum(1 for r in call_results if r['status']=='PASS')} PASS / {sum(1 for r in call_results if r['status']=='FAIL')} FAIL")

    flow_results = validate_flow(called, flow_name)
    passed   = sum(1 for r in flow_results if r["status"] == "PASS")
    warnings = sum(1 for r in flow_results if r["status"] == "WARN")
    failed   = sum(1 for r in flow_results if r["status"] == "FAIL")
    coverage = round((passed + warnings) / len(flow_results) * 100)
    print(f"✅ Flujo {flow_name}: {passed} PASS / {warnings} WARN / {failed} FAIL — {coverage}%")

    report_path = generate_report(config, flow_results, call_results, flow_name)
    print(f"📄 Certificado: {report_path}")
    print(f"   Abre con: open {report_path}")


if __name__ == "__main__":
    main()

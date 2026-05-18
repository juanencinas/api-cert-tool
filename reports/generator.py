"""
generator.py — Genera el certificado formal en HTML y PDF
"""

from datetime import datetime
from pathlib import Path
from jinja2 import Template

TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: 'Segoe UI', sans-serif; margin: 40px; color: #1a1a2e; }
  h1 { color: #0f3460; border-bottom: 3px solid #e94560; padding-bottom: 10px; }
  h2 { color: #0f3460; margin-top: 30px; }
  .summary { display: flex; gap: 20px; margin: 20px 0; }
  .badge { padding: 16px 28px; border-radius: 8px; text-align: center; }
  .pass { background: #d4edda; color: #155724; }
  .fail { background: #f8d7da; color: #721c24; }
  .total { background: #d1ecf1; color: #0c5460; }
  table { width: 100%; border-collapse: collapse; margin-top: 20px; }
  th { background: #0f3460; color: white; padding: 10px; text-align: left; }
  td { padding: 9px 10px; border-bottom: 1px solid #eee; font-size: 13px; }
  .PASS { color: #155724; font-weight: bold; }
  .FAIL { color: #721c24; font-weight: bold; }
  .issues { color: #856404; font-size: 12px; }
  .footer { margin-top: 40px; font-size: 12px; color: #666; border-top: 1px solid #eee; padding-top: 16px; }
  .certified { background: #0f3460; color: white; padding: 20px; border-radius: 8px; text-align: center; margin: 30px 0; }
</style>
</head>
<body>
  <h1>🔐 Certificado de Integración API</h1>
  <p><strong>Cliente:</strong> {{ client_name }}</p>
  <p><strong>API certificada:</strong> {{ api_title }} v{{ api_version }}</p>
  <p><strong>Fecha:</strong> {{ date }}</p>
  <p><strong>Sandbox:</strong> {{ sandbox_url }}</p>

  <h2>Resumen</h2>
  <div class="summary">
    <div class="badge total"><strong>{{ total }}</strong><br>Total</div>
    <div class="badge pass"><strong>{{ passed }}</strong><br>Passed</div>
    <div class="badge fail"><strong>{{ failed }}</strong><br>Failed</div>
    <div class="badge {{ 'pass' if coverage >= 80 else 'fail' }}">
      <strong>{{ coverage }}%</strong><br>Cobertura
    </div>
  </div>

  {% if failed == 0 %}
  <div class="certified">✅ INTEGRACIÓN CERTIFICADA — Todos los endpoints cumplen el contrato</div>
  {% else %}
  <div class="certified" style="background:#e94560;">
    ⚠️ CERTIFICACIÓN PENDIENTE — Se encontraron {{ failed }} hallazgo(s)
  </div>
  {% endif %}

  <h2>Detalle por endpoint</h2>
  <table>
    <tr><th>Método</th><th>Endpoint</th><th>Estado</th><th>Hallazgos</th></tr>
    {% for r in results %}
    <tr>
      <td><strong>{{ r.method }}</strong></td>
      <td>{{ r.path }}</td>
      <td class="{{ r.status }}">{{ r.status }}</td>
      <td class="issues">{{ r.issues | join(', ') if r.issues else '—' }}</td>
    </tr>
    {% endfor %}
  </table>

  <div class="footer">
    Generado automáticamente por la Herramienta de Certificación de APIs.<br>
    Fecha de emisión: {{ date }} | Versión contrato: {{ api_version }}
  </div>
</body>
</html>
"""


class ReportGenerator:
    def __init__(self, config: dict, results: list, contract: dict):
        self.config = config
        self.results = results
        self.contract = contract

    def generate(self) -> str:
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)
        coverage = round((passed / total * 100), 1) if total > 0 else 0

        html = Template(TEMPLATE).render(
            client_name=self.config.get("client_name", "Cliente"),
            api_title=self.contract.get("title", "API"),
            api_version=self.contract.get("version", "1.0"),
            date=datetime.now().strftime("%d/%m/%Y %H:%M"),
            sandbox_url=self.config.get("login", {}).get("url", ""),
            total=total,
            passed=passed,
            failed=failed,
            coverage=coverage,
            results=self.results,
        )

        output_dir = Path("reports/output")
        output_dir.mkdir(parents=True, exist_ok=True)
        client = self.config.get("client_name", "cliente").replace(" ", "_").lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        path = output_dir / f"certificado_{client}_{timestamp}.html"

        with open(path, "w") as f:
            f.write(html)

        try:
            from weasyprint import HTML
            pdf_path = str(path).replace(".html", ".pdf")
            HTML(string=html).write_pdf(pdf_path)
            print(f"  → PDF generado: {pdf_path}")
            return pdf_path
        except ImportError:
            print("  → WeasyPrint no instalado, reporte en HTML")
            return str(path)

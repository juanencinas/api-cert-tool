# API Cert Tool 🔐

Herramienta de certificación automática de integraciones API.

## ¿Qué hace?
- Entra al sandbox del cliente con Playwright
- Intercepta todos los requests a tus APIs
- Valida cada request contra tu contrato Swagger
- Genera un certificado PDF formal

## Estructura
```
api-cert-tool/
├── main.py                  # Punto de entrada
├── requirements.txt
├── config/
│   └── cliente_001.yaml     # Credenciales + flujo por cliente
├── swagger/
│   └── api_contrato.yaml    # Tu Swagger oficial
├── core/
│   ├── parser.py            # Lee el Swagger
│   ├── navigator.py         # Playwright: login + navegación
│   └── validator.py         # Valida requests vs contrato
└── reports/
    └── generator.py         # Genera certificado HTML/PDF
```

## Instalación
```bash
pip install -r requirements.txt
playwright install chromium
```

## Uso
```bash
python main.py config/cliente_001.yaml swagger/api_contrato.yaml
```

## Configuración del cliente
Edita `config/cliente_001.yaml` con los datos que te envía el cliente:
- URL del sandbox
- Usuario y contraseña de prueba
- Pasos del flujo de navegación

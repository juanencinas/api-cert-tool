"""
navigator.py — Entra al sandbox del cliente con Playwright
e intercepta todos los requests a las APIs
"""

from playwright.async_api import async_playwright, Request


class SandboxNavigator:
    def __init__(self, config: dict):
        self.config = config
        self.captured = []
        self.api_base_urls = config.get("api_base_urls", [])

    async def run(self) -> list:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,  # Ventana visible para debug
                args=["--start-maximized"]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            # Interceptar requests Y responses
            page.on("request", self._on_request)

            await self._login(page)

            for step in self.config.get("steps", []):
                try:
                    await self._execute_step(page, step)
                    await page.wait_for_timeout(300)
                except Exception as e:
                    print(f"  ⚠️  Paso omitido ({step.get('action')} {step.get('selector','')}): {type(e).__name__}")
                    continue

            # Esperar extra para capturar todos los requests async
            await page.wait_for_timeout(3000)
            await browser.close()

        return self.captured

    def _is_api_call(self, url: str) -> bool:
        if not self.api_base_urls:
            return True
        return any(base in url for base in self.api_base_urls)

    async def _on_request(self, request: Request):
        if self._is_api_call(request.url):
            self.captured.append({
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data,
                "resource_type": request.resource_type,
            })
            print(f"  📡 Capturado: {request.method} {request.url.split('/')[-1]}")

    async def _login(self, page):
        login_config = self.config.get("login", {})
        if not login_config:
            return
        await page.goto(login_config["url"])
        await page.wait_for_load_state("networkidle")
        if "username_selector" in login_config:
            await page.fill(login_config["username_selector"], login_config["username"])
        if "password_selector" in login_config:
            await page.fill(login_config["password_selector"], login_config["password"])
        if "submit_selector" in login_config:
            await page.click(login_config["submit_selector"])
            await page.wait_for_load_state("networkidle")
        print(f"  → Login exitoso en {login_config['url']}")

    async def _execute_step(self, page, step: dict):
        action   = step.get("action")
        selector = step.get("selector", "")
        value    = step.get("value", "")
        url      = step.get("url", "")
        timeout  = int(step.get("timeout", 10000))

        if action == "navigate":
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

        elif action == "click":
            selectors = [s.strip() for s in selector.split(",")]
            clicked = False
            for sel in selectors:
                try:
                    await page.click(sel, timeout=timeout)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                raise Exception(f"No se encontró elemento: {selector}")

        elif action == "click_first_visible":
            await page.wait_for_selector(selector, timeout=timeout)
            elements = await page.query_selector_all(selector)
            for el in elements:
                if await el.is_visible():
                    await el.click()
                    break

        elif action == "triple_click":
            selectors = [s.strip() for s in selector.split(",")]
            for sel in selectors:
                try:
                    await page.triple_click(sel, timeout=timeout)
                    break
                except Exception:
                    continue

        elif action == "fill":
            selectors = [s.strip() for s in selector.split(",")]
            for sel in selectors:
                try:
                    await page.fill(sel, value, timeout=timeout)
                    break
                except Exception:
                    continue

        elif action == "wait_for_selector":
            await page.wait_for_selector(selector, timeout=timeout)

        elif action == "wait":
            ms = int(value) if value else 1000
            await page.wait_for_timeout(ms)

        elif action == "press_key":
            await page.keyboard.press(value)

        elif action == "js":
            await page.evaluate(value)

        print(f"  → Paso ejecutado: {action} {selector or url or value}")

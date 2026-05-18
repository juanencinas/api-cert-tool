"""
navigator.py — Entra al sandbox del cliente con Playwright
e intercepta todos los requests a las APIs
"""

import asyncio
from playwright.async_api import async_playwright, Request


class SandboxNavigator:
    def __init__(self, config: dict):
        self.config = config
        self.captured = []
        self.api_base_urls = config.get("api_base_urls", [])

    async def run(self) -> list:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            page.on("request", self._on_request)

            await self._login(page)

            for step in self.config.get("steps", []):
                await self._execute_step(page, step)
                await page.wait_for_timeout(1000)

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
        action = step.get("action")
        selector = step.get("selector", "")
        value = step.get("value", "")
        url = step.get("url", "")

        if action == "navigate":
            await page.goto(url)
            await page.wait_for_load_state("networkidle")
        elif action == "click":
            await page.click(selector)
            await page.wait_for_timeout(500)
        elif action == "fill":
            await page.fill(selector, value)
        elif action == "wait":
            await page.wait_for_timeout(int(value))

        print(f"  → Paso ejecutado: {action} {selector or url}")

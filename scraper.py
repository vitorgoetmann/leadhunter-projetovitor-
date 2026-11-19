"""
scraper.py — usa playwright SÍNCRONO (sync_playwright) para funcionar
corretamente no Windows com Python 3.13, evitando o ProactorEventLoop bug.
"""
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def scrape_google_maps_sync(keyword: str, location: str, max_results: int = 30) -> list[dict]:
    """
    Abre o Google Maps, busca pelo keyword + location e retorna
    uma lista de dicionários com os detalhes de cada estabelecimento.
    Usa sync_playwright — compatível 100% com Windows/Python 3.13.
    """
    results = []
    search_query = f"{keyword} em {location}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        context = browser.new_context(
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            maps_url = (
                "https://www.google.com/maps/search/"
                + search_query.replace(" ", "+")
            )
            page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)

            # Aceitar cookies se aparecer
            for sel in [
                'button:has-text("Aceitar tudo")',
                'button:has-text("Accept all")',
                'button:has-text("Concordo")',
            ]:
                try:
                    btn = page.locator(sel)
                    if btn.count() > 0:
                        btn.first.click(timeout=2000)
                        page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass

            # Aguardar feed de resultados
            try:
                page.wait_for_selector('[role="feed"]', timeout=15000)
            except PlaywrightTimeout:
                print("[WARN] Feed de resultados não encontrado.")
                browser.close()
                return []

            # Scrollar para carregar mais resultados
            previous_count = 0
            no_change_streak = 0

            while no_change_streak < 5:
                current_count = page.locator(
                    '[role="feed"] a[href*="/maps/place/"]'
                ).count()

                if current_count >= max_results:
                    break

                if current_count == previous_count:
                    no_change_streak += 1
                else:
                    no_change_streak = 0
                    previous_count = current_count

                page.locator('[role="feed"]').evaluate("el => el.scrollBy(0, 1000)")
                page.wait_for_timeout(1200)

            # Coletar hrefs únicos
            link_els = page.locator('[role="feed"] a[href*="/maps/place/"]')
            link_count = min(link_els.count(), max_results)

            hrefs = []
            for i in range(link_count):
                href = link_els.nth(i).get_attribute("href")
                if href and href not in hrefs:
                    hrefs.append(href)

            print(f"[INFO] {len(hrefs)} lugares encontrados para raspar.")

            # Visitar cada página de detalhe
            for idx, href in enumerate(hrefs):
                try:
                    detail = _scrape_place_detail(context, href, idx + 1)
                    if detail:
                        results.append(detail)
                        print(f"[{idx+1}/{len(hrefs)}] OK {detail.get('nome', '?')}")
                    time.sleep(0.6)
                except Exception as e:
                    print(f"[WARN] Erro ao raspar lugar #{idx+1}: {e}")
                    continue

        except Exception as e:
            print(f"[ERROR] Erro geral no scraper: {e}")
        finally:
            browser.close()

    return results


def _scrape_place_detail(context, url: str, index: int) -> dict | None:
    """Abre a página de detalhe de um lugar e extrai todas as informações."""
    page = context.new_page()
    data: dict = {}

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2500)

        # ── NOME ──────────────────────────────────────────────────
        name = ""
        for sel in ["h1.DUwDvf", "h1[class*='fontHeadlineLarge']", "h1"]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    name = el.inner_text(timeout=4000).strip()
                    if name:
                        break
            except Exception:
                continue
        data["nome"] = name

        # ── CATEGORIA ─────────────────────────────────────────────
        category = ""
        for sel in [
            'button[jsaction*="category"]',
            'span.DkEaL',
            '[data-item-id*="category"] .fontBodyMedium',
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    category = el.inner_text(timeout=2000).strip()
                    if category:
                        break
            except Exception:
                continue
        data["categoria"] = category

        # ── AVALIAÇÃO ─────────────────────────────────────────────
        rating = ""
        for sel in [
            'span[aria-hidden="true"].ceNzKf',
            'div.F7nice span[aria-hidden="true"]',
            'span.MW4etd',
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    rating = el.inner_text(timeout=2000).strip().replace(",", ".")
                    if rating:
                        break
            except Exception:
                continue
        data["avaliacao"] = rating

        # ── TOTAL DE AVALIAÇÕES ───────────────────────────────────
        reviews_count = ""
        try:
            rev_el = page.locator(
                'span[aria-label*="avaliações"], span[aria-label*="reviews"]'
            ).first
            if rev_el.count() > 0:
                lbl = rev_el.get_attribute("aria-label", timeout=2000)
                nums = re.findall(r"[\d.]+", lbl or "")
                reviews_count = nums[0].replace(".", "") if nums else ""
        except Exception:
            pass
        data["total_avaliacoes"] = reviews_count



        # ── ENDEREÇO ──────────────────────────────────────────────
        address = ""
        for sel in [
            'button[data-item-id="address"] .fontBodyMedium',
            '[data-tooltip="Copiar endereço"] .Io6YTe',
            'button[aria-label*="Endereço"] .fontBodyMedium',
        ]:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    address = el.inner_text(timeout=2000).strip()
                    if address:
                        break
            except Exception:
                continue
        data["endereco"] = address

        # ── TELEFONES ─────────────────────────────────────────────
        telefones = []
        for sel in [
            'button[data-item-id^="phone:tel:"] .fontBodyMedium',
            '[data-tooltip="Copiar número de telefone"] .Io6YTe',
            'a[href^="tel:"]',
        ]:
            try:
                els = page.locator(sel)
                count = els.count()
                for i in range(count):
                    el = els.nth(i)
                    if "tel:" in sel:
                        raw = el.get_attribute("href", timeout=1000)
                        phone = (raw or "").replace("tel:", "").strip()
                    else:
                        phone = el.inner_text(timeout=1000).strip()
                    if phone and phone not in telefones:
                        telefones.append(phone)
            except Exception:
                continue
        data["telefones"] = telefones

        # ── REDES SOCIAIS E WEBSITES ──────────────────────────────
        websites = []
        for sel in [
            'a[data-item-id="authority"]',
            'a[aria-label*="Site"]',
            'a[aria-label*="Website"]',
            'a[href*="instagram.com"]',
            'a[href*="facebook.com"]',
            'a[href*="linkedin.com"]',
        ]:
            try:
                els = page.locator(sel)
                count = els.count()
                for i in range(count):
                    href = els.nth(i).get_attribute("href", timeout=1000) or ""
                    href = href.strip()
                    if href and "maps.google" not in href and "google.com/maps" not in href and href not in websites:
                        websites.append(href)
            except Exception:
                continue
        data["websites"] = websites



        # ── WHATSAPP ──────────────────────────────────────────────
        whatsapp = ""
        try:
            wa = page.locator('a[href*="wa.me"], a[href*="whatsapp.com"]').first
            if wa.count() > 0:
                whatsapp = wa.get_attribute("href") or ""
        except Exception:
            pass
        data["whatsapp"] = whatsapp

        # ── LINK MAPS + POSIÇÃO ───────────────────────────────────
        data["google_maps_url"] = page.url
        data["posicao"] = index

    except Exception as e:
        print(f"[WARN] Falha ao extrair detalhes de {url[:60]}: {e}")
        return None
    finally:
        page.close()

    if not data.get("nome"):
        return None

    return data


# Compatibilidade — app.py chama scrape_google_maps_sync diretamente
async def scrape_google_maps(keyword: str, location: str, max_results: int = 30) -> list[dict]:
    """Wrapper async — delega para a versão síncrona (usada apenas se chamada diretamente)."""
    return scrape_google_maps_sync(keyword, location, max_results)

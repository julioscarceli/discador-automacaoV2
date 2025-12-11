# scripts/cost_monitor.py (Versão Assíncrona e para Deploy)

import os
import time
import re
from typing import Dict, Any
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError # CORREÇÃO

# Lendo credenciais e URL de forma segura (do .env/Secrets)
# Estas variáveis devem estar no seu .env e Railway Secrets
BASE_URL = os.getenv("NEXT_ROUTER_URL", "https://190.89.249.51/security/login")
USUARIO = os.getenv("NEXT_ROUTER_USER", "linxsysglobal")
SENHA = os.getenv("NEXT_ROUTER_PASS", "00e7BA8-7f0f")


def clean_to_float(value):
    """Limpa a string de moeda (ex: R$ 5.665,28) e retorna um float."""
    if value == "—": return None
    try:
        value = re.sub(r'[^\d,.]', '', value or "")
        # Remove ponto de milhar, substitui vírgula decimal por ponto (formato BR -> US)
        return float(value.replace('.', '').replace(',', '.'))
    except:
        return None


# 🚨 FUNÇÃO CONVERTIDA PARA ASSÍNCRONA (coletar_custos_async)
async def coletar_custos_async(headless: bool = True) -> Dict[str, Any]:
    dados = {}
    async with async_playwright() as p:
        # Lançamento do navegador
        browser = await p.chromium.launch(headless=headless, timeout=60000)
        context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        try:
            # --- Login e Navegação ---
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=90000)

            username_selector = "#username"
            password_selector = "#password"
            await page.wait_for_selector(username_selector, state="visible", timeout=15000)
            await page.fill(username_selector, USUARIO)
            await page.fill(password_selector, SENHA)

            with page.expect_navigation(timeout=45000, wait_until="load"):
                await page.get_by_role("button", name="Conectar").click()

            await page.wait_for_load_state("networkidle", timeout=20000)

            # ============ 1. SALDO ATUAL (HOME) ============
            saldo_el_selector = "#system-container > div > div:nth-child(2) > div > h3"
            saldo_text = await page.text_content(saldo_el_selector, timeout=10000)
            dados["saldo_atual"] = clean_to_float(saldo_text)

            # ============ 2. NAVEGAÇÃO E CUSTO DIÁRIO ============
            dropdown_relatorios_xpath = '//*[@id="main-menu"]/li[5]/a'
            relatorio_link_selector = "#relatorioAgrupadoLinhas"

            await page.click(dropdown_relatorios_xpath, timeout=15000)
            await page.wait_for_selector(relatorio_link_selector, state="visible", timeout=10000)
            await page.click(relatorio_link_selector)

            await page.wait_for_selector("#txtDataI", timeout=45000)

            # XPaths dos Custos (Diário)
            custo_discador_xpath = '//*[@id="tblMain"]/tbody/tr[1]/td[7]'
            custo_ura_xpath = '//*[@id="tblMain"]/tbody/tr[2]/td[7]'

            discador_diario_text = await page.text_content(custo_discador_xpath, timeout=5000)
            ura_diario_text = await page.text_content(custo_ura_xpath, timeout=5000)

            dados["custo_diario_discador"] = clean_to_float(discador_diario_text)
            dados["custo_diario_ura"] = clean_to_float(ura_diario_text)

            # Custo Diário Total (FLOAT)
            dados["custo_diario_total"] = (dados["custo_diario_discador"] or 0) + (dados["custo_diario_ura"] or 0)

            # Placeholder para o custo semanal (a ser implementado)
            dados["custo_semanal"] = 0.0  # Valor para evitar KeyError no Dashboard

            return dados

        except PlaywrightTimeoutError:
            # Retorna None para os valores se o timeout ocorrer
            return {"saldo_atual": None, "custo_diario_total": None, "custo_semanal": None,
                    "erro": "Timeout durante o scraping."}
        except Exception as e:
            return {"saldo_atual": None, "custo_diario_total": None, "custo_semanal": None,
                    "erro": f"Erro inesperado: {e}"}
        finally:
            # Fechamento garantido do navegador
            if context: await context.close()
            if browser: await browser.close()


def processar_dados_para_dashboard_formatado(d: Dict[str, Any]) -> Dict[str, Any]:
    """Prepara e formata o dicionário de dados coletados (apenas Saldo e Diário) para o Dashboard."""

    # Formatação para Dashboard (R$ XX,XX)
    saldo = f"R$ {d['saldo_atual']:.2f}".replace('.', ',') if d.get('saldo_atual') is not None else "N/A"
    custo = f"R$ {d['custo_diario_total']:.2f}".replace('.', ',') if d.get('custo_diario_total') is not None else "N/A"
    custo_semanal = f"R$ {d['custo_semanal']:.2f}".replace('.', ',') if d.get('custo_semanal') is not None else "N/A"

    return {
        "saldo_atual": saldo,
        "custo_diario": custo,
        "custo_semanal": custo_semanal,
        # 🚨 CORREÇÃO DE SINTAXE: Usando datetime.now()
        "data_coleta": datetime.now().isoformat()
    }

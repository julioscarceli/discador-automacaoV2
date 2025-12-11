# manual_api_test.py (VERSÃO FINAL DE TESTE DE CONEXÃO E MÉTRICAS)

import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
from datetime import datetime

# Garante que o API_TOKEN seja lido imediatamente (necessário para httpx)
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")

# URLs base (Ajustadas para o caminho validado no Postman)
BASE_URL_MG = "https://186.194.50.155"
BASE_URL_SP = "https://186.194.50.149"


# --- FUNÇÕES DE INFRAESTRUTURA (Essenciais para o teste) ---

def get_base_url(server: str) -> str:
    """Retorna o caminho que funciona: http://IP/api/"""
    if server.upper() == "SP":
        return f"{BASE_URL_SP.rstrip('/')}/api/"
    base = BASE_URL_MG.rstrip('/')
    if base.startswith("https://"):
        base = base.replace("https://", "http://")
    return f"{base}/api/"


def extract_metrics(status_data, server_name):
    """Extrai os campos 'progresso' e 'saidas' de forma segura do JSON de status."""
    if not isinstance(status_data, dict) or status_data.get('status') == 'Erro':
        return {"progresso": "N/A", "saidas": "N/A"}
    progresso = status_data.get('progresso', 'N/D')
    try:
        # Assumindo que 'saidas' está aninhado em 'dados[0]'
        saidas = status_data['dados'][0]['saidas']
    except (KeyError, IndexError):
        saidas = 'N/D'
    return {"progresso": progresso, "saidas": saidas}


# ====================================================================
# [API CALL 1]: Listar Campanhas Ativas (POST)
# ====================================================================
async def api_list_campaigns(server: str):
    """Testa o endpoint list_campaign.php (POST)."""
    url = f"{get_base_url(server)}list_campaign.php"
    data = {'token': API_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        if hasattr(e, 'response') and e.response is not None:
            raise Exception(f"ERRO HTTP {e.response.status_code} na list_campaign. RESPOSTA: {e.response.text[:100]}")
        raise Exception(f"FALHA DE COMUNICAÇÃO na list_campaign: {e}")


# ====================================================================
# [API CALL 2]: Obter Status de Campanha em Execução (GET)
# ====================================================================
async def api_get_campaign_status(server: str, campaign_id: str):
    """Testa o endpoint campaign_exec.php (GET) com o ID da campanha."""
    url = f"{get_base_url(server)}campaign_exec.php"
    params = {'id': campaign_id, 'token': API_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        if hasattr(e, 'response') and e.response is not None:
            raise Exception(f"ERRO HTTP {e.response.status_code} na campaign_exec. RESPOSTA: {e.response.text[:100]}")
        raise Exception(f"FALHA DE COMUNICAÇÃO na campaign_exec: {e}")


# ====================================================================
# [EXECUÇÃO DO TESTE SEQUENCIAL PRINCIPAL]
# ====================================================================
async def run_test():
    # 1. LISTAR CAMPANHAS E EXTRAIR IDs
    print("\n--- INICIANDO TESTE 1: LISTAR CAMPANHAS ---")
    list_sp = await api_list_campaigns(server="SP")
    list_mg = await api_list_campaigns(server="MG")

    # Extração segura do primeiro ID
    campaign_id_sp = list_sp[0]['id'] if list_sp and list_sp[0].get('id') else None
    campaign_id_mg = list_mg[0]['id'] if list_mg and list_mg[0].get('id') else None

    if not campaign_id_sp or not campaign_id_mg:
        print("\n❌ FALHA: Não foi possível extrair IDs das campanhas. Teste de status ignorado.")
        return

    print(f"\n✅ ID SP para teste: {campaign_id_sp}")
    print(f"✅ ID MG para teste: {campaign_id_mg}")

    # 2. OBTER STATUS E MÉTRICAS
    print("\n--- INICIANDO TESTE 2: STATUS E MÉTRICAS ---")

    status_sp = await api_get_campaign_status(server="SP", campaign_id=campaign_id_sp)
    metrics_sp = extract_metrics(status_sp, "SP")

    status_mg = await api_get_campaign_status(server="MG", campaign_id=campaign_id_mg)
    metrics_mg = extract_metrics(status_mg, "MG")

    print("\n--- RESULTADO FINAL: MÉTRICAS DE EXECUÇÃO ---")
    print(f"[{'MG':<3}] Progresso: {metrics_mg['progresso']:<6} | Saídas: {metrics_mg['saidas']}")
    print(f"[{'SP':<3}] Progresso: {metrics_sp['progresso']:<6} | Saídas: {metrics_sp['saidas']}")

    # 3. PONTO DE INTEGRAÇÃO DO UPLOAD/CRIAÇÃO
    print("\n--- PONTO DE INTEGRAÇÃO ---")
    print("O próximo passo seria chamar a rotina de Importação (API CALL 3).")


if __name__ == '__main__':
    # Este script exige que as URLs base e o API_TOKEN estejam configurados.
    if not API_TOKEN:
        print("Erro: API_TOKEN não configurado no .env.")
    else:
        asyncio.run(run_test())
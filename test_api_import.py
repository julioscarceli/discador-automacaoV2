# scripts/test_api_import.py (Versão Final de Teste Duplo)

import asyncio
import httpx
import os
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

# Garante que o API_TOKEN seja lido imediatamente
load_dotenv()

# ====================================================================
# --- CONFIGURAÇÕES E CREDENCIAIS ---
# URLs base (Corrigidas para o caminho validado no Postman)
BASE_URL_MG = "http://186.194.50.155"
BASE_URL_SP = "https://186.194.50.149"

# Constantes de teste
API_TOKEN = os.getenv("API_TOKEN")
LOCAL_MAILING_BASE_DIR = r"D:\Ferramentas\5. Verificação Final\MAILING DISCADOR"
TEST_IMPORT_ID = "1"
TEST_LOGIN_CRM = "TESTE_API_LIMA"
SAIDAS_VALOR = "70"
FILA_NOME_MG = "DISCADOR_MG"
FILA_NOME_SP = "DISCADOR_SP"
# ----------------------------------------------------------------------

# --- Mapeamento do Mailing (Para usar no Worker) ---
MAILING_MAP = {
    "MG": "MAILING_DISCADOR_EMP",  # Servidor MG usa EMP
    "SP": "MAILING_DISCADOR_CARD"  # Servidor SP usa CARD
}


# --- FUNÇÕES CORE (Inclusas para Autonomia) ---

def get_base_url_for_api(server: str) -> str:
    """Retorna a URL base correta: http://IP/api/"""
    if server.upper() == "SP":
        base = BASE_URL_SP
    else:
        base = BASE_URL_MG
    return f"{base}/api/"


def get_fila_name(server: str) -> str:
    if server.upper() == "SP":
        return "DISCADOR_SP"
    return "DISCADOR_MG"


def _generate_metadata_line(campaign_id: str, mailling_name: str, server: str, login_crm: str = "AUTOMACAO") -> str:
    # ... (Lógica de metadados) ...
    fila_nome = get_fila_name(server)

    metadata = [
        campaign_id, mailling_name, SAIDAS_VALOR, fila_nome,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), login_crm,
        datetime.now().strftime('%Y-%m-%d'), "2025-12-31", "08:00:00", "20:00:00",
        "1", "simultanea", "1,2,3,4,5", "", ""
    ]
    return ";".join(metadata)


def _transform_client_data(source_csv_path: str, campaign_id: str, mailling_name: str, server: str,
                           login_crm: str) -> str:
    # ... (Lógica de transformação, assumida funcional) ...

    POS_NUMERO = 29;
    POS_NOME = 0;
    POS_CPF = 1;
    POS_LIVRE1 = 2;
    POS_CHAVE = 3
    try:
        df_source = pd.read_csv(source_csv_path, sep=';', encoding='latin-1', header=None, engine='python')
    except Exception as e:
        raise Exception(f"Falha na leitura do CSV de origem (Sep=;): {e}")

    df_target = pd.DataFrame()
    df_target[0] = df_source[POS_NUMERO].astype(str)
    df_target[1] = ""
    df_target[2] = df_source[POS_NOME]
    df_target[3] = df_source[POS_CPF].astype(str)
    df_target[4] = df_source[POS_LIVRE1].fillna('')
    df_target[5] = df_source[POS_CHAVE].fillna('')
    for i in range(6, 13): df_target[i] = ""

    metadata_line = _generate_metadata_line(campaign_id, mailling_name, server, login_crm)
    temp_target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_api_upload.csv")

    with open(temp_target_path, 'w', encoding='latin-1') as f:
        f.write(metadata_line + "\n")
    df_target.iloc[1:].to_csv(temp_target_path, mode='a', sep=';', header=False, index=False, encoding='latin-1')
    return temp_target_path


async def api_import_mailling_upload(server: str, campaign_id: str, source_csv_path: str, mailling_name: str,
                                     login_crm: str):
    """Executa a transformação local do CSV e envia o arquivo Multipart para a API."""
    temp_file_path = None
    try:
        temp_file_path = _transform_client_data(source_csv_path, campaign_id, mailling_name, server, login_crm)
        url = f"{get_base_url_for_api(server)}import_mailling.php"

        with open(temp_file_path, 'rb') as f:
            files = {'import': ('temp_api_upload.csv', f, 'text/csv')}
            data = {'token': API_TOKEN, 'ok': 'ok'}

            async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()

            raw_response_text = response.text
            try:
                return response.json()
            except json.JSONDecodeError:
                raise Exception(f"RESPOSTA BRUTA DO SERVIDOR (Não é JSON): {raw_response_text[:1000]}...")

    except Exception as e:
        raise Exception(f"ERRO CRÍTICO NA REQUISIÇÃO HTTP: {e}")

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# ====================================================================
# [ROTINA PRINCIPAL DE TESTE DUPLO]
# ====================================================================

async def run_isolated_api_upload_test():
    """Rotina principal que itera sobre MG e SP e dispara o upload."""

    TODAY_FILE_SUFFIX = datetime.now().strftime(' - %d-%m') + ".csv"

    results = {}

    for server_name in MAILING_MAP.keys():
        print(f"\n--- INICIANDO TESTE ISOLADO DE UPLOAD ({server_name}) ---")

        # 1. CONSTRUÇÃO DO CAMINHO DO ARQUIVO
        base_name = MAILING_MAP[server_name]
        source_file_path = os.path.join(LOCAL_MAILING_BASE_DIR, f"{base_name}{TODAY_FILE_SUFFIX}")

        if not os.path.exists(source_file_path):
            print(f"❌ ERRO: Arquivo de origem NÃO ENCONTRADO em: {source_file_path}")
            continue

        try:
            mailling_name_for_api = base_name + datetime.now().strftime(' - %d-%m')

            upload_result = await api_import_mailling_upload(
                server=server_name,
                campaign_id=TEST_IMPORT_ID,
                source_csv_path=source_file_path,
                mailling_name=mailling_name_for_api,
                login_crm=TEST_LOGIN_CRM
            )
            results[server_name] = upload_result

        except Exception as e:
            results[server_name] = {"success": False, "error": str(e)}
            print(f"❌ FALHA FINAL NO UPLOAD {server_name}: {e}")

    # --- RESULTADOS FINAIS ---
    print("\n\n=============== RESUMO GERAL DO UPLOAD ===============")
    for server, result in results.items():
        success = result.get('success', False)
        status = result.get('status', result.get('error', 'FALHA DE COMUNICAÇÃO'))
        print(f"[{server}] SUCESSO: {success} | STATUS: {status[:60]}...")
    print("======================================================")


if __name__ == '__main__':
    # Este é o script que você deve rodar localmente após garantir as URLs limpas.
    asyncio.run(run_isolated_api_upload_test())
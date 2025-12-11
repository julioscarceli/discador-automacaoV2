# utils/mailing_api.py (VERSÃO FINAL COM BASE64, MÉTRICAS E LIMPEZA DE CÓDIGO)

import httpx
import pandas as pd
import os
import datetime
import json
from dotenv import load_dotenv
import base64
from io import StringIO
from datetime import datetime as dt  # Alias para evitar conflito com datetime

# Carrega variáveis de ambiente (necessário para os.getenv)
load_dotenv()

# --- CONSTANTES GLOBAIS ---
# Em produção, estas viriam de config/settings.py
BASE_URL_MG = os.getenv("BASE_URL_MG", "http://186.194.50.155")
BASE_URL_SP = os.getenv("BASE_URL_SP", "https://186.194.50.149")
API_TOKEN = os.getenv("API_TOKEN")
SAIDAS_VALOR = os.getenv("SAIDAS_VALOR", "70")
FILA_NOME_MG = os.getenv("FILA_NOME_MG", "DISCADOR_MG")
FILA_NOME_SP = os.getenv("FILA_NOME_SP", "DISCADOR_SP")

if not API_TOKEN:
    print("ATENÇÃO: API_TOKEN não encontrado. As chamadas API falharão.")


# --- FUNÇÕES DE INFRAESTRUTURA E AUXILIARES ---

def get_base_url_for_api(server: str) -> str:
    """Retorna a URL base correta: http://IP/api/ (O caminho validado)."""
    if server.upper() == "SP":
        base = BASE_URL_SP
    else:
        base = BASE_URL_MG
    return f"{base.rstrip('/')}/api/"
# Garante que o Dash e os Workers sempre chamem o endpoint validado, evitando erros 404.





def get_fila_name(server: str) -> str:
    """Retorna o nome da fila correto para a construção do CSV."""
    if server.upper() == "SP":
        return FILA_NOME_SP
    return FILA_NOME_MG


def extract_metrics(status_data, server_name):
    """Extrai os campos 'progresso' e 'saidas' de forma segura do JSON de status."""
    if not isinstance(status_data, dict) or status_data.get('status') == 'Erro':
        return {"progresso": "N/A", "saidas": "N/A"}
    progresso = status_data.get('progresso', 'N/D')
    try:
        saidas = status_data['dados'][0]['saidas']
    except (KeyError, IndexError):
        saidas = 'N/D'
    return {"progresso": progresso, "saidas": saidas}
# Recebe o JSON bruto da API (campaign_exec.php) e extrai de forma segura os valores progresso e saídas.
# Formata o dado exato que o Dash exibe nos cartões de status.


def _generate_metadata_line(campaign_id: str, mailling_name: str, server: str, login_crm: str = "AUTOMACAO") -> str:
    """Cria a primeira linha de metadados (15 colunas) para o CSV."""
    fila_nome = get_fila_name(server)
    metadata = [
        campaign_id, mailling_name, SAIDAS_VALOR, fila_nome,
        dt.now().strftime('%Y-%m-%d %H:%M:%S'), login_crm,
        dt.now().strftime('%Y-%m-%d'), "2025-12-31", "08:00:00", "20:00:00",
        "1", "simultanea", "1,2,3,4,5", "", ""
    ]
    return ";".join(metadata)


# ====================================================================
# [TRANSFORMAÇÃO - BASE64]
# ====================================================================

def _transform_client_data(file_content_base64: str, campaign_id: str, mailling_name: str, server: str,
                           login_crm: str) -> str:
    """
    Recebe o conteúdo em Base64, decodifica, processa com Pandas, e salva o arquivo temporário.
    """
    try:
        # 1. DECODIFICAR O CONTEÚDO (STRING BASE64 -> BYTES -> STRING)
        decoded_bytes = base64.b64decode(file_content_base64)
        decoded_content = decoded_bytes.decode('latin-1')

    except Exception as e:
        raise Exception(f"Falha na decodificação do arquivo: {e}")

    # --- POSIÇÕES FIXAS DAS SUAS COLUNAS NO CSV ---
    POS_NUMERO = 29;
    POS_NOME = 0;
    POS_CPF = 1;
    POS_LIVRE1 = 2;
    POS_CHAVE = 3

    try:
        # 2. LER O CONTEÚDO COM O PANDAS DIRETAMENTE DA MEMÓRIA
        df_source = pd.read_csv(StringIO(decoded_content), sep=';', header=None, engine='python')
    except Exception as e:
        raise Exception(f"Falha na leitura do CSV de origem pelo Pandas: {e}")

    # 3. TRANSFORMAÇÃO DE COLUNAS
    df_target = pd.DataFrame()
    df_target[0] = df_source[POS_NUMERO].astype(str)
    df_target[1] = ""
    df_target[2] = df_source[POS_NOME]
    df_target[3] = df_source[POS_CPF].astype(str)
    df_target[4] = df_source[POS_LIVRE1].fillna('')
    df_target[5] = df_source[POS_CHAVE].fillna('')
    for i in range(6, 13): df_target[i] = ""

    # 4. GERAÇÃO E SALVAMENTO DO ARQUIVO TEMPORÁRIO
    metadata_line = _generate_metadata_line(campaign_id, mailling_name, server, login_crm)
    temp_target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_api_upload.csv")

    with open(temp_target_path, 'w', encoding='latin-1') as f:
        f.write(metadata_line + "\n")
    df_target.iloc[1:].to_csv(temp_target_path, mode='a', sep=';', header=False, index=False, encoding='latin-1')
    return temp_target_path
# CRÍTICA. Recebe a string Base64 do Dash, decodifica para CSV, usa Pandas para mapear
# as colunas (30 ➡️ 13) e salva o resultado como um arquivo temporário no servidor.

# Recebe a string Base64 do navegador, eliminando a necessidade de ler o arquivo do disco rígido local.





# ====================================================================
# [API CALLS DO DASHBOARD E WORKER]
# ====================================================================

# --- API CALL 1: LISTAR CAMPANHAS ---
async def api_list_campaigns(server: str):
    """Lista todas as campanhas ativas."""
    url = f"{get_base_url_for_api(server)}list_campaign.php"
    data = {'token': API_TOKEN}
    async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        return response.json()
# API Call 1. Lista as campanhas ativas para encontrar o ID da Campanha que está rodando.
# É o primeiro passo para saber o nome da campanha ativa.




# --- API CALL 2: OBTER STATUS DA CAMPANHA ---
async def api_get_campaign_status(server: str, campaign_id: str):
    """Obtém status detalhado de uma campanha (necessário para progresso)."""
    url = f"{get_base_url_for_api(server)}campaign_exec.php"
    params = {'id': campaign_id, 'token': API_TOKEN}
    async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
# API Call 2. Usa o ID para obter o status detalhado (Progresso/Saídas).
# Fornece os números de performance brutos para o Dash.


async def get_active_campaign_metrics(server: str) -> dict:
    """
    Função Master: Obtém todos os dados necessários (Nome, Progresso, Saídas)
    para um servidor em uma única chamada master.
    """
    try:
        campaigns = await api_list_campaigns(server)

        # 1. Checa se há campanhas ativas
        if not campaigns or not campaigns[0].get('id'):
            return {"nome": "Nenhuma Campanha Ativa", "progresso": "0%", "saidas": "0", "id": None}

        active_campaign = campaigns[0]
        campaign_id = active_campaign.get('id')

        # 2. Obtém o progresso detalhado
        status_data = await api_get_campaign_status(server, campaign_id)
        metrics = extract_metrics(status_data, server)

        return {
            "nome": active_campaign.get('nome', 'N/A'),
            "progresso": metrics['progresso'],
            "saidas": metrics['saidas'],
            "id": campaign_id
        }

    except Exception as e:
        # Retorna um erro amigável para o Dashboard
        return {"nome": "ERRO API", "progresso": "N/A", "saidas": "N/A", "id": None}
# Função Master. Combina o Call 1 e o Call 2, trata erros e retorna um dicionário limpo (nome, progresso, saídas) que o Dash pode usar diretamente.
# O app.py chama esta função a cada 10 segundos para atualizar o painel.





# --- API CALL 3: IMPORTAÇÃO DE MAILING (MULTIPART POST) ---
async def api_import_mailling_upload(server: str, campaign_id: str, file_content_base64: str, mailling_name: str,
                                     login_crm: str):
    """
    Recebe o conteúdo Base64 do Dash, transforma, e envia o arquivo Multipart para a API.
    """
    temp_file_path = None

    try:
        # 1. TRANSFORMAÇÃO E GERAÇÃO DO ARQUIVO TEMPORÁRIO (USANDO O CONTEÚDO BASE64)
        temp_file_path = _transform_client_data(file_content_base64, campaign_id, mailling_name, server, login_crm)

        # 2. CONFIGURAÇÃO E ENVIO MULTIPART/FORM-DATA
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

# API Call 3. Recebe a Base64, chama _transform_client_data para obter o arquivo temporário,
# e usa o httpx para enviar o Upload Multipart para o endpoint import_mailling.php.

# É o endpoint que é disparado quando o usuário clica nos botões de Importação Manual.

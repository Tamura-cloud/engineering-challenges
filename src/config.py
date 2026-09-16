"""Configuração central: caminhos, geometria do OCR e credenciais.

A chave da DeepSeek é lida exclusivamente do arquivo ``.env`` na raiz do
projeto (protegido pelo ``.gitignore``). Este módulo nunca escreve, imprime nem
serializa o valor da chave — ``require_api_key()`` devolve a string apenas para
o construtor do cliente.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
SCHEMA_PATH = REPO_ROOT / "challenges" / "actes" / "schema" / "results.schema.json"
EVENT_CODES_PATH = REPO_ROOT / "challenges" / "actes" / "schema" / "event_codes.json"
RESULTS_PATH = REPO_ROOT / "results.json"

#: Empresa sujeita do desafio. O schema oficial fixa esta SIREN como constante.
SUBJECT_SIREN = "480489707"

#: Holding controladora — base do bônus ``group``.
RELATED_SIREN = "499979540"

# Geometria: os polígonos do OCR vêm em PIXELS a 300 dpi, enquanto o PDF declara
# a página em PONTOS. A conversão para o espaço unitário está em
# ``src/grounding.py`` e foi conferida contra as bboxes do ``results.json``.
DPI_OF_OCR = 300
POINTS_PER_INCH = 72
PX_PER_POINT = DPI_OF_OCR / POINTS_PER_INCH

load_dotenv(REPO_ROOT / ".env")

DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip() or None
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.0"))
DEEPSEEK_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "2"))
DEEPSEEK_TIMEOUT_S = float(os.getenv("DEEPSEEK_TIMEOUT_S", "120"))

#: Orçamento de caracteres enviados por página no contexto da API.
CONTEXT_MAX_CHARS_PER_PAGE = int(os.getenv("CONTEXT_MAX_CHARS_PER_PAGE", "6000"))


def has_api_key() -> bool:
    """Indica se a chave da DeepSeek está disponível no ambiente."""
    return DEEPSEEK_API_KEY is not None


def require_api_key() -> str:
    """Devolve a chave da API ou falha com instrução de configuração."""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "ERRO: variável DEEPSEEK_API_KEY não definida.\n"
            f"Crie o arquivo {REPO_ROOT / '.env'} a partir do .env.example e "
            "preencha a linha DEEPSEEK_API_KEY=<sua-chave>.\n"
            "O arquivo .env é ignorado pelo git e nunca deve ser comitado."
        )
    return DEEPSEEK_API_KEY


def get_client() -> Any:
    """Cria o cliente OpenAI apontando para o endpoint compatível da DeepSeek."""
    from openai import OpenAI

    return OpenAI(
        api_key=require_api_key(),
        base_url=DEEPSEEK_BASE_URL,
        timeout=DEEPSEEK_TIMEOUT_S,
        max_retries=DEEPSEEK_MAX_RETRIES,
    )


def siren_dir(siren: str, kind: str = "actes") -> Path:
    """Diretório-base de um tipo de documento para uma SIREN."""
    return DATA_DIR / siren / kind

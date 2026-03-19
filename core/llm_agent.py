"""
Agente LLM — Integração com Gemini 1.5 Flash para formatação litúrgica de atas maçônicas.

Utiliza a biblioteca google-genai para enviar transcrições brutas e receber
atas formatadas segundo o rito e protocolo maçônico oficial.
"""

import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Templates de sessão disponíveis
TEMPLATES: dict[str, str] = {
    "Sessão Ordinária (Grau 1)": "Sessão Ordinária em Grau de Aprendiz",
    "Sessão Extraordinária (Grau 1)": "Sessão Extraordinária em Grau de Aprendiz",
    "Sessão Ordinária (Grau 2)": "Sessão Ordinária em Grau de Companheiro",
    "Sessão Extraordinária (Grau 2)": "Sessão Extraordinária em Grau de Companheiro",
    "Sessão Ordinária (Grau 3)": "Sessão Ordinária em Grau de Mestre",
    "Sessão Magna": "Sessão Magna de Instalação",
}

SYSTEM_PROMPT = """Você é um Secretário de Loja Maçônica altamente experiente e rigoroso.
Sua função é redigir Atas de Sessão a partir de transcrições brutas de áudio.

## REGRAS DE REDAÇÃO OBRIGATÓRIAS:

1. **ESTILO:** Redação formal, impessoal, sempre em 3ª pessoa do singular.
   - CORRETO: "O Venerável Mestre declarou abertos os trabalhos..."
   - INCORRETO: "Eu declarei abertos os trabalhos..."

2. **SIGLAS MAÇÔNICAS COM TRÊS PONTOS (obrigatório):**
   - A.·.R.·.L.·.S.·. = Augusta e Respeitável Loja Simbólica
   - V.·.M.·. = Venerável Mestre
   - G.·.A.·.D.·.U.·. = Grande Arquiteto do Universo
   - Ir.·. = Irmão / IIr.·. = Irmãos
   - Or.·. = Oriente
   - Gr.·. = Grau
   - Ob.·. = Obreiro(s)
   - M.·.I.·. = Muito Ilustre
   - P.·.M.·. = Past Master / Passado Mestre
   - 1.·. Vig.·. = Primeiro Vigilante
   - 2.·. Vig.·. = Segundo Vigilante

3. **ESTRUTURA OFICIAL DA ATA (seguir esta ordem exata):**
   a) **CABEÇALHO:** Nome da Loja, Oriente, data por extenso, tipo de sessão e grau.
   b) **ABERTURA:** Descrição formal da abertura dos trabalhos pelo V.·.M.·.
   c) **LEITURA DA ATA ANTERIOR:** Menção à aprovação ou ressalvas.
   d) **EXPEDIENTE:** Correspondências recebidas e enviadas.
   e) **SACO DE PROPOSTAS E INFORMAÇÕES:** Propostas de filiação, aumento de salário, etc.
   f) **ORDEM DO DIA:** Pauta principal da sessão (palestras, rituais, votações).
   g) **TRONCO DE BENEFICÊNCIA / TRONCO DE SOLIDARIEDADE:** Coleta e valor total.
   h) **PALAVRA A BEM DA ORDEM EM GERAL E DA ORDEM EM PARTICULAR:** Manifestações dos IIr.·.
   i) **ENCERRAMENTO:** Descrição formal do encerramento pelo V.·.M.·.
   j) **ASSINATURAS:** Indicação dos blocos V.·.M.·., Orador e Secretário.

4. **PROTEÇÃO DE DADOS PESSOAIS (PII):**
   - Valores monetários explícitos (ex: "R$ 15.000,00 no banco") → substituir por "[DADOS SENSÍVEIS OMITIDOS PARA PRESERVAÇÃO]"
   - Dados médicos detalhados de IIr.·. → substituir por "[DADOS SENSÍVEIS OMITIDOS PARA PRESERVAÇÃO]"
   - Detalhes bancários (agência, conta, senha) → substituir por "[DADOS SENSÍVEIS OMITIDOS PARA PRESERVAÇÃO]"
   - Endereços residenciais completos → substituir por "[DADOS SENSÍVEIS OMITIDOS PARA PRESERVAÇÃO]"
   - MANTER: nomes de IIr.·., cargos, datas, horários, valores de beneficência coletados em sessão.

5. **FORMATAÇÃO:**
   - Parágrafos completos e bem estruturados (não usar bullet points no corpo da ata).
   - Números por extenso quando inferiores a dez, exceto horas e datas.
   - Horários no formato "às 19h30" ou "às vinte horas".
   - Datas por extenso: "aos dezenove dias do mês de março de dois mil e vinte e seis".

6. **IDENTIFICAÇÃO DE FALANTES:**
   - "Venerável Mestre" na transcrição = V.·.M.·. na ata
   - "Colunas" na transcrição = indicar como intervenção das Colunas ou identificar o Ir.·. pelo contexto.

## IMPORTANTE:
- NÃO invente informações que não estejam na transcrição.
- Se algo estiver inaudível ou incompreensível, indique: "[trecho inaudível]".
- Mantenha fidelidade ao conteúdo, apenas formalizando a linguagem.
"""


def format_ata(
    raw_transcript: str,
    template_type: str,
    gemini_api_key: str,
) -> str:
    """
    Envia a transcrição bruta ao Gemini 1.5 Flash e retorna a ata formatada.

    Args:
        raw_transcript: Texto da transcrição mesclada com timestamps e falantes.
        template_type: Tipo de sessão selecionado pelo usuário.
        gemini_api_key: Chave da API Gemini (Google AI Studio).

    Returns:
        Texto da ata formatada segundo o rito maçônico.

    Raises:
        ValueError: Se a transcrição estiver vazia.
        RuntimeError: Se a API retornar erro.
    """
    if not raw_transcript.strip():
        raise ValueError("A transcrição enviada ao Gemini está vazia.")

    template_desc = TEMPLATES.get(template_type, template_type)

    client = genai.Client(api_key=gemini_api_key)

    user_prompt = (
        f"## TIPO DE SESSÃO: {template_desc}\n\n"
        f"## TRANSCRIÇÃO BRUTA:\n\n{raw_transcript}\n\n"
        "---\n"
        "Com base na transcrição acima, redija a Ata completa da sessão "
        "seguindo rigorosamente todas as regras do System Prompt."
    )

    logger.info(
        "Enviando transcrição ao Gemini 1.5 Flash (%d caracteres, template: %s).",
        len(raw_transcript),
        template_type,
    )

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
                max_output_tokens=8192,
            ),
        )

        ata_text = response.text
        if not ata_text:
            raise RuntimeError("Gemini retornou resposta vazia.")

        logger.info("Ata gerada com sucesso pelo Gemini (%d caracteres).", len(ata_text))
        return ata_text

    except Exception as exc:
        logger.error("Erro na chamada ao Gemini: %s", exc)
        raise RuntimeError(f"Falha ao gerar ata via Gemini: {exc}") from exc

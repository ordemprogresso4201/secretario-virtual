"""
Secretaria Digital IA — Interface Streamlit para automação de atas maçônicas.

Este módulo é o ponto de entrada da aplicação. Ele orquestra o pipeline completo:
Upload → Split FFMPEG → Transcrição Groq → Formatação Gemini → PDF → Drive/Calendar.

Segue o princípio de stateless: todos os arquivos temporários são armazenados em /tmp/
e removidos via garbage collection no bloco finally.
"""

import logging
import os
from datetime import datetime

import streamlit as st

from core.audio_engine import (
    format_merged_transcript,
    split_stereo_channels,
    transcribe_channels,
)
from core.gcp_services import patch_calendar_event, upload_to_drive
from core.llm_agent import TEMPLATES, format_ata
from core.pdf_builder import generate_pdf

# --- Configuração de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# --- Arquivos temporários rastreados para garbage collection ---
_TEMP_FILES: list[str] = []


def _register_temp_file(path: str) -> None:
    """Registra um arquivo temporário para limpeza posterior."""
    if path and path not in _TEMP_FILES:
        _TEMP_FILES.append(path)


def _cleanup_temp_files() -> None:
    """Remove todos os arquivos temporários registrados de /tmp/."""
    for path in _TEMP_FILES:
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("Arquivo temporário removido: %s", path)
        except OSError as exc:
            logger.warning("Falha ao remover %s: %s", path, exc)
    _TEMP_FILES.clear()


def _validate_env_vars() -> dict[str, str]:
    """
    Valida e retorna as variáveis de ambiente necessárias.

    Returns:
        Dicionário com as variáveis validadas.

    Raises:
        Exibe erros na UI do Streamlit caso variáveis estejam ausentes.
    """
    required_vars = {
        "GROQ_API_KEY": "Chave da API Groq para transcrição de áudio (STT)",
        "GEMINI_API_KEY": "Chave da API Gemini para formatação da ata (LLM)",
    }

    optional_vars = {
        "DRIVE_FOLDER_ID": "ID da pasta de destino no Google Drive",
        "CALENDAR_ID": "ID do calendário do Google para atualização de eventos",
    }

    env: dict[str, str] = {}
    missing: list[str] = []

    for var, desc in required_vars.items():
        value = os.environ.get(var, "")
        if not value:
            missing.append(f"**`{var}`**: {desc}")
        else:
            env[var] = value

    for var, desc in optional_vars.items():
        value = os.environ.get(var, "")
        env[var] = value  # Pode ser vazio (opcional)

    if missing:
        st.error("⚠️ **Variáveis de ambiente obrigatórias não configuradas:**")
        for item in missing:
            st.markdown(f"- {item}")
        st.info(
            "💡 Configure-as no Cloud Run via "
            "`gcloud run services update` ou no painel do Console GCP."
        )
        st.stop()

    return env


def _inject_custom_css() -> None:
    """Injeta CSS personalizado para ocultar menus nativos e melhorar a UI."""
    st.markdown(
        """
        <style>
            /* Oculta menus nativos do Streamlit */
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}

            /* Estilo do container principal */
            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
            }

            /* Estilo personalizado para o título */
            .main-title {
                text-align: center;
                color: #1a1a2e;
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 0.2rem;
            }

            .main-subtitle {
                text-align: center;
                color: #666;
                font-size: 1rem;
                margin-bottom: 2rem;
            }

            /* Cards de status */
            .stStatus > div {
                border-radius: 8px;
            }

            /* Upload area */
            .stFileUploader > div {
                border-radius: 8px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_header() -> None:
    """Renderiza o cabeçalho da aplicação."""
    st.markdown(
        '<p class="main-title">⚒️ Secretaria Digital IA</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="main-subtitle">'
        "Automação Inteligente de Atas Maçônicas · Powered by Gemini & Groq"
        "</p>",
        unsafe_allow_html=True,
    )
    st.divider()


def _render_sidebar() -> tuple[str, bool, bool]:
    """
    Renderiza a barra lateral com configurações.

    Returns:
        Tupla com (template_selecionado, habilitar_drive, habilitar_calendar).
    """
    with st.sidebar:
        st.header("⚙️ Configurações")

        template = st.selectbox(
            "📋 Tipo de Sessão",
            options=list(TEMPLATES.keys()),
            help="Selecione o tipo de sessão maçônica para a ata.",
        )

        st.divider()

        st.subheader("🔗 Integrações Google")

        enable_drive = st.checkbox(
            "📁 Upload para Google Drive",
            value=True,
            help="Envia o PDF para a pasta configurada no Drive.",
        )

        enable_calendar = st.checkbox(
            "📅 Atualizar Google Calendar",
            value=True,
            help="Adiciona o link da ata no evento do dia.",
        )

        st.divider()
        st.caption("v1.0.0 · Cloud Run Serverless")

    return template, enable_drive, enable_calendar


def _run_pipeline(
    uploaded_file: object,
    template: str,
    env: dict[str, str],
    enable_drive: bool,
    enable_calendar: bool,
) -> None:
    """
    Executa o pipeline completo de processamento de ata.

    Args:
        uploaded_file: Arquivo de áudio carregado pelo Streamlit.
        template: Tipo de sessão selecionado.
        env: Variáveis de ambiente validadas.
        enable_drive: Se True, faz upload para o Drive.
        enable_calendar: Se True, atualiza o Calendar.
    """
    # Caminhos temporários
    input_path = f"/tmp/upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    left_path = "/tmp/left_vm.mp3"
    right_path = "/tmp/right_col.mp3"
    pdf_path = "/tmp/ata.pdf"

    # Registra TODOS os arquivos temporários para garbage collection
    _register_temp_file(input_path)
    _register_temp_file(left_path)
    _register_temp_file(right_path)
    _register_temp_file(pdf_path)

    try:
        with st.status("🔄 Processando Sessão...", expanded=True) as status:

            # --- STEP 1: Salvar upload em /tmp/ ---
            st.write("📥 Salvando arquivo de áudio...")
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            logger.info("Áudio salvo em: %s", input_path)

            # --- STEP 2: Separar canais FFMPEG ---
            st.write("🎧 Extraindo canais estéreo via FFMPEG...")
            left_result, right_result = split_stereo_channels(input_path)
            logger.info("Canais extraídos: L=%s, R=%s", left_result, right_result)

            # --- STEP 3: Transcrição Groq (paralela) ---
            st.write("🎙️ Transcrevendo canais L e R via Groq Whisper...")
            segments = transcribe_channels(
                left_result, right_result, env["GROQ_API_KEY"]
            )
            merged_text = format_merged_transcript(segments)
            st.write(f"✅ Transcrição concluída: **{len(segments)}** segmentos.")
            logger.info("Transcrição: %d segmentos mesclados.", len(segments))

            # --- STEP 4: Formatação LLM (Gemini) ---
            st.write("🤖 Gemini formatando liturgia maçônica...")
            ata_text = format_ata(merged_text, template, env["GEMINI_API_KEY"])
            st.write(f"✅ Ata gerada: **{len(ata_text)}** caracteres.")

            # --- STEP 5: Geração de PDF ---
            st.write("📄 Gerando PDF com ReportLab...")
            pdf_output = generate_pdf(ata_text, template, pdf_path)
            logger.info("PDF gerado: %s", pdf_output)

            # --- STEP 6: Google Drive (opcional) ---
            web_view_link = ""
            if enable_drive and env.get("DRIVE_FOLDER_ID"):
                st.write("☁️ Sincronizando com Google Drive...")
                filename = (
                    f"Ata_{template.replace(' ', '_')}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                )
                web_view_link = upload_to_drive(
                    pdf_output, filename, env["DRIVE_FOLDER_ID"]
                )
                st.write("✅ Upload concluído!")
            elif enable_drive:
                st.write("⚠️ `DRIVE_FOLDER_ID` não configurado. Upload ignorado.")

            # --- STEP 7: Google Calendar (opcional) ---
            calendar_result = ""
            if enable_calendar and env.get("CALENDAR_ID") and web_view_link:
                st.write("📅 Atualizando Google Calendar...")
                calendar_result = patch_calendar_event(
                    env["CALENDAR_ID"], web_view_link
                )
                st.write(f"✅ {calendar_result}")
            elif enable_calendar and not web_view_link:
                st.write(
                    "⚠️ Calendar não atualizado: link do Drive não disponível."
                )

            status.update(label="✅ Sessão processada com sucesso!", state="complete")

        # --- Resultados finais ---
        st.balloons()

        st.success("🎉 **Ata gerada com sucesso!**")

        # Link do Drive
        if web_view_link:
            st.markdown(
                f"📁 **Link do Drive:** [Abrir Ata no Google Drive]({web_view_link})"
            )

        # Prévia da ata
        with st.expander("📝 Prévia da Ata (texto)", expanded=False):
            st.text_area(
                "Conteúdo da Ata",
                value=ata_text,
                height=400,
                disabled=True,
                label_visibility="collapsed",
            )

        # Download do PDF
        if os.path.exists(pdf_output):
            with open(pdf_output, "rb") as pdf_file:
                st.download_button(
                    label="⬇️ Baixar PDF da Ata",
                    data=pdf_file.read(),
                    file_name=f"Ata_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )

    except FileNotFoundError as exc:
        st.error(f"❌ **Arquivo não encontrado:** {exc}")
        logger.error("FileNotFoundError: %s", exc)

    except RuntimeError as exc:
        st.error(f"❌ **Erro no processamento:** {exc}")
        logger.error("RuntimeError: %s", exc)

    except ValueError as exc:
        st.error(f"❌ **Erro de validação:** {exc}")
        logger.error("ValueError: %s", exc)

    except Exception as exc:
        st.error(f"❌ **Erro inesperado:** {exc}")
        logger.exception("Erro não tratado no pipeline.")

    finally:
        # --- GARBAGE COLLECTION CRÍTICO ---
        _cleanup_temp_files()
        logger.info("Garbage collection executado. /tmp/ limpo.")


def main() -> None:
    """Ponto de entrada principal da aplicação Streamlit."""
    st.set_page_config(
        page_title="Secretaria Digital IA",
        page_icon="⚒️",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    _inject_custom_css()
    _render_header()

    # Validação de ambiente
    env = _validate_env_vars()

    # Sidebar
    template, enable_drive, enable_calendar = _render_sidebar()

    # Upload de áudio
    st.subheader("🎵 Upload do Áudio da Sessão")
    uploaded_file = st.file_uploader(
        "Selecione o arquivo de áudio estéreo da sessão",
        type=["mp3", "wav", "m4a", "ogg"],
        help="O áudio deve ser estéreo: canal esquerdo = V.·.M.·., canal direito = Colunas.",
    )

    if uploaded_file is not None:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        st.info(
            f"📎 **{uploaded_file.name}** ({file_size_mb:.1f} MB) "
            f"· Template: **{template}**"
        )

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            process_button = st.button(
                "⚡ Gerar Ata",
                type="primary",
                use_container_width=True,
            )

        if process_button:
            _run_pipeline(uploaded_file, template, env, enable_drive, enable_calendar)
    else:
        # Estado inicial
        st.info(
            "☝️ Faça o upload de um arquivo de áudio estéreo para iniciar o processamento."
        )

        with st.expander("ℹ️ Como funciona?", expanded=False):
            st.markdown(
                """
                1. **Upload** — Suba o áudio estéreo da sessão (.mp3, .wav, .m4a, .ogg)
                2. **Separação** — FFMPEG divide L (V.·.M.·.) e R (Colunas)
                3. **Transcrição** — Groq Whisper transcreve ambos os canais em paralelo
                4. **Formatação** — Gemini 1.5 Flash redige a ata no formato litúrgico oficial
                5. **PDF** — ReportLab gera o documento justificado com assinaturas
                6. **Drive & Calendar** — Upload automático e notificação aos IIr.·.
                """
            )


if __name__ == "__main__":
    main()

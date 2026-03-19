"""
LÚMEN — Secretaria Digital Autônoma.

Interface dark com pipeline: Upload → FFMPEG → Groq → Gemini → PDF → GCP.
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
from core.llm_agent import SYSTEM_PROMPT, TEMPLATES, format_ata
from core.pdf_builder import generate_pdf

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

_TEMP_FILES: list[str] = []


def _register_temp(path: str) -> None:
    if path and path not in _TEMP_FILES:
        _TEMP_FILES.append(path)


def _cleanup_temp() -> None:
    for path in _TEMP_FILES:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
    _TEMP_FILES.clear()


def _validate_env() -> dict[str, str]:
    required = {
        "GROQ_API_KEY": "Chave da API Groq (STT)",
        "GEMINI_API_KEY": "Chave da API Gemini (LLM)",
    }
    optional = {"DRIVE_FOLDER_ID": "", "CALENDAR_ID": ""}

    env: dict[str, str] = {}
    missing: list[str] = []

    for var, desc in required.items():
        val = os.environ.get(var, "")
        if not val:
            missing.append(f"**`{var}`**: {desc}")
        else:
            env[var] = val

    for var in optional:
        env[var] = os.environ.get(var, "")

    if missing:
        st.error("Variáveis de ambiente não configuradas:")
        for m in missing:
            st.markdown(f"- {m}")
        st.stop()

    return env


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSS INJECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _inject_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    *, *::before, *::after { box-sizing: border-box; }

    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stAppViewBlockContainer"] {
        background-color: #050507 !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* Aurora glow */
    .stApp::before {
        content: '';
        position: fixed;
        top: -20%; left: -10%;
        width: 600px; height: 600px;
        background: rgba(99, 102, 241, 0.12);
        border-radius: 50%;
        filter: blur(120px);
        pointer-events: none;
        z-index: 0;
        animation: pulseOrb 8s ease-in-out infinite;
    }
    .stApp::after {
        content: '';
        position: fixed;
        bottom: -20%; right: -10%;
        width: 600px; height: 600px;
        background: rgba(217, 119, 6, 0.07);
        border-radius: 50%;
        filter: blur(150px);
        pointer-events: none;
        z-index: 0;
    }
    @keyframes pulseOrb {
        0%, 100% { opacity: 0.6; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.05); }
    }

    /* Hide Streamlit chrome */
    #MainMenu, footer, header,
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    .stDeployButton { display: none !important; }

    .block-container {
        max-width: 1280px !important;
        padding: 1.5rem 2rem !important;
    }

    /* File uploader */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        background: rgba(0, 0, 0, 0.1) !important;
        transition: all 0.3s ease !important;
        padding: 1rem !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(99, 102, 241, 0.3) !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        border: none !important;
    }

    /* Primary button */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #4f46e5, #6366f1) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 0.875rem 2rem !important;
        font-weight: 700 !important;
        font-size: 1rem !important;
        box-shadow: 0 0 30px rgba(79, 70, 229, 0.25) !important;
        transition: all 0.3s ease !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background: linear-gradient(135deg, #6366f1, #818cf8) !important;
        box-shadow: 0 0 40px rgba(79, 70, 229, 0.4) !important;
        transform: translateY(-2px) !important;
    }

    /* Secondary button */
    .stButton > button:not([kind="primary"]) {
        background: rgba(255, 255, 255, 0.03) !important;
        color: #94a3b8 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
    }

    /* Download button */
    .stDownloadButton > button {
        background: rgba(99, 102, 241, 0.1) !important;
        color: #818cf8 !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
    }

    /* Selectbox */
    .stSelectbox > div > div {
        background: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* Checkbox */
    .stCheckbox label { color: #94a3b8 !important; }

    /* Status container */
    [data-testid="stStatus"],
    [data-testid="stExpander"] {
        background: rgba(10, 13, 20, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 14px !important;
    }

    /* Text area */
    .stTextArea textarea {
        background: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        color: #cbd5e1 !important;
        font-family: 'Inter', monospace !important;
    }

    /* Alerts */
    .stAlert, [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div {
        background: #0A0D14 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    /* Divider */
    hr { border-color: rgba(255, 255, 255, 0.05) !important; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }

    /* Columns gap */
    [data-testid="stHorizontalBlock"] { gap: 2rem !important; }

    /* ── Tradução do File Uploader para PT-BR ── */
    [data-testid="stFileUploaderDropzoneInstructions"] div:has(> small)::before {
        content: "Arraste e solte o arquivo aqui";
        font-size: 0.9rem;
        display: block;
        color: #94a3b8;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] span {
        font-size: 0 !important;
        visibility: hidden;
        position: absolute;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] small {
        font-size: 0 !important;
        visibility: hidden;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] small::before {
        content: "Limite de 200MB por arquivo";
        font-size: 0.75rem;
        visibility: visible;
        color: #475569;
    }
    [data-testid="stFileUploaderDropzone"] button {
        font-size: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "Selecionar arquivo";
        font-size: 0.9rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_header() -> None:
    """Cabeçalho LÚMEN com badge de status."""
    hdr_left, hdr_right = st.columns([8, 4])
    with hdr_left:
        st.markdown(
            "<h1 style='margin:0; font-size:2rem; font-weight:700; color:#fff;'>"
            "✦ LÚMEN"
            "<span style='color:#818cf8; font-weight:300;'> Secretaria Digital</span>"
            "</h1>",
            unsafe_allow_html=True,
        )
    with hdr_right:
        st.markdown(
            "<div style='text-align:right; padding-top:0.5rem;'>"
            "<span style='background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.25); "
            "color:#34d399; padding:6px 16px; border-radius:20px; font-size:0.75rem; "
            "font-weight:600; letter-spacing:0.05em;'>● Conectado</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    st.markdown("<hr style='margin:0.75rem 0 1.5rem 0;'>", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP_LABELS = [
    ("Separação de Canais", "Identificando e isolando canais do áudio."),
    ("Transcrição de Áudio", "Convertendo fala em texto com alta precisão."),
    ("Formatação da Ata", "Aplicando estrutura e formato oficial."),
    ("Geração de Documento", "Criando PDF e sincronizando com Google."),
]


def _run_pipeline(
    uploaded_file: object,
    template: str,
    env: dict[str, str],
    enable_drive: bool,
    enable_calendar: bool,
    log_container,
    custom_prompt: str = "",
) -> None:
    input_path = f"/tmp/upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    left_path = "/tmp/left_vm.mp3"
    right_path = "/tmp/right_col.mp3"
    pdf_path = "/tmp/ata.pdf"

    # Registrar apenas arquivos intermediários (NÃO o PDF final)
    for p in [input_path, left_path, right_path]:
        _register_temp(p)

    # Limpar qualquer estado anterior de erro
    st.session_state.pop("pipeline_error", None)
    st.session_state.pop("pipeline_done", None)

    try:
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        logger.info("Áudio salvo: %s", input_path)

        # ── Progresso no painel direito ──
        with log_container:
            st.markdown(
                "<p style='color:#64748b; font-size:0.7rem; font-weight:700; "
                "letter-spacing:0.1em; text-transform:uppercase; margin-bottom:1rem;'>"
                "🛡️ Progresso</p>",
                unsafe_allow_html=True,
            )

            progress_bar = st.progress(0, text="Iniciando processamento...")
            status_steps = st.status("Processando áudio...", expanded=True)

        # STEP 1 — Separação de canais
        with status_steps:
            st.write("🎧 **Separação de Canais** — Identificando canais do áudio...")
        progress_bar.progress(10, text="Separando canais...")
        left_result, right_result = split_stereo_channels(input_path)
        with status_steps:
            st.write("✅ Canais separados com sucesso.")
        progress_bar.progress(25, text="Canais separados.")

        # STEP 2 — Transcrição
        with status_steps:
            st.write("🎙️ **Transcrição de Áudio** — Convertendo fala em texto...")
        progress_bar.progress(30, text="Transcrevendo áudio...")
        segments = transcribe_channels(left_result, right_result, env["GROQ_API_KEY"])
        merged_text = format_merged_transcript(segments)
        with status_steps:
            st.write(f"✅ Transcrição concluída ({len(segments)} segmentos).")
        progress_bar.progress(50, text="Transcrição concluída.")

        # STEP 3 — Formatação com Gemini
        with status_steps:
            st.write("📝 **Formatação da Ata** — Aplicando estrutura oficial...")
        progress_bar.progress(55, text="Formatando ata com IA...")
        ata_text = format_ata(merged_text, template, env["GEMINI_API_KEY"], custom_prompt=custom_prompt)
        with status_steps:
            st.write(f"✅ Ata formatada ({len(ata_text)} caracteres).")
        progress_bar.progress(75, text="Ata formatada.")

        # STEP 4 — PDF + Google
        with status_steps:
            st.write("📄 **Geração de Documento** — Criando PDF e sincronizando...")
        progress_bar.progress(80, text="Gerando PDF...")
        pdf_output = generate_pdf(ata_text, template, pdf_path)

        # ── REGRA DE OURO: Salvar bytes do PDF ANTES de qualquer cleanup ──
        pdf_bytes = b""
        if pdf_output and os.path.exists(pdf_output):
            with open(pdf_output, "rb") as f:
                pdf_bytes = f.read()
            logger.info("PDF salvo em memória (%d bytes).", len(pdf_bytes))

        web_view_link = ""
        if enable_drive and env.get("DRIVE_FOLDER_ID"):
            try:
                filename = f"Ata_{template.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                web_view_link = upload_to_drive(pdf_output, filename, env["DRIVE_FOLDER_ID"])
                with status_steps:
                    st.write("✅ PDF enviado para o Google Drive.")
            except Exception as drive_exc:
                logger.warning("Falha no upload ao Drive (não crítico): %s", drive_exc)
                with status_steps:
                    st.write(f"⚠️ Falha ao enviar para o Drive: {drive_exc}")

        if enable_calendar and env.get("CALENDAR_ID") and web_view_link:
            try:
                patch_calendar_event(env["CALENDAR_ID"], web_view_link)
                with status_steps:
                    st.write("✅ Agenda do Google atualizada.")
            except Exception as cal_exc:
                logger.warning("Falha ao atualizar agenda (não crítico): %s", cal_exc)
                with status_steps:
                    st.write(f"⚠️ Falha ao atualizar agenda: {cal_exc}")

        progress_bar.progress(100, text="Concluído!")

        with status_steps:
            st.write("---")
            st.write("🎉 **Processamento finalizado com sucesso!**")

        status_steps.update(label="✅ Processamento concluído!", state="complete")

        # ── Persistir resultados no session_state (REGRA DE OURO) ──
        st.session_state["pipeline_done"] = True
        st.session_state["ata_text"] = ata_text
        st.session_state["pdf_bytes"] = pdf_bytes
        st.session_state["pdf_filename"] = f"Ata_{template.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        st.session_state["drive_link"] = web_view_link
        st.session_state["segments_count"] = len(segments)

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Erro no pipeline: %s", error_msg)

        # ── Persistir erro no session_state para exibição garantida ──
        st.session_state["pipeline_error"] = error_msg
        st.session_state["pipeline_done"] = False

        try:
            progress_bar.progress(0, text="Erro no processamento!")
            status_steps.update(label="❌ Erro no processamento", state="error")
            with status_steps:
                st.error(f"**Detalhes do erro:** {error_msg}")
        except Exception:
            pass  # UI elements may not exist if error was early

    finally:
        _cleanup_temp()
        # Limpar PDF temporário também
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except OSError:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _render_sidebar(env: dict[str, str]) -> dict[str, str]:
    """Sidebar com configurações de templates e prompt do sistema."""
    with st.sidebar:
        st.markdown(
            "<h2 style='margin:0; font-size:1.3rem; font-weight:700; color:#fff;'>"
            "⚙️ Configurações</h2>",
            unsafe_allow_html=True,
        )
        st.markdown("<hr style='margin:0.5rem 0 1rem 0;'>", unsafe_allow_html=True)

        # ── Gerenciar Templates ──
        st.markdown(
            "<p style='color:#818cf8; font-size:0.75rem; font-weight:700; "
            "letter-spacing:0.08em; text-transform:uppercase; margin-bottom:0.5rem;'>"
            "📋 Tipos de Sessão</p>",
            unsafe_allow_html=True,
        )

        # Inicializar templates editáveis no session_state
        if "custom_templates" not in st.session_state:
            st.session_state["custom_templates"] = dict(TEMPLATES)

        current_templates = st.session_state["custom_templates"]

        # Exibir templates existentes
        templates_to_remove = []
        for key, value in current_templates.items():
            with st.expander(f"📄 {key}", expanded=False):
                new_value = st.text_input(
                    "Descrição completa",
                    value=value,
                    key=f"tpl_{key}",
                    label_visibility="collapsed",
                )
                if new_value != value:
                    current_templates[key] = new_value
                if st.button("🗑️ Remover", key=f"del_{key}", use_container_width=True):
                    templates_to_remove.append(key)

        for k in templates_to_remove:
            current_templates.pop(k, None)
            st.rerun()

        # Adicionar novo template
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        with st.expander("➕ Adicionar novo tipo", expanded=False):
            new_key = st.text_input("Nome (exibição)", placeholder="Ex: Sessão Econômica")
            new_val = st.text_input("Descrição", placeholder="Ex: Sessão Econômica Ordinária")
            if st.button("✅ Adicionar", use_container_width=True) and new_key and new_val:
                current_templates[new_key] = new_val
                st.rerun()

        st.session_state["custom_templates"] = current_templates

        st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

        # ── Prompt do Sistema (Regras de Formatação) ──
        st.markdown(
            "<p style='color:#818cf8; font-size:0.75rem; font-weight:700; "
            "letter-spacing:0.08em; text-transform:uppercase; margin-bottom:0.5rem;'>"
            "✏️ Regras de Formatação</p>",
            unsafe_allow_html=True,
        )
        st.caption("Edite o prompt enviado à IA para ajustar o formato da ata.")

        if "custom_prompt" not in st.session_state:
            st.session_state["custom_prompt"] = SYSTEM_PROMPT

        edited_prompt = st.text_area(
            "Prompt do Sistema",
            value=st.session_state["custom_prompt"],
            height=400,
            label_visibility="collapsed",
        )
        st.session_state["custom_prompt"] = edited_prompt

        col_reset, col_info = st.columns(2)
        with col_reset:
            if st.button("🔄 Restaurar padrão", use_container_width=True):
                st.session_state["custom_prompt"] = SYSTEM_PROMPT
                st.rerun()
        with col_info:
            st.caption(f"{len(edited_prompt)} caracteres")

        st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

        # ── Info do Ambiente ──
        st.markdown(
            "<p style='color:#818cf8; font-size:0.75rem; font-weight:700; "
            "letter-spacing:0.08em; text-transform:uppercase; margin-bottom:0.5rem;'>"
            "🔗 Integrações</p>",
            unsafe_allow_html=True,
        )
        st.caption(f"Groq API: {'✅ Configurada' if env.get('GROQ_API_KEY') else '❌'}")
        st.caption(f"Gemini API: {'✅ Configurada' if env.get('GEMINI_API_KEY') else '❌'}")
        st.caption(f"Drive: {'✅ ' + env.get('DRIVE_FOLDER_ID', '')[:8] + '...' if env.get('DRIVE_FOLDER_ID') else '❌ Não configurado'}")
        st.caption(f"Agenda: {'✅ Configurada' if env.get('CALENDAR_ID') else '❌ Não configurada'}")

    return current_templates


def main() -> None:
    st.set_page_config(
        page_title="LÚMEN · Secretaria Digital",
        page_icon="✦",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _inject_css()
    env = _validate_env()

    # Sidebar de configurações
    active_templates = _render_sidebar(env)

    _render_header()

    # ── Layout duas colunas ──
    col_left, col_right = st.columns([7, 5], gap="large")

    with col_left:
        # ── Tipo de Sessão ──
        st.markdown(
            "<p style='color:#64748b; font-size:0.7rem; font-weight:700; "
            "letter-spacing:0.1em; text-transform:uppercase; margin-bottom:0.5rem;'>"
            "📜 Tipo de Sessão</p>",
            unsafe_allow_html=True,
        )

        template = st.selectbox(
            "Tipo de Sessão",
            options=list(active_templates.keys()),
            label_visibility="collapsed",
        )

        st.markdown("<div style='height:0.75rem;'></div>", unsafe_allow_html=True)

        # ── Integrações ──
        opt1, opt2 = st.columns(2)
        with opt1:
            enable_drive = st.checkbox("📁 Enviar para Google Drive", value=True)
        with opt2:
            enable_calendar = st.checkbox("📅 Atualizar Agenda", value=True)

        st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

        # ── Upload ──
        st.markdown(
            "<p style='color:#64748b; font-size:0.7rem; font-weight:700; "
            "letter-spacing:0.1em; text-transform:uppercase; margin-bottom:0.5rem;'>"
            "🎙️ Envio de Áudio</p>",
            unsafe_allow_html=True,
        )

        uploaded_file = st.file_uploader(
            "Selecione o arquivo de áudio",
            type=["mp3", "wav", "m4a", "ogg"],
            help="Canal esquerdo = V∴M∴ · Canal direito = Colunas. Áudio mono também é suportado.",
            label_visibility="collapsed",
        )

        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        # ── Mensagem de erro persistente (REGRA DE OURO) ──
        if st.session_state.get("pipeline_error"):
            st.error(f"❌ **Erro no último processamento:** {st.session_state['pipeline_error']}")
            if st.button("🔄 Tentar novamente", use_container_width=True):
                st.session_state.pop("pipeline_error", None)
                st.rerun()

        # ── Resultados ──
        if st.session_state.get("pipeline_done"):
            ata_text = st.session_state.get("ata_text", "")
            pdf_bytes = st.session_state.get("pdf_bytes", b"")
            pdf_filename = st.session_state.get("pdf_filename", "Ata.pdf")
            drive_link = st.session_state.get("drive_link", "")
            seg_count = st.session_state.get("segments_count", 0)

            st.success("✅ **Documento gerado com sucesso!** A ata foi redigida e está disponível para download.")

            # ── Download do PDF (SEMPRE disponível) ──
            if pdf_bytes:
                st.download_button(
                    "⬇️ Baixar PDF da Ata",
                    data=pdf_bytes,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.warning("⚠️ O PDF não pôde ser gerado. Verifique os logs.")

            with st.expander(f"📝 Prévia da Ata ({len(ata_text)} caracteres, {seg_count} segmentos)"):
                st.text_area(
                    "Conteúdo da Ata",
                    value=ata_text,
                    height=300,
                    disabled=True,
                    label_visibility="collapsed",
                )

            if drive_link:
                st.link_button(
                    "📁 Abrir no Google Drive",
                    url=drive_link,
                    use_container_width=True,
                )

            st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Processar novo áudio", use_container_width=True):
                for key in ["pipeline_done", "ata_text", "pdf_bytes",
                            "pdf_filename", "drive_link", "segments_count",
                            "pipeline_error"]:
                    st.session_state.pop(key, None)
                st.rerun()

        elif uploaded_file is not None:
            file_mb = uploaded_file.size / (1024 * 1024)
            st.info(
                f"📎 **{uploaded_file.name}** ({file_mb:.1f} MB) · {template}"
            )

            process = st.button(
                "✦  Iniciar Processamento",
                type="primary",
                use_container_width=True,
            )

            if process:
                st.session_state["pipeline_done"] = False
                st.session_state.pop("pipeline_error", None)
                _run_pipeline(
                    uploaded_file, template, env,
                    enable_drive, enable_calendar,
                    col_right.container(),
                    custom_prompt=st.session_state.get("custom_prompt", ""),
                )
                # Rerun SOMENTE se pipeline teve sucesso (para exibir download)
                # Se houve erro, NÃO fazer rerun (erro já visível na tela)
                if st.session_state.get("pipeline_done"):
                    st.rerun()

    with col_right:
        if not st.session_state.get("pipeline_done"):
            st.markdown(
                "<p style='color:#64748b; font-size:0.7rem; font-weight:700; "
                "letter-spacing:0.1em; text-transform:uppercase; margin-bottom:1rem;'>"
                "🛡️ Progresso</p>",
                unsafe_allow_html=True,
            )

            for label, desc in STEP_LABELS:
                st.markdown(
                    f"<div style='padding:0.75rem 1rem; margin-bottom:0.5rem; "
                    f"background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); "
                    f"border-radius:12px; opacity:0.35;'>"
                    f"<div style='font-size:0.85rem; font-weight:600; color:#e2e8f0;'>⬡ {label}</div>"
                    f"<div style='font-size:0.75rem; color:#64748b; margin-top:2px;'>{desc}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                "<p style='text-align:center; color:#475569; font-size:0.8rem; margin-top:2rem;'>"
                "Aguardando envio de áudio para iniciar.</p>",
                unsafe_allow_html=True,
            )

        else:
            # Show completed state
            drive_link = st.session_state.get("drive_link", "")
            st.markdown(
                "<p style='color:#64748b; font-size:0.7rem; font-weight:700; "
                "letter-spacing:0.1em; text-transform:uppercase; margin-bottom:1rem;'>"
                "🛡️ Progresso</p>",
                unsafe_allow_html=True,
            )

            for label, _ in STEP_LABELS:
                st.markdown(
                    f"<div style='padding:0.75rem 1rem; margin-bottom:0.5rem; "
                    f"background:rgba(16,185,129,0.05); border:1px solid rgba(16,185,129,0.15); "
                    f"border-radius:12px;'>"
                    f"<div style='font-size:0.85rem; font-weight:600; color:#34d399;'>✓ {label}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                "<p style='text-align:center; color:#34d399; font-size:0.85rem; "
                "margin-top:1.5rem; font-weight:600;'>"
                "✅ Todas as etapas concluídas</p>",
                unsafe_allow_html=True,
            )

    # Footer
    st.markdown(
        "<p style='text-align:center; color:#334155; font-size:0.7rem; margin-top:2rem;'>"
        "LÚMEN v1.1 · Processamento em nuvem</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

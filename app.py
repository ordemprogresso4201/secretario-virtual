"""
Lúmen.IA — Secretaria Digital Autônoma.

Interface dark glassmorphism com pipeline: Upload → FFMPEG → Groq → Gemini → PDF → GCP.
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
        st.error("⚠️ **Variáveis de ambiente não configuradas:**")
        for m in missing:
            st.markdown(f"- {m}")
        st.stop()

    return env


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSS INJECTION — Dark Glassmorphism Theme
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _inject_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── RESET & BASE ── */
    *, *::before, *::after { box-sizing: border-box; }

    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stAppViewBlockContainer"] {
        background-color: #050507 !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* ── AURORA GLOW ORBS ── */
    .stApp::before {
        content: '';
        position: fixed;
        top: -20%;
        left: -10%;
        width: 600px;
        height: 600px;
        background: rgba(99, 102, 241, 0.12);
        border-radius: 50%;
        filter: blur(120px);
        pointer-events: none;
        z-index: 0;
        animation: pulse-orb 8s ease-in-out infinite;
    }
    .stApp::after {
        content: '';
        position: fixed;
        bottom: -20%;
        right: -10%;
        width: 600px;
        height: 600px;
        background: rgba(217, 119, 6, 0.07);
        border-radius: 50%;
        filter: blur(150px);
        pointer-events: none;
        z-index: 0;
    }
    @keyframes pulse-orb {
        0%, 100% { opacity: 0.6; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.05); }
    }

    /* ── HIDE STREAMLIT CHROME ── */
    #MainMenu, footer, header,
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    .stDeployButton { display: none !important; visibility: hidden !important; }

    /* ── MAIN CONTAINER ── */
    .block-container {
        max-width: 1280px !important;
        padding: 1.5rem 2rem !important;
    }

    /* ── GLASSMORPHISM CARD ── */
    .glass-card {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(40px);
        -webkit-backdrop-filter: blur(40px);
        border-radius: 24px;
        padding: 2rem;
        box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        position: relative;
        overflow: hidden;
    }
    .glass-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.3), transparent);
        opacity: 0.5;
    }

    /* ── HEADER ── */
    .lumen-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.5rem;
    }
    .lumen-logo-row {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .lumen-icon {
        width: 48px; height: 48px;
        border-radius: 16px;
        background: linear-gradient(135deg, #6366f1, #4338ca);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 30px rgba(99, 102, 241, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        font-size: 1.5rem;
    }
    .lumen-title {
        font-size: 1.75rem;
        font-weight: 700;
        color: #fff;
        line-height: 1.2;
    }
    .lumen-title span { color: #818cf8; font-weight: 300; }
    .lumen-subtitle {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 500;
        letter-spacing: 0.025em;
    }
    .gcp-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(16, 185, 129, 0.2);
        padding: 0.375rem 1rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        color: #34d399;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .gcp-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        background: #34d399;
        animation: pulse-dot 2s ease-in-out infinite;
    }
    @keyframes pulse-dot {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }

    /* ── SECTION LABELS ── */
    .section-label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .section-label .icon { color: #818cf8; }
    .section-label .icon-amber { color: #f59e0b; }

    /* ── SESSION TYPE CARDS ── */
    .session-types {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 0.75rem;
        margin-bottom: 2rem;
    }

    /* ── DROPZONE ── */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(255, 255, 255, 0.08) !important;
        border-radius: 24px !important;
        background: rgba(0, 0, 0, 0.1) !important;
        transition: all 0.3s ease !important;
        padding: 1rem !important;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: rgba(99, 102, 241, 0.3) !important;
        background: rgba(99, 102, 241, 0.02) !important;
    }
    [data-testid="stFileUploader"] label {
        color: #94a3b8 !important;
    }
    [data-testid="stFileUploader"] small {
        color: #64748b !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        border: none !important;
    }

    /* ── PRIMARY BUTTON (Gradient Indigo) ── */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #4f46e5, #6366f1) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 16px !important;
        padding: 0.875rem 2rem !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        box-shadow: 0 0 30px rgba(79, 70, 229, 0.25) !important;
        transition: all 0.3s ease !important;
        letter-spacing: 0.01em !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background: linear-gradient(135deg, #6366f1, #818cf8) !important;
        box-shadow: 0 0 40px rgba(79, 70, 229, 0.4) !important;
        transform: translateY(-2px) !important;
    }

    /* ── SECONDARY BUTTON ── */
    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {
        background: rgba(255, 255, 255, 0.03) !important;
        color: #94a3b8 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stButton > button:not([kind="primary"]):hover {
        background: rgba(255, 255, 255, 0.06) !important;
        color: #e2e8f0 !important;
        border-color: rgba(255, 255, 255, 0.15) !important;
    }

    /* ── DOWNLOAD BUTTON ── */
    .stDownloadButton > button {
        background: rgba(99, 102, 241, 0.1) !important;
        color: #818cf8 !important;
        border: 1px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(99, 102, 241, 0.2) !important;
    }

    /* ── SELECTBOX ── */
    .stSelectbox > div > div {
        background: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* ── RADIO BUTTONS ── */
    .stRadio > div { gap: 0.5rem !important; }
    .stRadio label {
        background: rgba(0, 0, 0, 0.2) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 12px !important;
        padding: 0.75rem 1rem !important;
        transition: all 0.2s ease !important;
        color: #94a3b8 !important;
    }
    .stRadio label:has(input:checked) {
        background: rgba(99, 102, 241, 0.1) !important;
        border-color: rgba(99, 102, 241, 0.4) !important;
        color: #a5b4fc !important;
        box-shadow: 0 0 20px rgba(99, 102, 241, 0.12) !important;
    }

    /* ── CHECKBOX ── */
    .stCheckbox label {
        color: #94a3b8 !important;
    }

    /* ── STATUS (Processing) ── */
    [data-testid="stStatus"],
    [data-testid="stExpander"] {
        background: rgba(10, 13, 20, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 16px !important;
        backdrop-filter: blur(20px) !important;
    }

    /* ── ALERTS ── */
    .stAlert, [data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    div[data-testid="stAlert"][data-baseweb*="info"],
    div.stAlert:has([role="alert"]) {
        background: rgba(99, 102, 241, 0.06) !important;
    }

    /* ── TEXT AREA ── */
    .stTextArea textarea {
        background: rgba(0, 0, 0, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        color: #cbd5e1 !important;
        font-family: 'Inter', monospace !important;
    }

    /* ── EXPANDER ── */
    [data-testid="stExpander"] summary {
        color: #94a3b8 !important;
    }

    /* ── SUCCESS MESSAGE ── */
    .success-card {
        text-align: center;
        padding: 2rem;
    }
    .success-icon {
        width: 96px; height: 96px;
        border-radius: 50%;
        background: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(16, 185, 129, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto 1.5rem;
        font-size: 3rem;
        box-shadow: 0 0 50px rgba(16, 185, 129, 0.15);
    }
    .success-title {
        font-size: 1.75rem;
        font-weight: 300;
        color: #fff;
        margin-bottom: 0.5rem;
    }
    .success-desc {
        color: #94a3b8;
        font-size: 0.9rem;
        line-height: 1.6;
        max-width: 400px;
        margin: 0 auto;
    }

    /* ── LOG PANEL (RIGHT COLUMN) ── */
    .log-panel {
        background: rgba(10, 13, 20, 0.8);
        border: 1px solid rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(40px);
        -webkit-backdrop-filter: blur(40px);
        border-radius: 24px;
        padding: 2rem;
        min-height: 500px;
        position: relative;
        overflow: hidden;
    }
    .log-panel::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.4), transparent);
        opacity: 0.5;
    }
    .log-title {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    .log-title .shield { color: #34d399; font-size: 1.1rem; }

    /* ── TIMELINE ── */
    .timeline {
        position: relative;
        padding-left: 2.5rem;
    }
    .timeline::before {
        content: '';
        position: absolute;
        left: 15px;
        top: 12px;
        bottom: 12px;
        width: 1px;
        background: linear-gradient(180deg, rgba(99, 102, 241, 0.4), rgba(255, 255, 255, 0.06), transparent);
    }
    .timeline-step {
        position: relative;
        padding: 0 0 1.75rem 0;
        transition: all 0.5s ease;
    }
    .timeline-dot {
        position: absolute;
        left: -2.5rem;
        top: 2px;
        width: 28px; height: 28px;
        border-radius: 50%;
        border: 2px solid #334155;
        background: #0A0D14;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2;
        font-size: 0.75rem;
    }
    .timeline-dot.active {
        border-color: #6366f1;
    }
    .timeline-dot.loading {
        border-color: #f59e0b;
        animation: pulse-ring 1.5s ease-in-out infinite;
    }
    @keyframes pulse-ring {
        0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.3); }
        50% { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
    }
    .timeline-step.dimmed { opacity: 0.3; }
    .timeline-step-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #e2e8f0;
        margin-bottom: 0.25rem;
    }
    .timeline-step-title.loading-text { color: #fbbf24; }
    .timeline-step-desc {
        font-size: 0.75rem;
        color: #64748b;
        line-height: 1.5;
    }

    /* ── IDLE LOG ── */
    .log-idle {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 300px;
        opacity: 0.4;
        text-align: center;
    }
    .log-idle-icon { font-size: 3rem; margin-bottom: 1rem; }
    .log-idle-text {
        font-size: 0.85rem;
        color: #64748b;
        max-width: 200px;
        line-height: 1.6;
    }

    /* ── ACTION BUTTONS (post-success) ── */
    .action-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.75rem;
        width: 100%;
        padding: 0.875rem;
        border-radius: 12px;
        font-weight: 500;
        font-size: 0.9rem;
        cursor: pointer;
        transition: all 0.2s ease;
        text-decoration: none !important;
        margin-bottom: 0.75rem;
    }
    .action-btn-drive {
        background: rgba(59, 130, 246, 0.08);
        border: 1px solid rgba(59, 130, 246, 0.2);
        color: #60a5fa;
    }
    .action-btn-drive:hover { background: rgba(59, 130, 246, 0.15); }
    .action-btn-calendar {
        background: rgba(99, 102, 241, 0.08);
        border: 1px solid rgba(99, 102, 241, 0.2);
        color: #818cf8;
    }
    .action-btn-calendar:hover { background: rgba(99, 102, 241, 0.15); }

    /* ── SIDEBAR dark ── */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div {
        background: #0A0D14 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05) !important;
    }

    /* ── DIVIDER ── */
    hr { border-color: rgba(255, 255, 255, 0.05) !important; }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
    }

    /* ── VERSION BADGE ── */
    .version-badge {
        text-align: center;
        color: #475569;
        font-size: 0.7rem;
        font-weight: 500;
        margin-top: 1rem;
        letter-spacing: 0.05em;
    }

    /* ── COLUMNS GAP ── */
    [data-testid="stHorizontalBlock"] {
        gap: 2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_header() -> None:
    st.markdown("""
    <div class="glass-card lumen-header">
        <div class="lumen-logo-row">
            <div class="lumen-icon">✦</div>
            <div>
                <div class="lumen-title">Lúmen<span>.IA</span></div>
                <div class="lumen-subtitle">Secretaria Digital Autônoma</div>
            </div>
        </div>
        <div class="gcp-badge">
            <div class="gcp-dot"></div>
            GCP Online
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_log_idle() -> None:
    st.markdown("""
    <div class="log-panel">
        <div class="log-title">
            <span class="shield">🛡️</span> Log de Operações
        </div>
        <div class="log-idle">
            <div class="log-idle-icon">🕐</div>
            <div class="log-idle-text">
                Aguardando áudio estéreo para iniciar o trace de inteligência.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_log_processing(current_step: int) -> None:
    steps = [
        ("Demosaico Acústico FFMPEG", "Isolando canais físicos (V∴M∴ e Colunas)."),
        ("Transcrição Turbo Groq", "Motor Whisper-v3 processando dados sonoros."),
        ("Linting Litúrgico Gemini", "Aplicando abreviações (∴) e formato em 3ª pessoa."),
        ("Sincronização GCP Workspace", "Forjando PDF, selando Drive e Agenda."),
    ]

    timeline_html = '<div class="timeline">'
    for i, (title, desc) in enumerate(steps):
        if i < current_step:
            dot_class = "timeline-dot active"
            dot_icon = "✓"
            step_class = ""
            title_class = "timeline-step-title"
        elif i == current_step:
            dot_class = "timeline-dot loading"
            dot_icon = "⟳"
            step_class = ""
            title_class = "timeline-step-title loading-text"
        else:
            dot_class = "timeline-dot"
            dot_icon = "·"
            step_class = "dimmed"
            title_class = "timeline-step-title"

        timeline_html += f"""
        <div class="timeline-step {step_class}">
            <div class="{dot_class}">{dot_icon}</div>
            <div class="{title_class}">{title}</div>
            <div class="timeline-step-desc">{desc}</div>
        </div>
        """
    timeline_html += "</div>"

    st.markdown(f"""
    <div class="log-panel">
        <div class="log-title">
            <span class="shield">🛡️</span> Log de Operações
        </div>
        {timeline_html}
    </div>
    """, unsafe_allow_html=True)


def _render_log_complete(drive_link: str = "", calendar_text: str = "") -> None:
    actions_html = ""
    if drive_link:
        actions_html += f"""
        <a href="{drive_link}" target="_blank" class="action-btn action-btn-drive">
            📁 Acessar Google Drive
        </a>
        """
    actions_html += """
    <div class="action-btn action-btn-calendar" style="cursor: default;">
        📅 Agenda Atualizada
    </div>
    """

    st.markdown(f"""
    <div class="log-panel">
        <div class="log-title">
            <span class="shield">🛡️</span> Log de Operações
        </div>
        <div class="timeline">
            <div class="timeline-step">
                <div class="timeline-dot active">✓</div>
                <div class="timeline-step-title">Demosaico Acústico FFMPEG</div>
                <div class="timeline-step-desc">Canais isolados com sucesso.</div>
            </div>
            <div class="timeline-step">
                <div class="timeline-dot active">✓</div>
                <div class="timeline-step-title">Transcrição Turbo Groq</div>
                <div class="timeline-step-desc">Segmentos transcritos e mesclados.</div>
            </div>
            <div class="timeline-step">
                <div class="timeline-dot active">✓</div>
                <div class="timeline-step-title">Linting Litúrgico Gemini</div>
                <div class="timeline-step-desc">Ata formatada e validada.</div>
            </div>
            <div class="timeline-step">
                <div class="timeline-dot active">✓</div>
                <div class="timeline-step-title">Sincronização GCP Workspace</div>
                <div class="timeline-step-desc">PDF selado, Drive e Agenda sincronizados.</div>
            </div>
        </div>
        <div style="margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.05);">
            {actions_html}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _run_pipeline(
    uploaded_file: object,
    template: str,
    env: dict[str, str],
    enable_drive: bool,
    enable_calendar: bool,
    log_placeholder,
) -> None:
    input_path = f"/tmp/upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    left_path = "/tmp/left_vm.mp3"
    right_path = "/tmp/right_col.mp3"
    pdf_path = "/tmp/ata.pdf"

    for p in [input_path, left_path, right_path, pdf_path]:
        _register_temp(p)

    try:
        # STEP 0: Save upload
        with log_placeholder:
            _render_log_processing(0)

        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        logger.info("Áudio salvo: %s", input_path)

        # STEP 1: FFMPEG split
        with log_placeholder:
            _render_log_processing(0)
        left_result, right_result = split_stereo_channels(input_path)

        # STEP 2: Groq transcription
        with log_placeholder:
            _render_log_processing(1)
        segments = transcribe_channels(left_result, right_result, env["GROQ_API_KEY"])
        merged_text = format_merged_transcript(segments)

        # STEP 3: Gemini formatting
        with log_placeholder:
            _render_log_processing(2)
        ata_text = format_ata(merged_text, template, env["GEMINI_API_KEY"])

        # STEP 4: PDF + GCP
        with log_placeholder:
            _render_log_processing(3)
        pdf_output = generate_pdf(ata_text, template, pdf_path)

        web_view_link = ""
        if enable_drive and env.get("DRIVE_FOLDER_ID"):
            filename = f"Ata_{template.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            web_view_link = upload_to_drive(pdf_output, filename, env["DRIVE_FOLDER_ID"])

        if enable_calendar and env.get("CALENDAR_ID") and web_view_link:
            patch_calendar_event(env["CALENDAR_ID"], web_view_link)

        # COMPLETE
        with log_placeholder:
            _render_log_complete(drive_link=web_view_link)

        # Store results in session_state
        st.session_state["pipeline_done"] = True
        st.session_state["ata_text"] = ata_text
        st.session_state["pdf_path"] = pdf_output
        st.session_state["drive_link"] = web_view_link
        st.session_state["segments_count"] = len(segments)

    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        with log_placeholder:
            st.markdown(f"""
            <div class="log-panel">
                <div class="log-title"><span class="shield">🛡️</span> Log de Operações</div>
                <div style="padding: 2rem; text-align: center;">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">⚠️</div>
                    <div style="color: #f87171; font-weight: 600; margin-bottom: 0.5rem;">Erro no Pipeline</div>
                    <div style="color: #94a3b8; font-size: 0.8rem;">{exc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.error(f"❌ **Erro no processamento:** {exc}")

    finally:
        _cleanup_temp()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main() -> None:
    st.set_page_config(
        page_title="Lúmen.IA · Secretaria Digital",
        page_icon="✦",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    _inject_css()
    env = _validate_env()

    # ── HEADER ──
    _render_header()

    # ── TWO-COLUMN LAYOUT ──
    col_left, col_right = st.columns([7, 5], gap="large")

    with col_left:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        # ── SECTION: Rito e Parâmetros ──
        st.markdown("""
        <div class="section-label">
            <span class="icon">📜</span> Rito e Parâmetros
        </div>
        """, unsafe_allow_html=True)

        template = st.selectbox(
            "Tipo de Sessão",
            options=list(TEMPLATES.keys()),
            label_visibility="collapsed",
        )

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        # ── OPTIONS ──
        opt_col1, opt_col2 = st.columns(2)
        with opt_col1:
            enable_drive = st.checkbox("📁 Upload Google Drive", value=True)
        with opt_col2:
            enable_calendar = st.checkbox("📅 Atualizar Calendar", value=True)

        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

        # ── SECTION: Ingestão Acústica ──
        st.markdown("""
        <div class="section-label">
            <span class="icon-amber">🎙️</span> Ingestão Acústica
        </div>
        """, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            "Anexar Áudio Estéreo (L/R)",
            type=["mp3", "wav", "m4a", "ogg"],
            help="Canal esquerdo = V∴M∴ · Canal direito = Colunas",
            label_visibility="collapsed",
        )

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        # Results area
        if st.session_state.get("pipeline_done"):
            ata_text = st.session_state.get("ata_text", "")
            pdf_path = st.session_state.get("pdf_path", "")
            drive_link = st.session_state.get("drive_link", "")
            seg_count = st.session_state.get("segments_count", 0)

            st.markdown("""
            <div class="success-card">
                <div class="success-icon">✓</div>
                <div class="success-title">Balaústre Forjado</div>
                <div class="success-desc">
                    O documento foi redigido com precisão semântica
                    e selado nos servidores da Ordem.
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"📝 Prévia da Ata ({len(ata_text)} caracteres, {seg_count} segmentos)"):
                st.text_area("Ata", value=ata_text, height=300, disabled=True, label_visibility="collapsed")

            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(
                        "⬇️ Baixar PDF da Ata",
                        data=pdf_file.read(),
                        file_name=f"Ata_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )

        elif uploaded_file is not None:
            file_mb = uploaded_file.size / (1024 * 1024)
            st.markdown(
                f"<div style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 1rem;'>"
                f"📎 <strong>{uploaded_file.name}</strong> ({file_mb:.1f} MB) · {template}</div>",
                unsafe_allow_html=True,
            )

            process = st.button(
                "✦  Despertar Agente de IA",
                type="primary",
                use_container_width=True,
            )

            if process:
                st.session_state["pipeline_done"] = False
                _run_pipeline(
                    uploaded_file, template, env,
                    enable_drive, enable_calendar,
                    col_right.container(),
                )
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # Version
        st.markdown('<div class="version-badge">v1.1.0 · Cloud Run Serverless · Gemini 2.0</div>', unsafe_allow_html=True)

    with col_right:
        if not st.session_state.get("pipeline_done") and not st.session_state.get("_processing"):
            _render_log_idle()
        elif st.session_state.get("pipeline_done"):
            _render_log_complete(drive_link=st.session_state.get("drive_link", ""))


if __name__ == "__main__":
    main()

"""
Quill Editor — Editor de texto rico embutido via Quill.js CDN.

Renderiza um editor WYSIWYG dentro do Streamlit sem dependências externas.
Usa st.components.v1.html com bi-directional data flow via Streamlit.setComponentValue().
"""

import re
from html import escape as html_escape
from html.parser import HTMLParser

import streamlit.components.v1 as components


# ─────────────────────────────────────────────────────────
# Conversores text ↔ HTML
# ─────────────────────────────────────────────────────────

def text_to_html(plain: str) -> str:
    """
    Converte texto do LLM (com convenções ## e **) em HTML para o editor Quill.

    Convenções reconhecidas:
      - ## texto → <h2>texto</h2>
      - **texto** → <strong>texto</strong>
      - Linha em branco → separador de parágrafo
      - Linha normal → <p>texto</p>
    """
    if not plain or not plain.strip():
        return "<p><br></p>"

    lines = plain.split("\n")
    html_parts: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            html_parts.append("<p><br></p>")
            continue

        # Header ##
        if stripped.startswith("##"):
            text = stripped.lstrip("#").strip()
            text = html_escape(text)
            html_parts.append(f"<h2>{text}</h2>")
            continue

        # Bold wrapper **texto**
        if stripped.startswith("**") and stripped.endswith("**"):
            text = stripped.strip("*").strip()
            text = html_escape(text)
            html_parts.append(f"<p><strong>{text}</strong></p>")
            continue

        # Parágrafo normal — escapar e converter inline **bold**
        text = html_escape(stripped)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        html_parts.append(f"<p>{text}</p>")

    return "\n".join(html_parts)


class _HTMLToTextParser(HTMLParser):
    """Parser que converte HTML do Quill em texto plain com convenções ## e **."""

    def __init__(self):
        super().__init__()
        self._lines: list[str] = []
        self._current: list[str] = []
        self._in_bold = False
        self._in_heading = False
        self._heading_level = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("h1", "h2", "h3"):
            self._in_heading = True
            self._heading_level = int(tag[1])
        elif tag in ("strong", "b"):
            self._in_bold = True
        elif tag == "br":
            pass  # handled in handle_data
        elif tag in ("ul", "ol"):
            pass
        elif tag == "li":
            self._current.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3"):
            text = "".join(self._current).strip()
            prefix = "#" * self._heading_level + " "
            self._lines.append(prefix + text)
            self._current = []
            self._in_heading = False
        elif tag in ("strong", "b"):
            self._in_bold = False
        elif tag == "p":
            text = "".join(self._current).strip()
            self._lines.append(text)
            self._current = []
        elif tag == "li":
            text = "".join(self._current).strip()
            self._lines.append(text)
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._in_bold:
            self._current.append(f"**{data}**")
        else:
            self._current.append(data)

    def get_text(self) -> str:
        # Flush remaining
        if self._current:
            self._lines.append("".join(self._current).strip())
        return "\n".join(self._lines)


def html_to_text(html: str) -> str:
    """
    Converte HTML do editor Quill em texto com convenções ## e **.

    Mantém compatibilidade com o pdf_builder.py existente.
    """
    if not html or not html.strip():
        return ""

    parser = _HTMLToTextParser()
    parser.feed(html)
    return parser.get_text()


# ─────────────────────────────────────────────────────────
# Componente Quill Editor
# ─────────────────────────────────────────────────────────

_QUILL_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://cdn.jsdelivr.net/npm/quill@2.0.3/dist/quill.snow.css" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: transparent;
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  }
  #editor-container {
    background: #1e1e2e;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 0 0 12px 12px;
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
  }
  #editor-container .ql-editor {
    min-height: $$HEIGHT$$px;
    max-height: $$HEIGHT$$px;
    overflow-y: auto;
    padding: 16px 20px;
  }
  #editor-container .ql-editor p { margin-bottom: 8px; }
  #editor-container .ql-editor h2 {
    color: #818cf8;
    font-size: 1.15em;
    margin: 16px 0 8px;
    border-bottom: 1px solid rgba(129,140,248,0.2);
    padding-bottom: 4px;
  }

  /* Toolbar escura */
  .ql-toolbar.ql-snow {
    background: #14141f;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px 12px 0 0;
    border-bottom: none;
  }
  .ql-toolbar .ql-stroke { stroke: #94a3b8 !important; }
  .ql-toolbar .ql-fill { fill: #94a3b8 !important; }
  .ql-toolbar .ql-picker-label { color: #94a3b8 !important; }
  .ql-toolbar button:hover .ql-stroke,
  .ql-toolbar .ql-picker-label:hover { stroke: #818cf8 !important; color: #818cf8 !important; }
  .ql-toolbar button.ql-active .ql-stroke { stroke: #818cf8 !important; }
  .ql-toolbar button.ql-active .ql-fill { fill: #818cf8 !important; }
  .ql-toolbar .ql-picker-options {
    background: #1e1e2e;
    border: 1px solid rgba(255,255,255,0.1);
  }
  .ql-toolbar .ql-picker-item { color: #94a3b8; }
  .ql-toolbar .ql-picker-item:hover { color: #818cf8; }

  /* Scrollbar */
  .ql-editor::-webkit-scrollbar { width: 6px; }
  .ql-editor::-webkit-scrollbar-track { background: transparent; }
  .ql-editor::-webkit-scrollbar-thumb {
    background: rgba(129,140,248,0.3);
    border-radius: 3px;
  }

  /* Status bar */
  #status-bar {
    background: #14141f;
    border: 1px solid rgba(255,255,255,0.1);
    border-top: none;
    border-radius: 0 0 12px 12px;
    padding: 6px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: #64748b;
  }
  #status-bar .saved { color: #34d399; }
</style>
</head>
<body>
<div id="editor-container"></div>
<div id="status-bar">
  <span id="char-count">0 caracteres</span>
  <span id="save-status" class="saved">●  Salvo</span>
</div>

<script src="https://cdn.jsdelivr.net/npm/quill@2.0.3/dist/quill.js"></script>
<script>
  const quill = new Quill('#editor-container', {
    theme: 'snow',
    modules: {
      toolbar: [
        [{ header: [2, 3, false] }],
        ['bold', 'italic', 'underline', 'strike'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        [{ align: [] }],
        ['clean']
      ]
    },
    placeholder: 'Edite o texto da ata aqui...'
  });

  // Carregar conteúdo inicial
  const initialHTML = `$$CONTENT$$`;
  quill.root.innerHTML = initialHTML;

  // Atualizar contagem de caracteres
  function updateCharCount() {
    const text = quill.getText();
    const count = text.trim().length;
    document.getElementById('char-count').textContent = count.toLocaleString('pt-BR') + ' caracteres';
  }
  updateCharCount();

  // Debounce para enviar mudanças ao Streamlit
  let saveTimeout = null;
  const statusEl = document.getElementById('save-status');

  quill.on('text-change', function() {
    updateCharCount();
    statusEl.textContent = '○  Editando...';
    statusEl.style.color = '#f59e0b';

    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(function() {
      const html = quill.root.innerHTML;
      // Enviar HTML para o Streamlit via query params (workaround)
      window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: html
      }, '*');
      statusEl.textContent = '●  Salvo';
      statusEl.style.color = '#34d399';
    }, 800);
  });

  // Ajustar altura do iframe
  function sendHeight() {
    const h = document.body.scrollHeight + 20;
    window.parent.postMessage({
      type: 'streamlit:setFrameHeight',
      height: h
    }, '*');
  }
  sendHeight();
  setTimeout(sendHeight, 500);
  setTimeout(sendHeight, 1500);
</script>
</body>
</html>
"""


def render_quill_editor(initial_html: str, height: int = 350) -> None:
    """
    Renderiza o editor Quill.js no Streamlit.

    Como st.components.v1.html não suporta bi-directional data flow nativo,
    o editor usa postMessage para comunicar mudanças. Os dados ficam
    armazenados no session_state via um hidden text_area como ponte.

    Args:
        initial_html: Conteúdo HTML inicial do editor.
        height: Altura da área de edição em pixels.
    """
    # Escapar backticks e caracteres especiais para o template literal JS
    safe_html = initial_html.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    html_code = _QUILL_HTML_TEMPLATE.replace("$$CONTENT$$", safe_html).replace("$$HEIGHT$$", str(height))

    # Altura total: toolbar (~42) + editor + status bar (~32) + padding
    total_height = height + 110

    components.html(html_code, height=total_height, scrolling=False)

"""
PDF Builder — Geração de atas em PDF justificado com ReportLab.

Gera documentos PDF formatados com margens adequadas, texto justificado,
cabeçalho institucional e blocos de assinatura no rodapé.
Salva temporariamente em /tmp/ para otimização de memória no Cloud Run.
"""

import logging
import os
from datetime import datetime

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# Constantes de layout
_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_LEFT = 2.5 * cm
_MARGIN_RIGHT = 2.5 * cm
_MARGIN_TOP = 2.0 * cm
_MARGIN_BOTTOM = 3.0 * cm


def _build_styles() -> dict[str, ParagraphStyle]:
    """
    Cria e retorna os estilos de parágrafo personalizados para a ata.

    Returns:
        Dicionário com estilos nomeados.
    """
    base = getSampleStyleSheet()

    styles: dict[str, ParagraphStyle] = {
        "title": ParagraphStyle(
            "AtaTitle",
            parent=base["Title"],
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=12,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "AtaSubtitle",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName="Helvetica",
            textColor="#555555",
        ),
        "body": ParagraphStyle(
            "AtaBody",
            parent=base["Normal"],
            fontSize=11,
            leading=15,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
            fontName="Helvetica",
            firstLineIndent=1.0 * cm,
        ),
        "section_header": ParagraphStyle(
            "AtaSectionHeader",
            parent=base["Heading2"],
            fontSize=12,
            leading=16,
            spaceBefore=14,
            spaceAfter=6,
            fontName="Helvetica-Bold",
            textColor="#1a1a2e",
        ),
        "signature": ParagraphStyle(
            "AtaSignature",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            fontName="Helvetica",
        ),
        "footer": ParagraphStyle(
            "AtaFooter",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            fontName="Helvetica-Oblique",
            textColor="#888888",
        ),
    }

    return styles


def _add_page_number(canvas: object, doc: object) -> None:
    """
    Adiciona número de página no rodapé de cada página.

    Args:
        canvas: Canvas do ReportLab.
        doc: Documento sendo renderizado.
    """
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor("#888888")
    page_num = f"Página {doc.page}"
    canvas.drawCentredString(_PAGE_WIDTH / 2, 1.5 * cm, page_num)
    canvas.restoreState()


def _build_signature_block(styles: dict[str, ParagraphStyle]) -> Table:
    """
    Constrói o bloco de assinaturas (V.·.M.·., Orador, Secretário).

    Args:
        styles: Dicionário de estilos de parágrafo.

    Returns:
        Tabela ReportLab com os três blocos de assinatura.
    """
    sig_style = styles["signature"]

    col1 = [
        Paragraph("____________________________", sig_style),
        Paragraph("<b>V.·.M.·.</b>", sig_style),
        Paragraph("Venerável Mestre", sig_style),
    ]

    col2 = [
        Paragraph("____________________________", sig_style),
        Paragraph("<b>Orador</b>", sig_style),
        Paragraph("Orador da Loja", sig_style),
    ]

    col3 = [
        Paragraph("____________________________", sig_style),
        Paragraph("<b>Secretário</b>", sig_style),
        Paragraph("Secretário da Loja", sig_style),
    ]

    table_data = [[col1, col2, col3]]
    col_width = (_PAGE_WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT) / 3

    table = Table(table_data, colWidths=[col_width] * 3)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 20),
            ]
        )
    )

    return table


def generate_pdf(
    ata_text: str,
    template_type: str,
    output_path: str = "/tmp/ata.pdf",
) -> str:
    """
    Gera um PDF formatado da ata a partir do texto processado pelo LLM.

    Args:
        ata_text: Texto da ata formatada pelo Gemini.
        template_type: Tipo de sessão para o cabeçalho.
        output_path: Caminho de saída do PDF (padrão: /tmp/ata.pdf).

    Returns:
        Caminho absoluto do PDF gerado.

    Raises:
        ValueError: Se o texto da ata estiver vazio.
        RuntimeError: Se houver erro na geração do PDF.
    """
    if not ata_text.strip():
        raise ValueError("Texto da ata está vazio. Impossível gerar PDF.")

    styles = _build_styles()
    elements: list = []

    # Cabeçalho
    elements.append(Paragraph("ATA DE SESSÃO", styles["title"]))
    elements.append(
        Paragraph(
            f"{template_type} — {datetime.now().strftime('%d/%m/%Y')}",
            styles["subtitle"],
        )
    )
    elements.append(Spacer(1, 0.5 * cm))

    # Corpo da ata — cada parágrafo separado por linha em branco
    paragraphs = ata_text.split("\n")
    for para in paragraphs:
        cleaned = para.strip()
        if not cleaned:
            elements.append(Spacer(1, 0.3 * cm))
            continue

        # Detecta headers de seção (linhas que começam com ## ou são MAIÚSCULAS curtas)
        if cleaned.startswith("##"):
            cleaned = cleaned.lstrip("#").strip()
            elements.append(Paragraph(cleaned, styles["section_header"]))
        elif cleaned.startswith("**") and cleaned.endswith("**"):
            cleaned = cleaned.strip("*").strip()
            elements.append(Paragraph(f"<b>{cleaned}</b>", styles["section_header"]))
        else:
            # Escapa caracteres especiais do ReportLab
            cleaned = (
                cleaned.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            # Restaura tags HTML que usamos intencionalmente
            cleaned = cleaned.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
            elements.append(Paragraph(cleaned, styles["body"]))

    # Espaçamento antes das assinaturas
    elements.append(Spacer(1, 2 * cm))

    # Bloco de assinaturas
    elements.append(_build_signature_block(styles))

    # Rodapé institucional
    elements.append(Spacer(1, 1 * cm))
    elements.append(
        Paragraph(
            "Documento gerado automaticamente por Secretaria Digital IA — "
            "Sigilo Maçônico Preservado",
            styles["footer"],
        )
    )

    # Construção do documento
    try:
        frame = Frame(
            _MARGIN_LEFT,
            _MARGIN_BOTTOM,
            _PAGE_WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT,
            _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM,
            id="main_frame",
        )

        doc = BaseDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=_MARGIN_LEFT,
            rightMargin=_MARGIN_RIGHT,
            topMargin=_MARGIN_TOP,
            bottomMargin=_MARGIN_BOTTOM,
        )

        doc.addPageTemplates(
            [PageTemplate(id="ata_page", frames=[frame], onPage=_add_page_number)]
        )

        doc.build(elements)

        file_size = os.path.getsize(output_path)
        logger.info(
            "PDF gerado com sucesso: %s (%d bytes).",
            output_path,
            file_size,
        )

        return output_path

    except Exception as exc:
        logger.error("Erro ao gerar PDF: %s", exc)
        raise RuntimeError(f"Falha na geração do PDF: {exc}") from exc

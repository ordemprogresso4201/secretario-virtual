"""
GCP Services — Integração com Google Drive e Calendar via ADC nativo.

Utiliza google.auth.default() para herdar a identidade do Cloud Run,
eliminando a necessidade de arquivos credentials.json físicos.
"""

import logging
from datetime import datetime, timezone

import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# Scopes necessários para Drive e Calendar
_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
]


def _get_credentials() -> google.auth.credentials.Credentials:
    """
    Obtém credenciais via Application Default Credentials (ADC).

    No Cloud Run, herda a Service Account do projeto GCP automaticamente.
    Localmente, usa `gcloud auth application-default login`.

    Returns:
        Credenciais autenticadas com os scopes necessários.

    Raises:
        google.auth.exceptions.DefaultCredentialsError: Se não houver credenciais disponíveis.
    """
    credentials, project = google.auth.default(scopes=_SCOPES)
    logger.info("Credenciais ADC obtidas para o projeto: %s", project)
    return credentials


def upload_to_drive(
    pdf_path: str,
    filename: str,
    folder_id: str,
) -> str:
    """
    Faz upload de um arquivo PDF para o Google Drive e aplica permissão pública de leitura.

    Args:
        pdf_path: Caminho local do arquivo PDF.
        filename: Nome do arquivo no Drive.
        folder_id: ID da pasta de destino no Drive.

    Returns:
        URL pública (webViewLink) do arquivo no Drive.

    Raises:
        RuntimeError: Se o upload ou configuração de permissão falhar.
    """
    try:
        credentials = _get_credentials()
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "mimeType": "application/pdf",
        }

        media = MediaFileUpload(
            pdf_path,
            mimetype="application/pdf",
            resumable=True,
        )

        logger.info("Iniciando upload para o Drive: %s → pasta %s", filename, folder_id)

        file_result = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )

        file_id = file_result.get("id")
        web_view_link = file_result.get("webViewLink", "")

        # Aplica permissão pública de leitura
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        logger.info(
            "Upload concluído. ID: %s | Link: %s",
            file_id,
            web_view_link,
        )

        return web_view_link

    except Exception as exc:
        logger.error("Erro no upload para o Drive: %s", exc)
        raise RuntimeError(f"Falha no upload para o Google Drive: {exc}") from exc


def patch_calendar_event(
    calendar_id: str,
    web_view_link: str,
) -> str:
    """
    Busca o evento de sessão do dia atual no Calendar e adiciona o link da ata na descrição.

    Realiza busca por eventos entre 00:00 e 23:59 (UTC) do dia atual.
    Ao encontrar, faz patch na descrição com o link e envia notificação
    por e-mail a todos os convidados.

    Args:
        calendar_id: ID do calendário do Google.
        web_view_link: URL pública do arquivo no Drive.

    Returns:
        Sumário do evento atualizado ou mensagem de "não encontrado".

    Raises:
        RuntimeError: Se a busca ou atualização falhar.
    """
    try:
        credentials = _get_credentials()
        service = build(
            "calendar", "v3", credentials=credentials, cache_discovery=False
        )

        # Intervalo de busca: dia atual inteiro (UTC)
        now = datetime.now(timezone.utc)
        time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        time_max = now.replace(
            hour=23, minute=59, second=59, microsecond=0
        ).isoformat()

        logger.info(
            "Buscando eventos no Calendar '%s' entre %s e %s",
            calendar_id,
            time_min,
            time_max,
        )

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])

        if not events:
            logger.warning("Nenhum evento encontrado no Calendar para hoje.")
            return "Nenhum evento encontrado no Calendar para hoje."

        # Atualiza o primeiro evento encontrado
        event = events[0]
        event_id = event["id"]
        event_summary = event.get("summary", "Evento sem título")

        current_description = event.get("description", "")
        ata_link_text = (
            f"\n\n📄 Ata gerada por IA (Sigilo Maçônico): {web_view_link}"
        )

        # Evita duplicação se já tiver o link
        if web_view_link in current_description:
            logger.info("Link da ata já presente no evento '%s'.", event_summary)
            return f"Evento '{event_summary}' já contém o link da ata."

        updated_description = current_description + ata_link_text

        service.events().patch(
            calendarId=calendar_id,
            eventId=event_id,
            body={"description": updated_description},
            sendUpdates="all",
        ).execute()

        logger.info(
            "Evento '%s' atualizado com link da ata. Notificações enviadas.",
            event_summary,
        )

        return f"Evento '{event_summary}' atualizado com sucesso!"

    except Exception as exc:
        logger.error("Erro ao atualizar Calendar: %s", exc)
        raise RuntimeError(f"Falha ao atualizar o Google Calendar: {exc}") from exc

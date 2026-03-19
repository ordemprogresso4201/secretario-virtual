"""
Engine de Áudio — Separação de canais estéreo via FFMPEG e transcrição STT via Groq.

Utiliza subprocess para chamar ffmpeg nativamente (sem pydub), evitando
carregamento bruto em memória RAM. Otimizado para ambientes serverless (Cloud Run).
"""

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from groq import Groq

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """Segmento individual de transcrição com metadados de tempo e falante."""

    speaker: str
    start: float
    end: float
    text: str


def _get_audio_channels(input_path: str) -> int:
    """
    Detecta o número de canais do arquivo de áudio usando ffprobe.

    Args:
        input_path: Caminho do arquivo de áudio.

    Returns:
        Número de canais (1=mono, 2=estéreo).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels",
        "-of", "csv=p=0",
        input_path,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        channels = int(result.stdout.strip())
        logger.info("Áudio detectado: %d canal(is)", channels)
        return channels
    except (ValueError, subprocess.TimeoutExpired) as exc:
        logger.warning("Não foi possível detectar canais (%s). Assumindo estéreo.", exc)
        return 2


def split_stereo_channels(input_path: str) -> tuple[str, str]:
    """
    Separa um arquivo de áudio em dois canais mono via FFMPEG.

    Suporta tanto áudio estéreo (separa L/R) quanto mono (duplica para ambos).

    Args:
        input_path: Caminho absoluto do arquivo de áudio em /tmp/.

    Returns:
        Tupla com os caminhos (left_path, right_path) dos canais separados.

    Raises:
        RuntimeError: Se o ffmpeg retornar código de saída diferente de 0.
        FileNotFoundError: Se o arquivo de entrada não existir.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {input_path}")

    left_path = "/tmp/left_vm.mp3"
    right_path = "/tmp/right_col.mp3"

    channels = _get_audio_channels(input_path)

    if channels >= 2:
        # Estéreo: separa canal esquerdo (V.·.M.·.) e direito (Colunas)
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-map_channel", "0.0.0", left_path,
            "-map_channel", "0.0.1", right_path,
        ]
        logger.info("Áudio estéreo — separando canais L/R")
    else:
        # Mono: converte para mono mp3 e duplica para ambos os caminhos
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ac", "1",
            "-q:a", "2",
            left_path,
        ]
        logger.info("Áudio mono — será usado como canal único (V.·.M.·. + Colunas)")

    logger.info("Executando FFMPEG: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        logger.error("FFMPEG stderr: %s", result.stderr)
        raise RuntimeError(
            f"FFMPEG falhou (código {result.returncode}): {result.stderr[-500:]}"
        )

    # Se mono, copia o mesmo arquivo para o canal direito
    if channels < 2:
        import shutil
        shutil.copy2(left_path, right_path)
        logger.info("Mono: canal duplicado para L=%s e R=%s", left_path, right_path)

    logger.info("Canais processados com sucesso: L=%s, R=%s", left_path, right_path)
    return left_path, right_path


def _transcribe_single_channel(
    file_path: str,
    speaker_label: str,
    api_key: str,
) -> list[TranscriptionSegment]:
    """
    Transcreve um único canal de áudio usando a API Groq (whisper-large-v3).

    Args:
        file_path: Caminho do arquivo de áudio mono.
        speaker_label: Rótulo do falante (ex: 'Venerável Mestre', 'Colunas').
        api_key: Chave da API Groq.

    Returns:
        Lista de TranscriptionSegment com timestamps e texto.

    Raises:
        groq.APIError: Se a API retornar erro.
        FileNotFoundError: Se o arquivo não existir.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Canal de áudio não encontrado: {file_path}")

    client = Groq(api_key=api_key)

    logger.info("Transcrevendo canal [%s]: %s", speaker_label, file_path)

    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), audio_file),
            model="whisper-large-v3",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            language="pt",
        )

    segments: list[TranscriptionSegment] = []

    if hasattr(transcription, "segments") and transcription.segments:
        for seg in transcription.segments:
            segments.append(
                TranscriptionSegment(
                    speaker=speaker_label,
                    start=seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0),
                    end=seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0),
                    text=(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
                )
            )
    else:
        # Fallback: texto completo sem timestamps granulares
        full_text = getattr(transcription, "text", "")
        if full_text:
            segments.append(
                TranscriptionSegment(
                    speaker=speaker_label,
                    start=0.0,
                    end=0.0,
                    text=full_text.strip(),
                )
            )

    logger.info(
        "Canal [%s] transcrito: %d segmentos extraídos.",
        speaker_label,
        len(segments),
    )
    return segments


def transcribe_channels(
    left_path: str,
    right_path: str,
    groq_api_key: str,
) -> list[TranscriptionSegment]:
    """
    Transcreve ambos os canais em paralelo via ThreadPoolExecutor e mescla
    os resultados cronologicamente.

    Args:
        left_path: Caminho do canal esquerdo (Venerável Mestre).
        right_path: Caminho do canal direito (Colunas).
        groq_api_key: Chave da API Groq para autenticação.

    Returns:
        Lista unificada de TranscriptionSegment ordenada por timestamp.
    """
    all_segments: list[TranscriptionSegment] = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(
                _transcribe_single_channel, left_path, "Venerável Mestre", groq_api_key
            ): "left",
            executor.submit(
                _transcribe_single_channel, right_path, "Colunas", groq_api_key
            ): "right",
        }

        for future in as_completed(futures):
            channel = futures[future]
            try:
                segments = future.result()
                all_segments.extend(segments)
                logger.info("Canal '%s' processado com sucesso.", channel)
            except Exception as exc:
                logger.error("Erro ao transcrever canal '%s': %s", channel, exc)
                raise RuntimeError(
                    f"Falha na transcrição do canal '{channel}': {exc}"
                ) from exc

    # Mesclagem cronológica
    all_segments.sort(key=lambda s: s.start)

    logger.info(
        "Transcrição completa: %d segmentos mesclados cronologicamente.",
        len(all_segments),
    )
    return all_segments


def format_merged_transcript(segments: list[TranscriptionSegment]) -> str:
    """
    Formata os segmentos mesclados em um texto legível para o LLM.

    Args:
        segments: Lista de segmentos ordenados cronologicamente.

    Returns:
        String formatada com identificação de falante e timestamps.
    """
    lines: list[str] = []
    for seg in segments:
        timestamp = f"[{seg.start:.1f}s - {seg.end:.1f}s]"
        lines.append(f"{timestamp} [{seg.speaker}]: {seg.text}")

    return "\n".join(lines)

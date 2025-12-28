"""Gemini API client for STT, OCR, and face analysis."""
import json
import os
from pathlib import Path
from typing import Any

import google.genai as genai
from google.genai.types import GenerateContentConfig, Part

from app.utils.logging import logger


class GeminiClient:
    """Client for Gemini API operations."""

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        self.client = genai.Client(api_key=api_key)

    def transcribe_audio(self, audio_path: Path, mime_type: str) -> dict[str, Any]:
        """Transcribe audio to text using Gemini fast model."""
        try:
            # Read audio file
            with open(audio_path, "rb") as f:
                audio_data = f.read()

            # Create prompt
            system_instruction = "You are a speech-to-text engine. Return only valid JSON."
            user_prompt = """Transcribe the attached audio. Requirements:
- Keep original language.
- Do not invent words.
- If unclear, mark with [inaudible].
Return JSON:
{
  "language": "...",
  "text": "...",
  "segments": [{"start_sec":0.0,"end_sec":1.2,"text":"..."}]
}"""

            # Prepare content parts
            parts = [
                Part.from_bytes(data=audio_data, mime_type=mime_type),
                Part.from_text(text=user_prompt),
            ]

            # Generate content with fast model
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            # Parse JSON response
            result_text = response.text
            result = json.loads(result_text)

            # Validate structure
            if "text" not in result:
                raise ValueError("Missing 'text' field in transcription response")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            # Retry with repair prompt
            return self._retry_with_repair(audio_path, mime_type, "transcribe")
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise

    def ocr_handwriting(self, image_path: Path) -> dict[str, Any]:
        """Extract handwritten text from image using Gemini Pro model."""
        try:
            # Read image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Create prompt
            system_instruction = (
                "You are an OCR + editor for handwritten personal notes. Return only valid JSON."
            )
            user_prompt = """Extract handwritten text from the image.
Return JSON:
{
  "raw_text": "...",          // faithful transcription, preserve line breaks
  "cleaned_text": "...",      // light corrections: spelling, obvious missing letters, but DO NOT change meaning
  "language": "...",
  "confidence": 0.0-1.0,
  "notes": "short"
}"""

            # Prepare content parts
            parts = [
                Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                Part.from_text(text=user_prompt),
            ]

            # Generate content with pro model
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            # Parse JSON response
            result_text = response.text
            result = json.loads(result_text)

            # Validate structure
            if "cleaned_text" not in result:
                raise ValueError("Missing 'cleaned_text' field in OCR response")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            # Retry with repair prompt
            return self._retry_with_repair(image_path, "image/jpeg", "ocr")
        except Exception as e:
            logger.error(f"Error performing OCR: {e}")
            raise

    def analyze_face(self, image_path: Path) -> dict[str, Any]:
        """Analyze face emotion and stress level using Gemini Pro model."""
        try:
            # Read image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Create prompt
            system_instruction = (
                "You analyze facial expression conservatively. Return only valid JSON."
            )
            user_prompt = """Estimate dominant emotion and stress level from the face.
Return JSON:
{
  "dominant_emotion": "neutral|happy|sad|angry|fear|surprise|disgust",
  "stress_level_0_10": 0-10,
  "confidence": 0.0-1.0,
  "notes": "short"
}

Important: if the face is not clearly visible, return low confidence and explain in notes."""

            # Prepare content parts
            parts = [
                Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                Part.from_text(text=user_prompt),
            ]

            # Generate content with pro model
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            # Parse JSON response
            result_text = response.text
            result = json.loads(result_text)

            # Validate structure
            if "dominant_emotion" not in result:
                raise ValueError("Missing 'dominant_emotion' field in face analysis response")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            # Retry with repair prompt
            return self._retry_with_repair(image_path, "image/jpeg", "face")
        except Exception as e:
            logger.error(f"Error analyzing face: {e}")
            raise

    def _retry_with_repair(
        self, file_path: Path, mime_type: str, operation: str
    ) -> dict[str, Any]:
        """Retry operation with repair prompt for JSON parsing."""
        logger.info(f"Retrying {operation} with repair prompt")

        with open(file_path, "rb") as f:
            file_data = f.read()

        repair_prompt = "Return valid JSON only. Do not include any text outside JSON."

        parts = [
            Part.from_bytes(data=file_data, mime_type=mime_type),
            Part.from_text(text=repair_prompt),
        ]

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            result_text = response.text
            return json.loads(result_text)
        except Exception as e:
            logger.error(f"Retry failed: {e}")
            raise ValueError(f"Failed to get valid JSON response from Gemini: {e}")


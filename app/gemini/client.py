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
            parsed = json.loads(result_text)

            # Handle case where Gemini returns a list instead of dict
            if isinstance(parsed, list):
                if len(parsed) > 0 and isinstance(parsed[0], dict):
                    result = parsed[0]
                else:
                    logger.warning(f"Face analysis returned unexpected list format: {parsed}")
                    result = {}
            elif isinstance(parsed, dict):
                result = parsed
            else:
                logger.warning(f"Face analysis returned unexpected type: {type(parsed)}")
                result = {}

            # Validate structure with defaults
            if "dominant_emotion" not in result:
                logger.warning(f"Face analysis response missing 'dominant_emotion': {result}")
                result["dominant_emotion"] = "neutral"
            if "stress_level_0_10" not in result:
                result["stress_level_0_10"] = 5
            if "confidence" not in result:
                result["confidence"] = 0.3
            if "notes" not in result:
                result["notes"] = "Response format incomplete"

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

    def classify_text_content(self, text: str) -> dict[str, Any]:
        """Classify text content to determine event type."""
        try:
            system_instruction = (
                "You are a content classifier for a personal diary. Return only valid JSON."
            )
            user_prompt = f"""Analyze this diary entry text and classify it into one of these categories:
- reflection: Daily thoughts, reflections, feelings, experiences, general diary entries
- dream: Dreams, dream descriptions, sleep experiences
- mindform: Handwritten notes (but this is text, so unlikely - only if explicitly about handwriting)
- drawing: Descriptions of drawings or art
- other: Anything else

Text to classify:
{text}

Return JSON:
{{
  "event_type": "reflection|dream|mindform|drawing|other",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}"""

            parts = [Part.from_text(text=user_prompt)]

            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            result_text = response.text
            result = json.loads(result_text)

            # Validate and normalize
            event_type = result.get("event_type", "reflection")
            # Map to valid types
            valid_types = ["reflection", "dream", "mindform", "drawing", "other"]
            if event_type not in valid_types:
                event_type = "reflection"  # Default fallback

            return {
                "event_type": event_type,
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", ""),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from classification: {e}")
            # Default to reflection
            return {"event_type": "reflection", "confidence": 0.3, "reasoning": "Classification failed"}
        except Exception as e:
            logger.error(f"Error classifying text: {e}")
            return {"event_type": "reflection", "confidence": 0.3, "reasoning": "Classification error"}

    def classify_image(self, image_path: Path) -> dict[str, Any]:
        """Classify image to determine if it's handwriting, face, or drawing."""
        try:
            # Read image file
            with open(image_path, "rb") as f:
                image_data = f.read()

            system_instruction = (
                "You are an image classifier for a personal diary. Return only valid JSON."
            )
            user_prompt = """Analyze this image and classify it into one of these categories:
- mindform: Handwritten text, notes, journal entries (text written by hand)
- face_photo: A clear photo of a person's face
- drawing: Drawings, sketches, artwork, illustrations
- other: Anything else

Return JSON:
{
  "event_type": "mindform|face_photo|drawing|other",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}"""

            parts = [
                Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                Part.from_text(text=user_prompt),
            ]

            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=parts,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            result_text = response.text
            result = json.loads(result_text)

            # Validate and normalize
            event_type = result.get("event_type", "other")
            valid_types = ["mindform", "face_photo", "drawing", "other"]
            if event_type not in valid_types:
                event_type = "other"  # Default fallback

            return {
                "event_type": event_type,
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", ""),
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from image classification: {e}")
            return {"event_type": "other", "confidence": 0.3, "reasoning": "Classification failed"}
        except Exception as e:
            logger.error(f"Error classifying image: {e}")
            return {"event_type": "other", "confidence": 0.3, "reasoning": "Classification error"}


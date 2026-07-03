"""
Multi-Modal Perception Pipeline.

Processes and understands images, audio, and structured data alongside
text for richer context. Provides a unified interface for feature
extraction, classification, and similarity matching across modalities.

Requires: pip install Pillow torch torchvision librosa soundfile
"""
import base64
import hashlib
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Graceful degradation for optional dependencies
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import torch
    import torchvision.transforms as transforms
    import torchvision.models as models
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    import librosa
    import soundfile as sf
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False


class MultiModalPerception:
    """Unified perception pipeline for images, audio, text, and structured data.

    Extracts features, computes similarity across modalities, and
    provides classification for each supported input type.
    """

    def __init__(self, device: str = "cpu"):
        self.device = device
        self._image_model = None
        self._audio_model = None
        self._reports: List[Dict[str, Any]] = []
        self._init_models()

    def _init_models(self):
        """Lazy-load models only when needed."""
        pass  # Models loaded on first use

    def _get_image_model(self):
        if self._image_model is None and HAS_TORCH:
            self._image_model = models.resnet18(pretrained=True)
            self._image_model.eval()
            self._image_model.to(self.device)
        return self._image_model

    def perceive_image(self, image_data: Union[str, bytes, Path],
                       extract_features: bool = True) -> Dict[str, Any]:
        """Analyze an image from path, bytes, or base64 string.

        Returns classification, feature vector, and metadata.
        """
        if not HAS_PILLOW:
            return {"error": "Pillow required. Install with: pip install Pillow"}

        # Load image
        if isinstance(image_data, str) and image_data.startswith("data:image"):
            # Base64 URI
            header, encoded = image_data.split(",", 1)
            image_bytes = base64.b64decode(encoded)
            img = Image.open(io.BytesIO(image_bytes))
        elif isinstance(image_data, str) and Path(image_data).exists():
            img = Image.open(image_data)
        elif isinstance(image_data, bytes):
            img = Image.open(io.BytesIO(image_data))
        else:
            return {"error": "Unsupported image input format"}

        result = {
            "format": img.format,
            "size": img.size,
            "mode": img.mode,
            "width": img.width,
            "height": img.height,
        }

        if extract_features and HAS_TORCH:
            model = self._get_image_model()
            if model:
                transform = transforms.Compose([
                    transforms.Resize(256),
                    transforms.CenterCrop(224),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ])
                input_tensor = transform(img).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    features = model(input_tensor)
                    result["feature_vector"] = features[0].tolist()[:16]  # First 16 dims
                    # Simple classification using argmax
                    _, predicted = torch.max(features, 1)
                    result["predicted_class"] = int(predicted.item())
                logger.info(f"Image perceived: {img.size}, predicted class {predicted.item()}")

        return result

    def perceive_audio(self, audio_path: str, extract_features: bool = True) -> Dict[str, Any]:
        """Analyze an audio file.

        Returns sample rate, duration, and optionally MFCC features.
        """
        if not HAS_LIBROSA:
            return {"error": "librosa required. Install with: pip install librosa soundfile"}
        if not Path(audio_path).exists():
            return {"error": f"Audio file not found: {audio_path}"}

        try:
            y, sr = librosa.load(audio_path, sr=None)
            result = {
                "sample_rate": sr,
                "duration_seconds": round(len(y) / sr, 2),
                "num_samples": len(y),
            }

            if extract_features:
                # Extract MFCC features
                mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
                result["mfcc_mean"] = [round(float(m), 4) for m in mfccs.mean(axis=1)]
                result["mfcc_std"] = [round(float(m), 4) for m in mfccs.std(axis=1)]

                # Spectral centroid
                spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
                result["spectral_centroid_mean"] = round(float(spectral_centroids.mean()), 2)

                # Zero crossing rate
                zcr = librosa.feature.zero_crossing_rate(y)[0]
                result["zero_crossing_rate_mean"] = round(float(zcr.mean()), 4)

            logger.info(f"Audio perceived: {audio_path}, duration={result['duration_seconds']}")
            return result
        except Exception as e:
            return {"error": f"Failed to process audio: {str(e)}"}

    def perceive_structured_data(self, data: Dict[str, Any],
                                schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze structured data against optional schema."""
        result = {
            "type": type(data).__name__,
            "size": len(json.dumps(data)),
            "keys": list(data.keys()) if isinstance(data, dict) else [],
        }

        if schema:
            # Simple schema validation
            if isinstance(data, dict):
                for key in schema.get("required", []):
                    result[f"has_{key}"] = key in data
                result["schema_compliant"] = all(k in data for k in schema.get("required", []))
        
        return result

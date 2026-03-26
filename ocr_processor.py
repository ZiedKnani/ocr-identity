from paddleocr import PaddleOCR
import numpy as np
import cv2
from PIL import Image
import io
from typing import Dict, Any, List, Tuple
import logging

logger = logging.getLogger(__name__)

class OCRProcessor:
    """
    Wrapper PaddleOCR avec prétraitement et labellisation
    """

    def __init__(self, lang: str = "fr"):
        self.ocr = PaddleOCR(lang=lang, use_angle_cls=False)
        logger.info("✅ OCRProcessor initialisé")

    def _decode_image(self, image_bytes: bytes) -> np.ndarray:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Image non décodable")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    def _deskew_light(self, rgb_img: np.ndarray) -> np.ndarray:
        """Correction légère d'inclinaison pour éviter de dégrader les images déjà droites."""
        gray = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        th = cv2.bitwise_not(th)

        coords = np.column_stack(np.where(th > 0))
        if len(coords) < 200:
            return rgb_img

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Ne corrige que les angles plausibles, sinon conserve l'image.
        if abs(angle) < 0.8 or abs(angle) > 15:
            return rgb_img

        h, w = rgb_img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(rgb_img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def _enhance_lab(self, rgb_img: np.ndarray, clip_limit: float = 3.0) -> np.ndarray:
        lab = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        l2 = clahe.apply(l)
        merged = cv2.merge((l2, a, b))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)

    def _unsharp_mask(self, rgb_img: np.ndarray) -> np.ndarray:
        blurred = cv2.GaussianBlur(rgb_img, (0, 0), 1.2)
        return cv2.addWeighted(rgb_img, 1.35, blurred, -0.35, 0)

    def _build_preprocess_variants(self, rgb_img: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        """Construit des variantes d'image et laisse OCR choisir la meilleure."""
        base = self._deskew_light(rgb_img)

        # Variante 1: contrast boost + denoise.
        v1 = self._enhance_lab(base, clip_limit=3.0)
        v1 = cv2.bilateralFilter(v1, d=7, sigmaColor=45, sigmaSpace=45)

        # Variante 2: plus agressive sur faible contraste.
        v2 = self._enhance_lab(base, clip_limit=4.5)
        v2 = cv2.fastNlMeansDenoisingColored(v2, None, 4, 4, 7, 21)

        # Variante 3: sharpen léger pour textes fins.
        v3 = self._unsharp_mask(v1)

        return [
            ("base", base),
            ("enhanced", v1),
            ("enhanced_strong", v2),
            ("sharpened", v3),
        ]

    def _run_ocr_once(self, image: np.ndarray) -> Dict[str, Any]:
        result = self.ocr.ocr(image, cls=True)
        blocks = []
        lines = []
        confidences = []
        if result and result[0]:
            for idx, line in enumerate(result[0]):
                bbox, (text, conf) = line
                text = text.strip()
                if not text:
                    continue
                blocks.append({
                    "id": idx,
                    "text": text,
                    "confidence": round(float(conf), 3),
                    "bbox": [[float(x), float(y)] for x, y in bbox],
                    "label": "UNLABELED"
                })
                lines.append(text)
                confidences.append(float(conf))

        return {
            "blocks": blocks,
            "lines": lines,
            "full_text": " ".join(lines),
            "avg_conf": float(np.mean(confidences)) if confidences else 0.0,
            "image_size": f"{image.shape[1]}x{image.shape[0]}"
        }

    def _score_ocr_result(self, ocr_data: Dict[str, Any]) -> float:
        """Score robuste: confiance moyenne + densité de texte utile."""
        blocks = ocr_data.get("blocks", [])
        avg_conf = float(ocr_data.get("avg_conf", 0.0))
        useful = sum(1 for b in blocks if len(str(b.get("text", "")).strip()) >= 3)
        return (avg_conf * 0.7) + (min(useful / 20.0, 1.0) * 0.3)

    def preprocess(self, image_bytes: bytes) -> np.ndarray:
        """Prétraitement par défaut pour compatibilité (variante enhanced)."""
        try:
            rgb_img = self._decode_image(image_bytes)
            variants = dict(self._build_preprocess_variants(rgb_img))
            return variants.get("enhanced", rgb_img)
            
        except Exception as e:
            logger.warning(f"Prétraitement OCR échoué: {e}")
            return np.array(Image.open(io.BytesIO(image_bytes)).convert('RGB'))

    def run_ocr(self, image: np.ndarray) -> Dict[str, Any]:
        variants = self._build_preprocess_variants(image)

        best_data = None
        best_score = -1.0
        best_variant = "unknown"

        for variant_name, variant_img in variants:
            ocr_data = self._run_ocr_once(variant_img)
            score = self._score_ocr_result(ocr_data)
            if score > best_score:
                best_score = score
                best_data = ocr_data
                best_variant = variant_name

            # Arrêt anticipé si résultat déjà très bon.
            if ocr_data.get("avg_conf", 0.0) >= 0.95 and len(ocr_data.get("blocks", [])) >= 8:
                best_data = ocr_data
                best_variant = variant_name
                break

        if best_data is None:
            best_data = self._run_ocr_once(image)
            best_variant = "fallback"

        best_data["preprocess_variant"] = best_variant
        best_data["preprocess_score"] = round(float(best_score), 4) if best_score >= 0 else 0.0
        return best_data

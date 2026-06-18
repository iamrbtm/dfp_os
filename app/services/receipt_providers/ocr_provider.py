from __future__ import annotations

import json

from app.services.receipt_providers.base import BaseReceiptProvider, ProviderResult


class OCRProvider(BaseReceiptProvider):
    name = "ocr"

    def process(self, file_path: str, **kwargs) -> ProviderResult:
        enhanced_path = kwargs.get("enhanced_path") or file_path
        provider_name = kwargs.get("provider", "paddleocr")
        result = ProviderResult(success=False, errors=["OCR not available."])

        if provider_name == "paddleocr":
            result = self._run_paddle_ocr(enhanced_path)
        elif provider_name == "tesseract":
            result = self._run_tesseract(enhanced_path)
        elif provider_name == "easyocr":
            result = self._run_easyocr(enhanced_path)
        elif provider_name == "pytesseract":
            result = self._run_pytesseract(enhanced_path)

        if not result.success:
            fallback = kwargs.get("fallback_provider")
            if fallback:
                return self.process(enhanced_path, provider=fallback, **{k: v for k, v in kwargs.items() if k != "provider"})

        return result

    def _run_paddle_ocr(self, file_path: str) -> ProviderResult:
        try:
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            raw = ocr.ocr(file_path, cls=True)
            if raw and raw[0]:
                lines = []
                full_text = []
                for line in raw[0]:
                    bbox, (text, confidence) = line
                    lines.append({
                        "text": text,
                        "confidence": float(confidence),
                        "bbox": [[float(c) for c in coord] for coord in bbox],
                    })
                    full_text.append(text)
                return ProviderResult(
                    success=True,
                    raw_text="\n".join(full_text),
                    raw_json=str({"lines": lines}),
                    confidence=float(sum(ln["confidence"] for ln in lines)) / len(lines) if lines else 0.0,
                    data={"lines": lines, "page_count": 1},
                    diagnostics={"provider": "paddleocr", "line_count": len(lines)},
                )
        except ImportError:
            return ProviderResult(success=False, errors=["PaddleOCR is not installed."])
        except Exception as e:
            return ProviderResult(success=False, errors=[f"PaddleOCR error: {e}"])

        return ProviderResult(success=False, errors=["PaddleOCR returned no results."])

    def _run_tesseract(self, file_path: str) -> ProviderResult:
        import subprocess
        import json
        try:
            result = subprocess.run(
                ["tesseract", file_path, "stdout", "-l", "eng", "--psm", "4", "tsv"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                lines = []
                full_text = []
                for line in result.stdout.strip().split("\n")[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 12 and parts[11].strip():
                        text = parts[11].strip()
                        conf = float(parts[10]) if parts[10] and parts[10] != "-1" else 0.0
                        lines.append({
                            "text": text,
                            "confidence": conf / 100.0,
                        })
                        full_text.append(text)
                return ProviderResult(
                    success=True,
                    raw_text="\n".join(full_text),
                    raw_json=json.dumps({"lines": lines}),
                    confidence=sum(ln["confidence"] for ln in lines) / len(lines) if lines else 0.0,
                    data={"lines": lines},
                    diagnostics={"provider": "tesseract", "line_count": len(lines)},
                )
        except FileNotFoundError:
            return ProviderResult(success=False, errors=["Tesseract is not installed."])
        except Exception as e:
            return ProviderResult(success=False, errors=[f"Tesseract error: {e}"])

        return ProviderResult(success=False, errors=["Tesseract returned no results."])

    def _run_easyocr(self, file_path: str) -> ProviderResult:
        try:
            import easyocr
            reader = easyocr.Reader(["en"])
            raw = reader.readtext(file_path)
            if raw:
                lines = []
                full_text = []
                for bbox, text, confidence in raw:
                    lines.append({
                        "text": text,
                        "confidence": float(confidence),
                        "bbox": [[float(c) for c in coord] for coord in bbox],
                    })
                    full_text.append(text)
                return ProviderResult(
                    success=True,
                    raw_text="\n".join(full_text),
                    raw_json=str({"lines": lines}),
                    confidence=float(sum(ln["confidence"] for ln in lines)) / len(lines) if lines else 0.0,
                    data={"lines": lines},
                    diagnostics={"provider": "easyocr", "line_count": len(lines)},
                )
        except ImportError:
            return ProviderResult(success=False, errors=["EasyOCR is not installed."])
        except Exception as e:
            return ProviderResult(success=False, errors=[f"EasyOCR error: {e}"])

        return ProviderResult(success=False, errors=["EasyOCR returned no results."])

    def _run_pytesseract(self, file_path: str) -> ProviderResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ProviderResult(success=False, errors=["pytesseract or Pillow is not installed."])
        try:
            image = Image.open(file_path)
            raw_text = pytesseract.image_to_string(image)
            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
            if lines:
                return ProviderResult(
                    success=True,
                    raw_text=raw_text,
                    raw_json=json.dumps({"lines": [{"text": ln} for ln in lines]}),
                    confidence=0.7,
                    data={"lines": [{"text": ln} for ln in lines]},
                    diagnostics={"provider": "pytesseract", "line_count": len(lines)},
                )
        except Exception as e:
            return ProviderResult(success=False, errors=[f"pytesseract error: {e}"])
        return ProviderResult(success=False, errors=["pytesseract returned no results."])

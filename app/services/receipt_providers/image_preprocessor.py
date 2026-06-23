from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.services.receipt_providers.base import BaseReceiptProvider, ProviderResult


class ImagePreprocessorProvider(BaseReceiptProvider):
    name = "image_preprocessor"

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".pdf"}
    PREVIEW_EXTENSION = ".jpg"
    THUMBNAIL_MAX_SIZE = (300, 300)
    PREVIEW_MAX_SIZE = (1200, 1200)

    def process(self, file_path: str, **kwargs) -> ProviderResult:
        ext = Path(file_path).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return ProviderResult(
                success=False,
                errors=[f"Unsupported file type: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}"],
            )

        output_dir = kwargs.get("output_dir", os.path.dirname(file_path))
        result = ProviderResult(success=True, data={"original_path": file_path, "pages": []})

        if ext in {".heic", ".heif"}:
            converted = self._convert_heic(file_path, output_dir)
            if converted:
                result.data["pages"].append(converted)
                result.data["preview_path"] = converted
            else:
                return ProviderResult(success=False, errors=["HEIC/HEIF conversion failed."])
        elif ext == ".pdf":
            pages = self._convert_pdf(file_path, output_dir)
            if pages:
                result.data["pages"] = pages
                result.data["preview_path"] = pages[0]
            else:
                return ProviderResult(success=False, errors=["PDF conversion failed."])
        else:
            result.data["pages"] = [file_path]
            result.data["preview_path"] = file_path

        enhanced = self._enhance_for_ocr(result.data["preview_path"], output_dir)
        if enhanced:
            result.data["enhanced_path"] = enhanced

        thumbnail = self._generate_thumbnail(result.data["preview_path"], output_dir)
        if thumbnail:
            result.data["thumbnail_path"] = thumbnail

        return result

    def _convert_heic(self, file_path: str, output_dir: str) -> str | None:
        output = str(Path(output_dir) / f"{Path(file_path).stem}_converted.jpg")
        try:
            subprocess.run(
                ["magick", file_path, output],
                capture_output=True, timeout=30, check=False,
            )
            if Path(output).exists():
                return output
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            subprocess.run(
                ["convert", file_path, output],
                capture_output=True, timeout=30, check=False,
            )
            if Path(output).exists():
                return output
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _convert_pdf(self, file_path: str, output_dir: str) -> list[str]:
        pages = []
        output_prefix = str(Path(output_dir) / f"{Path(file_path).stem}_page")
        try:
            result = subprocess.run(
                [
                    "pdftoppm",
                    "-jpeg",
                    "-r",
                    "200",
                    "-f",
                    "1",
                    "-l",
                    "1",
                    file_path,
                    output_prefix,
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if result.returncode == 0:
                for f in sorted(Path(output_dir).glob(f"{Path(file_path).stem}_page-*.jpg")):
                    pages.append(str(f))
                if pages:
                    return pages
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            result = subprocess.run(
                ["magick", "-density", "200", file_path, str(Path(output_dir) / f"{Path(file_path).stem}_page_%d.jpg")],
                capture_output=True, timeout=60, check=False,
            )
            if result.returncode == 0:
                for f in sorted(Path(output_dir).glob(f"{Path(file_path).stem}_page_*.jpg")):
                    pages.append(str(f))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return pages

    def _enhance_for_ocr(self, image_path: str, output_dir: str) -> str | None:
        try:
            import cv2
        except ImportError:
            return None
        output = str(Path(output_dir) / f"{Path(image_path).stem}_enhanced.jpg")
        try:
            image = cv2.imread(image_path)
            if image is None:
                return None
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            cv2.imwrite(output, threshold)
            if Path(output).exists():
                return output
        except Exception:
            pass
        return None

    def _generate_thumbnail(self, image_path: str, output_dir: str) -> str | None:
        output = str(Path(output_dir) / f"{Path(image_path).stem}_thumb.jpg")
        try:
            subprocess.run(
                ["magick", image_path, "-resize", "300x300>", output],
                capture_output=True, timeout=15, check=False,
            )
            if Path(output).exists():
                return output
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

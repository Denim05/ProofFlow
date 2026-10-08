import io
from typing import Union
from PIL import Image, ImageEnhance, ImageOps


class ImagePreprocessor:
    """Configurable image preprocessing utilities for OCR evaluation.

    Operates without assuming preprocessing unconditionally improves recognition.
    """

    @staticmethod
    def load_image(image_input: Union[str, bytes, Image.Image]) -> Image.Image:
        if isinstance(image_input, Image.Image):
            return image_input
        if isinstance(image_input, bytes):
            return Image.open(io.BytesIO(image_input))
        return Image.open(image_input)

    @staticmethod
    def to_grayscale(image: Image.Image) -> Image.Image:
        """Converts image to 8-bit grayscale."""
        return image.convert("L")

    @staticmethod
    def enhance_contrast(image: Image.Image, factor: float = 1.8) -> Image.Image:
        """Applies auto-contrast and linear contrast stretching."""
        gray = image.convert("L") if image.mode != "L" else image
        autocontrast = ImageOps.autocontrast(gray, cutoff=2)
        enhancer = ImageEnhance.Contrast(autocontrast)
        return enhancer.enhance(factor)

    @staticmethod
    def upscale_to_dpi(image: Image.Image, target_dpi: int = 300, current_dpi: int = 72) -> Image.Image:
        """Scales low-resolution smartphone screenshots up to target DPI."""
        if current_dpi >= target_dpi:
            return image
        scale_factor = target_dpi / current_dpi
        new_width = int(image.width * scale_factor)
        new_height = int(image.height * scale_factor)
        return image.resize((new_width, new_height), Image.Resampling.BICUBIC)

    @classmethod
    def apply_pipeline(
        cls,
        image_input: Union[str, bytes, Image.Image],
        apply_contrast: bool = True,
        apply_upscale: bool = True,
    ) -> Image.Image:
        """Standard preprocessing combination for noisy smartphone screenshots."""
        img = cls.load_image(image_input)
        if apply_upscale and img.width < 1200:
            img = cls.upscale_to_dpi(img, target_dpi=300, current_dpi=96)
        if apply_contrast:
            img = cls.enhance_contrast(img)
        return img

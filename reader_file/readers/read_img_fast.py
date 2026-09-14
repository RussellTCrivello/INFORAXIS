"""
Fast Image Reader - Comprehensive OCR Text Extraction
Extracts complete textual content from images with coordinate tracking
Stores only OCR text content, preserving formatting
Optimized for speed and reliability
"""

import os
import logging
from typing import Dict, Any, Optional, Set
from pathlib import Path
import threading
import warnings

from core.ocr import get_ocr_engine, recognize_best

from .base_reader import BaseReader

logger = logging.getLogger(__name__)

# Suppress PIL warning about palette images with transparency
warnings.filterwarnings('ignore', message='.*Palette images with Transparency.*', category=UserWarning, module='PIL')

# Global cache for library imports
_LIBS_CACHE = {}
_LIBS_LOCK = threading.Lock()

# Cache for tesseract availability check
_TESSERACT_AVAILABLE = None
_TESSERACT_CHECKED = False
_TESSERACT_LOCK = threading.Lock()

# Default OCR languages - Hebrew prioritized for RTL text
DEFAULT_OCR_LANGUAGES = ["heb", "eng", "ara"]


class ImageFileReader(BaseReader):
    """
    Image file reader with comprehensive OCR extraction.
    Extracts complete textual content with bounding box coordinates.
    Stores only OCR text - no metadata in content.
    
    Returns structure:
    {
        "text": str - Extracted OCR text (formatting preserved),
        "ocr_coordinates": list - Bounding boxes for each word (optional),
        "ocr_language": str - Language used for OCR,
        "ocr_attempted": bool - Whether OCR was attempted,
        "ocr_successful": bool - Whether text was successfully extracted,
        "extraction_info": dict - Detailed extraction indicators,
        "location": dict - GPS coordinates if available (for paths.coordinates field, not content)
    }
    """
    
    def get_supported_extensions(self) -> Set[str]:
        """Return set of supported image extensions"""
        return {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', 
            '.tiff', '.tif', '.webp', '.ico', '.svg', '.heic', '.heif'
        }
    
    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read image file and extract OCR text content
        
        Args:
            file_info: Dictionary with 'path' key and optional 'languages' key
        
        Returns:
            Dictionary with extracted text content and extraction indicators
        """
        is_valid, error_msg = self.validate_file_info(file_info)
        if not is_valid:
            return self.create_error_result(error_msg or "Invalid file info", file_info.get("path", "unknown"))
        
        file_path = str(file_info.get("path"))
        languages = file_info.get("languages")
        # DETECT-01: dispatch on the content-verified type, not the filename.
        ext = self.effective_extension(file_info)
        
        try:
            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp',
                       '.tiff', '.tif', '.webp', '.ico', '.heic', '.heif'):
                result = self.read_image_file_fast(file_path, languages=languages)
                if result is None:
                    return self.create_error_result("Failed to read image file", file_path)
                return result
            elif ext == '.svg':
                return self.read_svg_file(file_path)
            else:
                error_msg = f"Unsupported image file type: {ext or file_path}"
                return self.handle_read_error(ValueError(error_msg), file_path, "read_file")
        except Exception as e:
            return self.handle_read_error(e, file_path, "read_file")
    
    def read_image_file_fast(self, filepath, languages=None):
        """
        Extract OCR text content from image file.
        
        Returns:
            dict: {
                "text": str - Extracted OCR text (formatting preserved),
                "ocr_coordinates": list - Bounding boxes for each word (optional),
                "ocr_language": str - Language used for OCR,
                "ocr_attempted": bool - Whether OCR was attempted,
                "ocr_successful": bool - Whether text was successfully extracted,
                "extraction_info": dict - Detailed extraction indicators,
                "location": dict - GPS coordinates if available (for paths.coordinates field, not content)
            }
        """
        if not os.path.exists(filepath):
            logger.warning(f"[EXTRACTION] File not found: {filepath}")
            return {
                "text": "",
                "ocr_attempted": False,
                "ocr_successful": False,
                "extraction_info": {
                    "error": "File not found",
                    "extracted": False,
                    "stored": False
                }
            }
        
        libs = self._get_libraries()
        Image = libs.get('Image')
        TAGS = libs.get('TAGS')
        GPSTAGS = libs.get('GPSTAGS')
        pytesseract = libs.get('pytesseract')
        cv2 = libs.get('cv2')
        np = libs.get('np')
        
        if not Image:
            logger.warning(f"[EXTRACTION] PIL/Image library not available for: {filepath}")
            return {
                "text": "",
                "ocr_attempted": False,
                "ocr_successful": False,
                "retryable": True,
                "extraction_info": {
                    "error": "PIL/Image library not available",
                    "reason": "required_dependency_unavailable",
                    "extracted": False,
                    "stored": False
                }
            }
        
        result = {
            "text": "",
            "ocr_attempted": False,
            "ocr_successful": False,
            "extraction_info": {
                "extracted": False,
                "stored": False,
                "text_length": 0,
                "word_count": 0,
                "coordinate_count": 0
            }
        }
        
        try:
            with Image.open(filepath) as img:
                width, height = img.size
                img_format = img.format
                
                # Even small/icon images are content-bearing input. Do not
                # discard them before OCR; the caller must receive either text
                # or an explicit retryable OCR failure.
                result["extraction_info"].update({
                    "image_size": f"{width}x{height}",
                    "image_format": img_format
                })
                
                # Extract GPS location (for paths.coordinates field, not content)
                location_info = None
                try:
                    exif_data = img._getexif()
                    if exif_data and TAGS and GPSTAGS:
                        gps_ifd = exif_data.get(34853)
                        if gps_ifd:
                            location_info = self._extract_gps_location(gps_ifd, GPSTAGS)
                            if location_info:
                                result["location"] = location_info
                                result["extraction_info"]["gps_extracted"] = True
                except Exception:
                    pass
                
                # Perform OCR extraction.
                # PHASE 2A: OCR is no longer tied to the tesseract binary. The
                # engine layer picks tesseract when present (it covers this
                # project's declared heb/eng/ara defaults) and otherwise falls
                # back to a pure-pip engine, so a host without tesseract still
                # gets OCR instead of silently producing nothing.
                use_tesseract = bool(pytesseract and self._is_tesseract_available())
                requested_languages = list(languages or DEFAULT_OCR_LANGUAGES)
                if use_tesseract:
                    try:
                        installed_languages = set(pytesseract.get_languages(config=""))
                        missing_languages = [
                            code for code in requested_languages
                            if code not in installed_languages
                        ]
                        if missing_languages:
                            logger.error(
                                "Missing Tesseract language data for %s: %s",
                                os.path.basename(filepath), ", ".join(missing_languages),
                            )
                            use_tesseract = False
                    except Exception:
                        use_tesseract = False
                fallback_engine = None if use_tesseract else get_ocr_engine()

                if use_tesseract or fallback_engine is not None:
                    result["ocr_attempted"] = True
                    rgb_img = img.convert("RGB")

                    # Preprocess image (shared by every engine)
                    if cv2 and np:
                        arr = np.array(rgb_img)
                        processed = self._fast_preprocess(arr, libs)
                        ocr_target = Image.fromarray(processed)
                        result["extraction_info"]["preprocessing"] = "enhanced"
                    else:
                        ocr_target = rgb_img.convert("L")
                        result["extraction_info"]["preprocessing"] = "grayscale"

                    if use_tesseract:
                        # Detect language
                        detected_lang = self._detect_language(rgb_img, pytesseract)
                        lang, config = self._get_optimized_tesseract_config(detected_lang, tuple(languages) if languages else None)

                        result["ocr_language"] = lang
                        result["extraction_info"]["detected_language"] = detected_lang
                        result["extraction_info"]["used_language"] = lang

                        # Extract text and coordinates comprehensively
                        ocr_result = self._extract_text_comprehensive(ocr_target, lang, pytesseract, config)

                        text = ocr_result.get("text", "")
                        ocr_coordinates = ocr_result.get("ocr_coordinates", [])

                        # Fallback if comprehensive extraction failed
                        if not text or not text.strip():
                            logger.debug(f"[EXTRACTION] Comprehensive OCR failed, trying fallback for: {os.path.basename(filepath)}")
                            try:
                                text = pytesseract.image_to_string(ocr_target, lang=lang, config=config)
                                if text and text.strip() and not ocr_coordinates:
                                    try:
                                        ocr_data = pytesseract.image_to_data(
                                            ocr_target, lang=lang, config=config,
                                            output_type=pytesseract.Output.DICT
                                        )
                                        ocr_coordinates = self._extract_coordinates_from_data(ocr_data)
                                    except Exception:
                                        pass
                            except Exception:
                                text = ""

                        ocr_engine_name_used = "tesseract"
                        try:
                            ocr_engine_version_used = str(pytesseract.get_tesseract_version())
                        except Exception:
                            ocr_engine_version_used = "unknown"
                        ocr_confidence_used = None
                    else:
                        # Alternate engine path. Same result contract, plus the
                        # per-block confidence that engine reports.
                        # Confidence-gated retry on the un-preprocessed image:
                        # the shared binarisation is tuned for tesseract and
                        # measurably harms small text for a neural engine.
                        engine_result = recognize_best(
                            fallback_engine,
                            ocr_target,
                            rgb_img,
                            list(languages) if languages else None,
                        )
                        text = engine_result.text or ""
                        ocr_coordinates = [
                            {
                                "word": block.text,
                                "confidence": block.confidence,
                                "bbox": list(block.bbox) if block.bbox else None
                            }
                            for block in engine_result.blocks
                        ]
                        lang = engine_result.language
                        result["ocr_language"] = lang
                        result["extraction_info"]["used_language"] = lang
                        if engine_result.error:
                            result["extraction_info"]["engine_error"] = engine_result.error

                        ocr_engine_name_used = engine_result.engine
                        ocr_engine_version_used = engine_result.engine_version
                        ocr_confidence_used = engine_result.mean_confidence
                        # Which input produced this reading - part of provenance.
                        result["ocr_input_variant"] = engine_result.input_variant

                    # Provenance: state how this text was derived so it is
                    # never mistaken for native document text.
                    result["ocr_engine"] = ocr_engine_name_used
                    result["ocr_engine_version"] = ocr_engine_version_used
                    result["ocr_derived"] = bool(text and text.strip())
                    if ocr_confidence_used is not None:
                        result["ocr_confidence"] = ocr_confidence_used

                    # Store extraction results
                    if text and text.strip():
                        result["text"] = text.rstrip()
                        result["ocr_successful"] = True
                        
                        text_length = len(text.strip())
                        word_count = len(text.strip().split())
                        coord_count = len(ocr_coordinates) if ocr_coordinates else 0
                        
                        result["extraction_info"].update({
                            "extracted": True,
                            "stored": True,
                            "text_length": text_length,
                            "word_count": word_count,
                            "coordinate_count": coord_count,
                            "image_size": f"{width}x{height}",
                            "image_format": img_format
                        })
                        
                        if ocr_coordinates:
                            result["ocr_coordinates"] = ocr_coordinates
                        
                        logger.info(
                            f"[EXTRACTION] ✅ {os.path.basename(filepath)} - "
                            f"Extracted: {text_length} chars, {word_count} words | "
                            f"Coordinates: {coord_count} words | "
                            f"Language: {lang}"
                        )
                    else:
                        result["ocr_successful"] = False
                        result["extraction_info"].update({
                            "extracted": False,
                            "stored": False,
                            "text_length": 0,
                            "word_count": 0,
                            "coordinate_count": len(ocr_coordinates) if ocr_coordinates else 0,
                            "image_size": f"{width}x{height}",
                            "image_format": img_format,
                            "reason": "no_text_extracted"
                        })
                        
                        if ocr_coordinates:
                            result["ocr_coordinates"] = ocr_coordinates
                            result["extraction_info"]["coordinate_count"] = len(ocr_coordinates)
                        
                        logger.info(
                            f"[EXTRACTION] ⚠️  {os.path.basename(filepath)} - "
                            f"No text extracted | "
                            f"Coordinates: {len(ocr_coordinates) if ocr_coordinates else 0} words | "
                            f"Language: {lang}"
                        )
                else:
                    # Never report an image as successfully processed when its
                    # pixels were not examined. The original file remains
                    # stored, but searchable content is explicitly marked as
                    # unavailable and the job can surface the dependency error.
                    result["ocr_attempted"] = True
                    result["ocr_engine"] = "unavailable"
                    result["extraction_info"].update({
                        "extracted": False,
                        "stored": False,
                        "error": "OCR is required but no OCR engine is available",
                        "reason": "ocr_required_engine_unavailable",
                        "image_size": f"{width}x{height}",
                        "image_format": img_format
                    })
                    logger.error(
                        "[EXTRACTION] OCR required but no engine is available for: %s",
                        os.path.basename(filepath),
                    )
                
                return result
        
        except Exception as e:
            logger.error(f"[EXTRACTION] ❌ Error processing {os.path.basename(filepath)}: {e}")
            return {
                "text": "",
                "ocr_attempted": False,
                "ocr_successful": False,
                "extraction_info": {
                    "error": str(e),
                    "extracted": False,
                    "stored": False
                }
            }
    
    def read_svg_file(self, filepath):
        """Read SVG file (text content only)"""
        try:
            if not os.path.exists(filepath):
                return {
                    "text": "",
                    "ocr_attempted": False,
                    "ocr_successful": False,
                    "extraction_info": {
                        "error": "File not found",
                        "extracted": False,
                        "stored": False
                    }
                }
            
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Extract text from SVG (simple extraction)
            import re
            # Extract text from <text> tags
            text_matches = re.findall(r'<text[^>]*>(.*?)</text>', content, re.DOTALL | re.IGNORECASE)
            extracted_text = '\n'.join(text_matches) if text_matches else ""
            
            result = {
                "text": extracted_text,
                "ocr_attempted": False,
                "ocr_successful": bool(extracted_text and extracted_text.strip()),
                "extraction_info": {
                    "extracted": bool(extracted_text and extracted_text.strip()),
                    "stored": bool(extracted_text and extracted_text.strip()),
                    "text_length": len(extracted_text.strip()) if extracted_text else 0,
                    "word_count": len(extracted_text.strip().split()) if extracted_text else 0,
                    "coordinate_count": 0,
                    "file_type": "SVG"
                }
            }
            
            # Extract basic SVG metadata
            width_match = re.search(r'width=["\'](\d+(?:\.\d+)?)["\']', content)
            height_match = re.search(r'height=["\'](\d+(?:\.\d+)?)["\']', content)
            viewbox_match = re.search(r'viewBox=["\']([^"\']+)["\']', content)
            
            if width_match:
                result["extraction_info"]["image_width"] = width_match.group(1)
            if height_match:
                result["extraction_info"]["image_height"] = height_match.group(1)
            if viewbox_match:
                result["extraction_info"]["viewBox"] = viewbox_match.group(1)
            
            return result
        except Exception as e:
            return {
                "text": "",
                "ocr_attempted": False,
                "ocr_successful": False,
                "extraction_info": {
                    "error": str(e),
                    "extracted": False,
                    "stored": False
                }
            }
    
    def _is_tesseract_available(self):
        """Check if tesseract is installed and available (cached)"""
        global _TESSERACT_AVAILABLE, _TESSERACT_CHECKED
        
        with _TESSERACT_LOCK:
            if _TESSERACT_CHECKED:
                return _TESSERACT_AVAILABLE
            
            _TESSERACT_CHECKED = True
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                _TESSERACT_AVAILABLE = True
                return True
            except Exception:
                _TESSERACT_AVAILABLE = False
                logger.warning("Tesseract OCR not installed or not in PATH. Image OCR will be skipped.")
                return False
    
    def _get_libraries(self):
        """Get image processing libraries (cached)"""
        global _LIBS_CACHE
        
        with _LIBS_LOCK:
            if _LIBS_CACHE:
                return _LIBS_CACHE
            
            try:
                from PIL import Image
                from PIL.ExifTags import TAGS, GPSTAGS
                _LIBS_CACHE['Image'] = Image
                _LIBS_CACHE['TAGS'] = TAGS
                _LIBS_CACHE['GPSTAGS'] = GPSTAGS
            except ImportError:
                _LIBS_CACHE['Image'] = None
                _LIBS_CACHE['TAGS'] = None
                _LIBS_CACHE['GPSTAGS'] = None
            
            try:
                import pytesseract
                _LIBS_CACHE['pytesseract'] = pytesseract
            except ImportError:
                _LIBS_CACHE['pytesseract'] = None
            
            try:
                import cv2
                import numpy as np
                _LIBS_CACHE['cv2'] = cv2
                _LIBS_CACHE['np'] = np
            except ImportError:
                _LIBS_CACHE['cv2'] = None
                _LIBS_CACHE['np'] = None
            
            return _LIBS_CACHE
    
    def _detect_language(self, img, pytesseract):
        """Detect script/language using Tesseract OSD"""
        try:
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            script = osd.get('script', '').lower()
            
            script_to_lang = {
                'hebrew': 'heb',
                'arabic': 'ara',
                'latin': 'eng',
                'cyrillic': 'rus',
                'han': 'chi_sim',
                'japanese': 'jpn',
                'korean': 'kor',
            }
            
            detected = script_to_lang.get(script)
            if detected:
                logger.debug(f"[LANGUAGE] Detected script: {script} -> {detected}")
                return detected
        except Exception:
            pass
        
        return None
    
    def _get_optimized_tesseract_config(self, detected_lang=None, languages=None, psm_mode=None):
        """
        Get optimized Tesseract configuration for maximum text extraction
        
        Args:
            detected_lang: Auto-detected language
            languages: Fallback language list
            psm_mode: PSM mode (None = auto-select PSM 11)
        
        Returns:
            tuple: (language_string, config_string)
        """
        libs = self._get_libraries()
        pytesseract = libs.get('pytesseract')
        
        if not pytesseract:
            return "eng", "--oem 3 --psm 11"
        
        try:
            available_langs = pytesseract.get_languages(config="")
        except:
            available_langs = ["eng"]
        
        # Priority: detected language first, then fallback languages
        if detected_lang and detected_lang in available_langs:
            lang_str = detected_lang
        else:
            selected_langs = []
            fallback_langs = languages if languages else DEFAULT_OCR_LANGUAGES
            for lang in fallback_langs:
                if lang in available_langs:
                    selected_langs.append(lang)
            
            if not selected_langs:
                selected_langs = ["eng"]
            
            lang_str = "+".join(selected_langs)
        
        # PSM 11: Sparse text - finds ALL text regardless of layout
        if psm_mode is None:
            psm_mode = 11
        
        config = f"--oem 3 --psm {psm_mode}"
        
        return lang_str, config
    
    def _extract_gps_location(self, gps_info, GPSTAGS):
        """Extract GPS location from EXIF data"""
        if not gps_info:
            return None

        gps = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}

        def to_deg(value):
            try:
                if isinstance(value[0], tuple):
                    d = value[0][0] / value[0][1]
                    m = value[1][0] / value[1][1]
                    s = value[2][0] / value[2][1]
                else:
                    d, m, s = value
                return d + (m / 60.0) + (s / 3600.0)
            except Exception:
                return None

        lat = lon = None

        if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
            lat = to_deg(gps["GPSLatitude"])
            if gps["GPSLatitudeRef"] == "S":
                lat = -lat

        if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
            lon = to_deg(gps["GPSLongitude"])
            if gps["GPSLongitudeRef"] == "W":
                lon = -lon

        if lat is None or lon is None:
            return None

        result = {
            "latitude": lat,
            "longitude": lon,
            "coordinates": f"{lat:.6f}, {lon:.6f}",
            "google_maps_url": f"https://www.google.com/maps?q={lat},{lon}"
        }

        if "GPSAltitude" in gps:
            result["altitude_meters"] = float(gps["GPSAltitude"])

        if "GPSTimeStamp" in gps:
            h, m, s = gps["GPSTimeStamp"]
            result["gps_time_utc"] = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

        return result
    
    def _extract_text_comprehensive(self, ocr_target, lang, pytesseract, base_config=None):
        """
        Extract text and coordinates using multiple PSM modes.
        Preserves formatting and structure.
        
        Args:
            ocr_target: PIL Image ready for OCR
            lang: Language string
            pytesseract: pytesseract module
            base_config: Base config string (optional)
        
        Returns:
            dict: {"text": str, "ocr_coordinates": list}
        """
        result = {"text": "", "ocr_coordinates": []}
        
        # Primary: PSM 11 (Sparse text) - finds ALL text regardless of layout
        primary_text = ""
        primary_coords = []
        try:
            config_11 = f"--oem 3 --psm 11"
            primary_text = pytesseract.image_to_string(ocr_target, lang=lang, config=config_11)
            if primary_text:
                primary_text = str(primary_text)
                try:
                    ocr_data = pytesseract.image_to_data(
                        ocr_target, lang=lang, config=config_11,
                        output_type=pytesseract.Output.DICT
                    )
                    primary_coords = self._extract_coordinates_from_data(ocr_data)
                except Exception:
                    pass
        except Exception:
            pass
        
        # Secondary: PSM 6 (Uniform block) - preserves paragraph structure
        secondary_text = ""
        secondary_coords = []
        try:
            config_6 = f"--oem 3 --psm 6"
            secondary_text = pytesseract.image_to_string(ocr_target, lang=lang, config=config_6)
            if secondary_text:
                secondary_text = str(secondary_text)
                try:
                    ocr_data = pytesseract.image_to_data(
                        ocr_target, lang=lang, config=config_6,
                        output_type=pytesseract.Output.DICT
                    )
                    secondary_coords = self._extract_coordinates_from_data(ocr_data)
                except Exception:
                    pass
        except Exception:
            pass
        
        # Use primary (PSM 11) if successful
        if primary_text and primary_text.strip():
            result["text"] = primary_text.rstrip()
            result["ocr_coordinates"] = primary_coords
            return result
        elif secondary_text and secondary_text.strip():
            result["text"] = secondary_text.rstrip()
            result["ocr_coordinates"] = secondary_coords
            return result
        
        # Fallback: PSM 3 (Fully automatic) or base_config
        try:
            if base_config:
                config_3 = base_config
            else:
                config_3 = f"--oem 3 --psm 3"
            fallback_text = pytesseract.image_to_string(ocr_target, lang=lang, config=config_3)
            if fallback_text and fallback_text.strip():
                result["text"] = str(fallback_text).rstrip()
                try:
                    ocr_data = pytesseract.image_to_data(
                        ocr_target, lang=lang, config=config_3,
                        output_type=pytesseract.Output.DICT
                    )
                    result["ocr_coordinates"] = self._extract_coordinates_from_data(ocr_data)
                except Exception:
                    pass
                return result
        except Exception:
            pass
        
        return result
    
    def _extract_coordinates_from_data(self, ocr_data):
        """
        Extract bounding box coordinates from OCR data
        
        Args:
            ocr_data: Dictionary from pytesseract.image_to_data()
        
        Returns:
            list: List of coordinate dictionaries
        """
        coordinates = []
        
        if not ocr_data or 'text' not in ocr_data:
            return coordinates
        
        try:
            for i in range(len(ocr_data['text'])):
                word_text = ocr_data['text'][i].strip()
                conf = int(ocr_data.get('conf', [0])[i]) if ocr_data.get('conf') else 0
                
                if word_text and conf > 0:
                    coordinates.append({
                        "text": word_text,
                        "x": ocr_data.get('left', [0])[i] if ocr_data.get('left') else 0,
                        "y": ocr_data.get('top', [0])[i] if ocr_data.get('top') else 0,
                        "width": ocr_data.get('width', [0])[i] if ocr_data.get('width') else 0,
                        "height": ocr_data.get('height', [0])[i] if ocr_data.get('height') else 0,
                        "confidence": conf,
                        "level": ocr_data.get('level', [0])[i] if ocr_data.get('level') else 0
                    })
        except Exception as e:
            logger.debug(f"Error extracting coordinates: {e}")
        
        return coordinates
    
    def _fast_preprocess(self, img_array, libs):
        """
        Enhanced image preprocessing for better OCR results
        
        Args:
            img_array: numpy array of image
            libs: cached libraries dict
        
        Returns:
            Preprocessed image ready for OCR
        """
        cv2 = libs.get('cv2')
        np = libs.get('np')
        
        if not cv2 or not np:
            return img_array
        
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Enhance contrast with CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Adaptive thresholding
        binary_adaptive = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        return binary_adaptive


# Module-level wrapper functions for cross-module use
_shared_reader_instance = None

def _get_shared_instance():
    """Get or create shared ImageFileReader instance"""
    global _shared_reader_instance
    if _shared_reader_instance is None:
        _shared_reader_instance = ImageFileReader()
    return _shared_reader_instance

def _get_libraries():
    """Module-level wrapper for _get_libraries"""
    return _get_shared_instance()._get_libraries()

def _detect_language(img, pytesseract):
    """Module-level wrapper for _detect_language"""
    return _get_shared_instance()._detect_language(img, pytesseract)

def _get_optimized_tesseract_config(detected_lang=None, languages=None):
    """Module-level wrapper for _get_optimized_tesseract_config"""
    return _get_shared_instance()._get_optimized_tesseract_config(detected_lang, languages)

def _fast_preprocess(img_array, libs):
    """Module-level wrapper for _fast_preprocess"""
    return _get_shared_instance()._fast_preprocess(img_array, libs)

def _is_tesseract_available():
    """Module-level wrapper for _is_tesseract_available"""
    return _get_shared_instance()._is_tesseract_available()

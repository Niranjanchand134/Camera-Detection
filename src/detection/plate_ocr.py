import os
import cv2
import logging

_plate_cascade = None
_cascade_initialized = False


def get_plate_cascade():
    global _plate_cascade, _cascade_initialized
    if not _cascade_initialized:
        _cascade_initialized = True
        try:
            plate_cascade_path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
            if os.path.exists(plate_cascade_path):
                _plate_cascade = cv2.CascadeClassifier(plate_cascade_path)
        except Exception as e:
            logging.warning(f"Plate cascade unavailable: {e}")
    return _plate_cascade


def detect_plate_text(vehicle_bgr, ocr_enabled: bool = True):
    cascade = get_plate_cascade()
    if cascade is None or vehicle_bgr is None or vehicle_bgr.size == 0:
        return None
    try:
        gray = cv2.cvtColor(vehicle_bgr, cv2.COLOR_BGR2GRAY)
        plates = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 20))
        if len(plates) == 0:
            return None
        x, y, w, h = max(plates, key=lambda p: p[2] * p[3])
        plate_crop = gray[y:y + h, x:x + w]

        if not ocr_enabled:
            return "DETECTED"

        try:
            import pytesseract
            text = pytesseract.image_to_string(
                plate_crop,
                config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            ).strip().replace("\n", "")
            return text if text else "DETECTED"
        except Exception:
            return "DETECTED"
    except Exception:
        return None

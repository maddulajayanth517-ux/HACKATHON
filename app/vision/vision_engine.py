import cv2
import numpy as np
from ultralytics import YOLO
import os
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import json
import mimetypes

# Ensure the temp directory exists for annotated images
TEMP_DIR = os.path.join(os.getcwd(), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

# Detection is deliberately conservative: a single weak/large box is not
# enough to classify a video as containing a pothole.
MIN_CONFIDENCE = 0.65
MIN_BOX_AREA_RATIO = 0.002
MAX_BOX_AREA_RATIO = 0.35
MIN_VIDEO_HITS = 2
VIDEO_SAMPLE_EVERY = 10

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "best.pt")
MODEL = YOLO(MODEL_PATH)


def estimate_pothole_severity(bbox, img_shape):
    """Estimate pothole severity and mock depth from a 2D bounding box.

    The depth value is a visual estimate, not a physical measurement. The
    result is deliberately conservative when the box or image dimensions are
    malformed so it can be used safely in a live video pipeline.
    """
    try:
        if len(bbox) != 4 or len(img_shape) < 2:
            raise ValueError

        image_height = float(img_shape[0])
        image_width = float(img_shape[1])
        if image_height <= 0 or image_width <= 0:
            raise ValueError

        coordinates = [float(value) for value in bbox]
        x1, y1, x2, y2 = coordinates
        x1, x2 = sorted((max(0.0, min(image_width, x1)), max(0.0, min(image_width, x2))))
        y1, y2 = sorted((max(0.0, min(image_height, y1)), max(0.0, min(image_height, y2))))

        box_width = x2 - x1
        box_height = y2 - y1
        box_area = box_width * box_height
        image_area = image_width * image_height
        area_ratio = box_area / image_area

        # A box ending near the bottom of the frame is visually closer.
        proximity_score = y2 / image_height
        area_score = min(area_ratio / 0.20, 1.0)

        if box_width == 0 or box_height == 0:
            shape_score = 0.0
        else:
            aspect_ratio = box_width / box_height
            shape_score = max(0.0, 1.0 - min(abs(aspect_ratio - 1.0), 1.0))

        risk_score = (area_score * 0.50) + (proximity_score * 0.30) + (shape_score * 0.20)

        if risk_score >= 0.78:
            severity_level, estimated_depth_cm = "Critical", 25
            message = "Large structural pothole detected. Immediate maintenance required."
        elif risk_score >= 0.55:
            severity_level, estimated_depth_cm = "High", 20
            message = "Significant pothole detected. Prompt maintenance recommended."
        elif risk_score >= 0.30:
            severity_level, estimated_depth_cm = "Medium", 15
            message = "Moderate pothole detected. Maintenance recommended."
        else:
            severity_level, estimated_depth_cm = "Low", 5
            message = "Small pothole detected. Routine maintenance recommended."

        email_report_string = (
            f"{severity_level.upper()} SEVERITY: {message} "
            f"Estimated depth: ~{estimated_depth_cm}cm."
        )
        return {
            "severity_level": severity_level,
            "estimated_depth_cm": estimated_depth_cm,
            "email_report_string": email_report_string,
        }
    except (TypeError, ValueError, IndexError, OverflowError):
        return {
            "severity_level": "Low",
            "estimated_depth_cm": 5,
            "email_report_string": (
                "LOW SEVERITY: Pothole geometry could not be estimated reliably. "
                "Estimated depth: ~5cm. Manual review recommended."
            ),
        }


def get_decimal_from_dms(dms, ref):
    """Converts Degrees/Minutes/Seconds EXIF to standard decimal format."""
    degrees, minutes, seconds = dms[0], dms[1], dms[2]
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if ref in ['S', 'W']: decimal = -decimal
    return round(decimal, 6)


def extract_gps(file_path):
    """Extracts GPS metadata from images. Videos return fallback coords."""
    try:
        image = Image.open(file_path)
        exif_data = image._getexif()
        if not exif_data: raise ValueError("No EXIF")

        for tag, value in exif_data.items():
            if TAGS.get(tag, tag) == "GPSInfo":
                gps_data = {GPSTAGS.get(t, t): value[t] for t in value}
                lat = get_decimal_from_dms(gps_data['GPSLatitude'], gps_data['GPSLatitudeRef'])
                lon = get_decimal_from_dms(gps_data['GPSLongitude'], gps_data['GPSLongitudeRef'])
                return lat, lon
    except Exception:
        return 16.2341, 80.5482  # Default coordinates

    return 16.2341, 80.5482


def apply_clahe(image):
    """OpenCV Preprocessing: Normalizes road texture and lighting."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    final_image = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
    return cv2.GaussianBlur(final_image, (3, 3), 0)


def process_frame(img):
    """Return a detection only when a box passes geometry and confidence checks."""
    h, w, _ = img.shape
    total_area = h * w
    results = MODEL(img, conf=MIN_CONFIDENCE, verbose=False)[0]

    defect_detected, max_severity, best_box = False, 0.0, None

    for box in results.boxes:
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        class_name = str(MODEL.names[class_id]).lower()

        if class_name not in {"pothole", "potholes"}:
            continue
        if confidence < MIN_CONFIDENCE:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        box_width = max(0, x2 - x1)
        box_height = max(0, y2 - y1)
        area_ratio = (box_width * box_height) / total_area
        center_y = (y1 + y2) / 2

        # Full-scene/background boxes are a common false positive. A pothole
        # must be a localized object in the lower roadway portion of a frame.
        if not MIN_BOX_AREA_RATIO <= area_ratio <= MAX_BOX_AREA_RATIO:
            continue
        if center_y < h * 0.42 or y2 < h * 0.55:
            continue

        severity = min(
            round((area_ratio * 20) + ((confidence - MIN_CONFIDENCE) * 2), 1),
            10.0,
        )

        if not defect_detected or severity > max_severity:
            defect_detected = True
            max_severity = severity
            best_box = (x1, y1, x2, y2)

    return defect_detected, max_severity, best_box


def annotate_and_save(img, max_severity, best_box, output_path):
    """Draws the bounding box or a 'Clear Road' message and saves the image."""
    if best_box:
        x1, y1, x2, y2 = best_box
        if max_severity >= 7:
            color, label = (0, 0, 255), f"SEVERE HAZARD: {max_severity}/10"
        elif max_severity > 4:
            color, label = (0, 165, 255), f"MODERATE: {max_severity}/10"
        else:
            color, label = (0, 255, 255), f"MINOR: {max_severity}/10"

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
        cv2.putText(
            img,
            label,
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )
    else:
        # If no defect is found, clearly state it on the image
        cv2.putText(img, "ROAD CLEAR: No Defects", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)

    cv2.imwrite(output_path, img)


def analyze_media(file_path):
    """Master Pipeline: Routes images and videos to the correct processor."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    mime_type, _ = mimetypes.guess_type(file_path)
    is_video = mime_type and mime_type.startswith('video')
    annotated_path = os.path.join(TEMP_DIR, "annotated_defect.jpg")

    if is_video:
        cap = cv2.VideoCapture(file_path)
        overall_max_severity, overall_best_box, overall_defect = 0.0, None, False
        best_frame = None
        valid_detections = []

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Save at least one frame in case the video is completely clean
            if best_frame is None:
                best_frame = frame.copy()

            if frame_count % VIDEO_SAMPLE_EVERY == 0:
                defect, severity, box = process_frame(frame)
                if defect:
                    valid_detections.append((frame_count, severity, box, frame.copy()))
            frame_count += 1
        cap.release()

        if len(valid_detections) >= MIN_VIDEO_HITS:
            overall_defect = True
            _, overall_max_severity, overall_best_box, best_frame = max(
                valid_detections, key=lambda item: item[1]
            )
        elif valid_detections:
            # One isolated detection is treated as noise for a video.
            best_frame = valid_detections[0][3]

        if best_frame is None:
            cap = cv2.VideoCapture(file_path)
            _, best_frame = cap.read()
            cap.release()

        if best_frame is not None:
            annotate_and_save(
                best_frame,
                overall_max_severity if overall_defect else 0.0,
                overall_best_box if overall_defect else None,
                annotated_path,
            )

        lat, lon = 16.2341, 80.5482
        estimate = (
            estimate_pothole_severity(overall_best_box, best_frame.shape)
            if overall_defect and overall_best_box and best_frame is not None
            else None
        )

        return {
            "defect_detected": overall_defect,
            "defect_type": "Structural Defect" if overall_defect else "None",
            "severity_score": overall_max_severity if overall_defect else 0,
            "severity_level": estimate["severity_level"] if estimate else None,
            "estimated_depth_cm": estimate["estimated_depth_cm"] if estimate else None,
            "email_report_string": estimate["email_report_string"] if estimate else None,
            "frames_checked": frame_count,
            "valid_detection_frames": len(valid_detections),
            "annotated_image_path": annotated_path,
            "raw_lat": lat, "raw_lon": lon
        }

    else:
        img = cv2.imread(file_path)
        if img is None: return {"error": "Could not read image file"}

        defect, severity, box = process_frame(img)
        annotate_and_save(img, severity, box, annotated_path)
        lat, lon = extract_gps(file_path)
        estimate = estimate_pothole_severity(box, img.shape) if defect and box else None

        return {
            "defect_detected": defect,
            "defect_type": "Structural Defect" if defect else "None",
            "severity_score": severity if defect else 0,
            "severity_level": estimate["severity_level"] if estimate else None,
            "estimated_depth_cm": estimate["estimated_depth_cm"] if estimate else None,
            "email_report_string": estimate["email_report_string"] if estimate else None,
            "annotated_image_path": annotated_path,
            "raw_lat": lat, "raw_lon": lon
        }


# --- Quick Local Test ---
if __name__ == "__main__":
    test_file = "test_pothole.jpg"  # Change to your test image or video file

    if os.path.exists(test_file):
        print(f"\n🚀 Analyzing media with custom model: '{test_file}'...")
        result = analyze_media(test_file)

        print("\n📊 --- Engine Output ---")
        if result.get("error"):
            print(f"❌ Error: {result['error']}")
        elif result["defect_detected"]:
            print(f"⚠️ DEFECT FOUND: {result['defect_type']} (Severity: {result['severity_score']}/10)")
        else:
            print("✅ NO DEFECTS FOUND: The road appears clear.")

        print(json.dumps(result, indent=4))
        print(f"\n📸 Visual proof saved to: '{result.get('annotated_image_path')}'")
    else:
        print(f"\n⚠️ ERROR: Please add '{test_file}' to your main project folder to test.")
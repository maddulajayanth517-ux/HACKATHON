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

# Load your custom-trained high-clarity Roboflow YOLO model
MODEL = YOLO('best.pt')


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
    """Core logic to analyze a single frame or image using the custom model."""
    h, w, _ = img.shape
    total_area = h * w
    processed_img = apply_clahe(img)

    # Run inference with a strict 0.4 confidence threshold to prevent false positives on clean roads
    results = MODEL(processed_img, conf=0.4, verbose=False)[0]

    defect_detected, max_severity, best_box = False, 0.0, None

    for box in results.boxes:
        defect_detected = True
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        area_ratio = ((x2 - x1) * (y2 - y1)) / total_area
        severity = min(round((area_ratio * 100) + 1.0, 1), 10.0)

        if severity > max_severity:
            max_severity = severity
            best_box = (x1, y1, x2, y2)

    return defect_detected, max_severity, best_box


def annotate_and_save(img, max_severity, best_box, output_path):
    """Draws the bounding box or a 'Clear Road' message and saves the image."""
    if best_box:
        x1, y1, x2, y2 = best_box
        if max_severity > 7:
            color, label = (0, 0, 255), f"SEVERE HAZARD: {max_severity}/10"
        elif max_severity > 4:
            color, label = (0, 165, 255), f"MODERATE: {max_severity}/10"
        else:
            color, label = (0, 255, 255), f"MINOR: {max_severity}/10"

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
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

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # Save at least one frame in case the video is completely clean
            if best_frame is None:
                best_frame = frame.copy()

            if frame_count % 5 == 0:
                defect, severity, box = process_frame(frame)
                if severity > overall_max_severity:
                    overall_max_severity = severity
                    overall_best_box = box
                    overall_defect = defect
                    best_frame = frame.copy()
            frame_count += 1
        cap.release()

        if best_frame is not None:
            annotate_and_save(best_frame, overall_max_severity, overall_best_box, annotated_path)

        lat, lon = 16.2341, 80.5482

        return {
            "defect_detected": overall_defect,
            "defect_type": "Structural Defect" if overall_defect else "None",
            "severity_score": overall_max_severity if overall_defect else 0,
            "annotated_image_path": annotated_path,
            "raw_lat": lat, "raw_lon": lon
        }

    else:
        img = cv2.imread(file_path)
        if img is None: return {"error": "Could not read image file"}

        defect, severity, box = process_frame(img)
        annotate_and_save(img, severity, box, annotated_path)
        lat, lon = extract_gps(file_path)

        return {
            "defect_detected": defect,
            "defect_type": "Structural Defect" if defect else "None",
            "severity_score": severity if defect else 0,
            "annotated_image_path": annotated_path,
            "raw_lat": lat, "raw_lon": lon
        }


# --- Quick Local Test ---
if __name__ == "__main__":
    test_file = "Test_vid.mp4"

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
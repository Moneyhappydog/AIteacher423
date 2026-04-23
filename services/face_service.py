"""
Face emotion detection service.
Uses OpenCV Haar cascade for face detection,
dlib 68-point landmarks for visualization,
and FER2013 mini-XCEPTION CNN for emotion classification.
"""
import base64
import io
import threading

import cv2
import numpy as np

# Lazy-loaded globals protected by lock
_lock = threading.Lock()
_face_detector = None
_emotion_model = None
_dlib_detector = None
_dlib_predictor = None

EMOTION_LABELS_CN = {
    0: '生气', 1: '厌恶', 2: '害怕',
    3: '开心', 4: '难过', 5: '惊讶', 6: '平静'
}
EMOTION_COLORS = {
    0: (60, 80, 220),   # angry - red/blue
    1: (40, 160, 40),   # disgust - green
    2: (200, 60, 200),  # fear - purple
    3: (30, 200, 255),  # happy - yellow/orange
    4: (200, 100, 30),  # sad - blue
    5: (0, 200, 200),   # surprise - teal
    6: (160, 160, 160), # neutral - gray
}


def _load_models(face_model_path, dlib_dat_path):
    global _face_detector, _emotion_model, _dlib_detector, _dlib_predictor
    with _lock:
        if _face_detector is None:
            import os
            # services/face_service.py -> services -> eduplatform (project root)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cascade_path = os.path.join(project_root, 'models', 'trained_models_face', 'detection_models', 'haarcascade_frontalface_default.xml')

            if os.path.exists(cascade_path):
                _face_detector = cv2.CascadeClassifier(cascade_path)
            else:
                # 文件不存在，抛出详细错误
                raise FileNotFoundError(
                    f"Haar cascade NOT FOUND!\n"
                    f"  Project root: {project_root}\n"
                    f"  Looking for: {cascade_path}\n"
                    f"  Please upload models/trained_models_face/detection_models/haarcascade_frontalface_default.xml to server!"
                )

        if _emotion_model is None:
            try:
                from tensorflow.keras.models import load_model
                _emotion_model = load_model(face_model_path, compile=False)
            except Exception as e:
                print(f"[FaceService] Failed to load emotion model: {e}")

        if _dlib_detector is None:
            try:
                import dlib
                _dlib_detector = dlib.get_frontal_face_detector()
                _dlib_predictor = dlib.shape_predictor(dlib_dat_path)
            except Exception as e:
                print(f"[FaceService] dlib not available: {e}")
                _dlib_detector = False  # Mark as unavailable


def predict_frame(image_b64: str, face_model_path: str, dlib_dat_path: str) -> dict:
    """Process a base64-encoded JPEG frame, return annotated image + emotion."""
    _load_models(face_model_path, dlib_dat_path)

    # Decode base64 image
    try:
        img_data = base64.b64decode(image_b64.split(',')[-1])
        nparr = np.frombuffer(img_data, np.uint8)
        bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if bgr_img is None:
            return {"error": "无法解析图像"}
    except Exception as e:
        return {"error": f"图像解码错误: {e}"}

    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    output_img = bgr_img.copy()

    # Detect faces
    faces = _face_detector.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )

    results = []

    for (x, y, w, h) in faces:
        # --- Draw dlib 68 landmarks ---
        if _dlib_detector and _dlib_predictor:
            try:
                import dlib
                rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
                shape = _dlib_predictor(gray, rect)
                for i in range(68):
                    px = shape.part(i).x
                    py = shape.part(i).y
                    cv2.circle(output_img, (px, py), 2, (0, 255, 100), -1)
            except Exception:
                pass

        # --- Emotion classification ---
        emotion_label_cn = '未检测到'
        emotion_idx = -1
        scores = []

        if _emotion_model is not None:
            try:
                emotion_target_size = _emotion_model.input_shape[1:3]
                x1 = max(0, x - 10)
                y1 = max(0, y - 10)
                x2 = min(bgr_img.shape[1], x + w + 10)
                y2 = min(bgr_img.shape[0], y + h + 10)
                face_gray = gray[y1:y2, x1:x2]
                face_resized = cv2.resize(face_gray, emotion_target_size)
                face_arr = face_resized.astype('float32') / 255.0
                face_arr = np.expand_dims(face_arr, axis=0)
                face_arr = np.expand_dims(face_arr, axis=-1)

                preds = _emotion_model.predict(face_arr, verbose=0)[0]
                emotion_idx = int(np.argmax(preds))
                emotion_label_cn = EMOTION_LABELS_CN.get(emotion_idx, '?')
                scores = [float(p) for p in preds]
            except Exception as e:
                print(f"[FaceService] Emotion inference error: {e}")

        # --- Draw bounding box and label ---
        color = EMOTION_COLORS.get(emotion_idx, (255, 255, 255))
        cv2.rectangle(output_img, (x, y), (x + w, y + h), color, 3)

        label_en = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']
        label_str = label_en[emotion_idx] if 0 <= emotion_idx < 7 else 'unknown'

        cv2.rectangle(output_img, (x, y - 35), (x + w, y), color, -1)
        cv2.putText(
            output_img, label_str, (x + 5, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA
        )

        results.append({
            'box': [int(x), int(y), int(w), int(h)],
            'emotion_idx': emotion_idx,
            'emotion_cn': emotion_label_cn,
            'emotion_en': label_str,
            'scores': scores
        })

    # Encode annotated image back to base64
    _, buffer = cv2.imencode('.jpg', output_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    img_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode('utf-8')

    return {
        'image': img_b64,
        'faces': results,
        'face_count': len(results)
    }

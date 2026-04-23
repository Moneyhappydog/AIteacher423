"""
人脸图像预处理服务
提供多种图像预处理方法，用于数据增强和标准化
"""
import os
import io
import base64
import random
import numpy as np
import cv2
from typing import Optional, Tuple, List, Dict

# dlib 68点关键点索引
LEFT_EYE_INDICES = [36, 37, 38, 39, 40, 41]
RIGHT_EYE_INDICES = [42, 43, 44, 45, 46, 47]

# 情绪标签
EMOTION_LABELS = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']


class FacePreprocessor:
    """人脸图像预处理器"""

    def __init__(self, dlib_model_path: str = None):
        """
        初始化预处理器

        Args:
            dlib_model_path: dlib 68点关键点模型路径
        """
        self.dlib_model_path = dlib_model_path
        self._detector = None
        self._shape_predictor = None
        self._lock = None

    def _init_models(self):
        """延迟加载模型"""
        if self._detector is None:
            import threading
            self._lock = threading.Lock()

            with self._lock:
                if self._detector is None:
                    import dlib
                    self._detector = dlib.get_frontal_face_detector()

                    if self.dlib_model_path and os.path.exists(self.dlib_model_path):
                        self._shape_predictor = dlib.shape_predictor(self.dlib_model_path)

    def load_image_from_base64(self, image_data: str) -> np.ndarray:
        """从base64加载图像"""
        img_bytes = base64.b64decode(image_data.split(',')[-1] if ',' in image_data else image_data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def load_image_from_file(self, filepath: str) -> np.ndarray:
        """从文件加载图像"""
        return cv2.imread(filepath)

    def image_to_base64(self, image: np.ndarray, format: str = 'JPEG') -> str:
        """图像转base64"""
        _, buffer = cv2.imencode(f'.{format}', image)
        return base64.b64encode(buffer).decode('utf-8')

    def image_to_base64_dataurl(self, image: np.ndarray, format: str = 'JPEG') -> str:
        """图像转base64 DataURL"""
        mime_type = 'image/jpeg' if format.lower() == 'jpeg' else f'image/{format.lower()}'
        _, buffer = cv2.imencode(f'.{format}', image)
        return f"data:{mime_type};base64,{base64.b64encode(buffer).decode('utf-8')}"

    # ── 基础预处理 ────────────────────────────────────────────────────────────

    def face_detection_and_align(self, image: np.ndarray, target_size: Tuple[int, int] = (128, 128)) -> Dict:
        """
        人脸检测与对齐

        Args:
            image: 输入图像 (BGR格式)
            target_size: 输出尺寸

        Returns:
            {
                'success': bool,
                'aligned_face': np.ndarray or None,
                'original_face': np.ndarray or None,
                'landmarks': list,
                'face_box': dict
            }
        """
        self._init_models()
        import dlib

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._detector(gray, 1)

        if len(faces) == 0:
            return {
                'success': False,
                'error': '未检测到人脸',
                'aligned_face': None,
                'original_face': None,
                'landmarks': [],
                'face_box': None
            }

        # 取最大的人脸
        face = max(faces, key=lambda f: f.width() * f.height())

        # 提取关键点
        if self._shape_predictor:
            shape = self._shape_predictor(gray, face)
            landmarks = [(point.x, point.y) for point in shape.parts()]
        else:
            landmarks = []

        # 人脸区域
        x, y, w, h = face.left(), face.top(), face.width(), face.height()

        # 扩展边界
        margin = int(max(w, h) * 0.2)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(image.shape[1], x + w + margin)
        y2 = min(image.shape[0], y + h + margin)

        # 裁剪原始人脸
        face_crop = image[y1:y2, x1:x2]

        # 如果有双眼关键点，进行对齐
        aligned_face = face_crop
        if self._shape_predictor and len(landmarks) >= 68:
            left_eye = np.mean([landmarks[i] for i in LEFT_EYE_INDICES], axis=0)
            right_eye = np.mean([landmarks[i] for i in RIGHT_EYE_INDICES], axis=0)

            # 计算旋转角度
            dx, dy = right_eye - left_eye
            angle = np.degrees(np.arctan2(dy, dx))

            # 目标眼睛位置（水平）
            eye_distance = np.linalg.norm(right_eye - left_eye)
            target_eye_distance = target_size[0] * 0.3
            scale = target_eye_distance / eye_distance if eye_distance > 0 else 1

            # 计算旋转中心
            center = ((left_eye[0] + right_eye[0]) / 2, (left_eye[1] + right_eye[1]) / 2)

            # 旋转矩阵
            M = cv2.getRotationMatrix2D(center, angle, scale)
            aligned_face = cv2.warpAffine(image, M, (image.shape[1], image.shape[0]))

            # 重新裁剪
            x, y, w, h = face.left(), face.top(), face.width(), face.height()
            margin = int(max(w, h) * 0.3)
            x1 = max(0, x - margin)
            y1 = max(0, y - margin)
            x2 = min(aligned_face.shape[1], x + w + margin)
            y2 = min(aligned_face.shape[0], y + h + margin)
            aligned_face = aligned_face[y1:y2, x1:x2]

        # 调整大小
        aligned_face = cv2.resize(aligned_face, target_size)

        return {
            'success': True,
            'aligned_face': aligned_face,
            'original_face': face_crop,
            'landmarks': landmarks[:68] if landmarks else [],
            'face_box': {'x': x, 'y': y, 'w': w, 'h': h}
        }

    def normalize(self, image: np.ndarray, method: str = 'minmax') -> np.ndarray:
        """
        图像归一化

        Args:
            image: 输入图像
            method: 'minmax' (0-1), 'standard' (均值0方差1)

        Returns:
            归一化后的图像
        """
        if method == 'minmax':
            return image.astype(np.float32) / 255.0
        elif method == 'standard':
            mean = np.mean(image)
            std = np.std(image)
            if std < 1e-6:
                std = 1.0
            return (image.astype(np.float32) - mean) / std
        return image.astype(np.float32) / 255.0

    def histogram_equalization(self, image: np.ndarray) -> np.ndarray:
        """
        直方图均衡化

        Args:
            image: 输入图像（灰度或彩色）

        Returns:
            均衡化后的图像
        """
        if len(image.shape) == 2:
            return cv2.equalizeHist(image)
        else:
            # 彩色图像 - 转换到YUV，对亮度通道均衡化
            yuv = cv2.cvtColor(image, cv2.COLOR_BGR2YUV)
            yuv[:, :, 0] = cv2.equalizeHist(yuv[:, :, 0])
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)

    def grayscale(self, image: np.ndarray) -> np.ndarray:
        """
        灰度化

        Args:
            image: 输入彩色图像

        Returns:
            灰度图像
        """
        if len(image.shape) == 2:
            return image
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ── 数据增强 - 几何变换 ───────────────────────────────────────────────────

    def horizontal_flip(self, image: np.ndarray) -> np.ndarray:
        """水平翻转"""
        return cv2.flip(image, 1)

    def random_rotation(self, image: np.ndarray, angle_range: Tuple[float, float] = (-10, 10)) -> np.ndarray:
        """
        随机旋转

        Args:
            image: 输入图像
            angle_range: 旋转角度范围 (min, max)

        Returns:
            旋转后的图像
        """
        angle = random.uniform(angle_range[0], angle_range[1])
        h, w = image.shape[:2]
        center = (w / 2, h / 2)

        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(image, M, (w, h), borderValue=(0, 0, 0))

    def random_crop(self, image: np.ndarray, crop_ratio: float = 0.8) -> np.ndarray:
        """
        随机裁剪

        Args:
            image: 输入图像
            crop_ratio: 裁剪比例 (0-1)

        Returns:
            裁剪并调整回原大小的图像
        """
        h, w = image.shape[:2]
        new_h, new_w = int(h * crop_ratio), int(w * crop_ratio)

        top = random.randint(0, h - new_h)
        left = random.randint(0, w - new_w)

        cropped = image[top:top + new_h, left:left + new_w]
        return cv2.resize(cropped, (w, h))

    # ── 数据增强 - 颜色变换 ──────────────────────────────────────────────────

    def adjust_brightness(self, image: np.ndarray, factor: float = 1.2) -> np.ndarray:
        """
        调整亮度

        Args:
            image: 输入图像
            factor: 亮度因子 (>1变亮, <1变暗)

        Returns:
            调整后的图像
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hsv = hsv.astype(np.float32)
        hsv[:, :, 2] = hsv[:, :, 2] * factor
        hsv[:, :, 2] = np.clip(hsv[:, :, 2], 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    def adjust_contrast(self, image: np.ndarray, factor: float = 1.3) -> np.ndarray:
        """
        调整对比度

        Args:
            image: 输入图像
            factor: 对比度因子

        Returns:
            调整后的图像
        """
        mean = np.mean(image)
        contrasted = (image.astype(np.float32) - mean) * factor + mean
        return np.clip(contrasted, 0, 255).astype(np.uint8)

    def adjust_saturation(self, image: np.ndarray, factor: float = 1.3) -> np.ndarray:
        """
        调整饱和度

        Args:
            image: 输入图像
            factor: 饱和度因子

        Returns:
            调整后的图像
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hsv = hsv.astype(np.float32)
        hsv[:, :, 1] = hsv[:, :, 1] * factor
        hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    def add_gaussian_noise(self, image: np.ndarray, mean: float = 0, std: float = 10) -> np.ndarray:
        """
        添加高斯噪声

        Args:
            image: 输入图像
            mean: 噪声均值
            std: 噪声标准差

        Returns:
            添加噪声后的图像
        """
        noise = np.random.normal(mean, std, image.shape).astype(np.float32)
        noisy = image.astype(np.float32) + noise
        return np.clip(noisy, 0, 255).astype(np.uint8)

    def apply_blur(self, image: np.ndarray, kernel_size: int = 5) -> np.ndarray:
        """
        高斯模糊

        Args:
            image: 输入图像
            kernel_size: 核大小（必须是奇数）

        Returns:
            模糊后的图像
        """
        if kernel_size % 2 == 0:
            kernel_size += 1
        return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)

    def adjust_hue(self, image: np.ndarray, shift: float = 10) -> np.ndarray:
        """
        调整色调

        Args:
            image: 输入图像
            shift: 色相偏移值 (-180 ~ 180)

        Returns:
            调整后的图像
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hsv = hsv.astype(np.float32)
        hsv[:, :, 0] = (hsv[:, :, 0] + shift) % 180
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # ── 组合预处理 ────────────────────────────────────────────────────────────

    def preprocess_single(
        self,
        image: np.ndarray,
        operations: List[str],
        params: Dict = None
    ) -> Tuple[np.ndarray, str]:
        """
        对单张图像应用预处理操作

        Args:
            image: 输入图像
            operations: 操作列表，如 ['align', 'flip', 'brightness']
            params: 操作参数字典

        Returns:
            (处理后的图像, 操作后缀名)
        """
        params = params or {}
        suffix_parts = []

        for op in operations:
            if op == 'align':
                result = self.face_detection_and_align(image)
                if result['success']:
                    image = result['aligned_face']
                    suffix_parts.append('align')
            elif op == 'grayscale':
                image = self.grayscale(image)
                suffix_parts.append('gray')
            elif op == 'histeq':
                image = self.histogram_equalization(image)
                suffix_parts.append('heq')
            elif op == 'hflip':
                image = self.horizontal_flip(image)
                suffix_parts.append('hflip')
            elif op == 'rotate':
                angle = params.get('rotation_angle', random.uniform(-10, 10))
                image = self.random_rotation(image, (angle, angle))
                suffix_parts.append(f'rot{int(angle)}')
            elif op == 'crop':
                ratio = params.get('crop_ratio', 0.8)
                image = self.random_crop(image, ratio)
                suffix_parts.append('crop')
            elif op == 'brightness':
                factor = params.get('brightness_factor', 1.2)
                image = self.adjust_brightness(image, factor)
                suffix_parts.append(f'bright{int(factor*10)}')
            elif op == 'contrast':
                factor = params.get('contrast_factor', 1.3)
                image = self.adjust_contrast(image, factor)
                suffix_parts.append(f'contrast{int(factor*10)}')
            elif op == 'saturation':
                factor = params.get('saturation_factor', 1.3)
                image = self.adjust_saturation(image, factor)
                suffix_parts.append(f'sat{int(factor*10)}')
            elif op == 'hue':
                shift = params.get('hue_shift', 10)
                image = self.adjust_hue(image, shift)
                suffix_parts.append(f'hue{int(shift)}')
            elif op == 'blur':
                kernel = params.get('blur_kernel', 5)
                image = self.apply_blur(image, kernel)
                suffix_parts.append(f'blur{kernel}')
            elif op == 'noise':
                std = params.get('noise_std', 10)
                image = self.add_gaussian_noise(image, std=std)
                suffix_parts.append(f'gnoise{std}')

        suffix = '_'.join(suffix_parts) if suffix_parts else 'original'
        return image, suffix

    def batch_preprocess(
        self,
        images: List[np.ndarray],
        operations: List[str],
        params: Dict = None
    ) -> List[Tuple[np.ndarray, str]]:
        """
        批量预处理

        Args:
            images: 图像列表
            operations: 操作列表
            params: 操作参数

        Returns:
            [(处理后图像, 操作后缀), ...]
        """
        return [self.preprocess_single(img, operations, params) for img in images]


def preprocess_image(
    image_data: str,
    operations: List[str],
    params: Dict = None,
    dlib_model_path: str = None
) -> Dict:
    """
    便捷预处理函数

    Args:
        image_data: base64编码的图像数据
        operations: 操作列表
        params: 操作参数
        dlib_model_path: dlib模型路径

    Returns:
        {
            'success': bool,
            'original': base64编码的原图,
            'processed': base64编码的处理后图,
            'suffix': 操作后缀,
            'width': 宽度,
            'height': 高度
        }
    """
    preprocessor = FacePreprocessor(dlib_model_path)

    try:
        original = preprocessor.load_image_from_base64(image_data)
        processed, suffix = preprocessor.preprocess_single(original, operations, params)

        return {
            'success': True,
            'original': preprocessor.image_to_base64_dataurl(original),
            'processed': preprocessor.image_to_base64_dataurl(processed),
            'suffix': suffix,
            'width': processed.shape[1],
            'height': processed.shape[0]
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_available_operations() -> List[Dict]:
    """获取所有可用的预处理操作"""
    return [
        {
            'id': 'align',
            'name': '人脸对齐',
            'category': '基础预处理',
            'description': '使用dlib检测人脸并进行仿射变换对齐'
        },
        {
            'id': 'grayscale',
            'name': '灰度化',
            'category': '基础预处理',
            'description': '将彩色图像转换为灰度图像'
        },
        {
            'id': 'histeq',
            'name': '直方图均衡化',
            'category': '基础预处理',
            'description': '增强图像对比度'
        },
        {
            'id': 'hflip',
            'name': '水平翻转',
            'category': '几何变换',
            'description': '随机水平翻转图像'
        },
        {
            'id': 'rotate',
            'name': '随机旋转',
            'category': '几何变换',
            'description': '-10°~+10°随机旋转'
        },
        {
            'id': 'crop',
            'name': '随机裁剪',
            'category': '几何变换',
            'description': '随机裁剪后调整回原尺寸'
        },
        {
            'id': 'brightness',
            'name': '亮度调整',
            'category': '颜色变换',
            'description': '调整图像亮度'
        },
        {
            'id': 'contrast',
            'name': '对比度调整',
            'category': '颜色变换',
            'description': '调整图像对比度'
        },
        {
            'id': 'saturation',
            'name': '饱和度调整',
            'category': '颜色变换',
            'description': '调整图像饱和度'
        },
        {
            'id': 'hue',
            'name': '色调调整',
            'category': '颜色变换',
            'description': '调整图像色调'
        },
        {
            'id': 'blur',
            'name': '模糊处理',
            'category': '颜色变换',
            'description': '高斯模糊效果'
        },
        {
            'id': 'noise',
            'name': '高斯噪声',
            'category': '颜色变换',
            'description': '添加高斯噪声'
        }
    ]

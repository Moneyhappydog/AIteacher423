"""
模型评估服务
功能：
1. 使用测试集评估模型
2. 计算评估指标（准确率、精确率、召回率、F1分数）
3. 生成评估报告
4. 结果同步到排行榜
"""
import os
import io
import json
import csv
import uuid
import tempfile
import shutil
from datetime import datetime
from config import Config
from services.testset_service import get_testset_service


class ModelEvalService:
    """模型评估服务"""

    # 评估结果存储目录
    EVAL_RESULTS_DIR = os.path.join(Config.BASE_DIR, 'data', 'eval_results')

    # 情绪标签映射（7类）
    FACE_EMOTION_MAP = {
        'angry': 0, 'disgust': 1, 'fear': 2,
        'happy': 3, 'sad': 4, 'surprise': 5, 'neutral': 6
    }

    # 中文标签到英文标签的映射
    FACE_CHINESE_TO_ENGLISH = {
        '生气': 'angry', '厌恶': 'disgust', '恐惧': 'fear',
        '开心': 'happy', '平静': 'neutral', '难过': 'sad', '惊讶': 'surprise',
        'neutral': 'neutral', 'angry': 'angry', 'happy': 'happy'
    }

    # 音频情绪标签映射（6类）
    AUDIO_EMOTION_MAP = {
        'anger': 0, 'fear': 1, 'happy': 2,
        'neutral': 3, 'sad': 4, 'surprise': 5
    }

    # 评估状态
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    def __init__(self):
        """确保目录存在"""
        os.makedirs(self.EVAL_RESULTS_DIR, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. 创建评估任务
    # ─────────────────────────────────────────────────────────────────────────

    def create_eval_task(self, model_id, testset_id, course, group_id):
        """
        创建评估任务

        Args:
            model_id: 模型ID
            testset_id: 测试集ID
            course: 课程类型 (face/audio)
            group_id: 小组ID

        Returns:
            dict: {success, task_id, message}
        """
        # 获取模型信息
        from services.model_import_service import get_model_import_service
        model_service = get_model_import_service()
        model_info = model_service.get_model(model_id)

        if not model_info:
            return {'success': False, 'message': '模型不存在'}

        # 获取测试集信息
        testset_service = get_testset_service()
        testsets = testset_service.get_group_available_testsets(course)

        testset_info = None
        for t in testsets:
            if t['testset_id'] == testset_id:
                testset_info = t
                break

        if not testset_info:
            return {'success': False, 'message': '测试集不存在或未发布给您'}

        # 创建任务
        task_id = str(uuid.uuid4())[:12]
        task_dir = os.path.join(self.EVAL_RESULTS_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        # 保存任务信息
        task_info = {
            'task_id': task_id,
            'model_id': model_id,
            'model_name': model_info.get('model_name', '未知模型'),
            'model_framework': model_info.get('framework', 'unknown'),
            'model_path': model_service.get_model_path(model_id),
            'testset_id': testset_id,
            'testset_name': testset_info.get('name', '未知测试集'),
            'course': course,
            'group_id': group_id,
            'status': self.STATUS_PENDING,
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'progress': 0,
            'total_samples': 0,
            'processed_samples': 0,
            'metrics': None,
            'predictions': [],
            'error': None
        }

        self._save_task(task_id, task_info)

        return {
            'success': True,
            'task_id': task_id,
            'message': '评估任务创建成功'
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 2. 执行评估
    # ─────────────────────────────────────────────────────────────────────────

    def run_evaluation(self, task_id):
        """
        执行评估任务

        Args:
            task_id: 任务ID

        Returns:
            dict: {success, metrics, report}
        """
        task_info = self._load_task(task_id)
        if not task_info:
            return {'success': False, 'message': '任务不存在'}

        # 更新状态为运行中
        task_info['status'] = self.STATUS_RUNNING
        task_info['started_at'] = datetime.now().isoformat()
        self._save_task(task_id, task_info)

        try:
            # 加载测试集
            testset_service = get_testset_service()
            course = task_info['course']
            testset_id = task_info['testset_id']

            # 获取测试集数据（不含标签）
            testset_dir = os.path.join(
                Config.BASE_DIR, 'data', 'test_sets', course,
                '_published', testset_id, 'data'
            )

            # 如果没有data子目录，使用主目录
            if not os.path.exists(testset_dir):
                testset_dir = os.path.join(
                    Config.BASE_DIR, 'data', 'test_sets', course,
                    '_published', testset_id
                )

            # 读取测试集标签
            labels_path = os.path.join(
                Config.BASE_DIR, 'data', 'test_sets', course,
                '_published', testset_id, 'test_labels.csv'
            )

            if not os.path.exists(labels_path):
                # 尝试生成标签
                labels_path = self._generate_labels_from_files(course, testset_dir, testset_id)

            # 加载真实标签
            true_labels = self._load_labels(labels_path)

            if not true_labels:
                raise Exception('无法加载测试集标签')

            # 获取测试文件
            ext = '.jpg' if course == 'face' else '.wav'
            test_files = [
                f for f in os.listdir(testset_dir)
                if os.path.isfile(os.path.join(testset_dir, f)) and f.endswith(ext)
            ]

            task_info['total_samples'] = len(test_files)
            self._save_task(task_id, task_info)

            # 加载模型（失败时抛出具体原因，例如缺少 onnxruntime）
            model = self._load_model(
                task_info['model_path'],
                task_info['model_framework']
            )

            # 执行推理
            predictions = []
            processed = 0

            emotion_map = self.FACE_EMOTION_MAP if course == 'face' else self.AUDIO_EMOTION_MAP
            emotion_list = list(emotion_map.keys())

            for filename in test_files:
                file_path = os.path.join(testset_dir, filename)

                # 获取预测结果
                pred = self._predict(model, file_path, course, task_info['model_framework'])
                predictions.append({
                    'filename': filename,
                    'predicted': pred['emotion'],
                    'confidence': pred['confidence']
                })

                processed += 1
                task_info['processed_samples'] = processed
                task_info['progress'] = int(processed / len(test_files) * 100)
                self._save_task(task_id, task_info)

            # 计算指标
            metrics = self._calculate_metrics(predictions, true_labels, emotion_list, course)

            # 更新任务结果
            task_info['status'] = self.STATUS_COMPLETED
            task_info['completed_at'] = datetime.now().isoformat()
            task_info['progress'] = 100
            task_info['metrics'] = metrics
            task_info['predictions'] = predictions
            self._save_task(task_id, task_info)

            # 更新模型的准确率
            from services.model_import_service import get_model_import_service
            model_service = get_model_import_service()
            model_service.update_model_accuracy(
                task_info['model_id'],
                metrics['accuracy']
            )

            # 同步到排行榜
            self._sync_to_leaderboard(task_info, metrics)

            return {
                'success': True,
                'task_id': task_id,
                'metrics': metrics,
                'report': self._generate_report(task_info, metrics)
            }

        except Exception as e:
            task_info['status'] = self.STATUS_FAILED
            task_info['error'] = str(e)
            task_info['completed_at'] = datetime.now().isoformat()
            self._save_task(task_id, task_info)
            return {'success': False, 'message': f'评估失败：{str(e)}'}

    # ─────────────────────────────────────────────────────────────────────────
    # 3. 加载模型
    # ─────────────────────────────────────────────────────────────────────────

    def _load_model(self, model_path, framework):
        """加载模型。失败时抛出异常，便于界面展示真实原因。"""
        if not os.path.exists(model_path):
            raise FileNotFoundError(f'模型文件不存在：{model_path}')

        fw = (framework or '').strip().lower()
        if not fw:
            fw = self._infer_framework_from_path(model_path)

        if fw == 'tensorflow':
            try:
                import tensorflow as tf
                return tf.keras.models.load_model(model_path, compile=False)
            except ImportError as e:
                raise ImportError(
                    '未安装 TensorFlow，无法加载 .h5/.keras 模型。请执行：pip install tensorflow'
                ) from e
            except Exception as e:
                raise RuntimeError(f'TensorFlow 模型加载失败：{e}') from e

        if fw == 'pytorch':
            try:
                import torch
                return torch.load(model_path, map_location='cpu')
            except ImportError as e:
                raise ImportError(
                    '未安装 PyTorch，无法加载 .pt/.pth 模型。请执行：pip install torch'
                ) from e
            except Exception as e:
                raise RuntimeError(f'PyTorch 模型加载失败：{e}') from e

        if fw == 'sklearn':
            try:
                import pickle
                with open(model_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                raise RuntimeError(f'sklearn/pickle 模型加载失败：{e}') from e

        if fw == 'onnx':
            try:
                import onnxruntime as ort  # noqa: F401
            except ImportError as e:
                raise ImportError(
                    '未安装 onnxruntime，无法推理 ONNX 模型。请在当前 Python 环境中执行：pip install onnxruntime'
                ) from e
            return {'type': 'onnx', 'path': model_path}

        raise ValueError(f'不支持的模型框架：{framework!r}（路径：{model_path}）')

    _EXT_TO_FRAMEWORK = {
        '.h5': 'tensorflow',
        '.keras': 'tensorflow',
        '.pt': 'pytorch',
        '.pth': 'pytorch',
        '.pkl': 'sklearn',
        '.joblib': 'sklearn',
        '.onnx': 'onnx',
    }

    @classmethod
    def _infer_framework_from_path(cls, model_path):
        ext = os.path.splitext(model_path)[1].lower()
        return cls._EXT_TO_FRAMEWORK.get(ext, '')

    # ─────────────────────────────────────────────────────────────────────────
    # 4. 推理
    # ─────────────────────────────────────────────────────────────────────────

    def _predict(self, model, file_path, course, framework):
        """
        使用模型进行预测

        Returns:
            dict: {emotion, confidence}
        """
        import logging
        logger = logging.getLogger('werkzeug')

        try:
            if course == 'face':
                result = self._predict_face(model, file_path, framework)
                logger.info(f"[EVAL DEBUG] Face prediction for {file_path}: {result}")
                return result
            else:
                result = self._predict_audio(model, file_path, framework)
                logger.info(f"[EVAL DEBUG] Audio prediction for {file_path}: {result}")
                return result

        except Exception as e:
            logger.error(f"[EVAL DEBUG] Prediction error for {file_path}: {e}")
            return {'emotion': 'neutral', 'confidence': 0.0}

    def _predict_face(self, model, image_path, framework):
        """人脸表情预测"""
        import numpy as np

        emotion_map = self.FACE_EMOTION_MAP
        emotions = list(emotion_map.keys())

        try:
            if framework == 'tensorflow':
                from tensorflow.keras.preprocessing.image import load_img, img_to_array

                # 加载并预处理图像
                img = load_img(image_path, color_mode='grayscale', target_size=(48, 48))
                arr = img_to_array(img)
                arr = arr / 255.0
                arr = np.expand_dims(arr, axis=0)

                # 预测
                preds = model.predict(arr, verbose=0)[0]

            elif framework == 'pytorch':
                import torch
                from PIL import Image
                from torchvision import transforms

                transform = transforms.Compose([
                    transforms.Grayscale(),
                    transforms.Resize((48, 48)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.5], std=[0.5])
                ])

                img = Image.open(image_path)
                tensor = transform(img).unsqueeze(0)

                model.eval()
                with torch.no_grad():
                    preds = model(tensor).numpy()[0]

            elif framework == 'sklearn':
                from tensorflow.keras.preprocessing.image import load_img, img_to_array

                img = load_img(image_path, color_mode='grayscale', target_size=(48, 48))
                arr = img_to_array(img).flatten().reshape(1, -1)
                arr = arr / 255.0

                pred_idx = model.predict(arr)[0]
                preds = np.zeros(len(emotions))
                preds[pred_idx] = 1.0

            elif framework == 'onnx':
                import onnxruntime as ort
                from PIL import Image

                # 加载图像并预处理（与 train_face0037.py 训练脚本一致）
                img = Image.open(image_path).convert('L').resize((48, 48))
                # 正确形状：(height, width) -> (1, height, width, channels) = (1, 48, 48, 1)
                arr = np.array(img, dtype=np.float32)
                arr = np.expand_dims(arr, axis=0)      # (1, 48, 48)
                arr = np.expand_dims(arr, axis=-1)     # (1, 48, 48, 1)
                arr = arr / 255.0

                # 创建 inference session
                sess = ort.InferenceSession(model['path'], providers=['CPUExecutionProvider'])

                # 获取输入输出名称
                input_name = sess.get_inputs()[0].name
                output_name = sess.get_outputs()[0].name

                # 推理
                logits = sess.run([output_name], {input_name: arr})[0][0]

                # ONNX 模型输出 logits，需要 softmax 转换为概率
                exp_logits = np.exp(logits - np.max(logits))  # 数值稳定
                preds = exp_logits / np.sum(exp_logits)

            else:
                return {'emotion': 'neutral', 'confidence': 0.5}

            # 解析结果
            pred_idx = np.argmax(preds)
            confidence = float(preds[pred_idx])
            emotion = emotions[pred_idx] if pred_idx < len(emotions) else 'neutral'

            return {'emotion': emotion, 'confidence': confidence}

        except Exception as e:
            import traceback
            print(f"[PRED ERROR FACE] {image_path}: {e}")
            traceback.print_exc()
            return {'emotion': 'neutral', 'confidence': 0.0}

    def _predict_audio(self, model, audio_path, framework):
        """音频情绪预测"""
        import numpy as np

        emotion_map = self.AUDIO_EMOTION_MAP
        emotions = list(emotion_map.keys())

        try:
            if framework == 'tensorflow':
                import librosa
                from tensorflow.keras.models import Model

                # 提取音频特征（与 train_audio0052.py 训练脚本完全一致）
                y, sr = librosa.load(audio_path, sr=16000)
                mfcc = librosa.feature.mfcc(
                    y=y,
                    sr=sr,
                    n_mfcc=40,
                    n_fft=400,
                    hop_length=160
                )

                # 对齐到固定长度 (MAX_LEN = 100)
                max_len = 100
                if mfcc.shape[1] < max_len:
                    pad_width = max_len - mfcc.shape[1]
                    mfcc = np.pad(mfcc, ((0, 0), (0, pad_width)), mode='constant')
                else:
                    mfcc = mfcc[:, :max_len]

                # 归一化（与训练脚本一致）
                mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)

                # 训练脚本使用 Conv1D，输入形状是 (time_steps, n_mfcc) = (100, 40)
                # 转置得到 (100, 40)
                mfcc = mfcc.T

                # 调整为 (batch, time_steps, n_mfcc) = (1, 100, 40)
                mfcc = mfcc.reshape(1, 100, 40).astype(np.float32)

                preds = model.predict(mfcc, verbose=0)[0]

            elif framework == 'pytorch':
                import torch
                import librosa

                # 提取音频特征（与 train_audio0052.py 训练脚本完全一致）
                y, sr = librosa.load(audio_path, sr=16000)
                mfcc = librosa.feature.mfcc(
                    y=y,
                    sr=sr,
                    n_mfcc=40,
                    n_fft=400,
                    hop_length=160
                )

                # 对齐到固定长度 (MAX_LEN = 100)
                max_len = 100
                if mfcc.shape[1] < max_len:
                    pad_width = max_len - mfcc.shape[1]
                    mfcc = np.pad(mfcc, ((0, 0), (0, pad_width)), mode='constant')
                else:
                    mfcc = mfcc[:, :max_len]

                # 归一化（与训练脚本一致）
                mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)

                # 转置得到 (time_steps, n_mfcc) = (100, 40)
                mfcc = mfcc.T

                # 调整为 (batch, time_steps, n_mfcc) = (1, 100, 40)
                mfcc_tensor = torch.FloatTensor(mfcc).unsqueeze(0)

                model.eval()
                with torch.no_grad():
                    preds = model(mfcc_tensor).numpy()[0]

            elif framework == 'sklearn':
                import librosa

                # 提取音频特征（与 train_audio0052.py 训练脚本一致）
                y, sr = librosa.load(audio_path, sr=16000)
                mfcc = librosa.feature.mfcc(
                    y=y,
                    sr=sr,
                    n_mfcc=40,
                    n_fft=400,
                    hop_length=160
                )

                # 对齐到固定长度 (MAX_LEN = 100)
                max_len = 100
                if mfcc.shape[1] < max_len:
                    pad_width = max_len - mfcc.shape[1]
                    mfcc = np.pad(mfcc, ((0, 0), (0, pad_width)), mode='constant')
                else:
                    mfcc = mfcc[:, :max_len]

                # 归一化（与训练脚本一致）
                mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)

                # 转置后展平为 (4000,) 特征向量
                mfcc_flat = mfcc.T.flatten().reshape(1, -1)

                pred_idx = model.predict(mfcc_flat)[0]
                preds = np.zeros(len(emotions))
                preds[pred_idx] = 1.0

            elif framework == 'onnx':
                import librosa
                import onnxruntime as ort

                # 提取 MFCC 特征（与 train_audio0052.py 训练脚本完全一致）
                y_audio, sr_audio = librosa.load(audio_path, sr=16000)
                mfcc = librosa.feature.mfcc(
                    y=y_audio,
                    sr=sr_audio,
                    n_mfcc=40,
                    n_fft=400,
                    hop_length=160
                )

                # 对齐到固定长度 (MAX_LEN = 100)
                max_len = 100
                if mfcc.shape[1] < max_len:
                    pad_width = max_len - mfcc.shape[1]
                    mfcc = np.pad(mfcc, ((0, 0), (0, pad_width)), mode='constant')
                else:
                    mfcc = mfcc[:, :max_len]

                # 归一化（与训练脚本一致）
                mfcc = (mfcc - np.mean(mfcc)) / (np.std(mfcc) + 1e-8)

                # 转置得到 (time_steps, n_mfcc) = (100, 40)
                mfcc = mfcc.T

                # 调整为 (batch, time_steps, n_mfcc) = (1, 100, 40)
                mfcc = mfcc.reshape(1, 100, 40).astype(np.float32)

                # 创建 inference session
                sess = ort.InferenceSession(model['path'], providers=['CPUExecutionProvider'])

                # 获取输入输出名称
                input_name = sess.get_inputs()[0].name
                output_name = sess.get_outputs()[0].name

                # 推理
                preds = sess.run([output_name], {input_name: mfcc})[0][0]

            else:
                return {'emotion': 'neutral', 'confidence': 0.5}

            # 解析结果
            pred_idx = np.argmax(preds)
            confidence = float(preds[pred_idx])
            emotion = emotions[pred_idx] if pred_idx < len(emotions) else 'neutral'

            return {'emotion': emotion, 'confidence': confidence}

        except Exception:
            return {'emotion': 'neutral', 'confidence': 0.0}

    # ─────────────────────────────────────────────────────────────────────────
    # 5. 计算指标
    # ─────────────────────────────────────────────────────────────────────────

    def _calculate_metrics(self, predictions, true_labels, emotion_list, course='face'):
        """计算评估指标"""
        import numpy as np

        def normalize_label(label, norm_course):
            """标准化标签为英文标签"""
            if not label:
                return 'neutral'
            label = str(label).strip()
            # 已经是英文标签
            if label in emotion_list:
                return label
            # 中文标签转换（人脸）
            if norm_course == 'face':
                return self.FACE_CHINESE_TO_ENGLISH.get(label, label)
            # 音频标签
            return label

        # 构建真实标签映射
        true_map = {}
        for item in true_labels:
            filename = item.get('filename', '')
            emotion = item.get('emotion') or item.get('label', '')
            normalized_emotion = normalize_label(emotion, course)
            true_map[filename] = normalized_emotion

        # 统计
        correct = 0
        total = 0
        confusion = np.zeros((len(emotion_list), len(emotion_list)), dtype=int)
        emotion_idx = {e: i for i, e in enumerate(emotion_list)}

        emotion_stats = {e: {'tp': 0, 'fp': 0, 'fn': 0} for e in emotion_list}

        for pred in predictions:
            filename = pred['filename']
            if filename not in true_map:
                continue

            true_emotion = true_map[filename]
            pred_emotion = pred['predicted']

            total += 1
            if true_emotion == pred_emotion:
                correct += 1

            # 更新混淆矩阵
            if true_emotion in emotion_idx and pred_emotion in emotion_idx:
                true_idx = emotion_idx[true_emotion]
                pred_idx = emotion_idx[pred_emotion]
                confusion[true_idx][pred_idx] += 1

            # 更新各类别统计
            if true_emotion in emotion_stats:
                emotion_stats[true_emotion]['tp'] += 1 if true_emotion == pred_emotion else 0
                emotion_stats[true_emotion]['fp'] += 1 if true_emotion != pred_emotion else 0
                emotion_stats[true_emotion]['fn'] += 1 if true_emotion != pred_emotion else 0

        # 计算总体指标
        accuracy = correct / total if total > 0 else 0

        # 计算各类别指标
        per_class = {}
        macro_precision = 0
        macro_recall = 0
        macro_f1 = 0

        for emotion in emotion_list:
            tp = emotion_stats[emotion]['tp']
            fp = emotion_stats[emotion]['fp']
            fn = emotion_stats[emotion]['fn']

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            per_class[emotion] = {
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'support': tp + fn
            }

            macro_precision += precision
            macro_recall += recall
            macro_f1 += f1

        # 宏平均
        n_classes = len(emotion_list)
        macro_precision /= n_classes
        macro_recall /= n_classes
        macro_f1 /= n_classes

        return {
            'accuracy': accuracy,
            'precision': macro_precision,
            'recall': macro_recall,
            'f1_score': macro_f1,
            'total_samples': total,
            'correct': correct,
            'per_class': per_class,
            'confusion_matrix': confusion.tolist() if isinstance(confusion, np.ndarray) else confusion,
            'emotion_list': emotion_list
        }

    def _load_labels(self, labels_path):
        """加载标签文件"""
        if not os.path.exists(labels_path):
            return []

        labels = []
        try:
            with open(labels_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    labels.append(row)
        except Exception:
            pass

        return labels

    def _generate_labels_from_files(self, course, testset_dir, testset_id):
        """从文件名生成标签"""
        emotion_map = self.FACE_EMOTION_MAP if course == 'face' else self.AUDIO_EMOTION_MAP
        ext = '.jpg' if course == 'face' else '.wav'

        labels_path = os.path.join(
            Config.BASE_DIR, 'data', 'test_sets', course,
            '_published', testset_id, 'test_labels.csv'
        )

        # 中文到英文的完整映射
        chinese_to_english = self.FACE_CHINESE_TO_ENGLISH if course == 'face' else {}

        # 构建所有可能的情绪关键词匹配列表
        all_emotion_keywords = {}
        for eng, idx in emotion_map.items():
            all_emotion_keywords[eng.lower()] = eng
        for cn, eng in chinese_to_english.items():
            all_emotion_keywords[cn] = eng

        labels = []
        for f in os.listdir(testset_dir):
            if not f.endswith(ext):
                continue

            # 从文件名解析情绪
            emotion = None
            f_lower = f.lower()
            for keyword, eng_emotion in all_emotion_keywords.items():
                if keyword in f_lower or keyword in f:
                    emotion = eng_emotion
                    break

            # 如果没找到，尝试从FACE_CHINESE_TO_ENGLISH中匹配
            if not emotion:
                for cn_emotion in self.FACE_CHINESE_TO_ENGLISH.keys():
                    if cn_emotion in f:
                        emotion = self.FACE_CHINESE_TO_ENGLISH[cn_emotion]
                        break

            # 如果还是没找到，使用文件名中的数字ID或默认neutral
            if not emotion:
                # 尝试提取数字索引
                import re
                numbers = re.findall(r'\d+', f)
                if numbers:
                    idx = int(numbers[0])
                    if course == 'face' and 0 <= idx <= 6:
                        emotion = list(emotion_map.keys())[idx]
                    elif course == 'audio' and 0 <= idx <= 5:
                        emotion = list(emotion_map.keys())[idx]

            # 确保至少有一个标签
            if not emotion:
                emotion = 'neutral'

            labels.append({
                'filename': f,
                'emotion': emotion,
                'label': emotion
            })

        # 保存标签文件
        if labels:
            os.makedirs(os.path.dirname(labels_path), exist_ok=True)
            with open(labels_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['filename', 'emotion', 'label'])
                writer.writeheader()
                writer.writerows(labels)

        return labels_path

    # ─────────────────────────────────────────────────────────────────────────
    # 6. 生成报告
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_report(self, task_info, metrics):
        """生成评估报告"""
        report = {
            'report_id': str(uuid.uuid4())[:8],
            'generated_at': datetime.now().isoformat(),
            'model': {
                'id': task_info['model_id'],
                'name': task_info['model_name'],
                'framework': task_info['model_framework']
            },
            'testset': {
                'id': task_info['testset_id'],
                'name': task_info['testset_name']
            },
            'summary': {
                'total_samples': metrics['total_samples'],
                'correct': metrics['correct'],
                'accuracy': f"{metrics['accuracy'] * 100:.2f}%",
                'duration': self._calc_duration(task_info)
            },
            'metrics': metrics
        }

        return report

    def _calc_duration(self, task_info):
        """计算评估耗时"""
        if not task_info.get('started_at') or not task_info.get('completed_at'):
            return None

        try:
            start = datetime.fromisoformat(task_info['started_at'])
            end = datetime.fromisoformat(task_info['completed_at'])
            duration = (end - start).total_seconds()
            return f"{duration:.1f}秒"
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # 7. 同步到排行榜
    # ─────────────────────────────────────────────────────────────────────────

    def _sync_to_leaderboard(self, task_info, metrics):
        """同步评估结果到排行榜

        注意：此函数确保评估结果写入正确的排行榜文件，
        不会影响其他课程类型的排行榜数据
        """
        try:
            from services.leaderboard_service import get_leaderboard_service, submit_eval_score

            # 确定榜单类型 - 直接使用 course + '_eval' 后缀
            course = task_info['course']
            leaderboard_type = f'{course}_eval'

            # 提交到排行榜（函数内部会确保正确的文件隔离）
            result = submit_eval_score(
                course=course,  # 传入原始 course (face/audio)
                group_id=task_info['group_id'],
                group_name=task_info['group_id'],  # 使用 group_id 作为 group_name
                model_id=task_info['model_id'],
                model_name=task_info['model_name'],
                accuracy=metrics['accuracy'],
                testset_id=task_info['testset_id'],
                metrics=metrics
            )

            # 同时写入数据库（用于管理后台统计）
            try:
                from models.orm_models import db, LeaderboardRecord
                # 确保 group_id 是整数
                group_id_str = task_info['group_id']
                if isinstance(group_id_str, str) and group_id_str.startswith('G'):
                    group_id_int = int(group_id_str[1:]) if group_id_str[1:].isdigit() else 0
                else:
                    group_id_int = int(group_id_str) if str(group_id_str).isdigit() else 0

                db_record = LeaderboardRecord(
                    group_id=group_id_int,
                    course=leaderboard_type,  # 使用正确的 leaderboard_type
                    accuracy=round(metrics.get('accuracy', 0), 4),
                    correct_count=int(metrics.get('correct', 0)) if metrics.get('correct') else 0,
                    total_count=int(metrics.get('total_samples', 0)) if metrics.get('total_samples') else 0,
                    time_cost_seconds=0,
                    model_file=task_info['model_id'],
                    model_config={'model_name': task_info['model_name'], 'testset_id': task_info.get('testset_id')},
                    composite_score=round(metrics.get('accuracy', 0) * 100, 2),
                    innovation_score=70,
                    is_public=True
                )
                db.session.add(db_record)
                db.session.commit()
            except Exception as db_err:
                import logging
                logging.warning(f"排行榜记录写入数据库失败: {db_err}")

            return True
        except Exception as e:
            import logging
            logging.error(f"同步排行榜失败: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # 8. 任务管理
    # ─────────────────────────────────────────────────────────────────────────

    def get_task(self, task_id):
        """获取任务信息"""
        return self._load_task(task_id)

    def get_task_progress(self, task_id):
        """获取任务进度"""
        task = self._load_task(task_id)
        if not task:
            return None

        return {
            'task_id': task_id,
            'status': task['status'],
            'progress': task['progress'],
            'processed_samples': task['processed_samples'],
            'total_samples': task['total_samples']
        }

    def get_group_tasks(self, group_id, course=None, limit=20):
        """获取小组的评估任务"""
        tasks = []

        if not os.path.exists(self.EVAL_RESULTS_DIR):
            return tasks

        for task_id in os.listdir(self.EVAL_RESULTS_DIR):
            task_info = self._load_task(task_id)
            if not task_info:
                continue

            if task_info.get('group_id') != group_id:
                continue

            if course and task_info.get('course') != course:
                continue

            tasks.append(task_info)

        # 按时间倒序
        tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return tasks[:limit]

    def get_task_report(self, task_id):
        """获取任务评估报告"""
        task = self._load_task(task_id)
        if not task:
            return None

        if task['status'] != self.STATUS_COMPLETED:
            return None

        return self._generate_report(task, task['metrics'])

    # ─────────────────────────────────────────────────────────────────────────
    # 辅助方法
    # ─────────────────────────────────────────────────────────────────────────

    def _save_task(self, task_id, task_info):
        """保存任务信息"""
        task_dir = os.path.join(self.EVAL_RESULTS_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        task_path = os.path.join(task_dir, 'task.json')
        with open(task_path, 'w', encoding='utf-8') as f:
            json.dump(task_info, f, ensure_ascii=False, indent=2)

    def _load_task(self, task_id):
        """加载任务信息"""
        task_path = os.path.join(self.EVAL_RESULTS_DIR, task_id, 'task.json')
        if not os.path.exists(task_path):
            return None

        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None


# 全局单例
_model_eval_service = None


def get_model_eval_service():
    """获取模型评估服务单例"""
    global _model_eval_service
    if _model_eval_service is None:
        _model_eval_service = ModelEvalService()
    return _model_eval_service

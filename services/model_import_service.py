"""
模型导入服务
功能：
1. 学生上传/拖拽导入本地训练的模型
2. 模型格式验证（.h5/.pt/.pkl）
3. 模型元数据管理
"""
import os
import io
import json
import uuid
import hashlib
from datetime import datetime
from config import Config


class ModelImportService:
    """模型导入服务"""

    # 模型存储根目录
    MODEL_ROOT = os.path.join(Config.BASE_DIR, 'data', 'uploaded_models')

    # 支持的模型格式
    SUPPORTED_FORMATS = {
        '.h5': 'tensorflow',
        '.keras': 'tensorflow',
        '.pt': 'pytorch',
        '.pth': 'pytorch',
        '.pkl': 'sklearn',
        '.joblib': 'sklearn',
        '.onnx': 'onnx'
    }

    # 最大文件大小（100MB）
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self):
        """确保目录存在"""
        os.makedirs(self.MODEL_ROOT, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. 模型上传
    # ─────────────────────────────────────────────────────────────────────────

    def upload_model(self, file_obj, group_id, course, model_name=None, description=''):
        """
        上传并保存模型文件

        Args:
            file_obj: 文件对象
            group_id: 小组ID
            course: 课程类型 (face/audio/emotion/eco)
            model_name: 模型名称（可选）
            description: 模型描述

        Returns:
            dict: {success, model_id, message, metadata}
        """
        # 检查文件
        if not file_obj:
            return {'success': False, 'message': '请提供模型文件'}

        filename = file_obj.filename if hasattr(file_obj, 'filename') else str(file_obj)
        file_ext = os.path.splitext(filename)[1].lower()

        # 验证格式
        if file_ext not in self.SUPPORTED_FORMATS:
            return {
                'success': False,
                'message': f'不支持的文件格式：{file_ext}。支持的格式：{", ".join(self.SUPPORTED_FORMATS.keys())}'
            }

        # 检查文件大小
        if hasattr(file_obj, 'content_length') and file_obj.content_length:
            if file_obj.content_length > self.MAX_FILE_SIZE:
                return {
                    'success': False,
                    'message': f'文件过大，最大支持 {self.MAX_FILE_SIZE // (1024*1024)}MB'
                }

        # 生成模型ID
        model_id = str(uuid.uuid4())[:12]

        # 创建小组目录
        group_dir = os.path.join(self.MODEL_ROOT, group_id)
        os.makedirs(group_dir, exist_ok=True)

        # 保存文件
        model_filename = f"{model_id}{file_ext}"
        model_path = os.path.join(group_dir, model_filename)

        try:
            if hasattr(file_obj, 'save'):
                file_obj.save(model_path)
            else:
                # 处理BytesIO或其他文件类型
                content = file_obj.read() if hasattr(file_obj, 'read') else file_obj
                with open(model_path, 'wb') as f:
                    f.write(content)
        except Exception as e:
            return {'success': False, 'message': f'文件保存失败：{str(e)}'}

        # 计算文件哈希
        file_hash = self._calculate_file_hash(model_path)

        # 生成元数据
        framework = self.SUPPORTED_FORMATS[file_ext]
        if not model_name:
            model_name = f"模型_{datetime.now().strftime('%m%d_%H%M')}"

        metadata = {
            'model_id': model_id,
            'group_id': group_id,
            'course': course,
            'model_name': model_name,
            'description': description,
            'filename': model_filename,
            'original_filename': filename,
            'file_path': os.path.join(group_id, model_filename),
            'file_size': os.path.getsize(model_path),
            'file_hash': file_hash,
            'framework': framework,
            'file_ext': file_ext,
            'uploaded_at': datetime.now().isoformat(),
            'is_active': True,
            'accuracy': None,  # 待评估后填充
            'eval_count': 0
        }

        # 保存元数据
        self._save_metadata(model_id, metadata)

        # 更新小组索引
        self._update_group_index(group_id)

        return {
            'success': True,
            'model_id': model_id,
            'message': '模型上传成功',
            'metadata': metadata
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 2. 模型列表
    # ─────────────────────────────────────────────────────────────────────────

    def _model_dict_for_api(self, metadata):
        """列表/前端展示用：补充图标与可读文件大小。"""
        m = dict(metadata)
        m['framework_icon'] = self.get_framework_icon(m.get('framework', ''))
        m['file_size_formatted'] = self.format_file_size(m.get('file_size') or 0)
        return m

    def get_group_models(self, group_id, course=None):
        """
        获取小组的模型列表

        Args:
            group_id: 小组ID
            course: 课程类型过滤（可选）

        Returns:
            list: 模型列表
        """
        # 防御：group_id 不能为空
        if not group_id:
            return []
        group_dir = os.path.join(self.MODEL_ROOT, group_id)
        if not os.path.exists(group_dir):
            return []

        models = []
        for item in os.listdir(group_dir):
            if item.endswith('.json'):
                model_id = item.replace('.json', '')
                metadata = self._load_metadata(model_id)
                if metadata:
                    # 按课程过滤
                    if course and metadata.get('course') != course:
                        continue
                    # 只返回活跃模型
                    if metadata.get('is_active', True):
                        models.append(self._model_dict_for_api(metadata))

        # 按上传时间倒序
        models.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
        return models

    def get_all_models(self, course=None, limit=None):
        """
        获取所有小组的模型（管理员用）

        Args:
            course: 课程类型过滤
            limit: 返回数量限制

        Returns:
            list: 模型列表
        """
        all_models = []

        if not os.path.exists(self.MODEL_ROOT):
            return all_models

        for group_id in os.listdir(self.MODEL_ROOT):
            group_dir = os.path.join(self.MODEL_ROOT, group_id)
            if not os.path.isdir(group_dir):
                continue

            for item in os.listdir(group_dir):
                if item.endswith('.json'):
                    model_id = item.replace('.json', '')
                    metadata = self._load_metadata(model_id)
                    if metadata:
                        if course and metadata.get('course') != course:
                            continue
                        if metadata.get('is_active', True):
                            all_models.append(self._model_dict_for_api(metadata))

        all_models.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)

        if limit:
            all_models = all_models[:limit]

        return all_models

    # ─────────────────────────────────────────────────────────────────────────
    # 3. 模型管理
    # ─────────────────────────────────────────────────────────────────────────

    def get_model(self, model_id):
        """获取模型详情"""
        return self._load_metadata(model_id)

    def get_model_path(self, model_id):
        """获取模型文件绝对路径"""
        metadata = self._load_metadata(model_id)
        if not metadata:
            return None
        return os.path.join(self.MODEL_ROOT, metadata['file_path'])

    def rename_model(self, model_id, new_name):
        """重命名模型"""
        metadata = self._load_metadata(model_id)
        if not metadata:
            return {'success': False, 'message': '模型不存在'}

        metadata['model_name'] = new_name
        self._save_metadata(model_id, metadata)

        return {'success': True, 'message': '重命名成功'}

    def delete_model(self, model_id):
        """删除模型"""
        metadata = self._load_metadata(model_id)
        if not metadata:
            return {'success': False, 'message': '模型不存在'}

        # 删除文件
        model_path = os.path.join(self.MODEL_ROOT, metadata['file_path'])
        if os.path.exists(model_path):
            os.remove(model_path)

        # 删除元数据
        group_id = metadata.get('group_id')
        meta_path = self._get_metadata_path(model_id, group_id)
        if os.path.exists(meta_path):
            os.remove(meta_path)

        # 更新索引
        self._update_group_index(metadata['group_id'])

        return {'success': True, 'message': '模型已删除'}

    def update_model_accuracy(self, model_id, accuracy):
        """更新模型准确率（评估后调用）"""
        metadata = self._load_metadata(model_id)
        if not metadata:
            return {'success': False, 'message': '模型不存在'}

        metadata['accuracy'] = accuracy
        metadata['eval_count'] = metadata.get('eval_count', 0) + 1
        metadata['last_eval_at'] = datetime.now().isoformat()

        self._save_metadata(model_id, metadata)

        return {'success': True, 'message': '准确率已更新'}

    # ─────────────────────────────────────────────────────────────────────────
    # 4. 模型验证
    # ─────────────────────────────────────────────────────────────────────────

    def validate_model(self, model_path, framework):
        """
        验证模型文件是否有效

        Args:
            model_path: 模型文件路径
            framework: 框架类型

        Returns:
            dict: {valid, message, model_info}
        """
        if not os.path.exists(model_path):
            return {'valid': False, 'message': '模型文件不存在'}

        try:
            if framework == 'tensorflow':
                return self._validate_tensorflow_model(model_path)
            elif framework == 'pytorch':
                return self._validate_pytorch_model(model_path)
            elif framework == 'sklearn':
                return self._validate_sklearn_model(model_path)
            else:
                return {'valid': True, 'message': '格式验证跳过，仅检查文件存在'}
        except Exception as e:
            return {'valid': False, 'message': f'模型验证失败：{str(e)}'}

    def _validate_tensorflow_model(self, model_path):
        """验证TensorFlow/Keras模型"""
        try:
            import tensorflow as tf
            model = tf.keras.models.load_model(model_path, compile=False)
            return {
                'valid': True,
                'message': '模型有效',
                'model_info': {
                    'input_shape': [inp.shape.as_list() for inp in model.inputs],
                    'output_shape': [out.shape.as_list() for out in model.outputs],
                    'layers': len(model.layers)
                }
            }
        except ImportError:
            # 没有tf，返回基本信息
            return {'valid': True, 'message': 'TensorFlow未安装，跳过详细验证'}
        except Exception as e:
            return {'valid': False, 'message': f'TensorFlow模型无效：{str(e)}'}

    def _validate_pytorch_model(self, model_path):
        """验证PyTorch模型"""
        try:
            import torch
            state_dict = torch.load(model_path, map_location='cpu')
            # 基本验证：检查是否是state_dict或完整模型
            if isinstance(state_dict, dict):
                keys = list(state_dict.keys())[:5]
                return {
                    'valid': True,
                    'message': 'PyTorch模型有效',
                    'model_info': {
                        'type': 'state_dict',
                        'sample_keys': keys,
                        'total_keys': len(state_dict)
                    }
                }
            return {'valid': True, 'message': 'PyTorch模型有效'}
        except ImportError:
            return {'valid': True, 'message': 'PyTorch未安装，跳过详细验证'}
        except Exception as e:
            return {'valid': False, 'message': f'PyTorch模型无效：{str(e)}'}

    def _validate_sklearn_model(self, model_path):
        """验证sklearn模型"""
        try:
            import pickle
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
            return {
                'valid': True,
                'message': 'sklearn模型有效',
                'model_info': {
                    'type': type(model).__name__
                }
            }
        except ImportError:
            return {'valid': True, 'message': 'sklearn未安装，跳过详细验证'}
        except Exception as e:
            return {'valid': False, 'message': f'sklearn模型无效：{str(e)}'}

    # ─────────────────────────────────────────────────────────────────────────
    # 5. 辅助方法
    # ─────────────────────────────────────────────────────────────────────────

    def _get_metadata_path(self, model_id, group_id=None):
        """获取元数据文件路径"""
        if group_id:
            return os.path.join(self.MODEL_ROOT, group_id, f"{model_id}.json")
        return os.path.join(self.MODEL_ROOT, f"{model_id}.json")

    def _load_metadata(self, model_id, group_id=None):
        """加载模型元数据"""
        # 如果没有指定 group_id，先尝试从元数据文件中获取
        meta_path = self._get_metadata_path(model_id, group_id)
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return None

        # 如果在根目录找不到，尝试在小组目录中查找
        if not group_id:
            # 遍历小组目录查找
            if os.path.exists(self.MODEL_ROOT):
                for item in os.listdir(self.MODEL_ROOT):
                    item_path = os.path.join(self.MODEL_ROOT, item)
                    if os.path.isdir(item_path):
                        candidate_path = os.path.join(item_path, f"{model_id}.json")
                        if os.path.exists(candidate_path):
                            try:
                                with open(candidate_path, 'r', encoding='utf-8') as f:
                                    return json.load(f)
                            except:
                                return None
        return None

    def _save_metadata(self, model_id, metadata):
        """保存模型元数据"""
        group_id = metadata.get('group_id')
        meta_path = self._get_metadata_path(model_id, group_id)
        # 确保目录存在
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _update_group_index(self, group_id):
        """更新小组模型索引"""
        index_path = os.path.join(self.MODEL_ROOT, group_id, '_index.json')
        models = self.get_group_models(group_id)
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump({
                'group_id': group_id,
                'model_count': len(models),
                'updated_at': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def _calculate_file_hash(self, file_path):
        """计算文件MD5哈希"""
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"

    def get_framework_icon(self, framework):
        """获取框架图标"""
        icons = {
            'tensorflow': '🧠',
            'pytorch': '🔥',
            'sklearn': '📊',
            'onnx': '🔷'
        }
        return icons.get(framework, '📦')


# 全局单例
_model_import_service = None


def get_model_import_service():
    """获取模型导入服务单例"""
    global _model_import_service
    if _model_import_service is None:
        _model_import_service = ModelImportService()
    return _model_import_service

"""
测试集管理核心服务
功能：
1. 收集全部小组已标注数据（人脸/音频）
2. 创建测试集草稿（可选数据）
3. 发布测试集（锁定数据，生成标签文件）
4. 测试集导出（包含标签文件）
5. 测试集预览
"""
import os
import io
import csv
import json
import shutil
import zipfile
import uuid
from datetime import datetime
from config import Config


class TestsetService:
    """测试集管理服务"""

    # 测试集数据根目录
    TESTSET_ROOT = os.path.join(Config.BASE_DIR, 'data', 'test_sets')

    # 情绪标签映射（7类）
    FACE_EMOTION_MAP = {
        'angry': 0, 'disgust': 1, 'fear': 2,
        'happy': 3, 'sad': 4, 'surprise': 5, 'neutral': 6
    }

    # 音频情绪标签映射（6类）
    AUDIO_EMOTION_MAP = {
        'anger': 0, 'fear': 1, 'happy': 2,
        'neutral': 3, 'sad': 4, 'surprise': 5
    }

    def __init__(self):
        """确保测试集目录结构存在"""
        self._ensure_directories()

    def _ensure_directories(self):
        """确保测试集目录结构存在"""
        dirs = [
            os.path.join(self.TESTSET_ROOT, 'face', '_published'),
            os.path.join(self.TESTSET_ROOT, 'face', '_draft'),
            os.path.join(self.TESTSET_ROOT, 'audio', '_published'),
            os.path.join(self.TESTSET_ROOT, 'audio', '_draft'),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. 获取所有小组已标注数据
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_group_annotated_data(self, data_type='face'):
        """
        获取所有小组的已标注数据

        Args:
            data_type: 'face' 或 'audio'

        Returns:
            dict: {group_id: {'count': int, 'files': [{filename, emotion, emotion_idx}], 'total': int}}
        """
        result = {}

        if data_type == 'face':
            data_root = os.path.join(Config.BASE_DIR, 'data', 'emotion_data')
            ext = '.jpg'
            emotion_map = self.FACE_EMOTION_MAP
        else:
            data_root = os.path.join(Config.BASE_DIR, 'data', 'audio_data')
            ext = '.wav'
            emotion_map = self.AUDIO_EMOTION_MAP

        if not os.path.exists(data_root):
            return result

        for group_id in os.listdir(data_root):
            group_dir = os.path.join(data_root, group_id)
            if not os.path.isdir(group_dir) or group_id.startswith('_'):
                continue

            files = []
            for f in os.listdir(group_dir):
                if not f.endswith(ext):
                    continue

                # 解析情绪标签
                emotion = self._parse_emotion(f, emotion_map)
                if emotion:
                    files.append({
                        'filename': f,
                        'emotion': emotion,
                        'emotion_idx': emotion_map[emotion],
                        'source_path': os.path.join(group_dir, f)
                    })

            if files:
                result[group_id] = {
                    'count': len(files),
                    'files': files,
                    'total': len(files)
                }

        return result

    def _parse_emotion(self, filename, emotion_map):
        """从文件名中解析情绪标签"""
        name = os.path.splitext(filename)[0]
        parts = name.split('_')
        for part in parts:
            if part in emotion_map:
                return part
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # 2. 测试集草稿管理
    # ─────────────────────────────────────────────────────────────────────────

    def create_draft(self, data_type, name, selected_files=None):
        """
        创建测试集草稿

        Args:
            data_type: 'face' 或 'audio'
            name: 测试集名称
            selected_files: 选中的文件列表 [{group_id, filename}, ...]，None表示全选

        Returns:
            dict: {success, draft_id, message}
        """
        draft_id = str(uuid.uuid4())[:8]
        draft_dir = os.path.join(self.TESTSET_ROOT, data_type, '_draft', draft_id)
        os.makedirs(draft_dir, exist_ok=True)

        # 获取所有小组数据
        all_data = self.get_all_group_annotated_data(data_type)

        # 选择文件
        if selected_files is None:
            # 全选
            selected_files = []
            for group_id, data in all_data.items():
                for f in data['files']:
                    selected_files.append({
                        'group_id': group_id,
                        'filename': f['filename']
                    })

        # 复制选中的文件
        copied_count = 0
        for item in selected_files:
            group_id = item['group_id']
            filename = item['filename']

            # 查找源文件
            source_path = None
            for data in all_data.get(group_id, {}).get('files', []):
                if data['filename'] == filename:
                    source_path = data['source_path']
                    break

            if source_path and os.path.exists(source_path):
                # 保持原文件名（不添加额外前缀，因为原文件名已包含 group_id）
                dest_name = filename
                dest_path = os.path.join(draft_dir, dest_name)
                shutil.copy2(source_path, dest_path)
                copied_count += 1

        # 保存草稿元数据
        metadata = {
            'draft_id': draft_id,
            'name': name,
            'data_type': data_type,
            'created_at': datetime.now().isoformat(),
            'total_files': copied_count,
            'selected_groups': list(set(item['group_id'] for item in selected_files))
        }

        meta_path = os.path.join(draft_dir, 'metadata.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        return {
            'success': True,
            'draft_id': draft_id,
            'message': f'草稿创建成功，已选择 {copied_count} 个文件',
            'metadata': metadata
        }

    def get_drafts(self, data_type):
        """获取所有测试集草稿"""
        draft_base = os.path.join(self.TESTSET_ROOT, data_type, '_draft')
        if not os.path.exists(draft_base):
            return []

        drafts = []
        for draft_id in os.listdir(draft_base):
            meta_path = os.path.join(draft_base, draft_id, 'metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    # 统计当前文件数
                    file_count = len([f for f in os.listdir(os.path.join(draft_base, draft_id))
                                      if not f.endswith('.json')])
                    metadata['current_files'] = file_count
                    drafts.append(metadata)

        return sorted(drafts, key=lambda x: x['created_at'], reverse=True)

    def delete_draft(self, data_type, draft_id):
        """删除测试集草稿"""
        draft_dir = os.path.join(self.TESTSET_ROOT, data_type, '_draft', draft_id)
        if os.path.exists(draft_dir):
            shutil.rmtree(draft_dir)
            return {'success': True, 'message': '草稿已删除'}
        return {'success': False, 'message': '草稿不存在'}

    def get_draft_files(self, data_type, draft_id):
        """获取草稿中的文件列表"""
        draft_dir = os.path.join(self.TESTSET_ROOT, data_type, '_draft', draft_id)
        if not os.path.exists(draft_dir):
            return []

        files = []
        for f in os.listdir(draft_dir):
            if f.endswith('.json'):
                continue

            # 解析来源信息
            parts = f.split('_', 1)
            group_id = parts[0] if len(parts) > 0 else 'unknown'
            original_name = parts[1] if len(parts) > 1 else f

            files.append({
                'filename': f,
                'original_name': original_name,
                'group_id': group_id
            })

        return files

    # ─────────────────────────────────────────────────────────────────────────
    # 3. 发布测试集
    # ─────────────────────────────────────────────────────────────────────────

    def publish_draft(self, data_type, draft_id, testset_name=None, publish_to_groups=False):
        """
        发布测试集（将草稿转为正式测试集）

        Args:
            data_type: 'face' 或 'audio'
            draft_id: 草稿ID
            testset_name: 测试集名称（可选）
            publish_to_groups: 是否发布给小组（True=小组可见数据但不可见标签，False=仅管理员可见）

        Returns:
            dict: {success, testset_id, message}
        """
        draft_dir = os.path.join(self.TESTSET_ROOT, data_type, '_draft', draft_id)
        if not os.path.exists(draft_dir):
            return {'success': False, 'message': '草稿不存在'}

        # 创建正式测试集目录
        testset_id = f"{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        published_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)

        # 根据发布选项决定目录结构
        if publish_to_groups:
            # 发布给小组：数据可见，标签不可见
            # 数据放在小组可见目录
            visible_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id, 'data')
            os.makedirs(visible_dir, exist_ok=True)
        else:
            os.makedirs(published_dir, exist_ok=True)

        # 复制文件（修复：保持原文件名，不添加额外前缀）
        files_info = []
        emotion_map = self.FACE_EMOTION_MAP if data_type == 'face' else self.AUDIO_EMOTION_MAP

        for f in os.listdir(draft_dir):
            if f.endswith('.json'):
                continue

            source_path = os.path.join(draft_dir, f)

            # 移除 draft 中错误添加的前缀，恢复原始文件名
            # draft 中文件名格式: {group_id}_{original_filename}
            # 原始文件名格式: {group_id}_{rest}
            # 需要还原为原始格式
            parts = f.split('_', 1)
            if len(parts) >= 2:
                # 检查是否有多余的 group_id_ 前缀
                original_name = parts[1] if parts[0] == parts[1].split('_')[0] else f
            else:
                original_name = f

            dest_name = original_name

            if publish_to_groups:
                dest_path = os.path.join(visible_dir, dest_name)
            else:
                dest_path = os.path.join(published_dir, dest_name)

            shutil.copy2(source_path, dest_path)

            # 解析情绪标签（使用原始文件名）
            emotion = self._parse_emotion(dest_name, emotion_map)
            if emotion:
                # 提取 group_id
                name_parts = dest_name.split('_', 1)
                group_id = name_parts[0] if len(name_parts) > 0 else 'unknown'

                files_info.append({
                    'filename': dest_name,
                    'original_filename': dest_name,
                    'group_id': group_id,
                    'emotion': emotion,
                    'emotion_idx': emotion_map[emotion]
                })

        # 生成测试集标签文件
        if files_info:
            if data_type == 'face':
                labels_filename = 'test_labels.csv'
                self._generate_face_labels_csv(files_info, published_dir, labels_filename)
            else:
                labels_filename = 'test_labels.csv'
                self._generate_audio_labels_csv(files_info, published_dir, labels_filename)

        # 如果发布给小组，创建小组可见版本（无标签文件）
        if publish_to_groups:
            # 创建小组可见标记文件（不是标签文件，是告诉小组有哪些数据可用）
            manifest = {
                'testset_id': testset_id,
                'name': testset_name or testset_id,
                'data_type': data_type,
                'total_samples': len(files_info),
                'published_at': datetime.now().isoformat(),
                'note': '此测试集已发布给您使用，请使用您的模型进行预测评估'
            }
            manifest_path = os.path.join(published_dir, '_manifest.json')
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 保存发布元数据
        publish_metadata = {
            'testset_id': testset_id,
            'name': testset_name or testset_id,
            'data_type': data_type,
            'draft_id': draft_id,
            'total_samples': len(files_info),
            'published_at': datetime.now().isoformat(),
            'published_by': 'admin',
            'publish_to_groups': publish_to_groups,
            'groups_published': ['all'] if publish_to_groups else []
        }

        meta_path = os.path.join(published_dir, 'metadata.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(publish_metadata, f, ensure_ascii=False, indent=2)

        # 删除草稿
        shutil.rmtree(draft_dir)

        return {
            'success': True,
            'testset_id': testset_id,
            'total_samples': len(files_info),
            'message': f'测试集发布成功，共 {len(files_info)} 个样本' + ('（已发布给所有小组）' if publish_to_groups else '（仅管理员可见）')
        }

    def _generate_face_labels_csv(self, files_info, dest_dir, filename):
        """生成人脸测试集标签CSV"""
        csv_path = os.path.join(dest_dir, filename)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['filename', 'label', 'label_idx'])
            for info in files_info:
                writer.writerow([info['filename'], info['emotion'], info['emotion_idx']])

    def _generate_audio_labels_csv(self, files_info, dest_dir, filename):
        """生成音频测试集标签CSV"""
        csv_path = os.path.join(dest_dir, filename)
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['filename', 'emotion', 'emotion_idx'])
            for info in files_info:
                writer.writerow([info['filename'], info['emotion'], info['emotion_idx']])

    # ─────────────────────────────────────────────────────────────────────────
    # 4. 外部导入测试集
    # ─────────────────────────────────────────────────────────────────────────

    def import_external_data(self, data_type, uploaded_files, testset_name, publish_to_groups=False):
        """
        导入外部数据作为测试集

        Args:
            data_type: 'face' 或 'audio'
            uploaded_files: 上传的文件列表 [(filename, file_content), ...]
            testset_name: 测试集名称
            publish_to_groups: 是否发布给小组

        Returns:
            dict: {success, testset_id, message}
        """
        testset_id = f"{data_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        published_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)

        os.makedirs(published_dir, exist_ok=True)

        # 保存上传的文件
        emotion_map = self.FACE_EMOTION_MAP if data_type == 'face' else self.AUDIO_EMOTION_MAP
        ext = '.jpg' if data_type == 'face' else '.wav'
        files_info = []

        for filename, content in uploaded_files:
            dest_path = os.path.join(published_dir, filename)

            # 保存文件
            if hasattr(content, 'read'):
                with open(dest_path, 'wb') as f:
                    f.write(content.read())
            else:
                with open(dest_path, 'wb') as f:
                    f.write(content)

            # 解析情绪标签
            emotion = self._parse_emotion(filename, emotion_map)
            if emotion:
                files_info.append({
                    'filename': filename,
                    'group_id': 'external',
                    'emotion': emotion,
                    'emotion_idx': emotion_map[emotion]
                })

        # 生成测试集标签文件（仅管理员可见）
        if files_info:
            if data_type == 'face':
                self._generate_face_labels_csv(files_info, published_dir, 'test_labels.csv')
            else:
                self._generate_audio_labels_csv(files_info, published_dir, 'test_labels.csv')

        # 如果发布给小组，创建无标签版本
        if publish_to_groups:
            visible_dir = os.path.join(published_dir, 'data')
            os.makedirs(visible_dir, exist_ok=True)

            # 复制数据文件（不含标签）
            for f in os.listdir(published_dir):
                if not f.endswith('.csv') and not f.startswith('_'):
                    shutil.copy2(
                        os.path.join(published_dir, f),
                        os.path.join(visible_dir, f)
                    )

        # 保存元数据
        publish_metadata = {
            'testset_id': testset_id,
            'name': testset_name,
            'data_type': data_type,
            'source': 'external',
            'total_samples': len(files_info),
            'published_at': datetime.now().isoformat(),
            'published_by': 'admin',
            'publish_to_groups': publish_to_groups
        }

        meta_path = os.path.join(published_dir, 'metadata.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(publish_metadata, f, ensure_ascii=False, indent=2)

        return {
            'success': True,
            'testset_id': testset_id,
            'total_samples': len(files_info),
            'message': f'外部数据导入成功，共 {len(files_info)} 个样本'
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 5. 测试集列表与预览
    # ─────────────────────────────────────────────────────────────────────────

    def get_published_testsets(self, data_type):
        """获取所有已发布的测试集"""
        published_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published')
        if not os.path.exists(published_dir):
            return []

        testsets = []
        for testset_id in os.listdir(published_dir):
            meta_path = os.path.join(published_dir, testset_id, 'metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                # 检查标签文件是否存在
                labels_exist = os.path.exists(
                    os.path.join(published_dir, testset_id, 'test_labels.csv')
                )

                # 统计文件数
                file_count = len([
                    f for f in os.listdir(os.path.join(published_dir, testset_id))
                    if not f.endswith('.json') and not f.endswith('.csv')
                ])

                metadata['labels_exist'] = labels_exist
                metadata['data_files'] = file_count
                testsets.append(metadata)

        return sorted(testsets, key=lambda x: x['published_at'], reverse=True)

    def get_testset_files(self, data_type, testset_id, include_labels=False):
        """
        获取测试集中的文件列表

        Args:
            data_type: 'face' 或 'audio'
            testset_id: 测试集ID
            include_labels: 是否包含标签信息（仅管理员可请求）

        Returns:
            list: 文件信息列表
        """
        testset_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)
        if not os.path.exists(testset_dir):
            return []

        files = []
        emotion_map = self.FACE_EMOTION_MAP if data_type == 'face' else self.AUDIO_EMOTION_MAP

        for f in os.listdir(testset_dir):
            if f.endswith('.json') or f.endswith('.csv') and not include_labels:
                continue

            emotion = self._parse_emotion(f, emotion_map)

            info = {
                'filename': f,
                'emotion': emotion,
                'emotion_idx': emotion_map.get(emotion) if emotion else None
            }

            # 如果需要标签且是标签文件
            if include_labels and f.endswith('.csv'):
                info['is_label_file'] = True

            files.append(info)

        return files

    def preview_testset_sample(self, data_type, testset_id, sample_count=5):
        """预览测试集样本"""
        testset_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)
        if not os.path.exists(testset_dir):
            return []

        samples = []
        emotion_map = self.FACE_EMOTION_MAP if data_type == 'face' else self.AUDIO_EMOTION_MAP
        ext = '.jpg' if data_type == 'face' else '.wav'

        count = 0
        for f in os.listdir(testset_dir):
            if count >= sample_count:
                break
            if f.endswith(ext):
                emotion = self._parse_emotion(f, emotion_map)
                samples.append({
                    'filename': f,
                    'emotion': emotion,
                    'emotion_idx': emotion_map.get(emotion) if emotion else None
                })
                count += 1

        return samples

    def delete_testset(self, data_type, testset_id):
        """删除测试集"""
        testset_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)
        if os.path.exists(testset_dir):
            shutil.rmtree(testset_dir)
            return {'success': True, 'message': '测试集已删除'}
        return {'success': False, 'message': '测试集不存在'}

    # ─────────────────────────────────────────────────────────────────────────
    # 6. 测试集导出
    # ─────────────────────────────────────────────────────────────────────────

    def export_testset(self, data_type, testset_id, include_labels=True):
        """
        导出测试集（包括标签文件）

        Args:
            data_type: 'face' 或 'audio'
            testset_id: 测试集ID
            include_labels: 是否包含标签文件（True=管理员导出，False=小组导出无标签）

        Returns:
            BytesIO: zip文件内容
        """
        testset_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published', testset_id)
        if not os.path.exists(testset_dir):
            return None

        memory_file = io.BytesIO()

        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(testset_dir):
                if not include_labels and (f.endswith('.csv') or f.endswith('.json')):
                    continue

                file_path = os.path.join(testset_dir, f)
                if os.path.isfile(file_path):
                    zf.write(file_path, f)

        memory_file.seek(0)
        return memory_file

    def export_draft(self, data_type, draft_id):
        """
        导出草稿（包含标签文件，供管理员预览）

        Args:
            data_type: 'face' 或 'audio'
            draft_id: 草稿ID

        Returns:
            BytesIO: zip文件内容
        """
        draft_dir = os.path.join(self.TESTSET_ROOT, data_type, '_draft', draft_id)
        if not os.path.exists(draft_dir):
            return None

        memory_file = io.BytesIO()

        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            emotion_map = self.FACE_EMOTION_MAP if data_type == 'face' else self.AUDIO_EMOTION_MAP
            files_info = []

            for f in os.listdir(draft_dir):
                if f.endswith('.json'):
                    continue

                file_path = os.path.join(draft_dir, f)
                if os.path.isfile(file_path):
                    zf.write(file_path, f)

                    # 收集标签信息
                    emotion = self._parse_emotion(f, emotion_map)
                    if emotion:
                        files_info.append({
                            'filename': f,
                            'emotion': emotion,
                            'emotion_idx': emotion_map[emotion]
                        })

            # 生成标签CSV
            if files_info:
                if data_type == 'face':
                    self._generate_face_labels_csv(files_info, None, None, zf)
                else:
                    self._generate_audio_labels_csv(files_info, None, None, zf)

        memory_file.seek(0)
        return memory_file

    def _generate_face_labels_csv(self, files_info, dest_dir, filename, zf=None):
        """生成人脸标签CSV（支持写入zip）"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['filename', 'label', 'label_idx'])
        for info in files_info:
            writer.writerow([info['filename'], info['emotion'], info['emotion_idx']])

        if zf:
            zf.writestr('test_labels.csv', output.getvalue())
        else:
            csv_path = os.path.join(dest_dir, filename)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                f.write(output.getvalue())

    def _generate_audio_labels_csv(self, files_info, dest_dir, filename, zf=None):
        """生成音频标签CSV（支持写入zip）"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['filename', 'emotion', 'emotion_idx'])
        for info in files_info:
            writer.writerow([info['filename'], info['emotion'], info['emotion_idx']])

        if zf:
            zf.writestr('test_labels.csv', output.getvalue())
        else:
            csv_path = os.path.join(dest_dir, filename)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                f.write(output.getvalue())

    # ─────────────────────────────────────────────────────────────────────────
    # 7. 小组获取测试集
    # ─────────────────────────────────────────────────────────────────────────

    def get_group_available_testsets(self, data_type):
        """
        获取小组可用的测试集（已发布但不含标签）

        Args:
            data_type: 'face' 或 'audio'

        Returns:
            list: 可用的测试集列表（无标签信息）
        """
        published_dir = os.path.join(self.TESTSET_ROOT, data_type, '_published')
        if not os.path.exists(published_dir):
            return []

        testsets = []
        for testset_id in os.listdir(published_dir):
            meta_path = os.path.join(published_dir, testset_id, 'metadata.json')
            if not os.path.exists(meta_path):
                continue

            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # 只返回发布给小组的测试集
            if not metadata.get('publish_to_groups', False):
                continue

            # 只返回不含标签的概要信息
            testsets.append({
                'testset_id': testset_id,
                'name': metadata.get('name', testset_id),
                'data_type': data_type,
                'total_samples': metadata.get('total_samples', 0),
                'published_at': metadata.get('published_at', '')
            })

        return sorted(testsets, key=lambda x: x['published_at'], reverse=True)

    def get_group_testset_sample(self, data_type, testset_id, sample_count=5):
        """
        获取测试集样本（不含标签，供小组使用）

        Args:
            data_type: 'face' 或 'audio'
            testset_id: 测试集ID
            sample_count: 样本数量

        Returns:
            list: 样本文件列表（无标签）
        """
        # 优先使用不含标签的data目录
        data_dir = os.path.join(
            self.TESTSET_ROOT, data_type, '_published', testset_id, 'data'
        )

        testset_dir = os.path.join(
            self.TESTSET_ROOT, data_type, '_published', testset_id
        )

        # 优先使用data目录（无标签）
        if os.path.exists(data_dir):
            source_dir = data_dir
        else:
            source_dir = testset_dir

        if not os.path.exists(source_dir):
            return []

        samples = []
        ext = '.jpg' if data_type == 'face' else '.wav'

        count = 0
        for f in os.listdir(source_dir):
            if count >= sample_count:
                break
            if f.endswith(ext):
                samples.append({
                    'filename': f,
                    'note': '请使用您的模型预测此文件的情绪标签'
                })
                count += 1

        return samples

    # ─────────────────────────────────────────────────────────────────────────
    # 8. 统计信息
    # ─────────────────────────────────────────────────────────────────────────

    def get_overview(self):
        """获取测试集总览统计"""
        result = {
            'face': self._get_type_overview('face'),
            'audio': self._get_type_overview('audio')
        }
        return result

    def _get_type_overview(self, data_type):
        """获取单个类型的统计"""
        # 统计已发布的测试集
        published = self.get_published_testsets(data_type)

        # 统计草稿
        drafts = self.get_drafts(data_type)

        # 统计源数据
        source_data = self.get_all_group_annotated_data(data_type)
        total_source = sum(d['count'] for d in source_data.values())

        return {
            'published_count': len(published),
            'published_samples': sum(t.get('total_samples', 0) for t in published),
            'draft_count': len(drafts),
            'draft_samples': sum(d.get('total_files', 0) for d in drafts),
            'source_groups': len(source_data),
            'source_total': total_source
        }


# 全局单例
_testset_service = None


def get_testset_service():
    """获取测试集服务单例"""
    global _testset_service
    if _testset_service is None:
        _testset_service = TestsetService()
    return _testset_service

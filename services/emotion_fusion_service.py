"""
情感计算服务 - 综合表情和声音的情绪分析

支持多种融合策略：
1. weighted_average: 加权平均（默认）
2. max_confidence: 最大置信度
3. emotion_voting: 情绪投票
4. adaptive: 自适应融合

支持可配置权重比例（表情权重 + 声音权重 = 100%）
"""

class EmotionFusion:
    """情感计算分析器"""

    # 支持的融合策略
    STRATEGIES = {
        'weighted_average': '加权平均',
        'max_confidence': '最大置信度',
        'emotion_voting': '情绪投票',
        'adaptive': '自适应融合'
    }

    # 表情模型的情绪标签（7个）
    FACE_EMOTION_LABELS = ['happy', 'sad', 'angry', 'fear', 'surprise', 'neutral', 'disgust']

    # 音频模型的情绪标签（6个）
    AUDIO_EMOTION_LABELS = ['happy', 'sad', 'angry', 'fear', 'surprise', 'neutral']

    # 所有情绪标签
    EMOTION_LABELS = ['happy', 'sad', 'angry', 'fear', 'surprise', 'neutral', 'disgust']

    # 情绪中文映射
    EMOTION_CN = {
        'happy': '开心', 'sad': '难过', 'angry': '生气',
        'fear': '害怕', 'surprise': '惊讶', 'neutral': '平静', 'disgust': '厌恶'
    }

    def __init__(self, face_weight=0.6, strategy='weighted_average'):
        """
        初始化融合器

        Args:
            face_weight: 表情权重 (0.0 ~ 1.0)，声音权重自动为 1 - face_weight
            strategy: 融合策略，可选 'weighted_average', 'max_confidence', 'emotion_voting', 'adaptive'
        """
        self.set_weight(face_weight)
        self.set_strategy(strategy)

    def set_weight(self, face_weight):
        """设置融合权重"""
        face_weight = max(0.0, min(1.0, float(face_weight)))
        self.face_weight = face_weight
        self.audio_weight = 1.0 - face_weight

    def set_strategy(self, strategy):
        """设置融合策略"""
        if strategy not in self.STRATEGIES:
            strategy = 'weighted_average'
        self.strategy = strategy

    def get_config(self):
        """获取当前配置"""
        return {
            'face_weight': self.face_weight,
            'audio_weight': self.audio_weight,
            'strategy': self.strategy,
            'strategy_name': self.STRATEGIES.get(self.strategy, '加权平均')
        }

    def fuse(self, face_result, audio_result):
        """
        融合表情和声音的情绪分析结果

        Args:
            face_result: {
                'emotion': 'happy',
                'scores': {'happy': 0.8, 'sad': 0.1, ...}
            }
            audio_result: {
                'emotion': 'happy',
                'scores': {'happy': 0.6, 'sad': 0.2, ...}
            }

        Returns:
            融合后的情绪判断结果
        """
        if not face_result and not audio_result:
            return {
                'success': False,
                'error': '没有有效的情绪输入'
            }

        # 如果只有一个输入，直接返回
        if not face_result:
            return self._format_result(audio_result, 'audio')
        if not audio_result:
            return self._format_result(face_result, 'face')

        # 根据策略进行融合
        if self.strategy == 'max_confidence':
            return self._fuse_max_confidence(face_result, audio_result)
        elif self.strategy == 'emotion_voting':
            return self._fuse_emotion_voting(face_result, audio_result)
        elif self.strategy == 'adaptive':
            return self._fuse_adaptive(face_result, audio_result)
        else:  # weighted_average (默认)
            return self._fuse_weighted_average(face_result, audio_result)

    def _fuse_weighted_average(self, face_result, audio_result):
        """加权平均融合策略"""
        fused_scores = {}

        # 初始化所有情绪分数
        for emotion in self.EMOTION_LABELS:
            face_score = face_result.get('scores', {}).get(emotion, 0)

            # 音频模型没有 disgust，将其映射为 0
            if emotion == 'disgust':
                audio_score = 0
            else:
                audio_score = audio_result.get('scores', {}).get(emotion, 0)

            # 加权融合
            fused_scores[emotion] = (
                face_score * self.face_weight +
                audio_score * self.audio_weight
            )

        return self._build_result(fused_scores, face_result, audio_result, 'weighted_average')

    def _fuse_max_confidence(self, face_result, audio_result):
        """最大置信度融合策略：直接选择置信度更高的模态"""
        face_confidence = face_result.get('scores', {}).get(face_result.get('emotion'), 0)
        audio_confidence = audio_result.get('scores', {}).get(audio_result.get('emotion'), 0)

        if face_confidence >= audio_confidence:
            dominant_emotion = face_result.get('emotion')
            confidence = face_confidence
            source = 'face'
        else:
            dominant_emotion = audio_result.get('emotion')
            confidence = audio_confidence
            source = 'audio'

        # 构建融合分数（直接使用选中模态的分数）
        fused_scores = {}
        for emotion in self.EMOTION_LABELS:
            if source == 'face':
                fused_scores[emotion] = face_result.get('scores', {}).get(emotion, 0)
            else:
                if emotion == 'disgust':
                    fused_scores[emotion] = 0
                else:
                    fused_scores[emotion] = audio_result.get('scores', {}).get(emotion, 0)

        return self._build_result(fused_scores, face_result, audio_result, 'max_confidence',
                                   dominant_emotion=dominant_emotion, confidence=confidence)

    def _fuse_emotion_voting(self, face_result, audio_result):
        """情绪投票融合策略：各模态的置信度乘以权重后投票"""
        vote_scores = {}

        # 表情投票（乘以表情权重）
        for emotion, score in face_result.get('scores', {}).items():
            if emotion in self.EMOTION_LABELS:
                vote_scores[emotion] = vote_scores.get(emotion, 0) + score * self.face_weight

        # 声音投票（音频没有 disgust，乘以声音权重）
        for emotion, score in audio_result.get('scores', {}).items():
            if emotion in self.EMOTION_LABELS and emotion != 'disgust':
                vote_scores[emotion] = vote_scores.get(emotion, 0) + score * self.audio_weight

        # 确保所有情绪都有分数（disgust 没有声音投票，默认为 0）
        for emotion in self.EMOTION_LABELS:
            if emotion not in vote_scores:
                vote_scores[emotion] = 0

        return self._build_result(vote_scores, face_result, audio_result, 'emotion_voting')

    def _fuse_adaptive(self, face_result, audio_result):
        """自适应融合策略：根据各模态的置信度动态调整权重"""
        face_emotion = face_result.get('emotion')
        audio_emotion = audio_result.get('emotion')

        face_confidence = face_result.get('scores', {}).get(face_emotion, 0)
        audio_confidence = audio_result.get('scores', {}).get(audio_emotion, 0)

        total_confidence = face_confidence + audio_confidence

        # 如果总置信度太低，使用默认权重
        if total_confidence < 0.1:
            adaptive_face_weight = self.face_weight
            adaptive_audio_weight = self.audio_weight
        else:
            # 动态权重：置信度高的模态获得更高权重
            adaptive_face_weight = face_confidence / total_confidence
            adaptive_audio_weight = audio_confidence / total_confidence

        fused_scores = {}
        for emotion in self.EMOTION_LABELS:
            face_score = face_result.get('scores', {}).get(emotion, 0)

            if emotion == 'disgust':
                audio_score = 0
            else:
                audio_score = audio_result.get('scores', {}).get(emotion, 0)

            fused_scores[emotion] = (
                face_score * adaptive_face_weight +
                audio_score * adaptive_audio_weight
            )

        result = self._build_result(fused_scores, face_result, audio_result, 'adaptive')
        result['adaptive_weights'] = {
            'face': round(adaptive_face_weight, 3),
            'audio': round(adaptive_audio_weight, 3)
        }
        return result

    def _build_result(self, fused_scores, face_result, audio_result, method,
                      dominant_emotion=None, confidence=None):
        """构建统一格式的融合结果"""
        # 归一化
        total = sum(fused_scores.values())
        if total > 0:
            fused_scores = {k: v/total for k, v in fused_scores.items()}

        # 找出最高分数的情绪
        if dominant_emotion is None:
            dominant_emotion = max(fused_scores, key=fused_scores.get)
        if confidence is None:
            confidence = fused_scores[dominant_emotion]

        # 获取中文名称
        face_emotion_cn = face_result.get('emotion_cn') or self.EMOTION_CN.get(
            face_result.get('emotion', ''), face_result.get('emotion', ''))
        audio_emotion_cn = audio_result.get('emotion_cn') or self.EMOTION_CN.get(
            audio_result.get('emotion', ''), audio_result.get('emotion', ''))

        # 获取 dominant_emotion 的中文名称
        dominant_emotion_cn = self.EMOTION_CN.get(dominant_emotion, dominant_emotion)

        result = {
            'success': True,
            'fused_emotion': dominant_emotion,
            'fused_emotion_cn': dominant_emotion_cn,
            'confidence': confidence,
            'fused_scores': fused_scores,
            'face_emotion': face_result.get('emotion'),
            'face_emotion_cn': face_emotion_cn,
            'audio_emotion': audio_result.get('emotion'),
            'audio_emotion_cn': audio_emotion_cn,
            'fusion_method': method,
            'fusion_method_name': self.STRATEGIES.get(method, '未知'),
            'weights': {
                'face': self.face_weight,
                'audio': self.audio_weight
            }
        }

        # max_confidence 策略：标记选中的模态
        if method == 'max_confidence':
            face_confidence = face_result.get('scores', {}).get(face_result.get('emotion'), 0)
            audio_confidence = audio_result.get('scores', {}).get(audio_result.get('emotion'), 0)
            result['selected_modality'] = 'face' if face_confidence >= audio_confidence else 'audio'

        return result

    def _format_result(self, result, source):
        """格式化单源结果"""
        emotion = result.get('emotion')
        emotion_cn = result.get('emotion_cn') or self.EMOTION_CN.get(emotion, emotion)

        return {
            'success': True,
            'fused_emotion': emotion,
            'fused_emotion_cn': emotion_cn,
            'confidence': result.get('scores', {}).get(emotion, 0),
            'fused_scores': result.get('scores', {}),
            'face_emotion': emotion if source == 'face' else None,
            'face_emotion_cn': emotion_cn if source == 'face' else None,
            'audio_emotion': emotion if source == 'audio' else None,
            'audio_emotion_cn': emotion_cn if source == 'audio' else None,
            'fusion_method': f'single_source_{source}',
            'fusion_method_name': f'单源_{source}',
            'weights': {
                'face': 1.0 if source == 'face' else 0.0,
                'audio': 1.0 if source == 'audio' else 0.0
            }
        }

    @classmethod
    def get_available_strategies(cls):
        """获取所有可用的融合策略"""
        return [
            {'id': k, 'name': v}
            for k, v in cls.STRATEGIES.items()
        ]


# 全局融合器实例（默认配置）
_fusion = None

def get_fusion():
    """获取全局融合器实例"""
    global _fusion
    if _fusion is None:
        _fusion = EmotionFusion()
    return _fusion


def get_fusion_with_config(face_weight=0.6, strategy='weighted_average'):
    """
    获取配置了特定参数的融合器

    Args:
        face_weight: 表情权重 (0.0 ~ 1.0)
        strategy: 融合策略

    Returns:
        配置好的 EmotionFusion 实例
    """
    fusion = EmotionFusion(face_weight=face_weight, strategy=strategy)
    return fusion


def analyze_emotion(face_result, audio_result, face_weight=0.6, strategy='weighted_average'):
    """
    情感分析主函数

    Args:
        face_result: 表情识别结果
        audio_result: 声音识别结果
        face_weight: 表情权重 (0.0 ~ 1.0)
        strategy: 融合策略

    Returns:
        融合后的情绪结果
    """
    fusion = get_fusion_with_config(face_weight=face_weight, strategy=strategy)
    return fusion.fuse(face_result, audio_result)

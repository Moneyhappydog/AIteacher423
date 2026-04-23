"""
音频预处理服务
提供多种音频预处理方法，用于数据增强和特征提取
"""
import os
import io
import base64
import random
import numpy as np
import librosa
import soundfile as sf
from typing import Optional, Tuple, List, Dict

# 情绪标签（6类，与HuBERT一致）
EMOTION_LABELS = ['anger', 'fear', 'happy', 'neutral', 'sad', 'surprise']


class AudioPreprocessor:
    """音频预处理器"""

    def __init__(self):
        """初始化预处理器"""
        self.sample_rate = 16000  # 标准采样率

    def load_audio_from_base64(self, audio_data: str, sr: int = None) -> Tuple[np.ndarray, int]:
        """
        从base64加载音频

        Args:
            audio_data: base64编码的音频数据
            sr: 目标采样率

        Returns:
            (音频波形, 采样率)
        """
        audio_bytes = base64.b64decode(audio_data.split(',')[-1] if ',' in audio_data else audio_data)
        audio, sample_rate = librosa.load(io.BytesIO(audio_bytes), sr=sr or self.sample_rate)
        return audio, sample_rate

    def load_audio_from_file(self, filepath: str, sr: int = None) -> Tuple[np.ndarray, int]:
        """
        从文件加载音频

        Args:
            filepath: 音频文件路径
            sr: 目标采样率

        Returns:
            (音频波形, 采样率)
        """
        audio, sample_rate = librosa.load(filepath, sr=sr or self.sample_rate)
        return audio, sample_rate

    def audio_to_base64(self, audio: np.ndarray, sr: int = None, format: str = 'WAV') -> str:
        """
        音频转base64

        Args:
            audio: 音频波形
            sr: 采样率
            format: 音频格式

        Returns:
            base64编码的音频数据
        """
        sr = sr or self.sample_rate
        buffer = io.BytesIO()
        sf.write(buffer, audio, sr, format=format)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')

    def audio_to_base64_dataurl(self, audio: np.ndarray, sr: int = None, format: str = 'WAV') -> str:
        """音频转base64 DataURL"""
        mime_type = 'audio/wav' if format.upper() == 'WAV' else f'audio/{format.lower()}'
        audio_b64 = self.audio_to_base64(audio, sr, format)
        return f"data:{mime_type};base64,{audio_b64}"

    # ── 基础预处理 ────────────────────────────────────────────────────────────

    def extract_mel_spectrogram(
        self,
        audio: np.ndarray,
        sr: int = None,
        n_mels: int = 128,
        n_fft: int = 2048,
        hop_length: int = 512
    ) -> Dict:
        """
        提取梅尔频谱图

        Args:
            audio: 音频波形
            sr: 采样率
            n_mels: 梅尔滤波器数量
            n_fft: FFT窗口大小
            hop_length: 帧移

        Returns:
            {
                'mel_spec': 梅尔频谱图,
                'sr': 采样率,
                'n_mels': 梅尔滤波器数量,
                'shape': 频谱图形状
            }
        """
        sr = sr or self.sample_rate
        mel_spec = librosa.feature.melspectrogram(
            y=audio,
            sr=sr,
            n_mels=n_mels,
            n_fft=n_fft,
            hop_length=hop_length
        )
        # 转换为分贝单位
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

        return {
            'mel_spec': mel_spec_db,
            'sr': sr,
            'n_mels': n_mels,
            'shape': mel_spec_db.shape,
        }

    def normalize(self, audio: np.ndarray, method: str = 'peak') -> np.ndarray:
        """
        音频归一化

        Args:
            audio: 音频波形
            method: 'peak' (峰值归一化到-1~1), 'rms' (RMS归一化), 'zscore' (均值0方差1)

        Returns:
            归一化后的音频
        """
        if method == 'peak':
            peak = np.max(np.abs(audio))
            if peak > 0:
                return audio / peak
            return audio
        elif method == 'rms':
            rms = np.sqrt(np.mean(audio ** 2))
            if rms > 0:
                return audio / rms * 0.1  # 归一化到RMS=0.1
            return audio
        elif method == 'zscore':
            mean = np.mean(audio)
            std = np.std(audio)
            if std > 0:
                return (audio - mean) / std
            return audio - mean
        return audio

    def trim_silence(self, audio: np.ndarray, sr: int = None, top_db: int = 30) -> Tuple[np.ndarray, int, int]:
        """
        静音切除

        Args:
            audio: 音频波形
            sr: 采样率
            top_db: 静音阈值（分贝）

        Returns:
            (切除静音后的音频, 原始起始位置, 结束位置)
        """
        sr = sr or self.sample_rate
        trimmed, index = librosa.effects.trim(audio, top_db=top_db)
        return trimmed, index[0], index[1]

    def resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        重采样

        Args:
            audio: 音频波形
            orig_sr: 原始采样率
            target_sr: 目标采样率

        Returns:
            重采样后的音频
        """
        return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)

    # ── 数据增强 - 时域 ───────────────────────────────────────────────────────

    def add_noise(self, audio: np.ndarray, noise_level: float = 0.005) -> np.ndarray:
        """
        添加随机噪声

        Args:
            audio: 音频波形
            noise_level: 噪声水平（相对于信号标准差）

        Returns:
            添加噪声后的音频
        """
        noise = np.random.normal(0, noise_level, audio.shape)
        return audio + noise * np.std(audio)

    def change_speed(self, audio: np.ndarray, speed_factor: float = 1.1) -> np.ndarray:
        """
        改变播放速度（保持音高）

        Args:
            audio: 音频波形
            speed_factor: 速度因子 (>1加速, <1减速)

        Returns:
            变速后的音频
        """
        return librosa.effects.time_stretch(audio, rate=speed_factor)

    def time_mask(self, audio: np.ndarray, sr: int = None, max_mask_len: float = 0.1) -> np.ndarray:
        """
        时间掩码

        Args:
            audio: 音频波形
            sr: 采样率
            max_mask_len: 最大掩码长度（秒）

        Returns:
            掩码后的音频
        """
        sr = sr or self.sample_rate
        mask_len_samples = int(max_mask_len * sr)

        # 随机掩码位置
        mask_start = random.randint(0, max(0, len(audio) - mask_len_samples))
        masked = audio.copy()
        masked[mask_start:mask_start + mask_len_samples] = 0

        return masked

    # ── 数据增强 - 频域 ───────────────────────────────────────────────────────

    def frequency_mask(self, audio: np.ndarray, sr: int = None, n_mels: int = 128, n_mask: int = 2) -> np.ndarray:
        """
        频率掩码（应用于梅尔频谱图）

        Args:
            audio: 音频波形
            sr: 采样率
            n_mels: 梅尔滤波器数量
            n_mask: 掩码数量

        Returns:
            掩码后的梅尔频谱图（需要重建音频时会损失质量）
        """
        # 先提取梅尔频谱图
        mel_spec = librosa.feature.melspectrogram(y=audio, sr=sr or self.sample_rate, n_mels=n_mels)
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

        # 随机频率掩码
        for _ in range(n_mask):
            f = random.randint(0, n_mels // 4)
            f0 = random.randint(0, mel_spec_db.shape[0] - f)
            mel_spec_db[f0:f0 + f, :] = mel_spec_db.mean()

        return mel_spec_db

    # ── 组合预处理 ────────────────────────────────────────────────────────────

    def preprocess_single(
        self,
        audio: np.ndarray,
        sr: int,
        operations: List[str],
        params: Dict = None
    ) -> Tuple[np.ndarray, int, str]:
        """
        对单段音频应用预处理操作

        Args:
            audio: 音频波形
            sr: 采样率
            operations: 操作列表
            params: 操作参数字典

        Returns:
            (处理后音频, 采样率, 操作后缀)
        """
        params = params or {}
        suffix_parts = []
        output_sr = sr

        for op in operations:
            if op == 'mel':
                # 梅尔频谱图 - 返回频谱图数据
                mel_result = self.extract_mel_spectrogram(audio, sr)
                suffix_parts.append('mel')
                # 注意：梅尔频谱图无法转回原始音频，这里返回原始音频用于导出
                # 实际应用时使用 mel_spec

            elif op == 'normalize':
                method = params.get('norm_method', 'peak')
                audio = self.normalize(audio, method)
                suffix_parts.append(f'norm_{method}')

            elif op == 'trim':
                audio, start, end = self.trim_silence(audio, sr)
                suffix_parts.append('trim')

            elif op == 'noise':
                level = params.get('noise_level', 0.005)
                audio = self.add_noise(audio, level)
                suffix_parts.append(f'noise{int(level*1000)}')

            elif op == 'speed':
                factor = params.get('speed_factor', 1.1)
                audio = self.change_speed(audio, factor)
                suffix_parts.append(f'speed{int(factor*10)}')

            elif op == 'time_mask':
                mask_len = params.get('mask_len', 0.1)
                audio = self.time_mask(audio, sr, mask_len)
                suffix_parts.append('tmask')

            elif op == 'freq_mask':
                n_mels = params.get('n_mels', 128)
                audio = self.frequency_mask(audio, sr, n_mels)
                suffix_parts.append('fmask')

            elif op == 'resample':
                target_sr = params.get('target_sr', 16000)
                audio = self.resample(audio, sr, target_sr)
                output_sr = target_sr
                suffix_parts.append(f'sr{target_sr}')

        suffix = '_'.join(suffix_parts) if suffix_parts else 'original'
        return audio, output_sr, suffix

    def get_waveform_data(self, audio: np.ndarray, sr: int, num_points: int = 200) -> List[float]:
        """
        获取波形数据用于可视化

        Args:
            audio: 音频波形
            sr: 采样率
            num_points: 数据点数量

        Returns:
            归一化的波形数据列表
        """
        # 降采样以减少数据量
        if len(audio) > num_points:
            indices = np.linspace(0, len(audio) - 1, num_points).astype(int)
            waveform = audio[indices]
        else:
            waveform = audio

        # 归一化到 -1~1
        peak = np.max(np.abs(waveform))
        if peak > 0:
            waveform = waveform / peak

        return waveform.tolist()

    def get_spectrogram_image(self, audio: np.ndarray, sr: int = None) -> np.ndarray:
        """
        获取频谱图图像数据用于预览

        Args:
            audio: 音频波形
            sr: 采样率

        Returns:
            频谱图图像 (RGB格式)
        """
        sr = sr or self.sample_rate
        mel_spec = librosa.feature.melspectrogram(y=audio, sr=sr, n_mels=128)
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

        # 归一化到 0-255
        mel_spec_db = (mel_spec_db - mel_spec_db.min()) / (mel_spec_db.max() - mel_spec_db.min() + 1e-8) * 255
        mel_spec_db = mel_spec_db.astype(np.uint8)

        # 转换为RGB (灰度图)
        return mel_spec_db


def preprocess_audio(
    audio_data: str,
    operations: List[str],
    params: Dict = None,
    return_format: str = 'audio'
) -> Dict:
    """
    便捷预处理函数

    Args:
        audio_data: base64编码的音频数据
        operations: 操作列表
        params: 操作参数
        return_format: 'audio' 返回音频, 'mel' 返回梅尔频谱图

    Returns:
        预处理结果
    """
    preprocessor = AudioPreprocessor()

    try:
        audio, sr = preprocessor.load_audio_from_base64(audio_data)
        processed_audio, output_sr, suffix = preprocessor.preprocess_single(audio, sr, operations, params)

        result = {
            'success': True,
            'original_audio': preprocessor.audio_to_base64_dataurl(audio, sr),
            'processed_audio': preprocessor.audio_to_base64_dataurl(processed_audio, output_sr),
            'suffix': suffix,
            'duration': float(len(processed_audio) / output_sr),
            'sample_rate': output_sr,
            'waveform': preprocessor.get_waveform_data(processed_audio, output_sr)
        }

        # 如果包含梅尔频谱图操作
        if 'mel' in operations:
            mel_result = preprocessor.extract_mel_spectrogram(processed_audio, output_sr)
            result['mel_spectrogram'] = mel_result['mel_spec'].tolist()
            result['mel_shape'] = mel_result['shape']

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def get_available_operations() -> List[Dict]:
    """获取所有可用的预处理操作"""
    return [
        {
            'id': 'mel',
            'name': '梅尔频谱图',
            'category': '基础预处理',
            'description': '提取梅尔频谱图特征'
        },
        {
            'id': 'normalize',
            'name': '音频归一化',
            'category': '基础预处理',
            'description': '峰值归一化到-1~1区间'
        },
        {
            'id': 'trim',
            'name': '静音切除',
            'category': '基础预处理',
            'description': '去除首尾静音段'
        },
        {
            'id': 'noise',
            'name': '添加噪声',
            'category': '数据增强-时域',
            'description': '添加随机高斯噪声'
        },
        {
            'id': 'speed',
            'name': '改变速度',
            'category': '数据增强-时域',
            'description': '改变播放速度，保持音高'
        },
        {
            'id': 'time_mask',
            'name': '时间掩码',
            'category': '数据增强-时域',
            'description': '随机遮蔽一段时间'
        },
        {
            'id': 'freq_mask',
            'name': '频率掩码',
            'category': '数据增强-频域',
            'description': '在梅尔频谱图上遮蔽频率'
        },
        {
            'id': 'resample',
            'name': '重采样',
            'category': '基础预处理',
            'description': '改变音频采样率'
        }
    ]

"""
Audio emotion recognition service using local HuBERT model.
Based on xmj2002/hubert-base-ch-speech-emotion-recognition.
"""
import threading
import os
import numpy as np

_lock = threading.Lock()
_processor = None
_model = None
_model_loaded = False

AUDIO_LABELS_CN = {
    0: '生气', 1: '害怕', 2: '开心',
    3: '平静', 4: '难过', 5: '惊讶'
}
AUDIO_LABELS_EN = {
    0: 'anger', 1: 'fear', 2: 'happy',
    3: 'neutral', 4: 'sad', 5: 'surprise'
}
AUDIO_EMOJI = {
    0: '😠', 1: '😨', 2: '😊',
    3: '😐', 4: '😢', 5: '😮'
}

SAMPLE_RATE = 16000
DURATION = 6  # seconds


def _define_model_class():
    """Define HuBERT classification model class at runtime to avoid import errors."""
    import torch
    import torch.nn as nn
    from transformers import HubertPreTrainedModel, HubertModel

    class HubertClassificationHead(nn.Module):
        def __init__(self, config):
            super().__init__()
            self.dense = nn.Linear(config.hidden_size, config.hidden_size)
            self.dropout = nn.Dropout(config.classifier_dropout)
            self.out_proj = nn.Linear(config.hidden_size, config.num_class)

        def forward(self, x):
            x = self.dense(x)
            x = torch.tanh(x)
            x = self.dropout(x)
            x = self.out_proj(x)
            return x

    class HubertForSpeechClassification(HubertPreTrainedModel):
        def __init__(self, config):
            super().__init__(config)
            self.hubert = HubertModel(config)
            self.classifier = HubertClassificationHead(config)
            self.init_weights()

        def forward(self, x):
            outputs = self.hubert(x)
            hidden_states = outputs[0]
            x = torch.mean(hidden_states, dim=1)
            x = self.classifier(x)
            return x

        def _tied_weights_keys(self):
            return {}

        @property
        def all_tied_weights_keys(self):
            return self._tied_weights_keys()

    return HubertForSpeechClassification


def _load_model(model_dir: str):
    global _processor, _model, _model_loaded
    with _lock:
        if _model_loaded:
            return
        try:
            from transformers import AutoConfig, Wav2Vec2FeatureExtractor
            import torch

            HubertForSpeechClassification = _define_model_class()

            config = AutoConfig.from_pretrained(model_dir)
            _processor = Wav2Vec2FeatureExtractor.from_pretrained(model_dir)
            _model = HubertForSpeechClassification.from_pretrained(
                model_dir, config=config
            )
            _model.eval()
            _model_loaded = True
            print("[AudioService] HuBERT model loaded successfully.")
        except Exception as e:
            print(f"[AudioService] Failed to load model: {e}")
            _model_loaded = True  # Prevent retry loops


def predict_audio(audio_path: str, model_dir: str) -> dict:
    """Classify emotion from audio file, return label + scores."""
    _load_model(model_dir)

    if _model is None or _processor is None:
        return {"error": "模型未能加载，请检查依赖项"}

    try:
        import librosa
        import torch
        import torch.nn.functional as F

        speech, sr = librosa.load(audio_path, sr=SAMPLE_RATE)

        # Pad or truncate to DURATION seconds
        target_len = DURATION * SAMPLE_RATE
        if len(speech) < target_len:
            speech = np.pad(speech, (0, target_len - len(speech)))
        else:
            speech = speech[:target_len]

        inputs = _processor(
            speech,
            padding="max_length",
            truncation=True,
            max_length=target_len,
            return_tensors="pt",
            sampling_rate=SAMPLE_RATE
        ).input_values

        with torch.no_grad():
            logits = _model(inputs)

        scores = F.softmax(logits, dim=1).detach().cpu().numpy()[0]
        pred_idx = int(np.argmax(scores))

        # Debug: 打印模型原始输出
        print(f"[AudioService] Raw scores: {scores}")
        print(f"[AudioService] Predicted idx={pred_idx}, en={AUDIO_LABELS_EN.get(pred_idx)}, cn={AUDIO_LABELS_CN.get(pred_idx)}")

        return {
            'emotion_idx': pred_idx,
            'emotion_cn': AUDIO_LABELS_CN.get(pred_idx, '未知'),
            'emotion_en': AUDIO_LABELS_EN.get(pred_idx, 'unknown'),
            'emoji': AUDIO_EMOJI.get(pred_idx, '❓'),
            'scores': {
                AUDIO_LABELS_EN[i]: float(scores[i])
                for i in range(len(scores))
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"音频分析失败: {str(e)}"}

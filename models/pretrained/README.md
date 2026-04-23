# 预训练模型库

> 存放可供编辑器直接引用的预训练模型文件

## 目录结构

```
pretrained/
├── face/
│   ├── resnet50_face.h5          # ResNet50 人脸识别预训练模型
│   ├── mobilenet_emotion.h5       # MobileNet 表情分类预训练模型
│   └── facenet_embedding.pkl      # FaceNet 人脸特征embedding
├── eco/
│   ├── lstm_ecobottle.h5          # LSTM 生态瓶时序预测模型
│   ├── transformer_ecobottle.h5   # Transformer 时序预测模型
│   └── prophet_baseline.pkl       # Prophet 基线模型
└── audio/
    ├── wav2vec2_emotion.pt       # Wav2Vec2 语音情绪预训练模型
    └── hubert_finetuned.pt        # HuBERT 微调模型
```

## 使用方式

在编辑器中，可以直接引用：

```python
# 加载预训练表情识别模型
from tensorflow.keras.models import load_model
model = load_model('/models/pretrained/face/mobilenet_emotion.h5')

# 加载预训练 LSTM 模型
model = load_model('/models/pretrained/eco/lstm_ecobottle.h5')
```

## 模型来源

- `mobilenet_emotion.h5`: 在 FER2013 数据集上预训练的 MobileNetV2 表情分类模型
- `lstm_ecobottle.h5`: 在历史生态瓶传感器数据上训练的 LSTM 时序预测模型
- `facenet_embedding.pkl`: FaceNet 预训练的人脸特征提取器

## 上传新模型

将模型文件放入对应目录后，在编辑器「数据集」面板的「预训练模型」区域即可看到。

**注意**: 模型文件大小建议不超过 500MB，超大模型请使用分片加载。

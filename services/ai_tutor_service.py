# -*- coding: utf-8 -*-
"""
services/ai_tutor_service.py — AI学习助手服务层

支持两种模式：
1. 本地规则引擎（默认，无网络依赖）— 预设问答库 + 关键词匹配
2. LLM API（需配置 LLM_API_KEY）— OpenAI / 火山引擎 / 豆包 等

降级策略：检测到 API 不可用时自动回退到本地规则引擎。
"""

import os
import re
import time
import logging
import json
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1. 本地规则引擎 — 预设问答库
# ──────────────────────────────────────────────────────────────────────────────

# 按类别组织的预设问答库
LOCAL_QA = {
    # 通用
    '什么是人工智能': (
        '人工智能（AI）就像给电脑装了一个"聪明的大脑"！它可以通过学习很多例子，'
        '学会做事情，比如识别图片中的物体、理解我们说的话，或者预测天气。\n\n'
        '在我们的课程里，你会用到两种AI技术：\n'
        '🤖 **表情识别** — 让电脑看懂你的表情\n'
        '🎤 **声音情绪识别** — 让电脑听懂你的情绪'
    ),
    '人工智能': (
        '人工智能（AI）就是让机器具有类似人类的思考和学习能力！'
        '它不需要程序员告诉它每一步怎么做，而是通过学习大量数据，自己总结规律。'
    ),
    'ai': 'AI是人工智能(Artificial Intelligence)的缩写，就是让机器具有人类智能的技术。',

    # 表情识别
    '表情识别': (
        '表情识别就像给电脑装上"火眼金睛"！\n'
        '它分三步走：\n'
        '1️⃣ **人脸检测** — 找到图片里人脸在哪里（用Haar级联分类器）\n'
        '2️⃣ **关键点检测** — 在脸上标记68个关键点（像眼角、嘴角的位置）\n'
        '3️⃣ **情绪分类** — 分析这些点的分布，判断是开心/难过/生气...（用CNN神经网络）'
    ),
    '表情识别是怎么工作的': (
        '想象你在看图找表情：\n'
        '• 先找到脸在哪里（人脸检测）\n'
        '• 再看眉毛、眼睛、嘴巴的形状（68关键点）\n'
        '• 最后对照已知的表情模式判断（CNN分类器）'
    ),
    '人脸检测': (
        '人脸检测使用 **Haar 特征 + 级联分类器**，就像用很多小窗户在图片上扫描，'
        '每个窗户问："这里有人脸吗？" — '
        '如果答案是YES，就找到了人脸区域。\n'
        '优点是速度快，可以实时检测！'
    ),
    'dlib': (
        'dlib 是一个强大的 C++ 机器学习库，我们用它来检测脸上的68个关键点。\n'
        '这些点覆盖了眉毛、眼睛、鼻子、嘴唇、脸部轮廓等区域，'
        '通过分析这些点的相对位置和距离，可以精确判断表情。\n'
        '比如：嘴角上扬 → 开心，眉毛下压 → 生气 😐 → 😊 → 😠'
    ),
    'cnn': (
        'CNN（卷积神经网络）就像一个层层筛选的"图像侦探"！\n'
        '🔍 第1层：识别边缘和纹理\n'
        '🔍 第2层：识别形状和部件\n'
        '🔍 第3层：识别整体模式（比如笑脸）\n\n'
        '每层都在提取越来越高级的特征，最后综合判断是哪一种情绪。'
    ),
    '卷积': (
        '卷积就像用一个"小窗口"在图片上滑动，每滑动一次就提取一次特征。\n'
        '想象你用放大镜在地图上找城市 — 放大镜就是卷积核，地图就是图片。\n'
        '通过不断滑动，就能提取出图片中的各种特征。'
    ),
    'mini-xception': (
        'mini-XCEPTION 是一种轻量级的表情识别模型（比普通Xception小很多）。\n'
        '它的特点是：\n'
        '• **体积小** — 只有几MB，可以快速加载\n'
        '• **精度高** — 在 FER2013 数据集上达到约65%的准确率（7分类）\n'
        '• **深度可分离卷积** — 用更少参数达到同样效果'
    ),
    'fer2013': (
        'FER2013 是全球最大的人工标注表情数据集（35,000+张图片）。\n'
        '包含7种情绪：生气、厌恶、害怕、开心、难过、惊讶、平静。\n'
        '我们的 mini-XCEPTION 模型就是在这个数据集上训练的！'
    ),
    '置信度': (
        '置信度（Confidence）表示模型对预测结果的"自信程度"。\n'
        '比如模型说"这是开心"，置信度0.95表示它有95%的把握。\n'
        '阈值调高：只显示很有把握的结果（更准但可能漏掉）\n'
        '阈值调低：显示更多结果（更全但可能出错）'
    ),
    '平滑': (
        '平滑滤波就像给结果加了一层"保护膜"，减少跳动。\n'
        '原理：用指数滑动平均（EMA），新值只占60%，旧值占40%。\n'
        '效果：结果不会忽高忽低，看起来更稳定 ✨'
    ),
    '中性': '现在系统里统一叫"平静"啦 😊 这是考虑到学生在教学场景下更自然的表达。',

    # 声音情绪
    '声音情绪': (
        '声音情绪识别就像"听声辨情绪"！\n'
        'AI会分析声音的：\n'
        '🎵 **音调** — 高兴时音调偏高\n'
        '🔊 **响度** — 生气时声音更大\n'
        '⚡ **语速** — 开心时说话更快\n'
        '🌊 **音色** — 不同情绪有不同的音色特征\n\n'
        '我们用 HuBERT 模型来提取这些声音特征并进行分类！'
    ),
    'hubert': (
        'HuBERT 是一个自监督的语音模型，它的神奇之处是：\n'
        '不需要人工标注的转录，只需要听大量语音，就能学会理解语音内容！\n'
        '就像婴儿学说话，先听大量语音，慢慢就能分辨不同的声音模式。'
    ),
    '语音识别': (
        '语音识别（ASR）是把声音转换成文字的技术。\n'
        '在我们的课程中，HuBERT 模型直接把语音映射到情绪类别，'
        '不需要先转文字，一步到位！'
    ),
    '音频': (
        '音频文件要转换成特定格式才能被AI模型处理：\n'
        '📋 **采样率**：必须是 16kHz（人声识别标准）\n'
        '📋 **声道**：必须单声道（mono）\n'
        '📋 **格式**：WAV（无损压缩）\n\n'
        '如果格式不对，系统会自动转换！'
    ),

    # 情感计算
    '情感计算': (
        '情感计算就是综合分析多种信息来判断情绪！\n'
        '就像人类同时看表情+听语气来判断朋友的心情。\n'
        '🤝 **融合策略**：表情60% + 声音40%（表情通常更可靠）'
    ),
    '融合': (
        '多模态融合就是"取长补短"：\n'
        '• 表情识别的优势：视觉信息直观\n'
        '• 声音识别的优势：不受遮挡影响\n'
        '• 两者结合：判断更准确！'
    ),
    '多模态': (
        '多模态（Multimodal）就是同时使用多种感知方式。\n'
        '就像我们人类：看表情 + 听语气 = 完整的情感理解 🤝'
    ),

    # 生态瓶 / 时序预测
    '生态瓶': (
        '生态瓶是一个封闭的小生态系统，里面有水生植物、微生物等。\n'
        '通过传感器监测：🌡️温度、💧湿度、☀️光照、🌬️氧气、🔋发电量\n'
        '我们用AI分析这些数据的变化规律，预测未来的状态！'
    ),
    '时序预测': (
        '时序预测就像"根据昨天猜明天"！\n\n'
        '📈 **多项式回归** — 用一条曲线拟合数据变化\n'
        '📊 **ARIMA** — 考虑数据自相关性（今天和昨天有关）\n'
        '🌲 **LightGBM** — 用决策树做梯度提升预测\n'
        '📅 **Prophet** — 分解趋势+周期+节假日效应'
    ),
    '预测': (
        '预测的本质是"找规律，推未来"：\n'
        '1️⃣ 收集历史数据\n'
        '2️⃣ 分析变化规律\n'
        '3️⃣ 用数学模型描述规律\n'
        '4️⃣ 代入未来时间，计算预测值\n\n'
        '数据越多、规律越稳定，预测越准！'
    ),
    '回归': (
        '回归分析就是找"最佳拟合线"：\n'
        '• 线性回归：用一条直线 y = ax + b 拟合\n'
        '• 多项式回归：用曲线 y = a₀ + a₁x + a₂x² + ... 拟合\n'
        '• 目标：让所有点到线的"总距离"最小'
    ),
    '多项式': (
        '多项式回归用曲线而非直线拟合数据：\n'
        '• 阶数越高，曲线越灵活（但可能过拟合）\n'
        '• 阶数1 = 直线（简单，但可能欠拟合）\n'
        '• 阶数2-3 = 抛物线/曲线（大多数场景够用）\n'
        '• 阶数过高 = 可能绕开数据点（过拟合）⚠️'
    ),
    'lightgbm': (
        'LightGBM（Light Gradient Boosting Machine）是一个高效的梯度提升算法：\n'
        '🌲 用大量决策树协同工作\n'
        '⚡ 专为大规模数据优化，速度快\n'
        '📈 支持回归和分类任务\n\n'
        '在时序预测中，它可以从多个角度分析数据规律。'
    ),
    'arima': (
        'ARIMA = 自回归（AR）+ 移动平均（MA）+ 差分（I）\n\n'
        '• **AR（自回归）**：今天 ≈ a×昨天 + b×前天 + ...\n'
        '• **MA（移动平均）**：平滑随机波动\n'
        '• **I（差分）**：把不稳定数据变稳定\n\n'
        'ARIMA擅长捕捉数据的自相关性！'
    ),
    'prophet': (
        'Prophet 是 Facebook 开发的时序预测工具：\n'
        '📈 **趋势（Trend）** — 整体上升/下降\n'
        '🔄 **周期（Seasonality）** — 日/周/月周期\n'
        '🎉 **节假日（Holiday）** — 特殊日期影响\n\n'
        '特点是：对异常值鲁棒，不需要太多调参！'
    ),
    'rmse': (
        'RMSE（均方根误差）= 预测误差的标准差\n\n'
        '想象你射击10次：\n'
        '• 每次偏离靶心的距离就是"误差"\n'
        '• RMSE 就是这些误差的综合衡量\n\n'
        'RMSE 越小，预测越准！'
    ),
    'mae': (
        'MAE（平均绝对误差）= 预测误差的平均值\n\n'
        '特点：\n'
        '• 所有误差一视同仁（不像RMSE那样放大大的误差）\n'
        '• 更直观：平均每个预测点差多少'
    ),
    'r2': (
        'R²（决定系数）衡量模型解释了多少数据变化：\n'
        '• R² = 1.0 → 完美预测\n'
        '• R² = 0.8 → 模型解释了80%的变化\n'
        '• R² < 0 → 模型比直接用平均值还差 ❌\n\n'
        '目标：R² 越接近1越好！'
    ),

    # 传感器
    '传感器': (
        '传感器是生态瓶的"感觉器官"！\n'
        '🌡️ **温度传感器** — 监测水温变化\n'
        '💧 **湿度传感器** — 监测空气湿度\n'
        '☀️ **光照传感器** — 监测光照强度\n'
        '🌬️ **氧气传感器** — 监测溶解氧含量\n'
        '🔋 **太阳能板** — 监测发电量'
    ),
    'csv': (
        'CSV = Comma Separated Values（逗号分隔值）\n\n'
        '就像用表格的方式存储数据：\n'
        'timestamp,temperature,humidity,light\n'
        '2024-01-01 08:00,25.3,65,120\n'
        '2024-01-01 09:00,25.8,64,350\n\n'
        '优点：简单、通用、几乎所有软件都能打开！'
    ),
    '闭环控制': (
        '闭环控制就像"自动调温器"：\n'
        '🌡️ 测温度 → 发现太热 → 开风扇 → 温度下降 → 继续测...\n\n'
        '三种策略：\n'
        '• **被动控制**：定时开关（简单但不智能）\n'
        '• **阈值控制**：超限才动作（中等）\n'
        '• **预测控制**：AI预判，提前调节（最智能！）'
    ),
    '控制': (
        '智能控制的目标是让生态瓶保持最佳状态：\n'
        '🌡️ 温度：22-28°C\n'
        '☀️ 光照：100-500 lux\n\n'
        '你可以通过调节阈值、选择控制策略来优化控制效果！'
    ),

    # 学习方法
    '如何提高准确率': (
        '提高准确率的几个技巧：\n'
        '1️⃣ **数据质量** — 采集多样化的数据（不同角度，光照）\n'
        '2️⃣ **数据增强** — 旋转、翻转、调亮度扩充数据\n'
        '3️⃣ **预处理** — 适当调整对比度、尺寸\n'
        '4️⃣ **选择模型** — 根据数据量选择合适的模型\n'
        '5️⃣ **参数调优** — 多试几组超参数'
    ),
    '刷榜': (
        '刷榜就是在排行榜上争取更高名次！🏆\n\n'
        '攻略：\n'
        '1️⃣ 先用基础参数跑通流程\n'
        '2️⃣ 调整预处理参数（对比度、尺寸等）\n'
        '3️⃣ 尝试不同模型\n'
        '4️⃣ 用验证集评估，选择最优配置\n'
        '5️⃣ 提交成绩到排行榜！'
    ),
    '排行榜': (
        '排行榜展示各小组的训练成绩！🏆\n\n'
        '排名依据：\n'
        '• **准确率**（主要指标）\n'
        '• **训练时间**（同等准确率下，用时短优先）'
    ),
    '技能树': (
        '技能树记录你在课程中的学习进度！🌳\n\n'
        '三大技能线：\n'
        '📷 数据技能 — 采集→标注→增强→贡献\n'
        '⚙️ 算法技能 — 预处理→模型选择→参数调优\n'
        '💬 AI技能 — 提问→审查→优化建议\n\n'
        '完成课程任务，解锁新技能！'
    ),
    '学习': (
        '学习建议：\n'
        '📚 第1课 — 先熟悉界面，多采集数据\n'
        '📚 第2课 — 调整参数，观察效果变化\n'
        '📚 第3课 — 尝试不同模型，理解各自优缺点\n'
        '📚 第4课 — 组合优化，冲榜！'
    ),

    # 技术问题
    '如何开始': (
        '欢迎开始学习！🎉\n\n'
        '建议按课程顺序推进：\n'
        '1️⃣ 先体验表情识别/声音情绪\n'
        '2️⃣ 了解数据采集流程\n'
        '3️⃣ 尝试模型训练和参数调整\n'
        '4️⃣ 参加刷榜挑战！'
    ),
    '摄像头': (
        '摄像头需要浏览器授权才能使用。\n'
        '首次使用时会弹出授权提示，点击"允许"即可。\n'
        '如果无法使用，可能是：\n'
        '• 浏览器不支持（推荐Chrome）\n'
        '• 被杀毒软件拦截\n'
        '• HTTPS环境下需要安全连接'
    ),
    '麦克风': (
        '麦克风同样需要浏览器授权。\n'
        '建议使用Chrome浏览器，点击允许即可。\n'
        '录音时长建议3-5秒，过短可能识别不准确，过长容易录入背景噪音。'
    ),
    '默认': None,  # 无精确匹配时用模糊匹配
}


# ──────────────────────────────────────────────────────────────────────────────
# 2. 本地知识检索函数
# ──────────────────────────────────────────────────────────────────────────────

def local_answer(question: str) -> Optional[str]:
    """
    在本地问答库中查找答案。
    返回 None 表示未找到，调用方应转向 LLM API。
    """
    q = question.strip()
    q_lower = q.lower()

    # 精确匹配
    if q in LOCAL_QA:
        val = LOCAL_QA[q]
        if val:
            return val

    # 模糊匹配：包含关键词
    keywords = [
        ('表情识别', LOCAL_QA.get('表情识别')),
        ('声音情绪', LOCAL_QA.get('声音情绪')),
        ('情感计算', LOCAL_QA.get('情感计算')),
        ('时序预测', LOCAL_QA.get('时序预测')),
        ('预测', LOCAL_QA.get('预测')),
        ('生态瓶', LOCAL_QA.get('生态瓶')),
        ('传感器', LOCAL_QA.get('传感器')),
        ('人工智能', LOCAL_QA.get('人工智能')),
        ('cnn', LOCAL_QA.get('cnn')),
        ('卷积', LOCAL_QA.get('卷积')),
        ('lightgbm', LOCAL_QA.get('lightgbm')),
        ('arima', LOCAL_QA.get('arima')),
        ('prophet', LOCAL_QA.get('prophet')),
        ('rmse', LOCAL_QA.get('rmse')),
        ('回归', LOCAL_QA.get('回归')),
        ('置信度', LOCAL_QA.get('置信度')),
        ('平滑', LOCAL_QA.get('平滑')),
        ('融合', LOCAL_QA.get('融合')),
        ('多模态', LOCAL_QA.get('多模态')),
        ('刷榜', LOCAL_QA.get('刷榜')),
        ('排行榜', LOCAL_QA.get('排行榜')),
        ('技能树', LOCAL_QA.get('技能树')),
        ('学习', LOCAL_QA.get('学习')),
        ('如何提高准确率', LOCAL_QA.get('如何提高准确率')),
        ('如何开始', LOCAL_QA.get('如何开始')),
        ('摄像头', LOCAL_QA.get('摄像头')),
        ('麦克风', LOCAL_QA.get('麦克风')),
    ]

    for keyword, answer in keywords:
        if keyword.lower() in q_lower or q_lower in keyword.lower():
            if answer:
                return answer

    # 无法匹配
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 3. LLM API 调用（可选）
# ──────────────────────────────────────────────────────────────────────────────

def call_llm_api(question: str, context: dict = None) -> dict:
    """
    调用外部 LLM API（如 OpenAI GPT、火山引擎、豆包等）。

    Args:
        question: 用户问题
        context: 额外上下文（如当前技能树状态、课程进度等）

    Returns:
        {
            'answer': str,         # AI 回复文本
            'source': str,         # 'local' | 'llm_api'
            'model': str,          # 使用的模型名称
            'tokens_used': int,    # token 消耗（仅 API 模式）
            'latency_ms': int,     # 响应耗时
            'error': str,          # 错误信息（如有）
        }
    """
    api_key = Config.LLM_API_KEY
    base_url = Config.LLM_BASE_URL
    model = Config.LLM_MODEL

    if not api_key or api_key.strip() == '':
        return {
            'answer': None,
            'source': 'llm_api',
            'model': model,
            'error': 'LLM_API_KEY 未配置，将使用本地规则引擎',
            'tokens_used': 0,
            'latency_ms': 0,
        }

    # 构建系统提示词
    system_prompt = (
        '你是香港科技大学（广州）× 编程猫 联合实验室教学平台的 AI 学习助手。\n'
        '你的角色是帮助小学生理解 AI 基础知识，用通俗易懂、活泼有趣的语言回答问题。\n\n'
        '涉及的技术领域：\n'
        '- 表情识别（CNN、dlib关键点、人脸检测）\n'
        '- 声音情绪识别（HuBERT、音频特征）\n'
        '- 情感计算（多模态融合）\n'
        '- 时序预测（多项式回归、ARIMA、LightGBM、Prophet）\n'
        '- 生态瓶传感器与闭环控制\n\n'
        '回答要求：\n'
        '1. 通俗易懂，适合小学生理解\n'
        '2. 适当使用 emoji 增加趣味性\n'
        '3. 如果问题超出课程范围，礼貌引导回到主题\n'
        '4. 如果不确定，诚实说"这个问题我也不太确定"，不要瞎编'
    )

    # 构建上下文
    user_prompt = question
    if context:
        ctx_parts = []
        if context.get('course'):
            ctx_parts.append(f"当前课程：{context['course']}")
        if context.get('lesson'):
            ctx_parts.append(f"当前课时：第{context['lesson']}课")
        if context.get('skills'):
            ctx_parts.append(f"已解锁技能：{', '.join(context['skills'])}")
        if ctx_parts:
            user_prompt = f"[背景信息：{'；'.join(ctx_parts)}]\n\n用户问题：{question}"

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]

    return _post_openai_compatible_messages(
        messages,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
        max_tokens=600,
    )


def _first_tip(tips: list | None) -> str | None:
    if not tips:
        return None
    return tips[0]


def _post_openai_compatible_messages(
    messages: list[dict],
    *,
    model: str,
    api_key: str,
    base_url: str | None,
    temperature: float,
    max_tokens: int,
) -> dict:
    """Post chat-completions with explicit UTF-8 JSON to avoid SDK encoding issues."""
    try:
        import httpx
    except ImportError:
        return {
            'answer': None,
            'source': 'llm_api',
            'model': model,
            'error': 'Please install httpx',
            'tokens_used': 0,
            'latency_ms': 0,
        }

    if not base_url:
        return {
            'answer': None,
            'source': 'llm_api',
            'model': model,
            'error': 'LLM_BASE_URL not configured',
            'tokens_used': 0,
            'latency_ms': 0,
        }

    endpoint = base_url.rstrip('/') + '/chat/completions'
    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json; charset=utf-8',
    }

    try:
        start_ms = int(time.time() * 1000)
        with httpx.Client(timeout=45.0, trust_env=False) as client:
            response = client.post(
                endpoint,
                headers=headers,
                content=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            )
        latency_ms = int(time.time() * 1000) - start_ms

        response.raise_for_status()
        data = response.json()

        answer = (
            data.get('choices', [{}])[0]
            .get('message', {})
            .get('content', '')
            .strip()
        )
        usage = data.get('usage') or {}
        tokens_used = usage.get('total_tokens', 0)

        return {
            'answer': answer or None,
            'source': 'llm_api',
            'model': data.get('model') or model,
            'tokens_used': tokens_used,
            'latency_ms': latency_ms,
            'error': None if answer else 'Empty LLM response',
        }
    except Exception as exc:
        logger.warning(f'LLM API call failed: {exc}')
        return {
            'answer': None,
            'source': 'llm_api',
            'model': model,
            'error': str(exc),
            'tokens_used': 0,
            'latency_ms': 0,
        }


def call_llm_messages(messages: list[dict]) -> dict:
    """Call the configured OpenAI-compatible API with prebuilt messages."""
    api_key = Config.LLM_API_KEY
    base_url = Config.LLM_BASE_URL
    model = Config.LLM_MODEL

    if not api_key or api_key.strip() == '':
        return {
            'answer': None,
            'source': 'llm_api',
            'model': model,
            'error': 'LLM_API_KEY not configured',
            'tokens_used': 0,
            'latency_ms': 0,
        }

    return _post_openai_compatible_messages(
        messages,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.5,
        max_tokens=700,
    )


def probe_llm_connection(prompt: str | None = None) -> dict:
    """Run a direct LLM probe without any local fallback."""
    probe_prompt = (prompt or '').strip() or '请只回复“探测成功”。'
    messages = [
        {
            'role': 'system',
            'content': '你是一个接口连通性探测助手。严格按要求简短作答，不要补充解释。',
        },
        {
            'role': 'user',
            'content': probe_prompt,
        },
    ]

    llm_result = call_llm_messages(messages)
    return {
        'ok': bool(llm_result.get('answer')),
        'answer': llm_result.get('answer'),
        'source': llm_result.get('source'),
        'model': llm_result.get('model'),
        'tokens_used': llm_result.get('tokens_used', 0),
        'latency_ms': llm_result.get('latency_ms', 0),
        'error': llm_result.get('error'),
        'prompt': probe_prompt,
    }


def compose_structured_response(
    question: str,
    request_context: dict,
    rule_result: dict,
    knowledge_context: dict,
    base_result: dict | None = None,
    llm_result: dict | None = None,
) -> dict:
    """Compose the phase 1 structured tutor response."""
    diagnosis = rule_result.get('diagnosis')
    tips = rule_result.get('tips') or []
    next_step = rule_result.get('next_step')

    if llm_result and llm_result.get('answer'):
        answer = llm_result['answer']
        source = llm_result.get('source', 'llm_api')
        mode = rule_result.get('mode') or detect_mode(question)
        tokens_used = llm_result.get('tokens_used', 0)
        latency_ms = llm_result.get('latency_ms', 0)
        model = llm_result.get('model')
    elif diagnosis and next_step:
        current_state = '我看了下你现在的进度，已经到这一小步啦。'
        answer_parts = [current_state, next_step]
        if _first_tip(tips):
            answer_parts.append(f"提示：{_first_tip(tips)}")
        answer = ''.join(answer_parts)
        source = 'hybrid' if knowledge_context.get('knowledge_refs') else 'rule'
        mode = rule_result.get('mode') or 'guide'
        tokens_used = 0
        latency_ms = 0
        model = None
    else:
        base_result = base_result or get_answer(
            question,
            context={
                'course': request_context.get('course'),
                'step_code': request_context.get('step_code'),
                'snapshot': request_context.get('snapshot'),
                'knowledge': knowledge_context.get('text'),
            },
            prefer_llm=False,
        )
        answer = base_result['answer']
        source = base_result['source']
        mode = base_result.get('mode', detect_mode(question))
        tokens_used = base_result.get('tokens_used', 0)
        latency_ms = base_result.get('latency_ms', 0)
        model = base_result.get('model')

    from services.ai_context_service import build_context_used

    context_used = build_context_used(
        request_context,
        rule_hits=rule_result.get('rule_hits') or [],
        knowledge_refs=knowledge_context.get('knowledge_refs') or [],
    )

    return {
        'answer': answer,
        'source': source,
        'model': model,
        'tokens_used': tokens_used,
        'latency_ms': latency_ms,
        'mode': mode,
        'diagnosis': diagnosis,
        'next_step': next_step,
        'tips': tips,
        'context_used': context_used,
        'llm_attempted': bool(llm_result),
        'llm_error': (llm_result or {}).get('error'),
        'rule_result': rule_result,
    }


def build_llm_messages_from_context(
    question: str,
    request_context: dict,
    rule_result: dict,
    knowledge_context: dict,
) -> list[dict]:
    """Build messages for a later context-aware LLM call."""
    system_prompt = (
        '你是面向小学高年级学生的 AI 学习助教。回答要短，先说当前状态，'
        '再说下一步，最后最多给一条提示。'
    )
    user_prompt = (
        f"问题：{question}\n"
        f"页面：{request_context.get('page')}\n"
        f"课程：{request_context.get('course')}\n"
        f"步骤：{request_context.get('step_code')}\n"
        f"诊断：{rule_result.get('diagnosis')}\n"
        f"最近操作：{request_context.get('recent_event_summaries')}\n\n"
        f"知识片段：\n{knowledge_context.get('text') or ''}"
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def build_context_llm_messages(
    question: str,
    request_context: dict,
    rule_result: dict,
    knowledge_context: dict,
) -> list[dict]:
    """Build the actual context-rich messages used by `/ai/ask`."""
    snapshot = request_context.get('snapshot') or {}
    recent_events = request_context.get('recent_event_summaries') or []
    tips = rule_result.get('tips') or []
    next_step = rule_result.get('next_step')
    knowledge_text = knowledge_context.get('text') or ''

    snapshot_lines = []
    for key, value in snapshot.items():
        if value is None or isinstance(value, (dict, list)):
            continue
        snapshot_lines.append(f'- {key}: {value}')
        if len(snapshot_lines) >= 8:
            break

    system_prompt = (
        '你是一位面向小学高年级学生的课堂 AI 助教。'
        '请用自然、温和、像老师在课堂上解释一样的中文回答。'
        '优先直接回答学生真正问的问题，不要一上来就讲系统状态。'
        '页面状态、最近操作、诊断结果、知识笔记只是你的隐藏参考，不要把内部事件名、字段名、step code、原始埋点直接念给学生听。'
        '如果学生问的是知识概念，就先讲明白原理，再轻轻联系他刚才页面上的操作。'
        '如果学生问的是“下一步怎么办”，再给出一条明确可执行的下一步。'
        '避免机械重复“提示、下一步、当前状态”这些标签；除非很有帮助，否则不要列很多条。'
        '回答尽量控制在 2 到 4 句，清楚、亲切、不官腔。'
    )
    user_prompt = (
        f"学生问题：{question}\n"
        f"页面：{request_context.get('page')}\n"
        f"课程：{request_context.get('course')}\n"
        f"步骤：{request_context.get('step_code')}\n"
        f"诊断：{rule_result.get('diagnosis')}\n"
        f"建议下一步：{next_step}\n"
        f"可参考提示：{tips}\n"
        f"最近操作摘要：{recent_events}\n"
        f"页面快照：\n{chr(10).join(snapshot_lines) if snapshot_lines else '- 无'}\n\n"
        f"知识笔记：\n{knowledge_text}\n\n"
        '请给出一段适合学生阅读的回答：先解答问题，再在必要时轻轻点出他现在所处的步骤，最后只给一条最值得做的下一步。'
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def _persist_tutor_message(
    request_context: dict,
    question: str,
    structured_result: dict,
) -> None:
    """Best-effort persistence for tutor Q&A text."""
    try:
        from models import AiTutorMessage, db

        message = AiTutorMessage(
            session_id=request_context['session_id'],
            group_id=request_context['group_id'],
            role='assistant',
            user_question_text=question,
            answer_text=structured_result.get('answer'),
            diagnosis=structured_result.get('diagnosis'),
            next_step=structured_result.get('next_step'),
            tips=structured_result.get('tips'),
            context_used=structured_result.get('context_used'),
            source=structured_result.get('source'),
        )
        db.session.add(message)
        db.session.commit()
    except Exception as exc:
        logger.warning(f'AI tutor message persistence skipped: {exc}')


def answer_with_context(
    question: str,
    raw_context: dict,
    group_id=None,
    prefer_llm: bool = False,
) -> dict:
    """Answer with page context, recent events, rules, and markdown knowledge."""
    from services import ai_context_store
    from services.ai_context_service import build_request_context
    from services.ai_knowledge_service import build_knowledge_context
    from services.ai_rule_service import detect_stuck
    from services.ai_session_service import update_session_diagnosis

    request_context = build_request_context(question, raw_context, group_id=group_id)
    rule_result = detect_stuck(request_context)
    knowledge_context = build_knowledge_context(
        request_context.get('course'),
        step_code=request_context.get('step_code'),
        diagnosis=rule_result.get('diagnosis'),
        question=question,
    )

    llm_result = None
    has_llm = bool(Config.LLM_API_KEY and Config.LLM_API_KEY.strip())
    if has_llm:
        llm_messages = build_context_llm_messages(
            question,
            request_context,
            rule_result,
            knowledge_context,
        )
        llm_result = call_llm_messages(llm_messages)

    base_result = None
    fallback_prefer_llm = prefer_llm and llm_result is None
    if not (llm_result and llm_result.get('answer')) and (not rule_result.get('diagnosis') or prefer_llm):
        base_context = {
            'course': request_context.get('course'),
            'step_code': request_context.get('step_code'),
            'snapshot': request_context.get('snapshot'),
            'recent_events': request_context.get('recent_event_summaries'),
            'diagnosis': rule_result.get('diagnosis'),
            'knowledge': knowledge_context.get('text'),
        }
        base_result = get_answer(question, context=base_context, prefer_llm=fallback_prefer_llm)

    structured = compose_structured_response(
        question,
        request_context,
        rule_result,
        knowledge_context,
        base_result=base_result,
        llm_result=llm_result,
    )

    if rule_result.get('diagnosis'):
        ai_context_store.set_diag(request_context['session_id'], rule_result)
        try:
            update_session_diagnosis(request_context['session_id'], rule_result)
        except Exception as exc:
            logger.warning(f'AI tutor diagnosis persistence skipped: {exc}')

    logger.info(
        'AI tutor answer source=%s llm_attempted=%s llm_error=%s diagnosis=%s session_id=%s',
        structured.get('source'),
        structured.get('llm_attempted'),
        structured.get('llm_error'),
        structured.get('diagnosis'),
        request_context.get('session_id'),
    )

    _persist_tutor_message(request_context, question, structured)
    return structured


# ──────────────────────────────────────────────────────────────────────────────
# 4. 主入口：获取回复
# ──────────────────────────────────────────────────────────────────────────────

def get_answer(question: str, context: dict = None, prefer_llm: bool = False) -> dict:
    """
    获取 AI 助手的回复。

    策略：
    1. 优先在本地知识库查找（快速、无网络依赖）
    2. 若 prefer_llm=True 或本地无答案 → 尝试 LLM API
    3. 若 LLM API 也失败 → 返回本地默认回复

    Args:
        question: 用户问题
        context: 额外上下文
        prefer_llm: 是否优先使用 LLM API

    Returns:
        {
            'answer': str,
            'source': 'local' | 'llm_api' | 'fallback',
            'model': str | None,
            'tokens_used': int,
            'latency_ms': int,
            'mode': 'qa' | 'code_review' | 'suggestion',
        }
    """
    # Step 1: 尝试本地规则引擎
    local_result = local_answer(question)
    if local_result and not prefer_llm:
        return {
            'answer': local_result,
            'source': 'local',
            'model': None,
            'tokens_used': 0,
            'latency_ms': 0,
            'mode': detect_mode(question),
        }

    # Step 2: 尝试 LLM API
    llm_result = call_llm_api(question, context)
    if llm_result.get('answer'):
        return {
            'answer': llm_result['answer'],
            'source': llm_result['source'],
            'model': llm_result['model'],
            'tokens_used': llm_result['tokens_used'],
            'latency_ms': llm_result['latency_ms'],
            'mode': detect_mode(question),
        }

    # Step 3: 本地有答案但 LLM 失败 → 返回本地答案
    if local_result:
        return {
            'answer': local_result,
            'source': 'local',
            'model': None,
            'tokens_used': 0,
            'latency_ms': 0,
            'mode': detect_mode(question),
        }

    # Step 4: 完全无法回答 → 返回默认回复
    return {
        'answer': (
            '哇，这是个好问题！😊 '
            '这个问题涉及比较深的内容，你可以尝试：\n'
            '1️⃣ 点击上方的模块卡片，亲自体验一下\n'
            '2️⃣ 向老师请教，或者在课堂上讨论\n'
            '3️⃣ 尝试换一种问法~'
        ),
        'source': 'fallback',
        'model': None,
        'tokens_used': 0,
        'latency_ms': 0,
        'mode': detect_mode(question),
    }


def detect_mode(question: str) -> str:
    """根据问题内容判断当前模式。"""
    q = question.lower()
    if any(k in q for k in ['代码', 'code', '帮我写', '写一个', 'python']):
        return 'code_review'
    if any(k in q for k in ['建议', '优化', '怎么提高', '改进']):
        return 'suggestion'
    return 'qa'


def code_review(code: str, language: str = 'python') -> dict:
    """
    代码审查功能。

    Args:
        code: 待审查的代码
        language: 语言类型

    Returns:
        {'feedback': str, 'issues': list[str], 'suggestions': list[str]}
    """
    # 先尝试本地规则
    local_issues = []
    local_suggestions = []

    if len(code) < 10:
        local_issues.append('代码太短，无法进行有效审查')

    if 'print' not in code and 'return' not in code and language == 'python':
        local_suggestions.append('建议添加输出语句，方便调试')

    if code.count('=') > 20:
        local_suggestions.append('变量较多，建议用字典或类来组织数据')

    # 调用 LLM API 进行深度审查
    llm_result = call_llm_api(
        f'请审查以下 Python 代码，指出问题并给出改进建议：\n\n```python\n{code}\n```',
        context={'task': 'code_review'}
    )

    if llm_result.get('answer'):
        return {
            'feedback': llm_result['answer'],
            'issues': local_issues,
            'suggestions': local_suggestions,
            'source': 'llm_api',
        }

    # API 不可用，返回本地基础审查
    feedback_parts = []
    if local_issues:
        feedback_parts.append('**发现的问题：**\n' + '\n'.join(f'• {i}' for i in local_issues))
    if local_suggestions:
        feedback_parts.append('**改进建议：**\n' + '\n'.join(f'• {s}' for s in local_suggestions))

    return {
        'feedback': '\n\n'.join(feedback_parts) if feedback_parts else '代码看起来没有明显问题 👍',
        'issues': local_issues,
        'suggestions': local_suggestions,
        'source': 'local',
    }


def get_learning_guide(course: str = None, lesson: int = None) -> str:
    """
    根据当前课程和课时，返回学习引导建议。
    """
    if course == 'emotion' or course == 'emotion_computing':
        guides = {
            1: '第1课建议：先熟悉界面，尝试用摄像头采集自己的表情数据！📷 采集时尽量保持光线充足、正对摄像头。',
            2: '第2课建议：现在你可以调整预处理参数了！试试调高/调低对比度，观察准确率的变化。📊',
            3: '第3课建议：尝试同时采集表情和声音数据，体验多模态融合！🤝',
            4: '第4课建议：准备好了吗？参加刷榜挑战，提交你的最佳成绩！🏆',
        }
    elif course == 'ecobottle':
        guides = {
            1: '第1课建议：先用模拟器采集一些数据，熟悉5个传感器的读数规律。🌱',
            2: '第2课建议：有了数据后，试试不同的预测模型（多项式/ARIMA/LightGBM），比较哪个效果更好！',
            3: '第3课建议：进入数据探索，看看各传感器之间的相关性，说不定能发现有趣的规律！🔍',
            4: '第4课建议：尝试预测控制策略，让AI帮你自动调节生态瓶！🎮',
        }
    else:
        guides = {
            None: '欢迎开始学习！🎉 建议从第1课开始，逐课推进。',
        }

    return guides.get(lesson, guides.get(None))

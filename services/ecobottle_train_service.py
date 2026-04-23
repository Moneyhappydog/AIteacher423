"""
生态瓶时序预测模型训练服务
支持多种模型：多项式回归、Prophet、ARIMA、LightGBM
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os

# 前端可能传的时间格式（含秒或不含秒）
TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S",   # 2026-03-19 12:30:00
    "%Y-%m-%d %H:%M",      # 2026-03-19 12:30
    "%m/%d %H:%M",         # 03/19 12:30
]

def parse_ts(ts_str):
    """解析时间字符串，返回 datetime；失败返回 None"""
    if not ts_str or not isinstance(ts_str, str):
        return None
    ts_str = ts_str.strip()
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None

def format_ts_label(dt):
    """格式化为图表横坐标：MM/DD HH:MM"""
    if dt is None:
        return ""
    return dt.strftime("%m/%d %H:%M")

class TimeSeriesTrainer:
    """时序模型训练器"""
    
    def __init__(self):
        self.models = {}
        self.training_history = []
        
    def preprocess_data(self, data, method='none'):
        """
        数据预处理
        method: 'none', 'mean', 'median', 'interpolate', 'outlier_clip'
        """
        df = pd.DataFrame(data)
        
        if method == 'mean':
            df = df.fillna(df.mean())
        elif method == 'median':
            df = df.fillna(df.median())
        elif method == 'interpolate':
            df = df.interpolate(method='linear')
        elif method == 'outlier_clip':
            # 3σ原则裁剪异常值
            for col in df.columns:
                if df[col].dtype in [np.float64, np.int64]:
                    mean = df[col].mean()
                    std = df[col].std()
                    df[col] = df[col].clip(mean - 3*std, mean + 3*std)
        
        return df
    
    def train_polynomial(self, x, y, degree=2):
        """多项式回归训练"""
        try:
            coefficients = np.polyfit(x, y, degree)
            poly = np.poly1d(coefficients)
            
            # 计算训练指标
            y_pred = poly(x)
            mse = np.mean((y - y_pred) ** 2)
            rmse = np.sqrt(mse)
            mae = np.mean(np.abs(y - y_pred))
            
            # R² 分数
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            
            return {
                'success': True,
                'model_type': 'polynomial',
                'degree': degree,
                'coefficients': coefficients.tolist(),
                'metrics': {
                    'mse': float(mse),
                    'rmse': float(rmse),
                    'mae': float(mae),
                    'r2': float(r2)
                },
                'poly': poly,
                'last_value': float(y[-1]) if len(y) > 0 else 50.0
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def train_arima(self, x, y, order=(2, 1, 2)):
        """ARIMA模型训练（简化版，使用滑动平均）"""
        try:
            # 简化的ARIMA实现
            df = pd.DataFrame({'value': y}, index=x)
            
            # 差分
            diff = np.diff(y)
            
            # 移动平均预测
            window = order[0]
            if len(y) < window:
                window = len(y) // 2
            
            # 计算MA
            ma = np.convolve(y, np.ones(window)/window, mode='valid')
            
            # 简单线性外推
            slope = (ma[-1] - ma[0]) / len(ma) if len(ma) > 1 else 0
            
            # 使用多项式回归计算指标
            coeffs = np.polyfit(x, y, 1)
            poly = np.poly1d(coeffs)
            y_pred = poly(x)
            mse = np.mean((y - y_pred) ** 2)
            r2 = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
            
            return {
                'success': True,
                'model_type': 'arima',
                'order': order,
                'metrics': {
                    'mse': float(mse),
                    'rmse': float(np.sqrt(mse)),
                    'mae': float(np.mean(np.abs(y - y_pred))),
                    'r2': float(r2)
                },
                'slope': float(slope),
                'window': window,
                'last_value': float(y[-1]) if len(y) > 0 else 50.0,
                'last_values': y[-3:].tolist() if len(y) >= 3 else y.tolist() + [50.0] * (3 - len(y))
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def train_lightgbm_model(self, x, y, params=None):
        """LightGBM时序预测"""
        try:
            # 尝试导入lightgbm
            import lightgbm as lgb
            
            if params is None:
                params = {
                    'objective': 'regression',
                    'metric': 'rmse',
                    'num_leaves': 31,
                    'learning_rate': 0.1,
                    'feature_fraction': 0.9
                }
            
            # 创建特征（滞后特征）
            df = pd.DataFrame({'y': y})
            for i in range(1, 4):
                df[f'lag_{i}'] = df['y'].shift(i)
            
            df = df.dropna()
            
            if len(df) < 5:
                # 数据太少，回退到多项式
                return self.train_polynomial(x[:len(df)], df['y'].values, degree=1)
            
            X = df[[f'lag_{i}' for i in range(1, 4)]].values
            y_train = df['y'].values
            
            train_data = lgb.Dataset(X, label=y_train)
            
            model = lgb.train(
                params,
                train_data,
                num_boost_round=100
            )
            
            # 计算训练指标
            y_pred = model.predict(X)
            mse = np.mean((y_train - y_pred) ** 2)
            r2 = 1 - np.sum((y_train - y_pred)**2) / np.sum((y_train - np.mean(y_train))**2)
            
            return {
                'success': True,
                'model_type': 'lightgbm',
                'metrics': {
                    'mse': float(mse),
                    'rmse': float(np.sqrt(mse)),
                    'mae': float(np.mean(np.abs(y_train - y_pred))),
                    'r2': float(r2)
                },
                'model': model
            }
        except ImportError:
            # LightGBM未安装，回退到多项式
            return self.train_polynomial(x, y, degree=2)
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # 各变量的合理取值范围（用于裁剪预测值）
    VARIABLE_BOUNDS = {
        'temperature':  (-50, 60),    # °C
        'humidity':     (0, 100),    # %
        'light':        (0, 100000),  # lux
        'oxygen':       (0, 30),    # %
        'solar_power':  (0, 500),    # mW
    }
    
    def _clip_predictions(self, predictions, confidence_intervals, variable_name):
        """裁剪预测值和置信区间到合理范围"""
        lo, hi = self.VARIABLE_BOUNDS.get(variable_name, (None, None))
        if lo is None:
            return predictions, confidence_intervals
        
        clipped_preds = np.clip(predictions, lo, hi)
        clipped_intervals = []
        for lower, upper in confidence_intervals:
            clipped_lower = max(lo, lower)
            clipped_upper = min(hi, upper)
            clipped_intervals.append([clipped_lower, clipped_upper])
        
        return clipped_preds.tolist(), clipped_intervals
    
    def predict(self, model_result, future_steps, last_x=None, variable_name='light'):
        """模型预测"""
        if not model_result['success']:
            return None
        
        model_type = model_result['model_type']
        
        if model_type == 'polynomial':
            poly = model_result['poly']
            # 生成未来时间点
            if last_x is None:
                last_x = np.array([i for i in range(future_steps * 2)])[-1]
            
            future_x = np.array([last_x + i + 1 for i in range(future_steps)])
            predictions = poly(future_x)
            
            # 计算置信区间（随预测步长增加）
            base_std = model_result.get('metrics', {}).get('rmse', 1)
            confidence_intervals = []
            for i in range(future_steps):
                # 不确定性随步长增加
                k = 1 + 0.15 * i
                lower = predictions[i] - 1.96 * base_std * k
                upper = predictions[i] + 1.96 * base_std * k
                confidence_intervals.append([float(lower), float(upper)])
            
            # 裁剪到合理范围
            predictions, confidence_intervals = self._clip_predictions(
                predictions, confidence_intervals, variable_name
            )
            
            return {
                'predictions': predictions,
                'confidence_intervals': confidence_intervals,
                'future_x': future_x.tolist()
            }
        
        elif model_type == 'arima':
            # 简化ARIMA预测
            slope = model_result.get('slope', 0)
            predictions = []
            last_val = model_result.get('last_value', 50)
            
            for i in range(future_steps):
                pred = last_val + slope * (i + 1)
                predictions.append(float(pred))
            
            confidence_intervals = [[p-5, p+5] for p in predictions]
            # 裁剪到合理范围
            predictions, confidence_intervals = self._clip_predictions(
                predictions, confidence_intervals, variable_name
            )
            
            return {
                'predictions': predictions,
                'confidence_intervals': confidence_intervals,
                'future_x': list(range(future_steps))
            }
        
        elif model_type == 'lightgbm':
            # LightGBM预测
            predictions = []
            last_vals = list(model_result.get('last_values', [50, 50, 50]))[-3:]
            
            for i in range(future_steps):
                if i == 0:
                    features = np.array([[last_vals[-3], last_vals[-2], last_vals[-1]]])
                else:
                    features = np.array([[last_vals[-2], last_vals[-1], predictions[-1]]])
                
                pred = model_result['model'].predict(features)[0]
                predictions.append(float(pred))
            
            base_std = model_result.get('metrics', {}).get('rmse', 1)
            confidence_intervals = [[p-base_std, p+base_std] for p in predictions]
            
            # 裁剪到合理范围
            predictions, confidence_intervals = self._clip_predictions(
                predictions, confidence_intervals, variable_name
            )
            
            return {
                'predictions': predictions,
                'confidence_intervals': confidence_intervals,
                'future_x': list(range(future_steps))
            }
        
        return None
    
    def analyze_experiment(self, data_history, predictions, model_config, metrics=None):
        """
        分析实验设置和结果
        返回分析报告
        """
        analysis = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_summary': {},
            'model_analysis': {},
            'model_metrics': {},  # 模型评估指标
            'recommendations': []
        }
        
        # 数据摘要
        for key, values in data_history.items():
            if values:
                arr = np.array(values)
                analysis['data_summary'][key] = {
                    'count': len(arr),
                    'mean': float(np.mean(arr)),
                    'std': float(np.std(arr)),
                    'min': float(np.min(arr)),
                    'max': float(np.max(arr)),
                    'trend': '上升' if arr[-1] > arr[0] else ('下降' if arr[-1] < arr[0] else '平稳')
                }
        
        # 模型分析
        analysis['model_analysis'] = {
            'model_type': model_config.get('model_type', 'polynomial'),
            'preprocessing': model_config.get('preprocessing', 'none'),
            'prediction_steps': model_config.get('prediction_steps', 12)
        }
        
        # 模型评估指标
        if metrics:
            for key, data in metrics.items():
                if data and isinstance(data, dict):
                    model_result = data.get('model_result', {})
                    if model_result and model_result.get('success'):
                        analysis['model_metrics'][key] = {
                            'model_type': model_result.get('model_type', 'unknown'),
                            'r2': model_result.get('metrics', {}).get('r2', 0),
                            'rmse': model_result.get('metrics', {}).get('rmse', 0),
                            'mae': model_result.get('metrics', {}).get('mae', 0),
                            'mse': model_result.get('metrics', {}).get('mse', 0)
                        }
        
        # 建议 - predictions 是 dict {'light': [...], 'temperature': [...], 'battery': [...]}
        # 合并所有通道的预测值
        all_preds = []
        if isinstance(predictions, dict):
            for v in predictions.values():
                if v is not None:
                    if hasattr(v, '__iter__') and not isinstance(v, (str, dict)):
                        try:
                            all_preds.extend(list(v))
                        except:
                            pass
        elif hasattr(predictions, '__iter__') and not isinstance(predictions, (str, dict)):
            try:
                all_preds = list(predictions)
            except:
                all_preds = []
        
        pred_arr = np.array(all_preds) if all_preds else np.array([])
        if len(pred_arr) > 0:
            if np.std(pred_arr) > np.std(arr) * 1.5:
                analysis['recommendations'].append('预测步长较长时，不确定性增加明显，建议减少预测步长以获得更准确的结果')
            
            if len(arr) < 10:
                analysis['recommendations'].append('训练数据较少，建议增加更多数据点以提高预测准确性')
        
        analysis['recommendations'].append('可以尝试不同的预处理方法，观察预测结果的变化')
        analysis['recommendations'].append('对比不同模型的预测效果，理解各模型的优缺点')
        
        return analysis


def poly_predict(x, y, degree):
    """多项式预测辅助函数"""
    coeffs = np.polyfit(x, y, degree)
    poly = np.poly1d(coeffs)
    return poly(x)


# 训练器单例
_trainer = None

def get_trainer():
    global _trainer
    if _trainer is None:
        _trainer = TimeSeriesTrainer()
    return _trainer


def train_model(data, config, timestamps=None):
    """
    训练模型主函数
    data: {'light': [], 'temperature': [], 'battery': []}
    config: {
        'model_type': 'polynomial' | 'arima' | 'lightgbm',
        'preprocessing': 'none' | 'mean' | 'median' | 'interpolate' | 'outlier_clip',
        'polynomial_degree': 1-3,
        'prediction_steps': 1-24
    }
    timestamps: 可选的时间戳字典 {'light': [...], 'temperature': [...], 'battery': [...]}
    """
    if timestamps is None:
        timestamps = {k: [] for k in data.keys()}
    trainer = get_trainer()
    results = {}
    
    # 预处理
    processed_data = trainer.preprocess_data(
        data, 
        config.get('preprocessing', 'none')
    )
    
    # 生成时间序列
    x = np.arange(len(processed_data))
    
    # 训练各通道
    for key, values in processed_data.items():
        # 确保values是列表类型
        values_list = values.tolist() if hasattr(values, 'tolist') else list(values)
        
        if not values_list or len(values_list) < 3:
            results[key] = {'success': False, 'error': '数据不足'}
            continue
        
        y = np.array(values_list)
        model_type = config.get('model_type', 'polynomial')
        
        # 训练模型
        if model_type == 'polynomial':
            degree = config.get('polynomial_degree', 2)
            model_result = trainer.train_polynomial(x, y, degree)
        elif model_type == 'arima':
            model_result = trainer.train_arima(x, y)
        elif model_type == 'lightgbm':
            model_result = trainer.train_lightgbm_model(x, y)
        else:
            model_result = trainer.train_polynomial(x, y, 2)
        
        # 预测
        prediction_steps = config.get('prediction_steps', 12)
        prediction = trainer.predict(model_result, prediction_steps, last_x=x[-1] if len(x) > 0 else None, variable_name=key)
        
        results[key] = {
            'model_result': {
                'success': model_result['success'],
                'model_type': model_result.get('model_type'),
                'metrics': model_result.get('metrics', {})
            },
            'prediction': prediction,
            'history': values_list
        }
        
        # 清理不可序列化的对象，防止JSON序列化错误
        model_result.pop('poly', None)
        model_result.pop('model', None)
    
    # 生成时间标签（与前端格式一致）
    for key in results.keys():
        hist = results[key].get('history', [])
        pred_obj = results[key].get('prediction', {})
        pred_vals = pred_obj.get('predictions', [])
        
        hist_ts = timestamps.get(key, [])
        future_labels = []
        if hist_ts and len(hist_ts) > 0:
            last_ts = parse_ts(hist_ts[-1])
            if last_ts is not None:
                for i in range(len(pred_vals)):
                    future_ts = last_ts + timedelta(hours=i+1)
                    future_labels.append(format_ts_label(future_ts))
                # 历史段也统一为 MM/DD HH:MM 显示
                hist_labels = [format_ts_label(parse_ts(s)) or s for s in hist_ts]
                labels = hist_labels + future_labels
            else:
                labels = [f"t{i+1}" for i in range(len(hist) + len(pred_vals))]
        else:
            labels = [f"t{i+1}" for i in range(len(hist) + len(pred_vals))]
        
        results[key]['labels'] = labels
        results[key]['split_idx'] = len(hist)
    
    # 生成分析报告 - 把 predictions 转为各通道的列表
    pred_dict = {}
    for k, v in results.items():
        if v.get('prediction'):
            pred = v['prediction'].get('predictions')
            if pred is not None:
                # 确保是 list
                if hasattr(pred, 'tolist'):
                    pred_dict[k] = pred.tolist()
                elif isinstance(pred, list):
                    pred_dict[k] = pred
                else:
                    pred_dict[k] = list(pred) if hasattr(pred, '__iter__') else []
            else:
                pred_dict[k] = []
        else:
            pred_dict[k] = []
    
    try:
        analysis = trainer.analyze_experiment(data, pred_dict, config, results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 如果分析失败，返回空分析
        analysis = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_summary': {},
            'model_analysis': config,
            'model_metrics': {},
            'recommendations': ['分析生成失败，但预测结果已返回']
        }
    
    return {
        'results': results,
        'analysis': analysis,
        'config': config
    }

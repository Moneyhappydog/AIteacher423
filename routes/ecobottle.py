"""
生态瓶时序预测路由更新 - 合并训练功能
"""
from flask import Blueprint, render_template, request, jsonify, current_app, Response
from services.ecobottle_train_service import train_model
import json
import os
from datetime import datetime
import pickle

# 导入登录验证装饰器
from routes.auth import login_required

eco_bp = Blueprint('eco', __name__, template_folder='../templates')

# 实验报告存储
EXPERIMENTS_FILE = 'data/experiment_reports.json'
MODELS_DIR = 'data/models'

@eco_bp.route('/')
@login_required
def index():
    return render_template('ecobottle.html')

@eco_bp.route('/predict', methods=['POST'])
@login_required
def predict():
    """
    预测接口 - 使用选择的模型进行预测
    支持：prophet（默认）、polynomial、arima、lightgbm
    以及训练保存的模型和自定义模型
    """
    try:
        data = request.json or {}
        # 与 /eco/train 一致：通道数据可在 body.data 内，也可在顶层
        channels = data.get('data')
        if not isinstance(channels, dict):
            channels = data

        light        = channels.get('light', [])
        temperature = channels.get('temperature', [])
        humidity    = channels.get('humidity', [])
        oxygen      = channels.get('oxygen', [])
        solar_power = channels.get('solar_power', [])
        model_type  = data.get('model_type', 'prophet')
        custom_model_id = data.get('model_id')  # 自定义模型ID

        print(f"[Predict] Received: temperature={len(temperature)}, humidity={len(humidity)}, light={len(light)}, oxygen={len(oxygen)}, solar_power={len(solar_power)}, model={model_type}")

        # 如果有自定义模型ID，尝试使用自定义模型
        if custom_model_id:
            try:
                from services.custom_model_service import infer_with_model
                features = {
                    'temperature': temperature[-1] if temperature else 25,
                    'humidity': humidity[-1] if humidity else 65,
                    'light': light[-1] if light else 120,
                    'oxygen': oxygen[-1] if oxygen else 20.5,
                    'solar_power': solar_power[-1] if solar_power else 0
                }
                result = infer_with_model(custom_model_id, {'features': features})
                if 'error' not in result:
                    return jsonify({
                        'success': True,
                        'predictions': result.get('predictions', []),
                        'model_source': 'custom',
                        'model_name': result.get('model_name'),
                        'model_accuracy': result.get('accuracy')
                    })
            except Exception as e:
                print(f'自定义模型推理失败: {e}')

        # 如果是prophet，使用Prophet服务
        if model_type == 'prophet':
            from services.prophet_service import predict_all
            result = predict_all(light, temperature, humidity, oxygen, solar_power)
            return jsonify(result)

        # 使用训练服务进行预测（训练服务需要纯数值列表，不是 [{ds,y}, ...]）
        from services.ecobottle_train_service import train_model

        def to_numeric_list(channel_data):
            if not channel_data:
                return []
            first = channel_data[0]
            if isinstance(first, dict):
                return [float(p.get('y', 0)) for p in channel_data]
            if isinstance(first, (int, float)):
                return [float(x) for x in channel_data]
            return []

        def extract_timestamps(channel_data):
            if not channel_data:
                return []
            first = channel_data[0]
            if isinstance(first, dict):
                return [p.get('ds', '') for p in channel_data]
            return []

        timestamps = {
            'temperature':  extract_timestamps(temperature),
            'humidity':     extract_timestamps(humidity),
            'light':        extract_timestamps(light),
            'oxygen':       extract_timestamps(oxygen),
            'solar_power':  extract_timestamps(solar_power),
        }

        train_data = {
            'temperature':  to_numeric_list(temperature),
            'humidity':     to_numeric_list(humidity),
            'light':        to_numeric_list(light),
            'oxygen':       to_numeric_list(oxygen),
            'solar_power':  to_numeric_list(solar_power),
        }
        
        config = {
            'model_type': model_type,
            'preprocessing': 'none',
            'polynomial_degree': 2,
            'prediction_steps': data.get('prediction_steps', 12)
        }
        
        # 安全调用 train_model - 传递 timestamps 用于生成横坐标
        try:
            result = train_model(train_data, config, timestamps)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'train_model 异常: {str(e)}'})
        
        if not isinstance(result, dict):
            return jsonify({'error': f'train_model 返回类型错误: {type(result)}'})
        
        print(f"[Predict] train_model result keys: {result.keys()}")
        if 'results' in result:
            for k, v in result['results'].items():
                print(f"[Predict] channel {k}: {type(v)}, content={v}")
        
        # 转换为前端期望的格式
        formatted_result = {}
        for key in ['temperature', 'humidity', 'light', 'oxygen', 'solar_power']:
            if key in result.get('results', {}):
                r = result['results'][key]
                # 安全处理：确保所有值都是可 JSON 序列化的
                try:
                    if isinstance(r, dict) and r.get('prediction'):
                        # 强制把 history 和 predictions 转成 list
                        if 'history' in r:
                            hist_val = r['history']
                            if hasattr(hist_val, 'tolist'):
                                r['history'] = hist_val.tolist()
                            elif not isinstance(hist_val, list):
                                r['history'] = list(hist_val) if hasattr(hist_val, '__iter__') else [hist_val]
                        if 'prediction' in r and isinstance(r['prediction'], dict):
                            pred_val = r['prediction'].get('predictions')
                            if pred_val is not None:
                                if hasattr(pred_val, 'tolist'):
                                    r['prediction']['predictions'] = pred_val.tolist()
                                elif not isinstance(pred_val, list):
                                    r['prediction']['predictions'] = list(pred_val) if hasattr(pred_val, '__iter__') else [pred_val]
                except Exception as e:
                    print(f"[Predict] safety convert error: {e}")
                
                print(f"[Predict] channel {key}: r={r}")
                if r.get('prediction'):
                    pred = r['prediction']
                    hist = r.get('history', [])
                    pred_list = pred.get('predictions', [])
                    # DEBUG
                    print(f"[Predict] key={key}, hist type={type(hist)}, hist={hist}")
                    print(f"[Predict] pred_list type={type(pred_list)}, pred_list={pred_list}")
                    # 确保是列表再拼接，避免 dict + dict 等类型错误
                    if not isinstance(hist, list):
                        try:
                            hist = list(hist) if hasattr(hist, '__iter__') and not isinstance(hist, (str, dict)) else [hist]
                        except Exception as e:
                            print(f"[Predict] hist convert error: {e}, setting to []")
                            hist = []
                    if not isinstance(pred_list, list):
                        try:
                            pred_list = list(pred_list) if hasattr(pred_list, '__iter__') and not isinstance(pred_list, (str, dict)) else [pred_list]
                        except Exception as e:
                            print(f"[Predict] pred_list convert error: {e}, setting to []")
                            pred_list = []
                    history_len = len(hist)
                    all_values = hist + pred_list
                    
                    intervals = pred.get('confidence_intervals') or []
                    if not isinstance(intervals, list):
                        intervals = []
                    # 置信区间只覆盖预测段，历史段用历史值填充，保证与 all_values 等长
                    upper_pred = [p[1] for p in intervals if isinstance(p, (list, tuple)) and len(p) >= 2]
                    lower_pred = [p[0] for p in intervals if isinstance(p, (list, tuple)) and len(p) >= 2]
                    pad = len(pred_list) - len(upper_pred)
                    if pad > 0:
                        last_upper = upper_pred[-1] if upper_pred else (hist[-1] if hist else 0)
                        last_lower = lower_pred[-1] if lower_pred else (hist[-1] if hist else 0)
                        upper_pred += [last_upper] * pad
                        lower_pred += [last_lower] * pad
                    fc_upper = list(hist) + upper_pred[:len(pred_list)]
                    fc_lower = list(hist) + lower_pred[:len(pred_list)]
                    
                    # 生成时间标签 - 与 Prophet 格式一致
                    hist_ts = timestamps.get(key, [])
                    if hist_ts and len(hist_ts) > 0:
                        # 解析最后一个时间戳，生成未来的时间标签
                        from datetime import datetime, timedelta
                        try:
                            last_ts_str = hist_ts[-1]
                            # 尝试解析时间
                            if ' ' in last_ts_str:
                                # 格式可能是 "2026-03-19 00:07" 或 "03/19 00:07"
                                if '/' in last_ts_str:
                                    base_format = "%m/%d %H:%M"
                                elif last_ts_str.count(':') >= 2:
                                    # "2026-03-19 12:30:00" 带秒
                                    base_format = "%Y-%m-%d %H:%M:%S"
                                else:
                                    base_format = "%Y-%m-%d %H:%M"
                                last_ts = datetime.strptime(last_ts_str, base_format)
                            else:
                                # 如果解析失败，使用默认时间
                                last_ts = datetime.now()
                            
                            # 生成预测段的时间标签
                            future_labels = []
                            for i in range(len(pred_list)):
                                future_ts = last_ts + timedelta(hours=i+1)
                                future_labels.append(future_ts.strftime("%m/%d %H:%M"))
                            # 历史段也转为 MM/DD HH:MM 显示
                            from services.ecobottle_train_service import parse_ts, format_ts_label
                            hist_display = [format_ts_label(parse_ts(s)) or s for s in hist_ts]
                            labels = hist_display + future_labels
                        except Exception as e:
                            print(f"[Predict] timestamp parse error: {e}")
                            labels = [f"t{i+1}" for i in range(len(all_values))]
                    else:
                        labels = [f"t{i+1}" for i in range(len(all_values))]
                    
                    # 获取后端返回的时间标签（由 train_model 生成）
                    result_labels = r.get('labels')
                    
                    # 添加与 Prophet 一致的字段，以及 y 轴范围
                    # 灵活自适应：根据实际数据动态调整纵轴范围
                    actual_min = min(all_values) if all_values else 0
                    actual_max = max(all_values) if all_values else 100

                    # 预设的理论范围
                    variable_bounds = {
                        'temperature': (-50, 60),   # °C
                        'humidity':    (0, 100),    # %
                        'light':       (0, 100000), # lux
                        'oxygen':      (0, 30),     # %
                        'solar_power': (0, 500),    # mW
                    }
                    fixed_bounds = variable_bounds.get(key, (None, None))

                    # 灵活策略：如果实际数据范围远小于固定范围，则自适应
                    # 否则使用固定范围（保证图表美观）
                    if fixed_bounds[0] is not None and fixed_bounds[1] is not None:
                        fixed_range = fixed_bounds[1] - fixed_bounds[0]
                        actual_range = actual_max - actual_min
                        # 如果实际范围小于固定范围的30%，则自适应
                        if actual_range < fixed_range * 0.3:
                            y_min = actual_min * 0.9 if actual_min > 0 else actual_min * 1.1
                            y_max = actual_max * 1.1
                        else:
                            y_min = fixed_bounds[0]
                            y_max = fixed_bounds[1]
                    else:
                        y_min = actual_min * 0.9 if actual_min > 0 else actual_min * 1.1
                        y_max = actual_max * 1.1

                    formatted_result[key] = {
                        'hist_labels': hist_ts if hist_ts else (result_labels[:history_len] if result_labels else labels[:history_len]),
                        'hist_values': hist,
                        'fc_labels': result_labels if result_labels else labels,
                        'fc_values': all_values,
                        'fc_upper': fc_upper,
                        'fc_lower': fc_lower,
                        'split_idx': history_len,
                        'trend': f"{key}预测完成",
                        'y_min': y_min,
                        'y_max': y_max
                    }
        
        print(f"[Predict] Train result keys: {formatted_result.keys()}")
        return jsonify(formatted_result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'预测失败: {str(e)}'})

def _normalize_train_config(config):
    """前端传 camelCase，后端用 snake_case；统一为 snake_case"""
    if not config:
        return {}
    return {
        'model_type': config.get('model_type') or config.get('modelType', 'polynomial'),
        'preprocessing': config.get('preprocessing', 'none'),
        'polynomial_degree': int(config.get('polynomial_degree') or config.get('polynomialDegree', 2)),
        'prediction_steps': int(config.get('prediction_steps') or config.get('predictionSteps', 12)),
    }


@eco_bp.route('/train', methods=['POST'])
@login_required
def train():
    """
    模型训练接口。
    使用的就是「数据预测」页面上方添加的数据点；
    所选模型、数据预处理、超参数都会真实参与训练。
    """
    try:
        data = request.json.get('data', {})
        config_raw = request.json.get('config', {})
        config = _normalize_train_config(config_raw)
        
        print(f"[Train] 接收到的config: {config}")
        print(f"[Train] 接收到的data keys: {data.keys()}")
        if data:
            for k, v in data.items():
                print(f"[Train] data[{k}] 长度: {len(v) if v else 0}, 第一项类型: {type(v[0]) if v else 'empty'}")
        
        # 验证数据
        if not data or all(not v for v in data.values()):
            return jsonify({'success': False, 'error': '没有足够的数据进行训练'})
        
        model_type = config.get('model_type', 'polynomial')
        print(f"[Train] 模型类型: {model_type}")
        
        # 提取时间戳（前端传的是 [{ds, y}, ...] 格式）
        timestamps = {
            'temperature':  [p.get('ds', '') for p in data.get('temperature', [])],
            'humidity':     [p.get('ds', '') for p in data.get('humidity', [])],
            'light':        [p.get('ds', '') for p in data.get('light', [])],
            'oxygen':       [p.get('ds', '') for p in data.get('oxygen', [])],
            'solar_power':  [p.get('ds', '') for p in data.get('solar_power', [])],
        }
        
        if model_type == 'prophet':
            # Prophet 使用独立服务，需要 [{ds, y}, ...] 格式
            from services.prophet_service import predict_all
            light_pts     = data.get('light', [])
            temp_pts      = data.get('temperature', [])
            humid_pts     = data.get('humidity', [])
            oxygen_pts    = data.get('oxygen', [])
            solar_pts     = data.get('solar_power', [])
            if not light_pts or not isinstance(light_pts[0], dict):
                return jsonify({'success': False, 'error': 'Prophet 需要带时间戳的数据，请确保在数据预测中添加了数据点'})
            pred_result = predict_all(light_pts, temp_pts, humid_pts, oxygen_pts, solar_pts)
            # 转成与 train_model 一致的 results 结构，供前端展示
            steps = config.get('prediction_steps', 12)
            results = {}
            analysis = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_summary': {},
                'model_analysis': {'model_type': 'prophet', 'preprocessing': 'none', 'prediction_steps': steps},
                'recommendations': ['Prophet 已完成时序拟合与预测。']
            }
            for key in ['temperature', 'humidity', 'light', 'oxygen', 'solar_power']:
                ch = pred_result.get(key, {})
                if ch.get('error'):
                    results[key] = {'success': False, 'error': ch['error']}
                    continue
                hist = ch.get('hist_values', [])
                fc = ch.get('fc_values', [])
                fc_lo = ch.get('fc_lower', [])
                fc_hi = ch.get('fc_upper', [])
                n = ch.get('split_idx', len(hist))
                pred_vals = fc[n:] if n < len(fc) else []
                intervals = []
                for i in range(len(pred_vals)):
                    idx = n + i
                    if idx < len(fc_lo) and idx < len(fc_hi):
                        intervals.append([fc_lo[idx], fc_hi[idx]])
                    else:
                        v = pred_vals[i] if i < len(pred_vals) else 0
                        intervals.append([v, v])
                # Prophet 返回的时间标签（包含历史和预测）
                prophet_labels = ch.get('fc_labels', [])
                # 添加到结果
                results[key] = {
                    'model_result': {'success': True, 'model_type': 'prophet', 'metrics': {}},
                    'prediction': {'predictions': pred_vals, 'confidence_intervals': intervals},
                    'history': hist,
                    'labels': prophet_labels,
                    'split_idx': n
                }
            result = {'results': results, 'analysis': analysis, 'config': config}
        else:
            # 多项式 / ARIMA / LightGBM：需要纯数值列表
            print(f"[Train] 原始data: {data}")
            
            # 安全检查：确保data不为空且格式正确
            if not data:
                return jsonify({'success': False, 'error': '数据为空'})
            
            # 检查数据格式并转换
            first_value = None
            for v in data.values():
                if v:
                    first_value = v[0] if isinstance(v, list) else v
                    break
            
            if first_value is None:
                return jsonify({'success': False, 'error': '数据格式错误'})
            
            if isinstance(first_value, dict):
                print("[Train] 检测到字典格式，转换为数值列表")
                data = {
                    k: [p.get('y', 0) for p in v] if v else []
                    for k, v in data.items()
                }
            print(f"[Train] 转换后的data: {data}")
            
            if not data or all(not v for v in data.values()):
                return jsonify({'success': False, 'error': '数据为空或不足'})
            
            result = train_model(data, config, timestamps)
        
        return jsonify({
            'success': True,
            'results': result['results'],
            'analysis': result['analysis'],
            'config': result['config']
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@eco_bp.route('/save_analysis', methods=['POST'])
@login_required
def save_analysis():
    """保存分析报告"""
    try:
        analysis = request.json.get('analysis', {})
        
        # 确保目录存在
        os.makedirs('data', exist_ok=True)
        
        # 读取现有报告
        reports = []
        if os.path.exists(EXPERIMENTS_FILE):
            with open(EXPERIMENTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
        
        # 添加新报告
        reports.append(analysis)
        
        # 保存
        with open(EXPERIMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'count': len(reports)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@eco_bp.route('/get_reports', methods=['GET'])
def get_reports():
    """获取所有实验报告"""
    try:
        if os.path.exists(EXPERIMENTS_FILE):
            with open(EXPERIMENTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
            return jsonify({'success': True, 'reports': reports})
        return jsonify({'success': True, 'reports': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@eco_bp.route('/export_report', methods=['GET'])
def export_report():
    """导出汇总报告"""
    try:
        if os.path.exists(EXPERIMENTS_FILE):
            with open(EXPERIMENTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
        else:
            reports = []
        
        # 生成汇总报告
        summary = {
            'export_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_experiments': len(reports),
            'experiments': reports
        }
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@eco_bp.route('/export_report_pdf', methods=['GET'])
def export_report_pdf():
    """导出实验报告为 PDF（中小学生友好排版）"""
    try:
        if os.path.exists(EXPERIMENTS_FILE):
            with open(EXPERIMENTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
        else:
            reports = []
        from services.eco_report_pdf import build_experiment_reports_pdf

        pdf_bytes = build_experiment_reports_pdf(reports if isinstance(reports, list) else [])
        from urllib.parse import quote

        fname = f"生态瓶实验报告_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        fname_ascii = f"eco_experiment_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        disp = f'attachment; filename="{fname_ascii}"; filename*=UTF-8\'\'{quote(fname)}'
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': disp},
        )
    except RuntimeError as e:
        return jsonify({'success': False, 'error': str(e)}), 503
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@eco_bp.route('/save_model', methods=['POST'])
def save_model():
    """保存训练好的模型"""
    try:
        data = request.json
        model_name = data.get('model_name', f"model_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        model_data = data.get('model_data', {})
        
        # 确保目录存在
        os.makedirs(MODELS_DIR, exist_ok=True)
        
        # 保存模型
        model_file = os.path.join(MODELS_DIR, f"{model_name}.json")
        with open(model_file, 'w', encoding='utf-8') as f:
            json.dump({
                'name': model_name,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': model_data
            }, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'model_name': model_name})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@eco_bp.route('/get_models', methods=['GET'])
def get_models():
    """获取所有可用的模型列表"""
    try:
        models = []
        
        # 预设模型
        preset_models = [
            {'name': 'prophet', 'display_name': 'Prophet', 'type': 'preset'},
            {'name': 'polynomial', 'display_name': '多项式回归', 'type': 'preset'},
            {'name': 'arima', 'display_name': 'ARIMA', 'type': 'preset'},
            {'name': 'lightgbm', 'display_name': 'LightGBM', 'type': 'preset'}
        ]
        models.extend(preset_models)
        
        # 训练保存的模型
        if os.path.exists(MODELS_DIR):
            for f in os.listdir(MODELS_DIR):
                if f.endswith('.json'):
                    try:
                        with open(os.path.join(MODELS_DIR, f), 'r', encoding='utf-8') as mf:
                            model_info = json.load(mf)
                            models.append({
                                'name': model_info.get('name', f[:-5]),
                                'display_name': model_info.get('name', f[:-5]),
                                'timestamp': model_info.get('timestamp', ''),
                                'type': 'custom'
                            })
                    except:
                        pass
        
        return jsonify({'success': True, 'models': models})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

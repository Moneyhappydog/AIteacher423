"""
闭环控制服务（模拟模式）
基于预测的智能生态瓶控制逻辑
"""
import json
import os
from datetime import datetime
from config import Config

CONTROL_DIR = Config.CONTROL_DIR
CONTROL_LOG_FILE = os.path.join(CONTROL_DIR, 'control_log.json')

# 控制阈值（与需求一致）
ECO_TEMP_MIN = Config.ECO_TEMP_MIN
ECO_TEMP_MAX = Config.ECO_TEMP_MAX
ECO_LIGHT_MIN = Config.ECO_LIGHT_MIN
ECO_LIGHT_MAX = Config.ECO_LIGHT_MAX


def _ensure_dir():
    os.makedirs(CONTROL_DIR, exist_ok=True)


def _load_log() -> dict:
    _ensure_dir()
    if os.path.exists(CONTROL_LOG_FILE):
        try:
            with open(CONTROL_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # 文件损坏或无法读取，直接重置
            pass
    return {"version": "2026-v1", "records": []}


def _save_log(log: dict):
    _ensure_dir()
    tmp_file = CONTROL_LOG_FILE + '.tmp'
    try:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, CONTROL_LOG_FILE)   # 原子替换，规避并发覆盖
    except IOError:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        raise


def calculate_control_action(current_values: dict, strategy: str = 'threshold', thresholds: dict = None) -> dict:
    """
    计算控制动作
    strategy: 'passive'(被动) / 'threshold'(阈值) / 'predictive'(预测)
    thresholds: 可选，键 temp_min/temp_max/light_min/light_max
    """
    t_min = ECO_TEMP_MIN
    t_max = ECO_TEMP_MAX
    l_min = ECO_LIGHT_MIN
    l_max = ECO_LIGHT_MAX
    if thresholds:
        def _v(val, fallback):
            try:
                f = float(val)
                return f if f is not None else fallback
            except (TypeError, ValueError):
                return fallback
        t_min = _v(thresholds.get('temp_min'), t_min)
        t_max = _v(thresholds.get('temp_max'), t_max)
        l_min = _v(thresholds.get('light_min'), l_min)
        l_max = _v(thresholds.get('light_max'), l_max)
    if t_min > t_max:
        t_min, t_max = t_max, t_min
    if l_min > l_max:
        l_min, l_max = l_max, l_min

    temp = current_values.get('temperature', 25.0)
    light = current_values.get('light', 120.0)

    actions = []
    temp_action = None
    light_action = None

    if strategy == 'passive':
        # 被动控制：定时开关
        pass
    elif strategy == 'threshold':
        # 阈值控制
        if temp > t_max:
            temp_action = 'fan_on'
            actions.append({'target': 'fan', 'action': 'on', 'reason': f'温度{temp:.1f}°C > {t_max}°C'})
        elif temp < t_min:
            temp_action = 'heat_on'
            actions.append({'target': 'heater', 'action': 'on', 'reason': f'温度{temp:.1f}°C < {t_min}°C'})
        else:
            actions.append({'target': 'fan', 'action': 'off', 'reason': '温度正常'})
            actions.append({'target': 'heater', 'action': 'off', 'reason': '温度正常'})

        if light < l_min:
            light_action = 'light_on'
            actions.append({'target': 'light', 'action': 'on', 'reason': f'光照{light:.0f}lux < {l_min}lux'})
        elif light > l_max:
            light_action = 'light_off'
            actions.append({'target': 'light', 'action': 'off', 'reason': f'光照{light:.0f}lux > {l_max}lux'})
        else:
            actions.append({'target': 'light', 'action': 'auto', 'reason': '光照正常'})
    else:
        # 预测控制（简化版，基于当前趋势）
        temp_trend = current_values.get('temp_trend', 0)
        light_trend = current_values.get('light_trend', 0)

        if temp + temp_trend * 5 > t_max:
            actions.append({'target': 'fan', 'action': 'preemptive_on', 'reason': '预测温度将过高，提前开风扇'})
            temp_action = 'fan_on'
        elif temp + temp_trend * 5 < t_min:
            actions.append({'target': 'heater', 'action': 'preemptive_on', 'reason': '预测温度将过低，提前加热'})
            temp_action = 'heat_on'

        if light + light_trend * 5 < l_min:
            actions.append({'target': 'light', 'action': 'preemptive_on', 'reason': '预测光照将不足，提前开灯'})
            light_action = 'light_on'

    return {
        'strategy': strategy,
        'timestamp': datetime.now().isoformat(),
        'current_values': current_values,
        'actions': actions,
        'temp_action': temp_action,
        'light_action': light_action
    }


def calculate_control_score(current_values: dict, thresholds: dict = None) -> dict:
    """
    计算控制得分
    温度40% + 光照30% + 节能30%
    thresholds: 可选，覆盖默认 Config 阈值，键 temp_min/temp_max/light_min/light_max
    """
    t_min = ECO_TEMP_MIN
    t_max = ECO_TEMP_MAX
    l_min = ECO_LIGHT_MIN
    l_max = ECO_LIGHT_MAX
    if thresholds:
        def _v(val, fallback):
            try:
                f = float(val)
                return f if f is not None else fallback
            except (TypeError, ValueError):
                return fallback
        t_min = _v(thresholds.get('temp_min'), t_min)
        t_max = _v(thresholds.get('temp_max'), t_max)
        l_min = _v(thresholds.get('light_min'), l_min)
        l_max = _v(thresholds.get('light_max'), l_max)
    if t_min > t_max:
        t_min, t_max = t_max, t_min
    if l_min > l_max:
        l_min, l_max = l_max, l_min

    temp = current_values.get('temperature', 25.0)
    light = current_values.get('light', 120.0)
    solar_power = current_values.get('solar_power', 0.0)
    using_solar = current_values.get('using_solar', False)

    # 温度得分
    if t_min <= temp <= t_max:
        # 在范围内，越接近中点越好
        mid = (t_min + t_max) / 2
        dist = abs(temp - mid)
        max_dist = (t_max - t_min) / 2
        temp_score = 100 * (1 - dist / max_dist) if max_dist > 0 else 100.0
    else:
        temp_score = max(0, 100 - abs(temp - (t_max if temp > t_max else t_min)) * 5)
    temp_score = min(100, max(0, temp_score))

    # 光照得分
    if l_min <= light <= l_max:
        mid = (l_min + l_max) / 2
        dist = abs(light - mid)
        max_dist = (l_max - l_min) / 2
        light_score = 100 * (1 - dist / max_dist) if max_dist > 0 else 100.0
    else:
        light_score = max(0, 100 - abs(light - (l_max if light > l_max else l_min)) * 0.2)
    light_score = min(100, max(0, light_score))

    # 节能得分
    if using_solar:
        energy_score = 100.0
    else:
        energy_score = 30.0  # 使用非太阳能得分较低

    # 综合得分
    composite = temp_score * 0.4 + light_score * 0.3 + energy_score * 0.3

    return {
        'temp_score': round(temp_score, 2),
        'light_score': round(light_score, 2),
        'energy_score': round(energy_score, 2),
        'composite_score': round(composite, 2),
        'temp_status': '正常' if t_min <= temp <= t_max else ('过高' if temp > t_max else '过低'),
        'light_status': '正常' if l_min <= light <= l_max else ('过强' if light > l_max else '不足')
    }


def log_control_action(group_id: str, action_record: dict):
    """记录控制动作"""
    log = _load_log()
    if 'records' not in log:
        log['records'] = []
    action_record['group_id'] = group_id
    log['records'].append(action_record)
    # 只保留最近1000条
    if len(log['records']) > 1000:
        log['records'] = log['records'][-1000:]
    _save_log(log)


def get_control_log(group_id: str = None) -> list:
    """获取控制日志"""
    log = _load_log()
    records = log.get('records', [])
    if group_id:
        records = [r for r in records if r.get('group_id') == group_id]
    return records[-100:]

"""
传感器数据服务（模拟模式）
处理生态瓶传感器数据的采集、存储、探索分析
"""
import json
import os
import csv
import io
from datetime import datetime
from config import Config

SENSOR_DATA_DIR = Config.SENSOR_DATA_DIR
SENSOR_RAW_DIR = os.path.join(SENSOR_DATA_DIR, 'raw')
SENSOR_PROCESSED_DIR = os.path.join(SENSOR_DATA_DIR, 'processed')
META_FILE = os.path.join(SENSOR_DATA_DIR, 'meta.json')

# 传感器通道定义（带合理范围）
SENSOR_CHANNELS = {
    'temperature': {'name': '温度', 'unit': '°C', 'icon': '🌡️',
                     'min': -10, 'max': 60, 'optimal_min': 22, 'optimal_max': 28},
    'humidity': {'name': '湿度', 'unit': '%', 'icon': '💧',
                  'min': 0, 'max': 100, 'optimal_min': 40, 'optimal_max': 80},
    'light': {'name': '光照', 'unit': 'lux', 'icon': '☀️',
              'min': 0, 'max': 2000, 'optimal_min': 100, 'optimal_max': 500},
    'oxygen': {'name': '氧气', 'unit': '%', 'icon': '🌬️',
               'min': 0, 'max': 30, 'optimal_min': 18, 'optimal_max': 25},
    'solar_power': {'name': '发电量', 'unit': 'mW', 'icon': '🔋',
                     'min': 0, 'max': 500, 'optimal_min': 0, 'optimal_max': 500}
}


def _ensure_dirs():
    """确保目录存在"""
    os.makedirs(SENSOR_RAW_DIR, exist_ok=True)
    os.makedirs(SENSOR_PROCESSED_DIR, exist_ok=True)


def _load_meta():
    """加载元数据"""
    if os.path.exists(META_FILE):
        with open(META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "version": "2026-v1",
        "updated_at": datetime.now().isoformat(),
        "channels": list(SENSOR_CHANNELS.keys()),
        "last_updated": None
    }


def _save_meta(meta):
    """保存元数据"""
    meta["last_updated"] = datetime.now().isoformat()
    with open(META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _get_group_file(group_id: str) -> str:
    """获取小组数据文件路径"""
    date_str = datetime.now().strftime('%Y%m%d')
    return os.path.join(SENSOR_RAW_DIR, f'{group_id}_{date_str}.json')


def add_sensor_record(group_id: str, group_name: str = None,
                       temperature: float = None, humidity: float = None,
                       light: float = None, oxygen: float = None,
                       solar_power: float = None, timestamp: str = None) -> dict:
    """
    添加一条传感器数据记录（模拟模式）
    """
    _ensure_dirs()
    file_path = _get_group_file(group_id)

    # 读取或创建数据
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {
            "group_id": group_id,
            "group_name": group_name or f'第{group_id.replace("G","")}组',
            "device_id": f"ESP32_{group_id}",
            "records": []
        }

    # 构建记录（CSV 导入时可带 timestamp，缺省则用当前时间）
    ts = (timestamp or '').strip()
    if not ts:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    record = {
        "timestamp": ts,
        "temperature": temperature if temperature is not None else 25.0,
        "humidity": humidity if humidity is not None else 65.0,
        "light": light if light is not None else 120.0,
        "oxygen": oxygen if oxygen is not None else 20.5,
        "solar_power": solar_power if solar_power is not None else 0.0,
        "status": "normal"
    }

    # 判断状态
    for ch, info in SENSOR_CHANNELS.items():
        val = record[ch]
        if val < info['min'] or val > info['max']:
            record['status'] = 'abnormal'
            break

    data['records'].append(record)

    # 保存
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return record


def batch_add_records(group_id: str, records: list) -> dict:
    """批量添加记录"""
    _ensure_dirs()
    added = 0
    for rec in records:
        add_sensor_record(
            group_id=group_id,
            group_name=rec.get('group_name'),
            temperature=rec.get('temperature'),
            humidity=rec.get('humidity'),
            light=rec.get('light'),
            oxygen=rec.get('oxygen'),
            solar_power=rec.get('solar_power'),
            timestamp=rec.get('timestamp')
        )
        added += 1
    return {"added": added}


def get_group_history(group_id: str, date: str = None) -> dict:
    """获取小组历史数据"""
    if date:
        file_path = os.path.join(SENSOR_RAW_DIR, f'{group_id}_{date}.json')
    else:
        file_path = _get_group_file(group_id)

    if not os.path.exists(file_path):
        return {"group_id": group_id, "records": []}

    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def delete_record(group_id: str, timestamp: str) -> dict:
    """
    根据时间戳删除单条记录
    """
    file_path = _get_group_file(group_id)
    if not os.path.exists(file_path):
        return {"error": "文件不存在"}

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = data.get('records', [])
    original_count = len(records)
    records = [r for r in records if r.get('timestamp') != timestamp]
    deleted = original_count - len(records)

    if deleted == 0:
        return {"error": "未找到该记录"}

    data['records'] = records
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"deleted": deleted}


def import_csv(group_id: str, csv_content: str) -> dict:
    """
    从CSV导入传感器数据
    CSV格式：timestamp,temperature,humidity,light,oxygen,solar_power
    """
    _ensure_dirs()

    csv_content = csv_content.lstrip('\ufeff')
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        return {'error': 'CSV内容为空或格式不正确'}

    reader = csv.DictReader(io.StringIO(csv_content))
    added = 0
    for row in reader:
        try:
            add_sensor_record(
                group_id=group_id,
                temperature=float(row.get('temperature', 25.0)),
                humidity=float(row.get('humidity', 65.0)),
                light=float(row.get('light', 120.0)),
                oxygen=float(row.get('oxygen', 20.5)),
                solar_power=float(row.get('solar_power', 0.0)),
                timestamp=row.get('timestamp') or None
            )
            added += 1
        except (ValueError, KeyError) as e:
            continue

    return {"imported": added}


def export_csv(group_id: str) -> str:
    """导出小组数据为CSV"""
    data = get_group_history(group_id)
    records = data.get('records', [])

    if not records:
        return ""

    output = io.StringIO()
    fieldnames = ['timestamp', 'temperature', 'humidity', 'light', 'oxygen', 'solar_power']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for rec in records:
        writer.writerow({k: rec.get(k, '') for k in fieldnames})

    return output.getvalue()


def explore_analysis(group_id: str) -> dict:
    """
    数据探索分析：相关性、趋势、滞后效应
    """
    data = get_group_history(group_id)
    records = data.get('records', [])

    if len(records) < 5:
        return {
            'error': '数据量不足，请先采集至少5条数据',
            'records_count': len(records)
        }

    import numpy as np

    # 提取数值序列
    temps = [r['temperature'] for r in records]
    lights = [r['light'] for r in records]
    humids = [r['humidity'] for r in records]
    oxygens = [r['oxygen'] for r in records]
    powers = [r['solar_power'] for r in records]

    def pearson_corr(x, y):
        if len(x) < 2:
            return 0.0
        x = np.array(x)
        y = np.array(y)
        if np.std(x) == 0 or np.std(y) == 0:
            return 0.0
        return float(np.corrcoef(x, y)[0, 1])

    # 相关性分析
    corr_light_temp = pearson_corr(lights, temps)
    corr_light_power = pearson_corr(lights, powers)
    corr_humid_temp = pearson_corr(humids, temps)

    # 相关性强度判断
    def corr_strength(r):
        r = abs(r)
        if r >= 0.7:
            return '强正相关' if r >= 0 else '强负相关'
        elif r >= 0.4:
            return '中等正相关' if r >= 0 else '中等负相关'
        elif r >= 0.2:
            return '弱正相关' if r >= 0 else '弱负相关'
        else:
            return '几乎无关'

    # 滞后效应分析（简化版）
    lag_effect = []
    if len(lights) >= 10:
        for lag in [1, 2, 3]:
            lagged_corr = pearson_corr(lights[:-lag], temps[lag:])
            if abs(lagged_corr) > abs(corr_light_temp) * 0.8:
                lag_effect.append({
                    'lag': lag,
                    'correlation': round(lagged_corr, 3),
                    'description': f'光照变化后约{lag}分钟，温度滞后响应'
                })

    # 趋势分析
    def trend_analysis(values, name):
        if len(values) < 2:
            return {'trend': '数据不足', 'amplitude': 0}
        values = np.array(values)
        mean_val = np.mean(values)
        amplitude = np.max(values) - np.min(values)
        slope = (values[-1] - values[0]) / (len(values) - 1)
        if slope > 0.1:
            trend = f'{name}呈上升趋势'
        elif slope < -0.1:
            trend = f'{name}呈下降趋势'
        else:
            trend = f'{name}基本平稳'
        return {
            'trend': trend,
            'mean': round(float(mean_val), 2),
            'amplitude': round(float(amplitude), 2),
            'min': round(float(np.min(values)), 2),
            'max': round(float(np.max(values)), 2)
        }

    return {
        'records_count': len(records),
        'time_range': {
            'start': records[0]['timestamp'] if records else None,
            'end': records[-1]['timestamp'] if records else None
        },
        'correlation': {
            'light_temp': {
                'value': round(corr_light_temp, 3),
                'strength': corr_strength(corr_light_temp)
            },
            'light_power': {
                'value': round(corr_light_power, 3),
                'strength': corr_strength(corr_light_power)
            },
            'humid_temp': {
                'value': round(corr_humid_temp, 3),
                'strength': corr_strength(corr_humid_temp)
            }
        },
        'lag_effect': lag_effect,
        'trends': {
            'temperature': trend_analysis(temps, '温度'),
            'light': trend_analysis(lights, '光照'),
            'humidity': trend_analysis(humids, '湿度'),
            'oxygen': trend_analysis(oxygens, '氧气'),
            'solar_power': trend_analysis(powers, '发电量')
        }
    }


def get_class_stats() -> dict:
    """获取全班数据统计"""
    _ensure_dirs()
    groups = {}
    for f in os.listdir(SENSOR_RAW_DIR):
        if f.endswith('.json'):
            group_id = f.split('_')[0]
            path = os.path.join(SENSOR_RAW_DIR, f)
            with open(path, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                records = data.get('records', [])
                groups[group_id] = {
                    'group_name': data.get('group_name', group_id),
                    'records_count': len(records),
                    'latest': records[-1]['timestamp'] if records else None
                }
    return groups


def clear_group_data(group_id: str) -> dict:
    """清空小组数据（删除 raw 目录下该组所有日期 JSON）"""
    _ensure_dirs()
    deleted = 0
    for f in os.listdir(SENSOR_RAW_DIR):
        if f.startswith(group_id + '_'):
            os.remove(os.path.join(SENSOR_RAW_DIR, f))
            deleted += 1
    return {"deleted_files": deleted}

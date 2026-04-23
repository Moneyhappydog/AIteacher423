"""
Time-series prediction service.
Uses polynomial trend regression + confidence intervals, similar in spirit to Prophet.
Falls back gracefully to linear regression for very few data points.
Predictions are clamped to physically realistic bounds per variable type.
"""
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 各变量在现实中的合理取值范围（预测值与置信区间均会裁剪到此范围）
VARIABLE_BOUNDS = {
    "temperature":  (-50, 60),    # °C
    "humidity":     (0, 100),    # %
    "light":        (0, 100000),  # lux
    "oxygen":       (0, 30),    # %
    "solar_power":  (0, 500),    # mW
}


def _get_bounds(variable_name: str) -> tuple:
    """根据变量名返回 (最小值, 最大值)，未配置则返回 (None, None) 表示不裁剪。"""
    lo, hi = VARIABLE_BOUNDS.get(variable_name, (None, None))
    return (lo, hi)


def predict_series(data_points: list, variable_name: str, periods: int = 12) -> dict:
    """
    Fit a trend model on data_points and return forecast.
    data_points: list of {"ds": "YYYY-MM-DD HH:MM:SS", "y": float}
    """
    if len(data_points) < 2:
        return {"error": f"{variable_name} 至少需要 2 个数据点才能进行预测"}

    try:
        df = pd.DataFrame(data_points)
        df['ds'] = pd.to_datetime(df['ds'])
        df['y'] = pd.to_numeric(df['y'])
        df = df.sort_values('ds').reset_index(drop=True)

        t0 = df['ds'].iloc[0]
        df['t'] = (df['ds'] - t0).dt.total_seconds()

        if len(df) >= 2:
            avg_step = df['t'].diff().dropna().mean()
        else:
            avg_step = 3600  # 1 hour default

        n = len(df)
        deg = min(2, n - 1)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            coeffs = np.polyfit(df['t'].values, df['y'].values, deg)

        poly_fn = np.poly1d(coeffs)
        y_fitted = poly_fn(df['t'].values)

        residuals = df['y'].values - y_fitted
        sigma = float(np.std(residuals)) if len(residuals) > 1 else 0.05 * (df['y'].max() - df['y'].min() + 1)

        t_last = df['t'].iloc[-1]
        future_t = [t_last + avg_step * (i + 1) for i in range(periods)]
        future_ds = [df['ds'].iloc[-1] + timedelta(seconds=avg_step * (i + 1)) for i in range(periods)]

        all_t  = np.concatenate([df['t'].values, future_t])
        all_ds = list(df['ds']) + future_ds
        all_y  = poly_fn(all_t)

        conf_mult = np.ones(len(all_t))
        conf_mult[n:] = [1.5 + 0.1 * i for i in range(periods)]

        upper = all_y + 1.96 * sigma * conf_mult
        lower = all_y - 1.96 * sigma * conf_mult

        # 按变量类型裁剪到现实合理范围
        lo, hi = _get_bounds(variable_name)
        if lo is not None and hi is not None:
            all_y  = np.clip(all_y,  lo, hi)
            upper  = np.clip(upper,  lo, hi)
            lower  = np.clip(lower,  lo, hi)

        def fmt_label(ts):
            if isinstance(ts, pd.Timestamp):
                return ts.strftime('%m/%d %H:%M')
            return str(ts)

        hist_labels = [fmt_label(df['ds'].iloc[i]) for i in range(n)]
        hist_values = df['y'].tolist()
        fc_labels   = [fmt_label(d) for d in all_ds]
        fc_values   = [round(float(v), 2) for v in all_y]
        fc_upper    = [round(float(v), 2) for v in upper]
        fc_lower    = [round(float(v), 2) for v in lower]

        return {
            "variable":    variable_name,
            "hist_labels": hist_labels,
            "hist_values": hist_values,
            "fc_labels":   fc_labels,
            "fc_values":   fc_values,
            "fc_upper":    fc_upper,
            "fc_lower":    fc_lower,
            "split_idx":   n,
            "trend":       _analyze_trend(fc_values[n:], variable_name)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"预测失败: {str(e)}"}


def predict_all(
    light_points:   list,
    temp_points:    list,
    humid_points:   list,
    oxygen_points: list,
    solar_points:  list
) -> dict:
    results = {}

    if light_points:
        results['light'] = predict_series(light_points, 'light')
    else:
        results['light'] = {'error': '无光照数据'}

    if temp_points:
        results['temperature'] = predict_series(temp_points, 'temperature')
    else:
        results['temperature'] = {'error': '无温度数据'}

    if humid_points:
        results['humidity'] = predict_series(humid_points, 'humidity')
    else:
        results['humidity'] = {'error': '无湿度数据'}

    if oxygen_points:
        results['oxygen'] = predict_series(oxygen_points, 'oxygen')
    else:
        results['oxygen'] = {'error': '无氧气数据'}

    if solar_points:
        results['solar_power'] = predict_series(solar_points, 'solar_power')
    else:
        results['solar_power'] = {'error': '无发电数据'}

    return results


_VARIABLE_LABELS = {
    'temperature':  '温度',
    'humidity':     '湿度',
    'light':        '光照',
    'oxygen':       '氧气',
    'solar_power':  '发电',
}


def _analyze_trend(forecast_values: list, variable_name: str) -> str:
    if not forecast_values or len(forecast_values) < 2:
        return f"{variable_name} 数据不足，无法分析趋势。"

    first = forecast_values[0]
    last  = forecast_values[-1]
    change = last - first
    pct = (change / first * 100) if first != 0 else 0

    label = _VARIABLE_LABELS.get(variable_name, variable_name)

    if abs(pct) < 5:
        trend_word = "保持稳定"
        advice_map = {
            'temperature':  '温度变化稳定，生态环境良好。',
            'humidity':     '湿度变化不大，生态瓶处于平衡状态。',
            'light':        '光照变化不大，生态瓶处于平衡状态。',
            'oxygen':       '氧气含量稳定，水体生态良好。',
            'solar_power':  '发电量变化稳定，太阳能供电正常。',
        }
    elif change > 0:
        trend_word = "呈上升趋势"
        advice_map = {
            'temperature':  '温度升高，注意给生态瓶降温，避免影响生物生存。',
            'humidity':     '湿度上升，注意通风避免过度潮湿。',
            'light':        '光照增强，植物光合作用会更旺盛！',
            'oxygen':       '氧气上升，水体溶氧状况改善！',
            'solar_power':  '发电量上升，太阳能充电效率良好！',
        }
    else:
        trend_word = "呈下降趋势"
        advice_map = {
            'temperature':  '温度下降，注意保温，维持生态平衡。',
            'humidity':     '湿度下降，可适当补充水分。',
            'light':        '光照减弱，植物光合作用可能放缓。',
            'oxygen':       '氧气下降，注意水体溶氧情况。',
            'solar_power':  '发电量下降，可能是光照不足导致。',
        }

    advice = advice_map.get(variable_name, '请关注该指标的变化趋势。')
    return f"未来预测：{label}{trend_word}。{advice}"

"""
传感器数据路由（模拟模式）
"""
from flask import Blueprint, request, jsonify, Response
from services.sensor_service import (
    add_sensor_record,
    batch_add_records,
    get_group_history,
    import_csv,
    export_csv,
    explore_analysis,
    get_class_stats,
    clear_group_data,
    delete_record,
    SENSOR_CHANNELS
)

# 导入登录验证装饰器
from routes.auth import login_required

sensor_data_bp = Blueprint('sensor_data', __name__, url_prefix='/sensor')


@sensor_data_bp.route('/')
@login_required
def index():
    """传感器采集页面"""
    from flask import render_template
    return render_template('sensor_collect.html')


@sensor_data_bp.route('/channels', methods=['GET'])
@login_required
def channels():
    """获取传感器通道定义"""
    return jsonify(SENSOR_CHANNELS)


@sensor_data_bp.route('/add', methods=['POST'])
@login_required
def add_record():
    """添加单条传感器记录"""
    from flask import session
    data = request.json
    # 从 session 获取小组信息，不允许伪造
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')
    group_name = session.get('group_name', session.get('username', '匿名小组'))

    record = add_sensor_record(
        group_id=group_id,
        group_name=group_name,
        temperature=data.get('temperature'),
        humidity=data.get('humidity'),
        light=data.get('light'),
        oxygen=data.get('oxygen'),
        solar_power=data.get('solar_power')
    )
    return jsonify(record)


@sensor_data_bp.route('/batch_add', methods=['POST'])
@login_required
def batch_add():
    """批量添加记录"""
    from flask import session
    data = request.json
    user_id = session.get('user_id')
    group_id = session.get('group_id', f'G{user_id:03d}' if user_id else 'G01')

    result = batch_add_records(
        group_id=group_id,
        records=data.get('records', [])
    )
    return jsonify(result)


@sensor_data_bp.route('/history/<group_id>', methods=['GET'])
@login_required
def history(group_id):
    """获取小组历史数据"""
    date = request.args.get('date')
    data = get_group_history(group_id, date)
    return jsonify(data)


@sensor_data_bp.route('/history', methods=['GET'])
def history_default():
    """获取小组历史数据（默认G01）"""
    group_id = request.args.get('group_id', 'G01')
    return history(group_id)


@sensor_data_bp.route('/upload', methods=['POST'])
@login_required
def upload_csv():
    """上传CSV文件导入传感器数据"""
    if 'file' not in request.files:
        # 尝试从JSON body获取
        data = request.json
        if data and 'csv_content' in data:
            group_id = data.get('group_id', 'G01')
            result = import_csv(group_id, data['csv_content'])
            return jsonify(result)
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    group_id = request.form.get('group_id', 'G01')

    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    csv_content = file.read().decode('utf-8')
    result = import_csv(group_id, csv_content)
    return jsonify(result)


@sensor_data_bp.route('/export/<group_id>', methods=['GET'])
def export(group_id):
    """导出CSV"""
    csv_data = export_csv(group_id)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={group_id}_sensor_data.csv'
        }
    )


@sensor_data_bp.route('/explore', methods=['POST'])
def explore():
    """数据探索分析"""
    data = request.json
    result = explore_analysis(data.get('group_id', 'G01'))
    return jsonify(result)


@sensor_data_bp.route('/explore/<group_id>', methods=['GET'])
def explore_group(group_id):
    """数据探索分析"""
    result = explore_analysis(group_id)
    return jsonify(result)


@sensor_data_bp.route('/class_stats', methods=['GET'])
def class_stats():
    """获取全班数据统计"""
    stats = get_class_stats()
    return jsonify(stats)


@sensor_data_bp.route('/clear/<group_id>', methods=['POST'])
def clear(group_id):
    """清空小组数据"""
    result = clear_group_data(group_id)
    return jsonify(result)


@sensor_data_bp.route('/delete_record/<group_id>/<path:timestamp>', methods=['POST'])
def delete_record_route(group_id, timestamp):
    """删除单条记录"""
    result = delete_record(group_id, timestamp)
    return jsonify(result)

"""
排行榜服务
刷榜系统：表情识别、声音识别、多模态融合、生态瓶预测等各模块排行榜
"""
import json
import os
from datetime import datetime
from config import Config

LEADERBOARD_DIR = Config.LEADERBOARD_DIR

# 排行榜文件映射
LEADERBOARD_FILES = {
    'emotion_face': 'emotion_face.json',
    'emotion_audio': 'emotion_audio.json',
    'emotion_fusion': 'emotion_fusion.json',
    'eco_collect': 'eco_collect.json',
    'eco_discovery': 'eco_discovery.json',
    'eco_prediction': 'eco_prediction.json',
    'eco_control': 'eco_control.json',
    # 模型评估榜单（确保隔离）
    'face_eval': 'face_eval.json',
    'audio_eval': 'audio_eval.json',
}


def _get_board_path(course: str) -> str:
    """获取排行榜文件路径"""
    filename = LEADERBOARD_FILES.get(course, f'{course}.json')
    return os.path.join(LEADERBOARD_DIR, filename)


def _load_board(course: str) -> dict:
    """加载排行榜数据"""
    path = _get_board_path(course)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 确保 course 字段正确
            data['course'] = course
            return data
    return {
        "version": "2026-v1",
        "course": course,  # 确保返回正确的 course
        "updated_at": datetime.now().isoformat(),
        "records": [],
        "test_set_size": 50,
        "last_updated_by": None
    }


def _save_board(course: str, board: dict):
    """保存排行榜数据"""
    path = _get_board_path(course)
    board["updated_at"] = datetime.now().isoformat()
    # 确保 course 字段正确，防止数据写入错误的文件
    board["course"] = course
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(board, f, ensure_ascii=False, indent=2)


def get_leaderboard(course: str) -> dict:
    """获取指定课程排行榜"""
    return _load_board(course)


def get_all_leaderboards() -> dict:
    """获取所有排行榜概览"""
    result = {}
    for course in LEADERBOARD_FILES.keys():
        board = _load_board(course)
        records = board.get('records', [])
        # 只返回前3名摘要
        top3 = sorted(records, key=lambda x: x.get('rank', 99))[:3]
        result[course] = {
            'total_records': len(records),
            'top3': top3,
            'updated_at': board.get('updated_at')
        }
    return result


def submit_score(course: str, group_id: str, group_name: str,
                 accuracy: float, correct: int, total: int,
                 time_cost_minutes: int, config: dict = None,
                 innovation_score: int = None,
                 awards: list = None) -> dict:
    """
    提交刷榜成绩
    返回更新后的排名信息
    """
    board = _load_board(course)

    # 计算综合得分
    # 综合得分 = 准确率得分×50% + 效率得分×20% + 创新得分×30%
    records = board.get('records', [])
    max_accuracy = max([r.get('accuracy', 0) for r in records], default=0)

    if max_accuracy > 0:
        accuracy_score = (accuracy / max_accuracy) * 100
    else:
        accuracy_score = 100.0

    # 效率得分 = (基准30分钟 / 实际用时) × 100，上限100
    baseline_minutes = 30
    efficiency_score = min(100.0, (baseline_minutes / max(time_cost_minutes, 1)) * 100)

    # 创新得分（默认70）
    innov_score = innovation_score if innovation_score is not None else 70

    composite_score = accuracy_score * 0.5 + efficiency_score * 0.2 + innov_score * 0.3

    # 构建新记录
    new_record = {
        'group_id': group_id,
        'group_name': group_name,
        'accuracy': round(accuracy, 4),
        'correct': correct,
        'total': total,
        'time_cost_minutes': time_cost_minutes,
        'config': config or {},
        'innovation_score': innov_score,
        'accuracy_score': round(accuracy_score, 2),
        'efficiency_score': round(efficiency_score, 2),
        'composite_score': round(composite_score, 2),
        'awards': awards or [],
        'timestamp': datetime.now().isoformat()
    }

    # 更新已有记录或新增
    updated = False
    for i, rec in enumerate(records):
        if rec.get('group_id') == group_id and rec.get('accuracy', 0) < accuracy:
            records[i] = new_record
            updated = True
            break

    if not updated:
        records.append(new_record)

    # 重新排名
    records.sort(key=lambda x: (x.get('composite_score', 0), x.get('accuracy', 0)), reverse=True)
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    # 保存
    board['records'] = records
    board['last_updated_by'] = group_id
    _save_board(course, board)

    # ── WebSocket 实时推送 ──────────────────────────────────────────────────────
    try:
        from services.websocket_service import broadcast_leaderboard_update
        broadcast_leaderboard_update(course, board)
    except Exception:
        pass  # WebSocket 未初始化时静默跳过

    # 返回本次提交的排名
    my_record = next((r for r in records if r['group_id'] == group_id), new_record)

    return {
        'rank': my_record['rank'],
        'accuracy_score': my_record.get('accuracy_score'),
        'efficiency_score': my_record.get('efficiency_score'),
        'composite_score': my_record.get('composite_score'),
        'total_teams': len(records),
        'is_new_record': updated or len(records) == 1
    }


def get_group_record(course: str, group_id: str) -> dict:
    """获取指定小组在排行榜上的记录"""
    board = _load_board(course)
    records = board.get('records', [])
    for rec in records:
        if rec.get('group_id') == group_id:
            return rec
    return {}


def get_class_stats(course: str = None) -> dict:
    """获取班级数据统计"""
    if course:
        board = _load_board(course)
        records = board.get('records', [])
        if not records:
            return {'total_teams': 0, 'avg_accuracy': 0, 'top_accuracy': 0}
        accuracies = [r.get('accuracy', 0) for r in records]
        return {
            'total_teams': len(records),
            'avg_accuracy': round(sum(accuracies) / len(accuracies), 4),
            'top_accuracy': max(accuracies),
            'test_set_size': board.get('test_set_size', 50)
        }
    else:
        # 所有课程汇总
        all_stats = {}
        for c in LEADERBOARD_FILES.keys():
            all_stats[c] = get_class_stats(c)
        return all_stats


def eco_submit_score(group_id: str, group_name: str,
                     mae_temperature: float, mae_light: float, mae_battery: float,
                     training_time_seconds: int, config: dict = None) -> dict:
    """
    生态瓶预测榜单提交（使用MAE作为评分标准，越低越好）
    """
    course = 'eco_prediction'
    board = _load_board(course)
    records = board.get('records', [])

    avg_mae = round((mae_temperature + mae_light + mae_battery) / 3, 4)

    # 转换策略：MAE越低得分越高
    # 先找最大MAE
    max_mae = max([r.get('avg_mae', avg_mae) for r in records], default=avg_mae)

    if max_mae > 0:
        mae_score = ((max_mae - avg_mae) / max_mae) * 100 + 50
    else:
        mae_score = 100.0

    # 效率分（基准60秒）
    efficiency_score = min(100.0, (60 / max(training_time_seconds, 1)) * 100)
    composite_score = mae_score * 0.7 + efficiency_score * 0.3

    new_record = {
        'group_id': group_id,
        'group_name': group_name,
        'mae_temperature': round(mae_temperature, 2),
        'mae_light': round(mae_light, 2),
        'mae_battery': round(mae_battery, 2),
        'avg_mae': avg_mae,
        'training_time_seconds': training_time_seconds,
        'mae_score': round(mae_score, 2),
        'efficiency_score': round(efficiency_score, 2),
        'composite_score': round(composite_score, 2),
        'config': config or {},
        'timestamp': datetime.now().isoformat()
    }

    updated = False
    for i, rec in enumerate(records):
        if rec.get('group_id') == group_id and rec.get('avg_mae', 999) > avg_mae:
            records[i] = new_record
            updated = True
            break

    if not updated:
        records.append(new_record)

    records.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    board['records'] = records
    board['last_updated_by'] = group_id
    _save_board(course, board)

    try:
        from services.websocket_service import broadcast_leaderboard_update
        broadcast_leaderboard_update(course, board)
    except Exception:
        pass

    my_record = next((r for r in records if r['group_id'] == group_id), new_record)

    return {
        'rank': my_record.get('rank', len(records)),
        'avg_mae': avg_mae,
        'composite_score': my_record.get('composite_score'),
        'total_teams': len(records),
        'is_new_record': updated or len(records) == 1
    }


def eco_control_submit(group_id: str, group_name: str,
                       temp_score: float, light_score: float, energy_score: float,
                       total_seconds: int, strategy: str = 'threshold') -> dict:
    """
    生态瓶综合控制榜提交
    评分：温度40% + 光照30% + 节能30%
    """
    course = 'eco_control'
    board = _load_board(course)
    records = board.get('records', [])

    composite_score = temp_score * 0.4 + light_score * 0.3 + energy_score * 0.3

    new_record = {
        'rank': 0,
        'group_id': group_id,
        'group_name': group_name,
        'temp_score': round(temp_score, 2),
        'light_score': round(light_score, 2),
        'energy_score': round(energy_score, 2),
        'composite_score': round(composite_score, 2),
        'total_seconds': total_seconds,
        'strategy': strategy,
        'timestamp': datetime.now().isoformat()
    }

    updated = False
    for i, rec in enumerate(records):
        if rec.get('group_id') == group_id and rec.get('composite_score', 0) < composite_score:
            records[i] = new_record
            updated = True
            break

    if not updated:
        records.append(new_record)

    records.sort(key=lambda x: x.get('composite_score', 0), reverse=True)
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    board['records'] = records
    board['last_updated_by'] = group_id
    _save_board(course, board)

    try:
        from services.websocket_service import broadcast_leaderboard_update
        broadcast_leaderboard_update(course, board)
    except Exception:
        pass

    my_record = next((r for r in records if r['group_id'] == group_id), new_record)

    return {
        'rank': my_record.get('rank', len(records)),
        'composite_score': composite_score,
        'total_teams': len(records),
        'is_new_record': updated or len(records) == 1
    }


def submit_eval_score(course: str, group_id: str, group_name: str,
                      model_id: str, model_name: str,
                      accuracy: float, testset_id: str = None,
                      metrics: dict = None) -> dict:
    """
    提交模型评估结果到排行榜
    用于模型评估榜单：face_eval, audio_eval
    评分：准确率即分数，无需额外计算

    注意：排行榜之间完全隔离，每个 course 类型有独立的排行榜文件
    不会互相影响，确保表情识别和声音情绪的评估结果分开存储
    """
    # 确定 leaderboard_type
    # course 可能是 'face', 'audio' 或已经是 'face_eval', 'audio_eval'
    if course.endswith('_eval'):
        leaderboard_type = course
    else:
        leaderboard_type = f'{course}_eval'

    # 确保排行榜文件映射存在（防御性编程）
    if leaderboard_type not in LEADERBOARD_FILES:
        LEADERBOARD_FILES[leaderboard_type] = f'{leaderboard_type}.json'

    board = _load_board(leaderboard_type)
    records = board.get('records', [])

    # 构建新记录
    new_record = {
        'group_id': group_id,
        'group_name': group_name,
        'model_id': model_id,
        'model_name': model_name,
        'accuracy': round(accuracy, 4),
        'testset_id': testset_id,
        'course_type': leaderboard_type,  # 标记榜单类型，用于隔离
        'timestamp': datetime.now().isoformat()
    }

    # 如果有详细指标
    if metrics:
        new_record['precision'] = round(metrics.get('precision', 0), 4)
        new_record['recall'] = round(metrics.get('recall', 0), 4)
        new_record['f1_score'] = round(metrics.get('f1_score', 0), 4)

    # 更新已有记录或新增
    # 重要：每个小组只保留准确率最高的那条记录
    updated = False
    found = False
    for i, rec in enumerate(records):
        if rec.get('group_id') == group_id:
            found = True
            # 只有当新分数更高时才更新（保留最佳模型）
            if rec.get('accuracy', 0) < accuracy:
                records[i] = new_record
                updated = True
            break

    # 只有在没找到该小组记录时才新增
    if not found:
        records.append(new_record)

    # 按准确率降序排列
    records.sort(key=lambda x: x.get('accuracy', 0), reverse=True)
    for i, rec in enumerate(records):
        rec['rank'] = i + 1

    board['records'] = records
    board['last_updated_by'] = group_id
    _save_board(leaderboard_type, board)

    # WebSocket 推送
    try:
        from services.websocket_service import broadcast_leaderboard_update
        broadcast_leaderboard_update(leaderboard_type, board)
    except Exception:
        pass

    my_record = next((r for r in records if r.get('group_id') == group_id), new_record)

    return {
        'rank': my_record.get('rank', len(records)),
        'accuracy': accuracy,
        'total_teams': len(records),
        'is_new_record': updated or (not found and len(records) == 1)
    }


def get_leaderboard_service():
    """获取排行榜服务实例（兼容 model_eval 调用）"""
    class LeaderboardServiceWrapper:
        def get_leaderboard(self, course: str) -> dict:
            return _load_board(course)

        def get_all_leaderboards(self) -> dict:
            result = {}
            for c in LEADERBOARD_FILES.keys():
                result[c] = _load_board(c)
            return result

    return LeaderboardServiceWrapper()

"""
routes/admin.py — 管理员控制台路由

超级管理员和教师的管理后台。
权限设计：
- 超级管理员：可对所有用户（教师、小组）进行增删改查
- 教师：只能对小组账号进行增删改查，不能管理其他教师
"""

from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


class SkipRow(Exception):
    """用于跳过当前CSV行（不记录为错误，只记录为跳过）"""
    pass


# ──────────────────────────────────────────────────────────────────────────────
# 权限装饰器
# ──────────────────────────────────────────────────────────────────────────────

def admin_or_teacher_required(f):
    """要求用户是超级管理员或教师"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login_page'))
        if session.get('role') not in ('super_admin', 'teacher'):
            return jsonify({'error': '权限不足，仅管理员或教师可访问'}), 403
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """要求用户是超级管理员"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login_page'))
        if session.get('role') != 'super_admin':
            return jsonify({'error': '权限不足，仅超级管理员可访问'}), 403
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────────────────────────────────────
# 页面路由
# ──────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@admin_or_teacher_required
def dashboard():
    """管理员控制台主页"""
    from models import db, User, Group, LeaderboardRecord, AuditLog

    # 统计信息
    total_users = User.query.count()
    total_groups = Group.query.count()
    total_teachers = User.query.filter_by(role='teacher').count()
    total_submissions = LeaderboardRecord.query.count()

    # 最新审计日志
    recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_groups=total_groups,
                           total_teachers=total_teachers,
                           total_submissions=total_submissions,
                           recent_logs=recent_logs)


@admin_bp.route('/user/create')
@admin_or_teacher_required
def create_user_page():
    """创建用户页面"""
    # 教师只能创建小组账号
    if session.get('role') == 'teacher':
        available_roles = ['group']
    else:
        available_roles = ['teacher', 'group']

    return render_template('admin/user_form.html',
                           user=None,
                           available_roles=available_roles,
                           is_edit=False)


@admin_bp.route('/user/edit/<int:user_id>')
@admin_or_teacher_required
def edit_user_page(user_id):
    """编辑用户页面"""
    from models import User, Group

    user = User.query.get_or_404(user_id)

    # 权限检查
    current_role = session.get('role')
    if current_role == 'teacher':
        if user.role != 'group':
            return jsonify({'error': '权限不足，教师只能编辑小组账号'}), 403
    elif current_role == 'super_admin':
        # 超管可以编辑任何人，但不能编辑自己
        if user.role == 'super_admin' and user.id == session['user_id']:
            return jsonify({'error': '不能编辑自己的账号信息'}), 403

    return render_template('admin/user_form.html',
                           user=user,
                           available_roles=['teacher', 'group'] if current_role == 'super_admin' else ['group'],
                           is_edit=True)


# ──────────────────────────────────────────────────────────────────────────────
# API 路由
# ──────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/api/overview')
@admin_or_teacher_required
def api_overview():
    """获取系统概览数据"""
    from models import db, User, Group, LeaderboardRecord
    from sqlalchemy import func

    # 小组统计数据
    group_stats = db.session.query(
        Group.group_code,
        User.display_name,
        User.is_active,
        Group.experience,
        LeaderboardRecord.accuracy
    ).join(
        User, Group.user_id == User.id
    ).outerjoin(
        LeaderboardRecord, Group.user_id == LeaderboardRecord.group_id
    ).filter(
        User.role == 'group'
    ).order_by(Group.group_code).all()

    # 排行榜统计
    leaderboard_stats = db.session.query(
        LeaderboardRecord.course,
        func.count(LeaderboardRecord.id).label('count'),
        func.max(LeaderboardRecord.accuracy).label('max_accuracy')
    ).group_by(LeaderboardRecord.course).all()

    return jsonify({
        'success': True,
        'group_stats': [
            {
                'group_code': g.group_code,
                'display_name': g.display_name,
                'is_active': g.is_active,
                'experience': g.experience or 0,
                'best_accuracy': float(g.accuracy) if g.accuracy else None
            } for g in group_stats
        ],
        'leaderboard_stats': [
            {
                'course': s.course,
                'submission_count': s.count,
                'best_accuracy': float(s.max_accuracy) if s.max_accuracy else None
            } for s in leaderboard_stats
        ]
    })


@admin_bp.route('/api/users')
@admin_or_teacher_required
def api_list_users():
    """获取用户列表"""
    from models import User, Group

    role = request.args.get('role')
    query = User.query

    if role:
        query = query.filter_by(role=role)

    # 教师只能看到小组账号
    if session.get('role') == 'teacher':
        query = query.filter_by(role='group')

    users = query.order_by(User.created_at.desc()).all()

    result = []
    for u in users:
        data = u.to_dict()
        if u.group:
            data['group_info'] = u.group.to_dict()
        result.append(data)

    return jsonify({'success': True, 'users': result})


@admin_bp.route('/api/users', methods=['POST'])
@admin_or_teacher_required
def api_create_user():
    """创建新用户"""
    from models import db, User, Group, SkillProgress, AuditLog

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    display_name = (data.get('display_name') or username).strip()
    role = data.get('role', 'group')
    group_code = (data.get('group_code') or '').strip()
    member_count = data.get('member_count', 6)

    # 权限检查：教师只能创建小组账号
    if session.get('role') == 'teacher' and role != 'group':
        return jsonify({'error': '��限不足，教师只能创建小组账号'}), 403

    # 基础校验
    if not username or len(username) < 2:
        return jsonify({'error': '用户名至少需要2个字符'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少需要6个字符'}), 400
    if role not in ('teacher', 'group'):
        return jsonify({'error': '无效的角色'}), 400

    # 检查用户名唯一性
    if User.query.filter_by(username=username).first():
        return jsonify({'error': f'用户名 {username} 已被注册'}), 409

    # 小组账号需要检查小组编号
    if role == 'group':
        if not group_code:
            group_code = f'G{username}' if username.startswith('G') else f'G{username.upper()}'
        if Group.query.filter_by(group_code=group_code).first():
            return jsonify({'error': f'小组编号 {group_code} 已被占用'}), 409

    # 创建用户
    user = User(
        username=username,
        display_name=display_name,
        role=role,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    # 如果是小组，同时创建 group 记录
    if role == 'group':
        grp = Group(
            user_id=user.id,
            group_code=group_code,
            member_count=member_count,
            skill_tree={'data': 0, 'algo': 0, 'ai': 0},
        )
        db.session.add(grp)
        db.session.flush()

        # 初始化技能树进度
        sp = SkillProgress(
            group_id=user.id,
            skills={'data': 0, 'algo': 0, 'ai': 0},
            total_xp=0,
        )
        db.session.add(sp)

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='CREATE_USER',
        target_type='user',
        target_id=str(user.id),
        detail={'username': username, 'role': role, 'group_code': group_code if role == 'group' else None},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'{"小组" if role == "group" else "教师"}账号创建成功',
        'user': user.to_dict()
    })


@admin_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_or_teacher_required
def api_update_user(user_id):
    """更新用户信息"""
    from models import db, User, Group, AuditLog

    target = User.query.get_or_404(user_id)

    # 权限检查
    current_role = session.get('role')
    if current_role == 'teacher' and target.role != 'group':
        return jsonify({'error': '权限不足，教师只能编辑小组账号'}), 403

    # 超管不能编辑自己
    if current_role == 'super_admin' and target.role == 'super_admin' and target.id == session['user_id']:
        return jsonify({'error': '不能编辑自己的账号信息'}), 403

    data = request.get_json() or {}

    # 更新字段
    if 'display_name' in data:
        target.display_name = data['display_name'].strip()

    if 'password' in data and data['password']:
        if len(data['password']) < 6:
            return jsonify({'error': '密码至少需要6个字符'}), 400
        target.set_password(data['password'])

    if 'is_active' in data and current_role == 'super_admin':
        # 超管可以修改任何人启用状态，教师只能修改小组
        if current_role == 'teacher' and target.role != 'group':
            return jsonify({'error': '权限不足'}), 403
        target.is_active = bool(data['is_active'])

    # 更新小组扩展信息
    if target.group and 'group_info' in data:
        gi = data['group_info']
        if 'member_count' in gi:
            target.group.member_count = gi['member_count']
        # 小组可使用所有课程模块，不再限制 course 字段

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='UPDATE_USER',
        target_type='user',
        target_id=str(user_id),
        detail={'updated_fields': list(data.keys())},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    result = target.to_dict()
    if target.group:
        result['group_info'] = target.group.to_dict()

    return jsonify({'success': True, 'message': '用户信息已更新', 'user': result})


@admin_bp.route('/api/users/batch-delete', methods=['POST'])
@admin_or_teacher_required
def api_batch_delete_users():
    """批量删除用户账号"""
    from models import db, User, Group, FaceDataset, AudioDataset, EcobottleDataset, ModelFile, Notebook, LeaderboardRecord, AuditLog, SkillProgress
    from config import Config
    import os
    import shutil

    # 数据目录路径
    EMOTION_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'emotion_data')
    AUDIO_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'audio_data')

    data = request.get_json() or {}
    user_ids = data.get('user_ids', [])

    if not user_ids:
        return jsonify({'error': '请选择要删除的用户'}), 400

    # 限制批量删除数量
    if len(user_ids) > 50:
        return jsonify({'error': '单次批量删除最多50个账号'}), 400

    # 教师只能删除小组账号
    current_role = session.get('role')
    if current_role == 'teacher':
        for uid in user_ids:
            user = User.query.get(uid)
            if user and user.role != 'group':
                return jsonify({'error': '权限不足，教师只能删除小组账号'}), 403

    # 不能删除自己
    if session['user_id'] in user_ids:
        return jsonify({'error': '不能删除自己的账号'}), 403

    # 不能删除超级管理员
    target_users = User.query.filter(User.id.in_(user_ids)).all()
    for u in target_users:
        if u.role == 'super_admin':
            return jsonify({'error': '不能删除超级管理员账号'}), 403

    deleted_count = 0
    deleted_usernames = []
    errors = []

    for uid in user_ids:
        try:
            user = User.query.get(uid)
            if not user:
                continue
            # 不能删除自己
            if user.id == session['user_id']:
                errors.append(f'用户 {user.username} 是当前账号，无法删除')
                continue
            # 不能删除超级管理员
            if user.role == 'super_admin':
                errors.append(f'用户 {user.username} 是超级管理员，无法删除')
                continue

            username = user.username
            group_id = None

            # 收集需要清理的文件路径
            file_paths_to_delete = []

            # 如果是小组账号，先收集文件路径和删除关联数据
            if user.role == 'group' and user.group:
                group_id = user.group.user_id

                # 收集数据集文件路径并删除记录
                for Model, records in [
                    (FaceDataset, FaceDataset.query.filter_by(group_id=group_id).all()),
                    (AudioDataset, AudioDataset.query.filter_by(group_id=group_id).all()),
                    (EcobottleDataset, EcobottleDataset.query.filter_by(group_id=group_id).all()),
                    (ModelFile, ModelFile.query.filter_by(group_id=group_id).all()),
                    (Notebook, Notebook.query.filter_by(group_id=group_id).all()),
                    (LeaderboardRecord, LeaderboardRecord.query.filter_by(group_id=group_id).all()),
                ]:
                    for r in records:
                        if r.file_path:
                            file_paths_to_delete.append(r.file_path)
                    for r in records:
                        db.session.delete(r)

                # 删除技能进度
                sp = SkillProgress.query.filter_by(group_id=group_id).first()
                if sp:
                    db.session.delete(sp)

                # 删除小组编辑器工作区
                for dir_name in ['editor_workspaces', 'editor_codes']:
                    workspace_dir = os.path.join('data', dir_name, f'G{group_id}')
                    if os.path.exists(workspace_dir):
                        file_paths_to_delete.append(workspace_dir)

                # 删除小组的表情和音频数据目录
                file_paths_to_delete.append(os.path.join(EMOTION_DATA_DIR, username))
                file_paths_to_delete.append(os.path.join(AUDIO_DATA_DIR, username))

                # 删除 Group 记录
                db.session.delete(user.group)

            # 先删除该用户的审计日志记录（避免外键约束问题）
            AuditLog.query.filter_by(user_id=user.id).delete()

            # 删除 User 记录
            db.session.delete(user)
            deleted_count += 1
            deleted_usernames.append(username)

            # 清理文件（在循环内处理，不等待最后提交）
            for fp in file_paths_to_delete:
                try:
                    if os.path.isdir(fp):
                        shutil.rmtree(fp, ignore_errors=True)
                    elif os.path.isfile(fp):
                        os.remove(fp)
                    elif not fp.startswith('static'):
                        full_path = os.path.join('static', fp)
                        if os.path.isdir(full_path):
                            shutil.rmtree(full_path, ignore_errors=True)
                        elif os.path.isfile(full_path):
                            os.remove(full_path)
                except Exception:
                    pass

            # 清理表情和音频测试集中该小组贡献的数据
            # 测试集中文件名格式为: {username}_{原文件名}
            for test_set_dir in [
                os.path.join(EMOTION_DATA_DIR, '_test_set'),
                os.path.join(AUDIO_DATA_DIR, '_test_set'),
            ]:
                if os.path.isdir(test_set_dir):
                    for f in os.listdir(test_set_dir):
                        if f.startswith(f'{username}_'):
                            try:
                                os.remove(os.path.join(test_set_dir, f))
                            except Exception:
                                pass

        except Exception as e:
            errors.append(f'删除用户 {uid} 时出错: {str(e)}')

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='BATCH_DELETE_USER',
        target_type='user',
        target_id=','.join(map(str, user_ids)),
        detail={
            'deleted_count': deleted_count,
            'deleted_usernames': deleted_usernames,
            'errors': errors
        },
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'成功删除 {deleted_count} 个账号',
        'deleted_count': deleted_count,
        'errors': errors
    })


@admin_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_or_teacher_required
def api_delete_user(user_id):
    """删除用户"""
    from models import db, User, Group, FaceDataset, AudioDataset, EcobottleDataset, ModelFile, Notebook, LeaderboardRecord, AuditLog, SkillProgress
    from config import Config
    import os
    import shutil

    # 数据目录路径
    EMOTION_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'emotion_data')
    AUDIO_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'audio_data')

    target = User.query.get_or_404(user_id)

    # 权限检查
    current_role = session.get('role')
    if current_role == 'teacher' and target.role != 'group':
        return jsonify({'error': '权限不足，教师只能删除小组账号'}), 403

    # 不能删除自己
    if target.id == session['user_id']:
        return jsonify({'error': '不能删除自己的账号'}), 403

    # 不能删除超级管理员
    if target.role == 'super_admin':
        return jsonify({'error': '不能删除超级管理员账号'}), 403

    username = target.username
    user_id_deleted = target.id
    group_id = None

    # 收集需要清理的文件路径
    file_paths_to_delete = []

    # 如果是小组账号，先收集文件路径和删除关联数据
    if target.role == 'group' and target.group:
        group_id = target.group.user_id

        # 收集数据集文件路径
        for Model, records in [
            (FaceDataset, FaceDataset.query.filter_by(group_id=group_id).all()),
            (AudioDataset, AudioDataset.query.filter_by(group_id=group_id).all()),
            (EcobottleDataset, EcobottleDataset.query.filter_by(group_id=group_id).all()),
            (ModelFile, ModelFile.query.filter_by(group_id=group_id).all()),
            (Notebook, Notebook.query.filter_by(group_id=group_id).all()),
            (LeaderboardRecord, LeaderboardRecord.query.filter_by(group_id=group_id).all()),
        ]:
            for r in records:
                if r.file_path:
                    file_paths_to_delete.append(r.file_path)
            # 删除记录
            for r in records:
                db.session.delete(r)

        # 删除技能进度
        sp = SkillProgress.query.filter_by(group_id=group_id).first()
        if sp:
            db.session.delete(sp)

        # 删除小组编辑器工作区
        for dir_name in ['editor_workspaces', 'editor_codes']:
            workspace_dir = os.path.join('data', dir_name, f'G{group_id}')
            if os.path.exists(workspace_dir):
                file_paths_to_delete.append(workspace_dir)

        # 删除小组的表情和音频数据目录
        file_paths_to_delete.append(os.path.join(EMOTION_DATA_DIR, username))
        file_paths_to_delete.append(os.path.join(AUDIO_DATA_DIR, username))

        # 删除 Group 记录
        db.session.delete(target.group)

    # 先删除该用户的审计日志记录（避免外键约束问题）
    AuditLog.query.filter_by(user_id=target.id).delete()

    # 删除 User 记录
    db.session.delete(target)
    db.session.commit()

    # 清理文件
    for fp in file_paths_to_delete:
        try:
            if os.path.isdir(fp):
                shutil.rmtree(fp, ignore_errors=True)
            elif os.path.isfile(fp):
                os.remove(fp)
            elif not fp.startswith('static'):
                full_path = os.path.join('static', fp)
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path, ignore_errors=True)
                elif os.path.isfile(full_path):
                    os.remove(full_path)
        except Exception:
            pass

    # 清理表情和音频测试集中该小组贡献的数据
    for test_set_dir in [
        os.path.join(EMOTION_DATA_DIR, '_test_set'),
        os.path.join(AUDIO_DATA_DIR, '_test_set'),
    ]:
        if os.path.isdir(test_set_dir):
            for f in os.listdir(test_set_dir):
                if f.startswith(f'{username}_'):
                    try:
                        os.remove(os.path.join(test_set_dir, f))
                    except Exception:
                        pass

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='DELETE_USER',
        target_type='user',
        target_id=str(user_id_deleted),
        detail={'deleted_username': username, 'files_cleaned': len(file_paths_to_delete)},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'用户 {username} 已删除'})


@admin_bp.route('/api/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_or_teacher_required
def api_toggle_user_active(user_id):
    """切换用户启用/禁用状态"""
    from models import db, User, AuditLog

    target = User.query.get_or_404(user_id)

    # 权限检查
    if session.get('role') == 'teacher' and target.role != 'group':
        return jsonify({'error': '权限不足，教师只能操作小组账号'}), 403

    # 不能禁用自己
    if target.id == session['user_id']:
        return jsonify({'error': '不能禁用自己的账号'}), 403

    # 不能禁用超级管理员
    if target.role == 'super_admin':
        return jsonify({'error': '不能禁用超级管理员'}), 403

    target.is_active = not target.is_active
    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='TOGGLE_USER_ACTIVE',
        target_type='user',
        target_id=str(user_id),
        detail={'username': target.username, 'is_active': target.is_active},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'is_active': target.is_active})


@admin_bp.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@admin_or_teacher_required
def api_reset_password(user_id):
    """重置用户密码"""
    from models import db, User, AuditLog

    data = request.get_json() or {}
    new_password = data.get('new_password', 'Maogang@2026')

    target = User.query.get_or_404(user_id)

    # 权限检查
    if session.get('role') == 'teacher' and target.role != 'group':
        return jsonify({'error': '权限不足，教师只能重置小组账号密码'}), 403

    # 不能重置自己
    if target.id == session['user_id']:
        return jsonify({'error': '不能重置自己的密码'}), 403

    target.set_password(new_password)
    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='RESET_PASSWORD',
        target_type='user',
        target_id=str(user_id),
        detail={'username': target.username, 'reset_by': session['username']},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'密码已重置为: {new_password}'})


@admin_bp.route('/api/groups/check-code')
@admin_or_teacher_required
def api_check_group_code():
    """检查小组编号是否可用"""
    from models import Group

    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({'available': False, 'error': '请提供小组编号'}), 400

    existing = Group.query.filter_by(group_code=code).first()
    return jsonify({'available': existing is None, 'code': code})


@admin_bp.route('/api/audit-logs')
@admin_or_teacher_required
def api_audit_logs():
    """获取审计日志"""
    from models import AuditLog, User
    from sqlalchemy import desc

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    action = request.args.get('action')
    user_id = request.args.get('user_id', type=int)

    query = AuditLog.query

    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    pagination = query.order_by(desc(AuditLog.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取用户名
    user_ids = set(log.user_id for log in pagination.items)
    users = {u.id: u.username for u in User.query.filter(User.id.in_(user_ids)).all()}

    return jsonify({
        'success': True,
        'logs': [{
            'id': log.id,
            'username': users.get(log.user_id, 'Unknown'),
            'action': log.action,
            'target_type': log.target_type,
            'target_id': log.target_id,
            'detail': log.detail,
            'ip_address': log.ip_address,
            'created_at': log.created_at.isoformat() if log.created_at else None
        } for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


@admin_bp.route('/api/leaderboard/all')
@admin_or_teacher_required
def api_leaderboard_all():
    """获取所有排行榜记录（管理员视图）"""
    from models import LeaderboardRecord, Group, User
    from sqlalchemy import desc

    course = request.args.get('course')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = LeaderboardRecord.query

    if course:
        query = query.filter(LeaderboardRecord.course == course)

    pagination = query.order_by(desc(LeaderboardRecord.submitted_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取小组信息
    group_ids = set(r.group_id for r in pagination.items)
    groups = {g.user_id: g for g in Group.query.filter(Group.user_id.in_(group_ids)).all()}
    users = {u.id: u for u in User.query.filter(User.id.in_(group_ids)).all()}

    return jsonify({
        'success': True,
        'records': [{
            'id': r.id,
            'group_code': groups.get(r.group_id, None) and groups[r.group_id].group_code,
            'group_name': users.get(r.group_id, None) and users[r.group_id].display_name,
            'course': r.course,
            'accuracy': float(r.accuracy) if r.accuracy else None,
            'correct_count': r.correct_count,
            'total_count': r.total_count,
            'time_cost_seconds': r.time_cost_seconds,
            'composite_score': float(r.composite_score) if r.composite_score else None,
            'innovation_score': r.innovation_score,
            'is_public': r.is_public,
            'submitted_at': r.submitted_at.isoformat() if r.submitted_at else None
        } for r in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


# ──────────────────────────────────────────────────────────────────────────────
# 测试集管理 API
# ──────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/api/datasets/overview')
@admin_or_teacher_required
def api_datasets_overview():
    """获取测试集概览统计"""
    from models import FaceDataset, AudioDataset, EcobottleDataset
    from sqlalchemy import func

    face_stats = db.session.query(
        FaceDataset.dataset_type,
        FaceDataset.status,
        func.count(FaceDataset.id).label('count')
    ).group_by(FaceDataset.dataset_type, FaceDataset.status).all()

    audio_stats = db.session.query(
        AudioDataset.dataset_type,
        AudioDataset.status,
        func.count(AudioDataset.id).label('count')
    ).group_by(AudioDataset.dataset_type, AudioDataset.status).all()

    eco_stats = db.session.query(
        EcobottleDataset.dataset_type,
        EcobottleDataset.status,
        func.count(EcobottleDataset.id).label('count')
    ).group_by(EcobottleDataset.dataset_type, EcobottleDataset.status).all()

    return jsonify({
        'success': True,
        'face': _format_dataset_stats(face_stats),
        'audio': _format_dataset_stats(audio_stats),
        'ecobottle': _format_dataset_stats(eco_stats)
    })


def _format_dataset_stats(stats):
    """格式化数据集统计"""
    result = {'train': {'pending': 0, 'confirmed': 0, 'rejected': 0},
              'test': {'pending': 0, 'confirmed': 0, 'rejected': 0},
              'total': 0}
    for s in stats:
        if s.dataset_type in result:
            result[s.dataset_type][s.status] = s.count
            result['total'] += s.count
    return result


@admin_bp.route('/api/datasets/face')
@admin_or_teacher_required
def api_datasets_face():
    """获取表情数据集列表（支持筛选）"""
    from models import FaceDataset, Group, User

    dataset_type = request.args.get('type')  # train / test / None(全部)
    status = request.args.get('status')  # pending / confirmed / rejected / None(全部)
    group_id = request.args.get('group_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = FaceDataset.query

    if dataset_type:
        query = query.filter(FaceDataset.dataset_type == dataset_type)
    if status:
        query = query.filter(FaceDataset.status == status)
    if group_id:
        query = query.filter(FaceDataset.group_id == group_id)

    pagination = query.order_by(FaceDataset.uploaded_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 获取小组信息
    group_ids = set(d.group_id for d in pagination.items)
    groups = {g.user_id: g for g in Group.query.filter(Group.user_id.in_(group_ids)).all()}
    users = {u.id: u for u in User.query.filter(User.id.in_(group_ids)).all()}

    return jsonify({
        'success': True,
        'datasets': [{
            'id': d.id,
            'group_code': groups.get(d.group_id, None) and groups[d.group_id].group_code,
            'group_name': users.get(d.group_id, None) and users[d.group_id].display_name,
            'file_path': d.file_path,
            'file_name': d.file_name,
            'label': d.label,
            'label_source': d.label_source,
            'confidence': float(d.confidence) if d.confidence else None,
            'dataset_type': d.dataset_type,
            'status': d.status,
            'uploaded_at': d.uploaded_at.isoformat() if d.uploaded_at else None
        } for d in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


@admin_bp.route('/api/datasets/audio')
@admin_or_teacher_required
def api_datasets_audio():
    """获取声音数据集列表（支持筛选）"""
    from models import AudioDataset, Group, User

    dataset_type = request.args.get('type')
    status = request.args.get('status')
    group_id = request.args.get('group_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = AudioDataset.query

    if dataset_type:
        query = query.filter(AudioDataset.dataset_type == dataset_type)
    if status:
        query = query.filter(AudioDataset.status == status)
    if group_id:
        query = query.filter(AudioDataset.group_id == group_id)

    pagination = query.order_by(AudioDataset.uploaded_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    group_ids = set(d.group_id for d in pagination.items)
    groups = {g.user_id: g for g in Group.query.filter(Group.user_id.in_(group_ids)).all()}
    users = {u.id: u for u in User.query.filter(User.id.in_(group_ids)).all()}

    return jsonify({
        'success': True,
        'datasets': [{
            'id': d.id,
            'group_code': groups.get(d.group_id, None) and groups[d.group_id].group_code,
            'group_name': users.get(d.group_id, None) and users[d.group_id].display_name,
            'file_path': d.file_path,
            'file_name': d.file_name,
            'duration_sec': float(d.duration_sec) if d.duration_sec else None,
            'label': d.label,
            'label_source': d.label_source,
            'confidence': float(d.confidence) if d.confidence else None,
            'dataset_type': d.dataset_type,
            'status': d.status,
            'uploaded_at': d.uploaded_at.isoformat() if d.uploaded_at else None
        } for d in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


@admin_bp.route('/api/datasets/ecobottle')
@admin_or_teacher_required
def api_datasets_ecobottle():
    """获取生态瓶数据集列表（支持筛选）"""
    from models import EcobottleDataset, Group, User

    dataset_type = request.args.get('type')
    status = request.args.get('status')
    group_id = request.args.get('group_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    query = EcobottleDataset.query

    if dataset_type:
        query = query.filter(EcobottleDataset.dataset_type == dataset_type)
    if status:
        query = query.filter(EcobottleDataset.status == status)
    if group_id:
        query = query.filter(EcobottleDataset.group_id == group_id)

    pagination = query.order_by(EcobottleDataset.uploaded_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    group_ids = set(d.group_id for d in pagination.items)
    groups = {g.user_id: g for g in Group.query.filter(Group.user_id.in_(group_ids)).all()}
    users = {u.id: u for u in User.query.filter(User.id.in_(group_ids)).all()}

    return jsonify({
        'success': True,
        'datasets': [{
            'id': d.id,
            'group_code': groups.get(d.group_id, None) and groups[d.group_id].group_code,
            'group_name': users.get(d.group_id, None) and users[d.group_id].display_name,
            'file_path': d.file_path,
            'file_name': d.file_name,
            'record_count': d.record_count,
            'feature_cols': d.feature_cols,
            'target_col': d.target_col,
            'dataset_type': d.dataset_type,
            'status': d.status,
            'uploaded_at': d.uploaded_at.isoformat() if d.uploaded_at else None
        } for d in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


@admin_bp.route('/api/datasets/<dataset_type>/<int:dataset_id>/status', methods=['PUT'])
@admin_or_teacher_required
def api_update_dataset_status(dataset_type, dataset_id):
    """更新数据集审核状态"""
    from models import AuditLog

    data = request.get_json() or {}
    new_status = data.get('status')

    if new_status not in ('pending', 'confirmed', 'rejected'):
        return jsonify({'error': '无效的状态值'}), 400

    # 根据类型获取对应模型
    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    dataset = model.query.get_or_404(dataset_id)
    old_status = dataset.status
    dataset.status = new_status
    dataset.reviewed_by = session['user_id']
    dataset.reviewed_at = db.func.now()

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='UPDATE_DATASET_STATUS',
        target_type=f'{dataset_type}_dataset',
        target_id=str(dataset_id),
        detail={'old_status': old_status, 'new_status': new_status, 'file_name': dataset.file_name},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'状态已更新为: {new_status}'})


@admin_bp.route('/api/datasets/<dataset_type>/batch-status', methods=['PUT'])
@admin_or_teacher_required
def api_batch_update_dataset_status(dataset_type):
    """批量更新数据集审核状态"""
    from models import AuditLog

    data = request.get_json() or {}
    dataset_ids = data.get('dataset_ids', [])
    new_status = data.get('status')

    if not dataset_ids:
        return jsonify({'error': '请选择要更新的数据集'}), 400
    if new_status not in ('pending', 'confirmed', 'rejected'):
        return jsonify({'error': '无效的状态值'}), 400

    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    updated_count = model.query.filter(
        model.id.in_(dataset_ids)
    ).update({
        'status': new_status,
        'reviewed_by': session['user_id'],
        'reviewed_at': db.func.now()
    }, synchronize_session=False)

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='BATCH_UPDATE_DATASET_STATUS',
        target_type=f'{dataset_type}_dataset',
        target_id=','.join(map(str, dataset_ids)),
        detail={'count': updated_count, 'new_status': new_status},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'已更新 {updated_count} 条记录'})


@admin_bp.route('/api/datasets/<dataset_type>/<int:dataset_id>', methods=['DELETE'])
@admin_or_teacher_required
def api_delete_dataset(dataset_type, dataset_id):
    """删除数据集记录"""
    from models import AuditLog
    import os

    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    dataset = model.query.get_or_404(dataset_id)
    file_path = dataset.file_path
    file_name = dataset.file_name

    # 删除数据库记录
    db.session.delete(dataset)
    db.session.commit()

    # 尝试删除物理文件
    try:
        full_path = os.path.join('static', file_path) if not file_path.startswith('static') else file_path
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass  # 文件删除失败不影响数据库操作

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='DELETE_DATASET',
        target_type=f'{dataset_type}_dataset',
        target_id=str(dataset_id),
        detail={'file_name': file_name, 'file_path': file_path},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': '数据集已删除'})


@admin_bp.route('/api/datasets/groups')
@admin_or_teacher_required
def api_datasets_groups():
    """获取所有小组列表（用于筛选）"""
    from models import Group, User

    groups = db.session.query(Group, User).join(User, Group.user_id == User.id).filter(
        User.role == 'group'
    ).order_by(Group.group_code).all()

    return jsonify({
        'success': True,
        'groups': [{
            'user_id': g.user_id,
            'group_code': g.group_code,
            'group_name': u.display_name
        } for g, u in groups]
    })


@admin_bp.route('/api/datasets/export/<dataset_type>')
@admin_or_teacher_required
def api_export_dataset(dataset_type, page=1, per_page=1000):
    """导出数据集（生成CSV下载）"""
    import csv
    import io
    from flask import make_response

    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    datasets = model.query.filter_by(status='confirmed').all()

    output = io.StringIO()

    if dataset_type == 'face':
        writer = csv.writer(output)
        writer.writerow(['id', 'group_code', 'file_name', 'label', 'label_source', 'dataset_type', 'uploaded_at'])
        for d in datasets:
            writer.writerow([d.id, d.group_id, d.file_name, d.label, d.label_source, d.dataset_type, d.uploaded_at])

    elif dataset_type == 'audio':
        writer = csv.writer(output)
        writer.writerow(['id', 'group_code', 'file_name', 'duration_sec', 'label', 'label_source', 'dataset_type', 'uploaded_at'])
        for d in datasets:
            writer.writerow([d.id, d.group_id, d.file_name, d.duration_sec, d.label, d.label_source, d.dataset_type, d.uploaded_at])

    elif dataset_type == 'ecobottle':
        writer = csv.writer(output)
        writer.writerow(['id', 'group_code', 'file_name', 'record_count', 'feature_cols', 'target_col', 'dataset_type', 'uploaded_at'])
        for d in datasets:
            writer.writerow([d.id, d.group_id, d.file_name, d.record_count, ','.join(d.feature_cols) if d.feature_cols else '', d.target_col, d.dataset_type, d.uploaded_at])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={dataset_type}_datasets.csv'

    return response


# ──────────────────────────────────────────────────────────────────────────────
# 全局测试集上传管理 API
# ──────────────────────────────────────────────────────────────────────────────

@admin_bp.route('/api/datasets/global/upload', methods=['POST'])
@admin_or_teacher_required
def api_upload_global_dataset():
    """上传全局测试集文件（管理员上传，不属于任何小组）"""
    from models import db, FaceDataset, AudioDataset, EcobottleDataset, AuditLog
    from flask import current_app
    import os
    import uuid
    import base64

    dataset_type = request.form.get('dataset_type', 'face')
    label = request.form.get('label', '')
    status = request.form.get('status', 'confirmed')  # 管理员上传默认已确认

    if dataset_type not in ('face', 'audio', 'ecobottle'):
        return jsonify({'error': '无效的数据集类型'}), 400

    # 验证标签
    valid_labels = {
        'face': ['happy', 'sad', 'angry', 'surprised', 'fearful', 'disgusted', 'neutral'],
        'audio': ['angry', 'fearful', 'happy', 'neutral', 'sad', 'surprised'],
        'ecobottle': []  # 生态瓶不需要情绪标签
    }
    if dataset_type == 'face' and label not in valid_labels['face']:
        return jsonify({'error': f'无效的表情标签: {label}'}), 400
    if dataset_type == 'audio' and label not in valid_labels['audio']:
        return jsonify({'error': f'无效的声音标签: {label}'}), 400

    # 确定存储目录和模型
    if dataset_type == 'face':
        upload_dir = os.path.join('static', 'uploads', 'global_datasets', 'face')
        ModelClass = FaceDataset
    elif dataset_type == 'audio':
        upload_dir = os.path.join('static', 'uploads', 'global_datasets', 'audio')
        ModelClass = AudioDataset
    else:
        upload_dir = os.path.join('static', 'uploads', 'global_datasets', 'ecobottle')
        ModelClass = EcobottleDataset

    os.makedirs(upload_dir, exist_ok=True)

    results = []

    # 处理文件上传
    if 'file' in request.files:
        files = request.files.getlist('file')
        for file in files:
            if file.filename == '':
                continue

            # 生成唯一文件名
            ext = os.path.splitext(file.filename)[1].lower()
            unique_name = f"admin_{uuid.uuid4().hex[:8]}{ext}"
            file_path = os.path.join(upload_dir, unique_name)
            relative_path = os.path.join('uploads', 'global_datasets', dataset_type, unique_name)

            file.save(file_path)

            # 创建数据库记录（group_id 为 0 表示管理员上传）
            record = ModelClass(
                group_id=0,  # 0 表示全局测试集
                file_path=relative_path,
                file_name=file.filename,
                label=label if label else 'unknown',
                label_source='teacher',
                dataset_type='test',
                status=status
            )
            db.session.add(record)
            results.append({
                'file_name': file.filename,
                'status': 'saved',
                'id': record.id
            })

    # 处理 Base64 图片数据（表情/声音）
    elif 'images' in request.form or 'image' in request.form:
        images_data = request.form.get('images') or request.form.get('image')
        if images_data:
            try:
                images_list = json.loads(images_data) if images_data.startswith('[') else [images_data]
            except:
                images_list = [images_data]

            for i, img_b64 in enumerate(images_list):
                if not img_b64:
                    continue

                try:
                    # 解码并保存图片
                    img_data = base64.b64decode(img_b64.split(',')[1] if ',' in img_b64 else img_b64)
                    unique_name = f"admin_{uuid.uuid4().hex[:8]}.jpg"
                    file_path = os.path.join(upload_dir, unique_name)
                    relative_path = os.path.join('uploads', 'global_datasets', dataset_type, unique_name)

                    with open(file_path, 'wb') as f:
                        f.write(img_data)

                    record = ModelClass(
                        group_id=0,
                        file_path=relative_path,
                        file_name=f"image_{i+1}.jpg",
                        label=label if label else 'unknown',
                        label_source='teacher',
                        dataset_type='test',
                        status=status
                    )
                    db.session.add(record)
                    results.append({
                        'file_name': f"image_{i+1}.jpg",
                        'status': 'saved',
                        'id': record.id
                    })
                except Exception as e:
                    results.append({
                        'file_name': f"image_{i+1}.jpg",
                        'status': 'error',
                        'error': str(e)
                    })

    # 处理 CSV 文件（生态瓶）
    elif 'csv_data' in request.form:
        csv_content = request.form.get('csv_data', '')
        unique_name = f"admin_{uuid.uuid4().hex[:8]}.csv"
        file_path = os.path.join(upload_dir, unique_name)
        relative_path = os.path.join('uploads', 'global_datasets', dataset_type, unique_name)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(csv_content)

        # 解析 CSV 获取统计信息
        import csv as csv_module
        record_count = 0
        feature_cols = []
        target_col = 'label'
        try:
            lines = csv_content.strip().split('\n')
            reader = csv_module.reader(lines)
            rows = list(reader)
            if rows:
                headers = rows[0]
                record_count = len(rows) - 1
                feature_cols = [h for h in headers if h.lower() not in ('label', 'target', 'y')]
                target_col = 'label' if 'label' in [h.lower() for h in headers] else headers[-1]
        except:
            pass

        record = ModelClass(
            group_id=0,
            file_path=relative_path,
            file_name=unique_name,
            label=target_col,
            label_source='teacher',
            dataset_type='test',
            status=status,
            record_count=record_count,
            feature_cols=feature_cols,
            target_col=target_col
        )
        db.session.add(record)
        results.append({
            'file_name': unique_name,
            'status': 'saved',
            'id': record.id,
            'record_count': record_count
        })

    else:
        return jsonify({'error': '未提供任何文件或数据'}), 400

    db.session.commit()

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='UPLOAD_GLOBAL_DATASET',
        target_type=f'{dataset_type}_global_dataset',
        target_id=str(len(results)),
        detail={
            'dataset_type': dataset_type,
            'count': len(results),
            'label': label,
            'results': results
        },
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'成功上传 {len(results)} 个文件',
        'results': results
    })


@admin_bp.route('/api/datasets/global/list')
@admin_or_teacher_required
def api_global_dataset_list():
    """获取全局测试集列表（管理员上传的，group_id=0）"""
    from models import FaceDataset, AudioDataset, EcobottleDataset

    dataset_type = request.args.get('type', 'face')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    # 只查询 group_id=0 的全局测试集
    query = model.query.filter_by(group_id=0)

    pagination = query.order_by(model.uploaded_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'success': True,
        'datasets': [{
            'id': d.id,
            'file_path': d.file_path,
            'file_name': d.file_name,
            'label': d.label,
            'dataset_type': d.dataset_type,
            'status': d.status,
            'uploaded_at': d.uploaded_at.isoformat() if d.uploaded_at else None
        } for d in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'page': page
    })


@admin_bp.route('/api/users/csv/template/<role_type>')
@admin_or_teacher_required
def api_download_csv_template(role_type):
    """下载CSV导入模板

    role_type: 'teacher' 或 'group'
    """
    import csv
    import io
    from flask import make_response

    if role_type not in ('teacher', 'group'):
        return jsonify({'error': '无效的角色类型'}), 400

    output = io.StringIO()

    if role_type == 'teacher':
        # 教师账号CSV模板
        writer = csv.writer(output)
        writer.writerow(['username', 'password', 'display_name', 'remark'])
        writer.writerow(['teacher_zhang', 'Maogang@2026', '张老师', '示例备注'])
        writer.writerow(['teacher_li', 'Maogang@2026', '李老师', ''])
        filename = 'teacher_accounts_template.csv'
    else:
        # 小组账号CSV模板
        writer = csv.writer(output)
        writer.writerow(['username', 'password', 'display_name', 'group_code', 'member_count', 'remark'])
        writer.writerow(['G01', 'Maogang@2026', '第一小组', 'G01', '6', '示例备注'])
        writer.writerow(['G02', 'Maogang@2026', '第二小组', 'G02', '6', ''])
        writer.writerow(['G03', 'Maogang@2026', '第三小组', 'G03', '8', '8人小组'])
        filename = 'group_accounts_template.csv'

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'
    return response


@admin_bp.route('/api/users/csv/preview', methods=['POST'])
@admin_or_teacher_required
def api_preview_csv():
    """预览CSV文件内容，自动检测编码"""
    import io

    if 'preview_file' not in request.files:
        return jsonify({'success': False, 'error': '请提供文件'}), 400

    file = request.files['preview_file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    # 读取原始数据并自动检测编码
    raw_data = file.read()
    csv_content = None
    detected_encoding = None

    # 先检查是否有 BOM
    if raw_data.startswith(b'\xef\xbb\xbf'):
        # UTF-8 BOM
        csv_content = raw_data.decode('utf-8-sig')
        detected_encoding = 'utf-8-sig (BOM)'
    elif raw_data.startswith(b'\xff\xfe') or raw_data.startswith(b'\xfe\xff'):
        # UTF-16 BOM
        try:
            csv_content = raw_data.decode('utf-16')
            detected_encoding = 'utf-16'
        except:
            csv_content = None

    # 如果没有 BOM，尝试各种编码
    if csv_content is None:
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030']
        for encoding in encodings:
            try:
                # 验证是否能完全解码
                decoded = raw_data.decode(encoding)
                # 检查是否包含有效字符
                if '\x00' not in decoded[:100]:  # 排除 UTF-16 误判
                    csv_content = decoded
                    detected_encoding = encoding
                    break
            except (UnicodeDecodeError, LookupError):
                continue

    if csv_content is None:
        return jsonify({'success': False, 'error': '无法识别文件编码，请将CSV保存为UTF-8格式'}), 400

    # 清理可能的问题字符
    csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')

    # 生成预览文本（前6行）
    lines = csv_content.split('\n')
    preview_lines = []
    for i, line in enumerate(lines[:6]):
        if line.strip():
            # 检测是否是有效的CSV行（包含逗号或制表符）
            if ',' in line or '\t' in line:
                cells = line.split(',')
                preview_lines.append(f"{i+1}. {' | '.join([c.strip() for c in cells])}")
            else:
                preview_lines.append(f"{i+1}. {line.strip()}")

    preview_text = '\n'.join(preview_lines)

    return jsonify({
        'success': True,
        'csv_content': csv_content,
        'preview_text': preview_text,
        'detected_encoding': detected_encoding,
        'total_lines': len([l for l in lines if l.strip()])
    })


@admin_bp.route('/api/users/csv/import', methods=['POST'])
@admin_or_teacher_required
def api_import_users_csv():
    """通过CSV批量导入用户账号

    CSV格式（教师）：
        username,password,display_name,remark
        teacher_zhang,Maogang@2026,张老师,数学教师
        teacher_li,Maogang@2026,李老师,

    CSV格式（小组）：
        username,password,display_name,group_code,member_count,remark
        G01,Maogang@2026,第一小组,G01,6,AI方向
        G02,Maogang@2026,第二小组,G02,6,
    """
    from models import db, User, Group, SkillProgress, AuditLog
    import csv
    import io

    # 检查是否有文件上传
    if 'file' not in request.files and 'csv_content' not in request.form:
        return jsonify({'error': '请提供CSV文件或csv_content参数'}), 400

    role_type = request.form.get('role_type', 'group')
    if role_type not in ('teacher', 'group'):
        return jsonify({'error': 'role_type必须是teacher或group'}), 400

    # 教师只能导入小组账号
    current_role = session.get('role')
    if current_role == 'teacher' and role_type != 'group':
        return jsonify({'error': '权限不足，教师只能导入小组账号'}), 403

    # 读取CSV内容（支持多种编码）
    csv_content = ''
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '未选择文件'}), 400
        raw_data = file.read()
        # 尝试多种编码方式解析
        for encoding in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
            try:
                csv_content = raw_data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not csv_content:
            return jsonify({'error': '无法解析文件编码，请使用UTF-8编码的CSV文件'}), 400
    else:
        csv_content = request.form.get('csv_content', '')

    if not csv_content.strip():
        return jsonify({'error': 'CSV内容为空'}), 400

    # 解析CSV
    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
    except Exception as e:
        return jsonify({'error': f'CSV解析失败: {str(e)}'}), 400

    if len(rows) < 2:
        return jsonify({'error': 'CSV至少需要包含表头和1行数据'}), 400

    header = [h.strip().lower() for h in rows[0]]
    data_rows = rows[1:]

    # 验证表头
    if role_type == 'teacher':
        required_fields = ['username', 'password', 'display_name']
        optional_fields = ['remark']
    else:
        required_fields = ['username', 'password', 'display_name', 'group_code']
        optional_fields = ['member_count', 'remark']

    for field in required_fields:
        if field not in header:
            return jsonify({'error': f'CSV缺少必需列: {field}'}), 400

    imported_count = 0
    skipped_count = 0
    skipped_reasons = []
    errors = []

    for i, row in enumerate(data_rows, start=2):
        # 使用子事务：每行独立，失败只回滚当前行
        try:
            with db.session.begin_nested():
                if len(row) < len(required_fields):
                    errors.append(f'第{i}行: 数据列数不足，需要{len(required_fields)}列')
                    skipped_count += 1
                    skipped_reasons.append(f'第{i}行: 数据列数不足')
                    raise SkipRow(f'第{i}行: 数据列数不足')

                # 构建字段映射
                row_data = {}
                for j, h in enumerate(header):
                    if j < len(row):
                        row_data[h] = row[j].strip()

                username = row_data.get('username', '')
                password = row_data.get('password', '')
                display_name = row_data.get('display_name', '') or username
                remark = row_data.get('remark', '') or ''

                # 基本校验
                if not username or len(username) < 2:
                    errors.append(f'第{i}行: 用户名无效')
                    skipped_count += 1
                    skipped_reasons.append(f'第{i}行({username or "空"}): 用户名无效')
                    raise SkipRow(f'第{i}行: 用户名无效')

                if len(password) < 6:
                    errors.append(f'第{i}行: 密码至少6位')
                    skipped_count += 1
                    skipped_reasons.append(f'第{i}行({username}): 密码至少6位')
                    raise SkipRow(f'第{i}行: 密码至少6位')

                # 检查用户名唯一性
                if User.query.filter_by(username=username).first():
                    errors.append(f'第{i}行: 用户名 {username} 已存在')
                    skipped_count += 1
                    skipped_reasons.append(f'第{i}行({username}): 用户名已存在')
                    raise SkipRow(f'第{i}行: 用户名已存在')

                # 创建用户
                user = User(
                    username=username,
                    display_name=display_name,
                    role=role_type,
                    remark=remark if remark else None,
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()

                # 如果是小组，同时创建 group 记录
                if role_type == 'group':
                    group_code_val = row_data.get('group_code', '').strip() or f'G{username.upper()}'
                    member_count_str = row_data.get('member_count', '6')
                    try:
                        member_count = int(member_count_str) if member_count_str else 6
                    except ValueError:
                        member_count = 6

                    # 检查小组编号唯一性
                    if Group.query.filter_by(group_code=group_code_val).first():
                        errors.append(f'第{i}行: 小组编号 {group_code_val} 已存在')
                        skipped_count += 1
                        skipped_reasons.append(f'第{i}行({username}): 小组编号已存在')
                        raise SkipRow(f'第{i}行: 小组编号已存在')

                    grp = Group(
                        user_id=user.id,
                        group_code=group_code_val,
                        member_count=member_count,
                        skill_tree={'data': 0, 'algo': 0, 'ai': 0},
                    )
                    db.session.add(grp)
                    db.session.flush()

                    # 初始化技能树进度
                    sp = SkillProgress(
                        group_id=user.id,
                        skills={'data': 0, 'algo': 0, 'ai': 0},
                        total_xp=0,
                    )
                    db.session.add(sp)

                imported_count += 1

        except SkipRow:
            # 已经记录了错误和跳过计数，继续下一行
            continue
        except Exception as e:
            errors.append(f'第{i}行: {str(e)}')
            skipped_count += 1
            skipped_reasons.append(f'第{i}行: 处理失败')
            # 子事务会自动回滚，无需手动操作

    try:
        # 提交所有成功导入的数据
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # 主事务提交失败，这是严重错误
        return jsonify({
            'success': False,
            'error': f'数据提交失败: {str(e)}'
        }), 500

    # 记录审计日志（独立事务，失败不影响导入结果）
    try:
        AuditLog.log(
            user_id=session['user_id'],
            action='IMPORT_USERS_CSV',
            target_type='user',
            detail={
                'role_type': role_type,
                'imported_count': imported_count,
                'skipped_count': skipped_count,
                'total_rows': len(data_rows)
            },
            ip_address=request.remote_addr,
        )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # 审计日志失败只打印警告，不影响返回结果
        print(f"Warning: AuditLog failed: {e}")

    result_msg = f'导入完成：成功 {imported_count} 个，'
    if skipped_count > 0:
        result_msg += f'跳过 {skipped_count} 个'
    if errors:
        result_msg += f'，错误: {", ".join(errors[:5])}'

    return jsonify({
        'success': True,
        'message': result_msg,
        'detail': {
            'imported_count': imported_count,
            'skipped_count': skipped_count,
            'total_rows': len(data_rows),
            'errors': errors[:20]  # 最多返回20条错误
        }
    })


@admin_bp.route('/api/users/csv/export')
@admin_or_teacher_required
def api_export_users_csv():
    """导出用户账号为CSV

    Query参数：
        role: 筛选角色 (teacher/group)，可选，默认导出全部
    """
    from models import db, User, Group
    import csv
    import io
    from flask import make_response

    role = request.args.get('role')

    query = User.query
    if role:
        query = query.filter_by(role=role)

    # 教师只能导出小组账号
    if session.get('role') == 'teacher':
        query = query.filter_by(role='group')

    users = query.order_by(User.role, User.created_at).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 写入表头
    writer.writerow(['username', 'display_name', 'role', 'group_code', 'member_count', 'is_active', 'created_at', 'remark'])

    for u in users:
        group = u.group
        group_code = group.group_code if group else ''
        member_count = group.member_count if group else ''
        created_at = u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else ''

        writer.writerow([
            u.username,
            u.display_name,
            u.role,
            group_code,
            member_count,
            '是' if u.is_active else '否',
            created_at,
            u.remark or ''
        ])

    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'user_accounts_export.csv'
    return response


@admin_bp.route('/api/datasets/global/<dataset_type>/<int:dataset_id>', methods=['DELETE'])
@admin_or_teacher_required
def api_delete_global_dataset(dataset_type, dataset_id):
    """删除全局测试集"""
    from models import db, AuditLog
    import os

    model_map = {
        'face': FaceDataset,
        'audio': AudioDataset,
        'ecobottle': EcobottleDataset
    }

    model = model_map.get(dataset_type)
    if not model:
        return jsonify({'error': '无效的数据集类型'}), 400

    record = model.query.filter_by(id=dataset_id, group_id=0).first()
    if not record:
        return jsonify({'error': '记录不存在或无权删除'}), 404

    file_path = record.file_path

    # 删除数据库记录
    db.session.delete(record)
    db.session.commit()

    # 删除物理文件
    try:
        full_path = os.path.join('static', file_path)
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass

    # 审计日志
    AuditLog.log(
        user_id=session['user_id'],
        action='DELETE_GLOBAL_DATASET',
        target_type=f'{dataset_type}_global_dataset',
        target_id=str(dataset_id),
        detail={'file_name': record.file_name},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': '全局测试集已删除'})

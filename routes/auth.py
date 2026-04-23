"""
routes/auth.py — 用户认证路由

提供登录、注册、登出、修改密码等 API。
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


# ──────────────────────────────────────────────────────────────────────────────
# 辅助装饰器
# ──────────────────────────────────────────────────────────────────────────────

def login_required(f):
    """要求用户已登录，否则返回 401。"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated


def teacher_required(f):
    """要求用户是教师或超管。"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('auth.login_page'))
        from models import User
        user = User.query.get(session['user_id'])
        if not user or user.role not in ('super_admin', 'teacher'):
            return jsonify({'error': '权限不足，仅教师或管理员可操作'}), 403
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """要求用户是超管。"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '请先登录'}), 401
        from models import User
        user = User.query.get(session['user_id'])
        if not user or user.role != 'super_admin':
            return jsonify({'error': '权限不足，仅管理员可操作'}), 403
        return f(*args, **kwargs)
    return decorated


def admin_or_teacher_required(f):
    """要求用户是超管或教师。"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'error': '请先登录'}), 401
            return redirect(url_for('auth.login_page'))
        from models import User
        user = User.query.get(session['user_id'])
        if not user or user.role not in ('super_admin', 'teacher'):
            return jsonify({'error': '权限不足，仅教师或管理员可操作'}), 403
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """返回当前登录用户（None if 未登录）。"""
    if 'user_id' not in session:
        return None
    from models import User
    return User.query.get(session['user_id'])


def get_group_member_count_for_session(default: int = 6) -> int:
    """
    当前登录账号所属小组的成员人数（与后台创建小组时填写的 member_count 一致）。
    教师、管理员等非小组账号返回 default，仅用于采集页成员下拉占位。
    """
    uid = session.get('user_id')
    if not uid:
        return default
    from models import User
    user = User.query.get(uid)
    if user is None or user.group is None:
        return default
    n = int(user.group.member_count or 1)
    return max(1, min(n, 99))


# ──────────────────────────────────────────────────────────────────────────────
# 页面路由（返回 HTML）
# ──────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET'])
def login_page():
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET'])
def register_page():
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    return render_template('register.html')


# ──────────────────────────────────────────────────────────────────────────────
# API 路由（返回 JSON）
# ──────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or request.form.get('username', '')).strip()
    password = (data.get('password') or request.form.get('password', ''))

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    from models import db, User, AuditLog

    try:
        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({'error': '用户名或密码错误'}), 401

        if not user.is_active:
            return jsonify({'error': '账号已被禁用，请联系管理员'}), 403

        if not user.check_password(password):
            return jsonify({'error': '用户名或密码错误'}), 401

        # 检查是否为占位密码（首次部署的默认账号）
        if user.password_hash.startswith('$werkzeug$placeholder$'):
            return jsonify({
                'error': '请先修改默认密码再登录',
                'code': 'PASSWORD_NOT_SET',
                'user_id': user.id,
            }), 403

        # 写入 session
        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session.permanent = True  # 记住登录状态

        # 更新小组信息到 session（使用try包裹，防止延迟加载问题）
        # 注意：教师/管理员没有 group 记录，也需要设置 group_id 用于模型管理
        try:
            if user.group:
                session['group_id'] = user.group.group_code
                session['group_name'] = user.group.group_name or user.display_name or user.username
                from datetime import datetime
                user.group.last_active_at = datetime.utcnow()
                db.session.commit()
            else:
                # 教师/管理员使用 user_id 作为 group_id（用于个人模型存储）
                session['group_id'] = f"user_{user.id}"
                session['group_name'] = user.display_name or user.username
        except Exception as group_error:
            db.session.rollback()
            import logging
            logging.warning(f"小组信息更新失败: {group_error}")
            # 即使更新失败，也要设置基础 group_id
            if 'group_id' not in session:
                session['group_id'] = f"user_{user.id}" if user.role != 'group' else str(user.id)
                session['group_name'] = user.display_name or user.username

        # 审计日志（使用 try-catch 防止失败阻断登录）
        try:
            AuditLog.log(
                user_id=user.id,
                action=AuditLog.ACTION_LOGIN,
                ip_address=request.remote_addr,
                user_agent=str(request.user_agent)[:200] if request.user_agent else '',
            )
            db.session.commit()
        except Exception as audit_error:
            db.session.rollback()
            import logging
            logging.warning(f"审计日志写入失败: {audit_error}")

        return jsonify({
            'success': True,
            'user': user.to_dict(),
            'redirect': url_for('main.index'),
        })

    except Exception as e:
        import logging
        logging.error(f"登录过程发生错误: {e}")
        return jsonify({'error': f'登录失败: {str(e)}'}), 500


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    display_name = (data.get('display_name') or username).strip()
    role = data.get('role', 'group')
    group_code = (data.get('group_code') or '').strip()
    member_count = data.get('member_count', 1)

    # 基本校验
    if not username or len(username) < 2:
        return jsonify({'error': '用户名至少需要2个字符'}), 400
    if len(password) < 6:
        return jsonify({'error': '密码至少需要6个字符'}), 400
    if role not in ('group',):
        return jsonify({'error': '目前只开放小组账号注册，教师账号请联系管理员创建'}), 403

    from models import db, User, Group, SkillProgress, AuditLog

    # 检查用户名唯一性
    if User.query.filter_by(username=username).first():
        return jsonify({'error': f'用户名 {username} 已被注册'}), 409

    # 检查小组编号唯一性
    if role == 'group' and group_code:
        if Group.query.filter_by(group_code=group_code).first():
            return jsonify({'error': f'小组编号 {group_code} 已被注册'}), 409

    # 创建用户
    user = User(
        username=username,
        display_name=display_name,
        role=role,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # 获取 user.id

    # 如果是小组，同时创建 group 记录
    if role == 'group':
        grp = Group(
            user_id=user.id,
            group_code=group_code or f'G{user.id:03d}',
            course=data.get('course', 'emotion'),
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
        user_id=user.id,
        action=AuditLog.ACTION_CREATE_GROUP if role == 'group' else 'REGISTER',
        detail={'username': username, 'role': role, 'group_code': group_code},
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:200],
    )
    db.session.commit()

    # 自动登录
    session['user_id'] = user.id
    session['role'] = user.role
    session['username'] = user.username
    session.permanent = True

    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'redirect': url_for('main.index'),
    })


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    user_id = session.get('user_id')
    if user_id:
        from models import db, AuditLog
        AuditLog.log(
            user_id=user_id,
            action=AuditLog.ACTION_LOGOUT,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:200],
        )
        db.session.commit()

    session.clear()
    return redirect(url_for('auth.login_page'))


@auth_bp.route('/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({'error': '未登录'}), 401
    result = user.to_dict()
    if user.group:
        result['group'] = user.group.to_dict()
    return jsonify(result)


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password or not new_password:
        return jsonify({'error': '旧密码和新密码都不能为空'}), 400
    if len(new_password) < 6:
        return jsonify({'error': '新密码至少需要6个字符'}), 400

    from models import db, User, AuditLog
    user = User.query.get(session['user_id'])
    if not user.check_password(old_password):
        return jsonify({'error': '旧密码不正确'}), 400

    user.set_password(new_password)
    db.session.commit()

    AuditLog.log(
        user_id=user.id,
        action='CHANGE_PASSWORD',
        detail={'username': user.username},
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:200],
    )
    db.session.commit()

    return jsonify({'success': True, 'message': '密码修改成功'})


# ──────────────────────────────────────────────────────────────────────────────
# 教师/管理员：小组管理 API
# ──────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/groups', methods=['GET'])
@teacher_required
def list_groups():
    """教师/超管获取所有小组列表"""
    from models import User, Group
    groups = Group.query.join(User).filter(User.role == 'group').all()
    return jsonify({
        'groups': [g.to_dict() for g in groups],
    })


@auth_bp.route('/groups/<int:group_id>', methods=['GET'])
@teacher_required
def get_group(group_id):
    """教师/超管获取单个小组详情"""
    from models import User, Group
    grp = Group.query.get_or_404(group_id)
    user = grp.user
    return jsonify({
        'user': user.to_dict(),
        'group': grp.to_dict(),
    })


@auth_bp.route('/groups/<int:group_id>/reset-password', methods=['POST'])
@teacher_required
def reset_group_password(group_id):
    """教师/超管重置小组密码"""
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password', '')
    if not new_password or len(new_password) < 6:
        return jsonify({'error': '新密码至少需要6个字符'}), 400

    from models import db, User, Group, AuditLog
    grp = Group.query.get_or_404(group_id)
    user = grp.user
    user.set_password(new_password)
    db.session.commit()

    AuditLog.log(
        user_id=session['user_id'],
        action='RESET_PASSWORD',
        target_type='group',
        target_id=str(group_id),
        detail={'group_code': grp.group_code, 'reset_by': session['username']},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'小组 {grp.group_code} 的密码已重置'})


@auth_bp.route('/groups/<int:group_id>', methods=['DELETE'])
@admin_required
def delete_group(group_id):
    """超管删除小组账号"""
    from models import db, User, Group, AuditLog, FaceDataset, AudioDataset, EcobottleDataset, ModelFile, Notebook, LeaderboardRecord, SkillProgress
    from config import Config
    import os
    import shutil

    # 数据目录路径
    EMOTION_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'emotion_data')
    AUDIO_DATA_DIR = os.path.join(Config.BASE_DIR, 'data', 'audio_data')

    grp = Group.query.get_or_404(group_id)
    user = grp.user
    group_code = grp.group_code
    username = user.username
    user_id = user.id

    # 收集需要清理的文件路径
    file_paths_to_delete = []

    # 收集数据集文件路径并删除记录
    for Model, records in [
        (FaceDataset, FaceDataset.query.filter_by(group_id=grp.user_id).all()),
        (AudioDataset, AudioDataset.query.filter_by(group_id=grp.user_id).all()),
        (EcobottleDataset, EcobottleDataset.query.filter_by(group_id=grp.user_id).all()),
        (ModelFile, ModelFile.query.filter_by(group_id=grp.user_id).all()),
        (Notebook, Notebook.query.filter_by(group_id=grp.user_id).all()),
        (LeaderboardRecord, LeaderboardRecord.query.filter_by(group_id=grp.user_id).all()),
    ]:
        for r in records:
            if r.file_path:
                file_paths_to_delete.append(r.file_path)
        for r in records:
            db.session.delete(r)

    # 删除技能进度
    sp = SkillProgress.query.filter_by(group_id=grp.user_id).first()
    if sp:
        db.session.delete(sp)

    # 删除小组编辑器工作区
    for dir_name in ['editor_workspaces', 'editor_codes']:
        workspace_dir = os.path.join('data', dir_name, f'G{grp.user_id}')
        if os.path.exists(workspace_dir):
            file_paths_to_delete.append(workspace_dir)

    # 删除小组的表情和音频数据目录
    file_paths_to_delete.append(os.path.join(EMOTION_DATA_DIR, username))
    file_paths_to_delete.append(os.path.join(AUDIO_DATA_DIR, username))

    # 先删除该用户的审计日志记录（避免外键约束问题）
    AuditLog.query.filter_by(user_id=user.id).delete()

    # 删除 Group 记录
    db.session.delete(grp)

    # 删除 User 记录
    db.session.delete(user)
    db.session.commit()

    # 清理文件
    for fp in file_paths_to_delete:
        try:
            if os.path.isdir(fp):
                shutil.rmtree(fp, ignore_errors=True)
            elif os.path.isfile(fp):
                os.remove(fp)
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
        action=AuditLog.ACTION_DELETE_GROUP,
        target_type='group',
        target_id=str(group_id),
        detail={'deleted_user_id': user_id, 'group_code': group_code, 'files_cleaned': len(file_paths_to_delete)},
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({'success': True, 'message': f'小组 {group_code} 已删除'})

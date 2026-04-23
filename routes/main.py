from flask import Blueprint, render_template, redirect, url_for, session

# 导入登录验证装饰器
from routes.auth import login_required

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    return render_template('index.html')

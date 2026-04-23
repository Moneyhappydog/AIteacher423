"""
缓存工具模块

提供 Redis 缓存装饰器，用于高并发优化。
"""

from functools import wraps
from flask import request
from flask_caching import Cache

# 全局缓存实例
cache = Cache()


def init_cache(app, config):
    """初始化缓存"""
    cache.init_app(app, config)


def cached(timeout=None, key_prefix='view:%s'):
    """
    缓存装饰器

    使用方式：
        @cached(timeout=60)
        def get_data():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 生成缓存 key
            cache_key = key_prefix % request.path
            if request.args:
                cache_key += '?' + request.query_string.decode('utf-8')

            rv = cache.get(cache_key)
            if rv is None:
                rv = f(*args, **kwargs)
                cache.set(cache_key, rv, timeout=timeout)
            return rv
        return decorated_function
    return decorator


def invalidate_cache(cache_key):
    """清除指定缓存"""
    cache.delete(cache_key)


def invalidate_cache_prefix(prefix):
    """清除指定前缀的缓存"""
    # 遍历所有已知键匹配前缀（实际生产中建议维护键索引或使用 scan_iter）
    cache.delete_many(*[k for k in (cache.cache._cache.keys() if hasattr(cache.cache, '_cache') else [])
                        if isinstance(k, str) and k.startswith(prefix)])

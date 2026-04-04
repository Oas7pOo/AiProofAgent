import time
import logging
from functools import wraps
from datetime import datetime
import os

# 创建profiler专用的logger
profiler_logger = logging.getLogger('AiProofAgent.Profiler')
profiler_logger.setLevel(logging.DEBUG)

# 确保log文件夹存在
log_dir = "log"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 生成以时间命名的日志文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
profiler_log_file = os.path.join(log_dir, f"time_{timestamp}.log")

# 添加文件处理器
fh = logging.FileHandler(profiler_log_file, encoding='utf-8')
fh.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
fh.setFormatter(fmt)
profiler_logger.addHandler(fh)

# 记录装饰器的初始化信息
profiler_logger.info(f"Profiler initialized. Log file: {profiler_log_file}")

# 函数调用计数和时间统计
function_stats = {}

def profile(func):
    """装饰器：记录函数的运行时间和调用次数"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 记录函数名
        func_name = f"{func.__module__}.{func.__name__}"
        
        # 初始化函数统计信息
        if func_name not in function_stats:
            function_stats[func_name] = {
                'call_count': 0,
                'total_time': 0.0,
                'avg_time': 0.0
            }
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行函数
        result = func(*args, **kwargs)
        
        # 计算运行时间
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # 更新统计信息
        stats = function_stats[func_name]
        stats['call_count'] += 1
        stats['total_time'] += elapsed_time
        stats['avg_time'] = stats['total_time'] / stats['call_count']
        
        # 记录函数调用信息
        profiler_logger.info(f"Function: {func_name}, Call Count: {stats['call_count']}, Elapsed Time: {elapsed_time:.4f}s, Total Time: {stats['total_time']:.4f}s, Avg Time: {stats['avg_time']:.4f}s")
        
        return result
    return wrapper

def print_stats():
    """打印所有函数的统计信息"""
    profiler_logger.info("=== Function Profile Statistics ===")
    for func_name, stats in function_stats.items():
        profiler_logger.info(f"{func_name}: Calls={stats['call_count']}, Total={stats['total_time']:.4f}s, Avg={stats['avg_time']:.4f}s")
    profiler_logger.info("================================")

import logging
import sys
import os
from datetime import datetime

def get_logger(name="AiProofAgent"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.WARNING)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.WARNING)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    logger.propagate = False
    return logger


def setup_root_logger(level=logging.WARNING):
    logger = get_logger("AiProofAgent")
    logger.setLevel(level)
    for h in logger.handlers:
        h.setLevel(level)
    return logger


def setup_file_logger():
    """设置文件日志记录器，每次运行以时间命名日志文件"""
    # 确保log文件夹存在
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 生成以时间命名的日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"app_{timestamp}.log")
    
    # 获取根日志器
    root_logger = logging.getLogger("AiProofAgent")
    
    # 清除现有的文件处理器
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
    
    # 添加文件处理器
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)
    
    # 记录日志文件创建信息
    root_logger.warning(f"日志文件已创建: {log_file}")
    
    return log_file

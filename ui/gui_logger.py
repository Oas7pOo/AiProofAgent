import logging

class TkTextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        if self.text_widget:
            self.text_widget.after(0, self._append, msg)

    def _append(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")


def setup_gui_logger(text_widget, level=logging.INFO):
    """为 GUI 界面单独添加 TkTextHandler"""
    # 获取根 logger，确保捕获所有子 logger 的日志
    logger = logging.getLogger("AiProofAgent")
    logger.setLevel(level)
    
    # 确保日志传播到父 logger
    logger.propagate = False
    
    # 移除旧的 GUI handler 如果存在
    logger.handlers = [h for h in logger.handlers if not isinstance(h, TkTextHandler)]
    
    gui_handler = TkTextHandler(text_widget)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    gui_handler.setFormatter(fmt)
    gui_handler.setLevel(level)
    logger.addHandler(gui_handler)
    
    # 同时设置所有子 logger 的级别
    for name in list(logging.root.manager.loggerDict.keys()):
        if name.startswith("AiProofAgent"):
            child_logger = logging.getLogger(name)
            child_logger.setLevel(level)
            # 确保子 logger 不重复处理（避免重复输出）
            if not any(isinstance(h, TkTextHandler) for h in child_logger.handlers):
                child_logger.addHandler(gui_handler)

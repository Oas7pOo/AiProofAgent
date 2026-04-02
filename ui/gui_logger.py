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
    logger = logging.getLogger("AiProofAgent")
    logger.setLevel(level)
    
    # 移除旧的 GUI handler 如果存在
    logger.handlers = [h for h in logger.handlers if not isinstance(h, TkTextHandler)]
    
    gui_handler = TkTextHandler(text_widget)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    gui_handler.setFormatter(fmt)
    gui_handler.setLevel(level)
    logger.addHandler(gui_handler)

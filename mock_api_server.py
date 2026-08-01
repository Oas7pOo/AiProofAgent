import threading
import time
import json
import uuid
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from flask import Flask, request as flask_request, jsonify

app = Flask(__name__)
request_queue = []
request_lock = threading.Lock()
ui_update_queue = queue.Queue()
selected_request_id = None

def generate_openai_chat_response(content):
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "mock-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content.strip()},
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(content),
            "total_tokens": len(content)
        }
    }

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = flask_request.get_json()
        req_id = str(uuid.uuid4())[:8]
        timestamp = time.strftime("%H:%M:%S")
        
        messages = data.get('messages', [])
        model = data.get('model', 'unknown')
        temperature = data.get('temperature', 0.7)
        
        req_info = {
            'id': req_id,
            'timestamp': timestamp,
            'model': model,
            'temperature': temperature,
            'messages': messages,
            'response': None,
            'event': threading.Event()
        }
        
        with request_lock:
            request_queue.append(req_info)
        
        ui_update_queue.put('update')
        
        if not req_info['event'].wait(timeout=60000):
            return jsonify(generate_openai_chat_response("[SYSTEM] 请求超时，未收到人工回复")), 504
        
        if req_info['response'] is None:
            return jsonify(generate_openai_chat_response("[SYSTEM] 人工取消了回复")), 400
        
        return jsonify(generate_openai_chat_response(req_info['response']))
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/v1/completions', methods=['POST'])
def completions():
    try:
        data = flask_request.get_json()
        req_id = str(uuid.uuid4())[:8]
        timestamp = time.strftime("%H:%M:%S")
        
        prompt = data.get('prompt', '')
        model = data.get('model', 'unknown')
        
        req_info = {
            'id': req_id,
            'timestamp': timestamp,
            'model': model,
            'temperature': 0,
            'messages': [{'role': 'user', 'content': prompt}],
            'response': None,
            'event': threading.Event()
        }
        
        with request_lock:
            request_queue.append(req_info)
        
        ui_update_queue.put('update')
        
        if not req_info['event'].wait(timeout=300):
            return jsonify({"error": "Request timeout"}), 504
        
        if req_info['response'] is None:
            return jsonify({"error": "Cancelled"}), 400
        
        return jsonify({
            "id": f"cmpl-{uuid.uuid4().hex[:24]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": "mock-model",
            "choices": [{
                "text": req_info['response'].strip(),
                "index": 0,
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt),
                "completion_tokens": len(req_info['response']),
                "total_tokens": len(prompt) + len(req_info['response'])
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

def start_flask_server(port=8080):
    app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False)

request_listbox = None
request_detail = None
response_text = None
root = None

def check_ui_updates():
    while not ui_update_queue.empty():
        try:
            ui_update_queue.get_nowait()
            update_request_list()
        except queue.Empty:
            break
    root.after(100, check_ui_updates)

def update_request_list():
    if not request_listbox:
        return
    
    current_selection = None
    if request_listbox.curselection():
        current_selection = request_listbox.curselection()[0]
    
    request_listbox.delete(0, tk.END)
    
    with request_lock:
        for req in request_queue:
            status = "● 等待中" if req['response'] is None else "✓ 已回复"
            request_listbox.insert(tk.END, f"[{req['timestamp']}] {req['id']} {status}")
    
    if current_selection is not None and current_selection < request_listbox.size():
        request_listbox.selection_set(current_selection)
        on_request_select(None)

def on_request_select(event):
    global selected_request_id
    
    if not request_listbox or not request_detail:
        return
    
    selection = request_listbox.curselection()
    if not selection:
        return
    
    index = selection[0]
    
    with request_lock:
        if index < len(request_queue):
            req = request_queue[index]
            selected_request_id = req['id']
            
            detail = f"请求ID: {req['id']}\n"
            detail += f"时间: {req['timestamp']}\n"
            detail += f"模型: {req['model']}\n"
            detail += f"温度: {req['temperature']}\n"
            detail += "------------------------\n"
            
            for msg in req['messages']:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                detail += f"{role}:\n{content}\n\n"
            
            request_detail.delete("1.0", tk.END)
            request_detail.insert("1.0", detail)
            
            if req['response'] is not None:
                response_text.delete("1.0", tk.END)
                response_text.insert("1.0", req['response'])

def copy_request_detail():
    if not root or not request_detail:
        return

    detail = request_detail.get("1.0", "end-1c")
    if not detail:
        messagebox.showwarning("提示", "请先选择一个请求")
        return

    root.clipboard_clear()
    root.clipboard_append(detail)
    root.update()
    messagebox.showinfo("成功", "请求详情已复制到剪贴板")

def submit_response():
    global selected_request_id
    
    if not selected_request_id or not response_text:
        messagebox.showwarning("提示", "请先选择一个请求")
        return
    
    content = response_text.get("1.0", tk.END)
    
    with request_lock:
        for req in request_queue:
            if req['id'] == selected_request_id:
                if req['response'] is None:
                    req['response'] = content
                    req['event'].set()
                    messagebox.showinfo("成功", "回复已发送")
                else:
                    messagebox.showwarning("提示", "该请求已回复过")
                break
    
    response_text.delete("1.0", tk.END)
    update_request_list()

def cancel_request():
    global selected_request_id
    
    if not selected_request_id:
        messagebox.showwarning("提示", "请先选择一个请求")
        return
    
    with request_lock:
        for req in request_queue:
            if req['id'] == selected_request_id:
                if req['response'] is None:
                    req['response'] = None
                    req['event'].set()
                    messagebox.showinfo("已取消", "请求已取消")
                else:
                    messagebox.showwarning("提示", "该请求已回复过")
                break
    
    response_text.delete("1.0", tk.END)
    request_detail.delete("1.0", tk.END)
    update_request_list()

def clear_completed():
    with request_lock:
        completed = [req for req in request_queue if req['response'] is not None]
        for req in completed:
            request_queue.remove(req)
    
    response_text.delete("1.0", tk.END)
    request_detail.delete("1.0", tk.END)
    update_request_list()
    messagebox.showinfo("完成", "已清除所有已处理的请求")

def create_gui():
    global root, request_listbox, request_detail, response_text
    
    root = tk.Tk()
    root.title("Mock API Server")
    root.geometry("1200x700")
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    tab1 = ttk.Frame(notebook)
    notebook.add(tab1, text="请求监控")
    
    left_frame = ttk.Frame(tab1)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
    
    right_frame = ttk.Frame(tab1)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
    
    ttk.Label(left_frame, text="请求队列", font=('Arial', 12, 'bold')).pack(pady=5)
    
    request_listbox = tk.Listbox(left_frame, width=40)
    request_listbox.pack(fill=tk.BOTH, expand=True, padx=5)
    request_listbox.bind('<<ListboxSelect>>', on_request_select)
    
    ttk.Label(left_frame, text="请求详情", font=('Arial', 12, 'bold')).pack(pady=5)
    
    request_detail = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, height=20)
    request_detail.pack(fill=tk.BOTH, expand=True, padx=5)

    request_detail_button_frame = ttk.Frame(left_frame)
    request_detail_button_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
    ttk.Button(
        request_detail_button_frame,
        text="复制请求内容",
        command=copy_request_detail,
    ).pack(side=tk.RIGHT)
    
    ttk.Label(right_frame, text="回复内容", font=('Arial', 12, 'bold')).pack(pady=5)
    
    response_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=25)
    response_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
    
    button_frame = ttk.Frame(right_frame)
    button_frame.pack(fill=tk.X, pady=5)
    
    ttk.Button(button_frame, text="发送回复", command=submit_response).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="取消请求", command=cancel_request).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="清除已处理", command=clear_completed).pack(side=tk.RIGHT, padx=5)
    
    tab2 = ttk.Frame(notebook)
    notebook.add(tab2, text="服务器设置")
    
    settings_frame = ttk.LabelFrame(tab2, text="服务器配置")
    settings_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    ttk.Label(settings_frame, text="服务器地址:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
    ttk.Label(settings_frame, text="http://127.0.0.1:8080").grid(row=0, column=1, sticky=tk.W, padx=10, pady=10)
    
    ttk.Label(settings_frame, text="可用接口:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
    ttk.Label(settings_frame, text="POST /v1/chat/completions").grid(row=2, column=0, sticky=tk.W, padx=30, pady=2)
    ttk.Label(settings_frame, text="POST /v1/completions").grid(row=3, column=0, sticky=tk.W, padx=30, pady=2)
    ttk.Label(settings_frame, text="GET /health").grid(row=4, column=0, sticky=tk.W, padx=30, pady=2)
    
    ttk.Label(settings_frame, text="使用说明:").grid(row=5, column=0, sticky=tk.W, padx=10, pady=10)
    instruction = """1. 将您的程序的 Base URL 设置为: http://127.0.0.1:8080
2. API Key 可以填写任意值（不会验证）
3. 当请求到达时，左侧列表会显示请求
4. 点击选择一个请求查看详情
5. 在右侧文本框中输入回复内容
6. 点击"发送回复"将内容返回给请求方"""
    ttk.Label(settings_frame, text=instruction, wraplength=500, justify=tk.LEFT).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=10, pady=5)
    
    root.after(100, check_ui_updates)
    
    return root

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_flask_server, args=(8080,), daemon=True)
    server_thread.start()
    time.sleep(1)
    print("Mock API Server started on http://127.0.0.1:8080")
    
    root = create_gui()
    root.mainloop()

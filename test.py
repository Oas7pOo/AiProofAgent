import requests
import json

url = "http://127.0.0.1:8317/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "123456"  # 必须和 config.yaml 中的密钥一致
}
data = {
    "model": "gpt-5.6-terra",
    "messages": [{"role": "user", "content": "你好，请用一句话介绍你自己"}]
}

response = requests.post(url, json=data, headers=headers)
print("状态码:", response.status_code)
if response.status_code == 200:
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
else:
    print("错误详情:", response.text)
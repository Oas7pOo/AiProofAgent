import requests
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_api_request():
    """测试 API 请求"""
    # 从 config.yaml 读取配置
    import yaml
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 测试代码也需要优先读取根级别的 api_key
    api_key = config.get('api_key', '') or config.get('llm', {}).get('api_key', '')
    base_url = config.get('base_url', '') or config.get('llm', {}).get('base_url', 'https://apis.iflow.cn/v1')
    model = config.get('model', '') or config.get('llm', {}).get('model', 'deepseek-v3.2')
    timeout = config.get('timeout', 120) or config.get('llm', {}).get('timeout', 120)
    
    # 打印 API Key（部分隐藏）
    hidden_api_key = api_key[:4] + '***' + api_key[-4:] if api_key else ''
    logger.info(f"测试配置: URL={base_url}, Model={model}, Key已填入={'是' if api_key else '否'}, Key={hidden_api_key}")
    
    # 测试 1: 使用 requests 直接发送请求（模拟之前的成功代码）
    logger.info("测试 1: 使用 requests 直接发送请求")
    try:
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        
        # 构建 payload
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, test message."}
            ]
        }
        
        # 拼接 URL
        base_url_clean = str(base_url or "").rstrip("/")
        url = f"{base_url_clean}/chat/completions"
        logger.info(f"发送请求到: {url}")
        
        # 发送请求
        response = session.post(
            url,
            json=payload,
            timeout=timeout
        )
        
        logger.info(f"响应状态码: {response.status_code}")
        logger.info(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"响应 JSON: {json.dumps(result, indent=2, ensure_ascii=False)}")
                if 'choices' in result:
                    logger.info("✅ 响应包含 choices 字段")
                else:
                    logger.error("❌ 响应缺失 choices 字段")
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON 解析失败: {e}")
        else:
            logger.error(f"❌ 请求失败，状态码: {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ 测试 1 失败: {e}")
    
    # 测试 2: 使用 OpenAI SDK 发送请求（当前实现）
    logger.info("\n测试 2: 使用 OpenAI SDK 发送请求")
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key if api_key else "EMPTY",
            base_url=base_url,
            timeout=timeout
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, test message."}
            ],
            timeout=timeout
        )
        
        logger.info(f"响应对象: {response}")
        if hasattr(response, 'choices'):
            logger.info("✅ 响应包含 choices 字段")
            logger.info(f"生成内容: {response.choices[0].message.content}")
        else:
            logger.error("❌ 响应缺失 choices 字段")
            # 尝试获取原始响应
            if hasattr(response, 'model_dump'):
                raw_dict = response.model_dump()
                logger.info(f"原始响应: {json.dumps(raw_dict, indent=2, ensure_ascii=False)}")
                
    except Exception as e:
        logger.error(f"❌ 测试 2 失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_request()

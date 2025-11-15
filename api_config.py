"""
API 配置文件

在此处填写/管理 OpenAI 兼容的 API Key 与 Base URL（“节点”）。
推荐使用环境变量覆盖：
- OPENAI_API_KEY：API 密钥
- OPENAI_BASE_URL：Base URL（例如 https://api.openai.com/v1 或自建兼容网关）
- OPENAI_GPT_MODEL：可选，默认 gpt-4o
- OPENAI_WHISPER_MODEL：可选，默认 whisper-1
"""

from dataclasses import dataclass
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore


# 直接在此写入默认值（会被同名环境变量覆盖）
API_KEY = ""
BASE_URL = "https://api.openai.com/v1"
GPT_MODEL = "gpt-4o"
WHISPER_MODEL = "whisper-1"


@dataclass
class APISettings:
    api_key: str
    base_url: str
    gpt_model: str
    whisper_model: str


def load_settings() -> APISettings:
    # 尝试从同目录的 .env 读取（可选）
    if load_dotenv is not None:
        env_path = Path(__file__).with_name('.env')
        if env_path.exists():
            load_dotenv(env_path)
    api_key = os.getenv("OPENAI_API_KEY", API_KEY)
    base_url = os.getenv("OPENAI_BASE_URL", BASE_URL)
    gpt_model = os.getenv("OPENAI_GPT_MODEL", GPT_MODEL)
    whisper_model = os.getenv("OPENAI_WHISPER_MODEL", WHISPER_MODEL)
    return APISettings(
        api_key=api_key,
        base_url=base_url,
        gpt_model=gpt_model,
        whisper_model=whisper_model,
    )



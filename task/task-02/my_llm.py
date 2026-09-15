# my_llm.py
import os
from typing import Optional
from hello_agents import HelloAgentsLLM
from hello_agents.core.llm_adapters import create_adapter


class MyLLM(HelloAgentsLLM):
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = "auto",
        **kwargs
    ):
        # 检查provider是否为我们想处理的'dashscope'
        if provider == "dashscope":
            print("正在使用自定义的 DashScope Provider")

            # 解析 DashScope 的凭证
            self.api_key = api_key or os.getenv("LLM_API_KEY")
            self.base_url = base_url or os.getenv("LLM_BASE_URL") or "https://coding.dashscope.aliyuncs.com/v1"

            # 验证凭证是否存在
            if not self.api_key:
                raise ValueError("DashScope API key not found. Please set LLM_API_KEY environment variable.")

            # 设置默认模型和其他参数
            self.model = model or os.getenv("LLM_MODEL_ID") or "qwen-plus"
            self.temperature = kwargs.get('temperature', 0.7)
            self.max_tokens = kwargs.get('max_tokens')
            self.timeout = int(kwargs.get('timeout', os.getenv("LLM_TIMEOUT", "60")))
            self.kwargs = kwargs

            # 通过 create_adapter 创建适配器（DashScope 兼容 OpenAI 格式，自动走 OpenAIAdapter）
            self._adapter = create_adapter(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                model=self.model,
            )

            # 最后一次调用的统计信息
            self.last_call_stats = None

        else:
            # 如果不是 dashscope, 则完全使用父类的原始逻辑来处理
            super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)

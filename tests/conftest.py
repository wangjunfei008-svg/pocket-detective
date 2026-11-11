"""让测试不吃机器上的密钥和部署开关。"""

from __future__ import annotations

import pytest

_ENV_KEYS = (
    "MODELSCOPE_API_TOKEN",
    "MODELSCOPE_API_KEY",
    "DASHSCOPE_API_KEY",
    "POCKET_DETECTIVE_FORCE_MOCK",
    "POCKET_DETECTIVE_ALLOW_ENDPOINT_CONFIG",
    "DGX_SPARK_BASE_URL",
    "DGX_SPARK_MODEL",
    "LOCAL_LLM_BASE_URL",
    "LOCAL_LLM_MODEL",
)


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)

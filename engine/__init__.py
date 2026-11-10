"""游戏引擎包：算力双模客户端 + 科学原理数据库。"""

from engine.llm_client import (
    MODE_CLOUD,
    MODE_LOCAL,
    MODE_MOCK,
    BackendInfo,
    LLMClient,
    mock_reply,
)
from engine.science_facts import (
    ExperimentResult,
    InspectResult,
    ScienceEngine,
    load_scenario,
    scenario_path,
)

__all__ = [
    "LLMClient",
    "BackendInfo",
    "MODE_LOCAL",
    "MODE_CLOUD",
    "MODE_MOCK",
    "mock_reply",
    "ScienceEngine",
    "ExperimentResult",
    "InspectResult",
    "load_scenario",
    "scenario_path",
]

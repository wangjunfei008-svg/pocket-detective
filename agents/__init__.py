"""智能体包：角色人设与游戏状态机。"""

from agents.characters import (
    CHILD_SAFETY_RULES,
    MOOD_CONFESS,
    MOOD_NERVOUS,
    MOOD_NORMAL,
    MOOD_SURPRISED,
    TONE_RULES,
    build_messages,
    build_sparky_messages,
    build_system_prompt,
    mood_from_guilt,
)
from agents.game_state import ENERGY_MAX, MAX_GUILT, ChatTurn, GameState, STAGE_PLAYING, STAGE_WON

__all__ = [
    "GameState",
    "ChatTurn",
    "STAGE_PLAYING",
    "STAGE_WON",
    "MAX_GUILT",
    "ENERGY_MAX",
    "mood_from_guilt",
    "build_messages",
    "build_system_prompt",
    "build_sparky_messages",
    "CHILD_SAFETY_RULES",
    "TONE_RULES",
    "MOOD_NORMAL",
    "MOOD_SURPRISED",
    "MOOD_NERVOUS",
    "MOOD_CONFESS",
]

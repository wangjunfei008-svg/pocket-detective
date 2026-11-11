"""道具背包、线索收集度与心虚状态机。

`GameState` 是纯 Python 可测试对象（不依赖 Streamlit），
`app.py` 只负责把它渲染成绘本界面。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.characters import MOOD_CONFESS, MOOD_NORMAL, mood_from_guilt
from engine.science_facts import OUTCOME_SUCCESS, ScienceEngine

STAGE_PLAYING = "playing"
STAGE_DEDUCTION = "deduction"
STAGE_WON = "won"

MAX_GUILT = 100
ENERGY_MAX = 100
# 没做对这个人的实验之前，心虚度到这里就停住，不能靠刷问题招供。
GUILT_CAP_BEFORE_EXPERIMENT = 55


@dataclass
class ChatTurn:
    role: str  # player | suspect | sparky | system
    text: str
    speaker: str = ""
    kind: str = "say"  # say | experiment | clue | confession | help | system
    suspect_id: str = ""
    item_id: str = ""
    mood: str = MOOD_NORMAL
    fact_id: Optional[str] = None
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "text": self.text,
            "speaker": self.speaker,
            "kind": self.kind,
            "suspect_id": self.suspect_id,
            "item_id": self.item_id,
            "mood": self.mood,
            "fact_id": self.fact_id,
        }


class GameState:
    """一局游戏的完整状态：背包、线索、心虚度、能量、阶段。"""

    def __init__(self, engine: Optional[ScienceEngine] = None, player_name: str = "小侦探"):
        self.engine = engine or ScienceEngine()
        self.player_name = player_name or "小侦探"
        self.created_at = time.time()
        self.stage: str = STAGE_PLAYING
        self.active_suspect: str = (self.engine.suspects()[0]["id"] if self.engine.suspects() else "")
        self.active_item: Optional[str] = None
        self.energy: int = 0
        self.score: int = 0
        self.steps: int = 0
        self.inspected: List[str] = []
        self.collected_clues: List[str] = []
        self.solved_experiments: List[str] = []
        self.confessed: List[str] = []
        self.guilt: Dict[str, int] = {s["id"]: 0 for s in self.engine.suspects()}
        self.moods: Dict[str, str] = {s["id"]: MOOD_NORMAL for s in self.engine.suspects()}
        self.asked_topics: Dict[str, set] = {s["id"]: set() for s in self.engine.suspects()}
        self.observed_with_magnifier: set = set()
        self.history: Dict[str, List[ChatTurn]] = {s["id"]: [] for s in self.engine.suspects()}
        self.sparky_history: List[ChatTurn] = []
        self.journal: List[str] = []
        self.deduction_attempts: int = 0
        self.final_verdict: Optional[Dict[str, Any]] = None
        self.last_event: Dict[str, Any] = {}
        self.facts_learned: List[str] = []

    # ------------------------------------------------------------ 背包
    @property
    def items(self) -> List[Dict[str, Any]]:
        return self.engine.items()

    def select_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        item = self.engine.item(item_id)
        if item is None:
            return None
        self.active_item = item_id if self.active_item != item_id else None
        return item

    @property
    def active_item_label(self) -> str:
        return self.engine.item_label(self.active_item) if self.active_item else "（手里空空的）"

    # ------------------------------------------------------------ 线索
    def has_clue(self, clue_id: str) -> bool:
        return clue_id in self.collected_clues

    def add_clue(self, clue_id: str) -> bool:
        if not clue_id or self.has_clue(clue_id):
            return False
        clue = self.engine.clue(clue_id)
        if clue is None:
            return False
        self.collected_clues.append(clue_id)
        self.score += 30
        fact_id = clue.get("related_fact")
        if fact_id and fact_id not in self.facts_learned:
            self.facts_learned.append(fact_id)
        self.journal.append(f"📌 收录线索：{clue.get('emoji', '')} {clue.get('name', '')}")
        if self.stage == STAGE_PLAYING and self.engine.can_deduct(self.collected_clues):
            self.stage = STAGE_DEDUCTION
        return True

    def clue_objects(self) -> List[Dict[str, Any]]:
        return [self.engine.clue(c) for c in self.collected_clues if self.engine.clue(c)]

    def inspect(self, hotspot_id: str) -> Dict[str, Any]:
        """勘查现场热点（自动带上手里的放大镜）。"""
        self.steps += 1
        result = self.engine.inspect(hotspot_id, self.active_item)
        added = False
        if result.clue_id:
            added = self.add_clue(result.clue_id)
            if added and hotspot_id not in self.inspected:
                self.inspected.append(hotspot_id)
        if not added and result.clue_id is None and hotspot_id not in self.inspected:
            self.inspected.append(hotspot_id)
        if result.energy_delta and added:
            self._gain_energy(result.energy_delta)
        self.last_event = {
            "type": "inspect",
            "hotspot_id": hotspot_id,
            "outcome": result.outcome,
            "title": result.title,
            "text": result.text,
            "added": added,
            "requires_item": result.requires_item,
            "fact_id": result.science_fact_id,
        }
        return self.last_event

    # ------------------------------------------------------------ 对话
    def push_turn(self, suspect_id: str, turn: ChatTurn) -> None:
        self.history.setdefault(suspect_id, []).append(turn)
        self.steps += 1

    def ask(self, suspect_id: str, question: str) -> Dict[str, Any]:
        """向嫌疑人提问：命中预设话题则推进心虚度，返回回复与状态变化。"""
        suspect = self.engine.suspect(suspect_id) or {}
        self.steps += 1
        topic = self._match_topic(suspect, question)
        asked = self.asked_topics.setdefault(suspect_id, set())
        if topic:
            reply = topic.get("reply", "")
            topic_id = topic.get("id")
            if topic_id and topic_id in asked:
                delta = 0
            else:
                if topic_id:
                    asked.add(topic_id)
                delta = int(topic.get("guilt_delta", 0))
        else:
            reply = ""
            delta = 0
        fact_id = suspect.get("science_fact_id")
        mood = self.mood_of(suspect_id)
        turn = ChatTurn(role="player", text=question, speaker=self.player_name, suspect_id=suspect_id, mood=mood)
        self.push_turn(suspect_id, turn)
        # 先落孩子的提问，再结算心虚度：满格时招供台词才会自然地接在提问后面
        guilt = self.add_guilt(suspect_id, delta)
        mood = self.mood_of(suspect_id)
        self.last_event = {
            "type": "ask",
            "suspect_id": suspect_id,
            "topic_id": topic.get("id") if topic else None,
            "reply": reply,
            "guilt": guilt,
            "mood": mood,
            "fact_id": fact_id,
            "needs_llm": not bool(reply),
        }
        return self.last_event

    def record_reply(self, suspect_id: str, text: str, *, kind: str = "say", fact_id: Optional[str] = None) -> ChatTurn:
        turn = ChatTurn(
            role="suspect",
            text=text,
            speaker=(self.engine.suspect(suspect_id) or {}).get("name", ""),
            kind=kind,
            suspect_id=suspect_id,
            mood=self.moods.get(suspect_id, MOOD_NORMAL),
            fact_id=fact_id,
        )
        history = self.history.setdefault(suspect_id, [])
        if history and history[-1].kind == "confession" and kind != "confession":
            history.insert(len(history) - 1, turn)
        else:
            history.append(turn)
        return turn

    def _match_topic(self, suspect: Dict[str, Any], question: str) -> Optional[Dict[str, Any]]:
        from agents.characters import _normalize_question  # 延迟导入避免循环

        normalized = _normalize_question(question)
        best: Optional[Dict[str, Any]] = None
        best_hits = 0
        for topic in suspect.get("topics") or []:
            hits = sum(1 for word in topic.get("keywords") or [] if _normalize_question(word) in normalized)
            if hits > best_hits:
                best, best_hits = topic, hits
        return best

    # ------------------------------------------------------------ 实验
    def run_experiment(self, suspect_id: str, item_id: Optional[str] = None) -> Dict[str, Any]:
        item_id = item_id or self.active_item
        if not item_id:
            self.last_event = {"type": "experiment", "outcome": "no_item", "text": "你手里还没有道具，先从科学小背包里选一个吧！"}
            return self.last_event
        self.steps += 1
        result = self.engine.experiment(suspect_id, item_id, already_solved=self.solved_experiments)
        guilt_delta = int(result.guilt_delta)
        energy_delta = int(result.energy_delta)
        if item_id == "magnifier":
            if suspect_id in self.observed_with_magnifier:
                guilt_delta = 0
                energy_delta = 0
            else:
                self.observed_with_magnifier.add(suspect_id)
        added = False
        if result.success:
            added = self.add_clue(result.clue_id or "")
            if result.clue_id and result.clue_id not in self.solved_experiments:
                self.solved_experiments.append(result.clue_id)
            self._gain_energy(energy_delta)
            self.score += 80
            if result.science_fact_id and result.science_fact_id not in self.facts_learned:
                self.facts_learned.append(result.science_fact_id)
            self.journal.append(f"🧪 小实验成功：{self.engine.item_label(item_id)} → {(self.engine.clue(result.clue_id) or {}).get('name', '')}")
        elif result.outcome == "nothing" and energy_delta:
            self._gain_energy(energy_delta)
        # 先呈现实验反应，再结算心虚度：心虚度满格时招供台词才会排在实验之后
        self.push_turn(
            suspect_id,
            ChatTurn(
                role="suspect",
                text=result.reply,
                speaker=(self.engine.suspect(suspect_id) or {}).get("name", ""),
                kind="experiment" if result.success else "say",
                suspect_id=suspect_id,
                item_id=item_id,
                mood=self.moods.get(suspect_id, MOOD_NORMAL),
                fact_id=result.science_fact_id,
            ),
        )
        if result.success and guilt_delta:
            self.add_guilt(suspect_id, guilt_delta)
        elif result.outcome == "nothing" and guilt_delta:
            self.add_guilt(suspect_id, guilt_delta)
        self.last_event = {
            "type": "experiment",
            "outcome": result.outcome,
            "suspect_id": suspect_id,
            "item_id": item_id,
            "title": result.title,
            "reply": result.reply,
            "detail": result.detail,
            "notes": result.notes,
            "clue_id": result.clue_id,
            "added": added,
            "guilt": self.guilt.get(suspect_id, 0),
            "mood": self.moods.get(suspect_id, MOOD_NORMAL),
            "fact_id": result.science_fact_id,
            "confessed": suspect_id in self.confessed,
            "confession": (self.engine.suspect(suspect_id) or {}).get("experiment", {}).get("confession", "")
            if suspect_id in self.confessed
            else "",
        }
        return self.last_event

    # ------------------------------------------------------------ 心虚度
    def experiment_done(self, suspect_id: str) -> bool:
        suspect = self.engine.suspect(suspect_id) or {}
        clue_id = (suspect.get("experiment") or {}).get("success_clue")
        return bool(clue_id and clue_id in self.solved_experiments)

    def add_guilt(self, suspect_id: str, delta: int) -> int:
        current = self.guilt.get(suspect_id, 0)
        if suspect_id in self.confessed:
            self.guilt[suspect_id] = MAX_GUILT
            self.moods[suspect_id] = MOOD_CONFESS
            return MAX_GUILT
        current = max(0, current + int(delta))
        if self.experiment_done(suspect_id):
            current = min(MAX_GUILT, current)
        else:
            current = min(GUILT_CAP_BEFORE_EXPERIMENT, current)
        self.guilt[suspect_id] = current
        self.moods[suspect_id] = mood_from_guilt(current, confessed=current >= MAX_GUILT)
        if current >= MAX_GUILT:
            self._confess(suspect_id)
        return current

    def _confess(self, suspect_id: str) -> None:
        """心虚度满格：立刻把招供台词写进对话，保证「大哭 + 招供」一定发生。"""
        if suspect_id in self.confessed:
            return
        self.confessed.append(suspect_id)
        suspect = self.engine.suspect(suspect_id) or {}
        experiment = suspect.get("experiment") or {}
        confession = experiment.get("confession", "") or "「好吧，我说实话……」"
        self.record_reply(suspect_id, confession, kind="confession", fact_id=suspect.get("science_fact_id"))
        bonus = experiment.get("confession_clue")
        if bonus:
            self.add_clue(bonus)
        self.journal.append(f"🙇 {suspect.get('name', '')} 把自己的那件事说出来了。")
        self.score += 60
        self._gain_energy(25)

    def guilt_of(self, suspect_id: str) -> int:
        return int(self.guilt.get(suspect_id, 0))

    def mood_of(self, suspect_id: str) -> str:
        return self.moods.get(suspect_id, MOOD_NORMAL)

    # ------------------------------------------------------------ 能量
    def _gain_energy(self, amount: int) -> int:
        self.energy = max(0, min(ENERGY_MAX, self.energy + int(amount)))
        return self.energy

    def charge(self, amount: int = 10) -> int:
        return self._gain_energy(amount)

    # ------------------------------------------------------------ 结案
    @property
    def can_deduct(self) -> bool:
        return self.engine.can_deduct(self.collected_clues)

    def missing_clues(self) -> List[Dict[str, Any]]:
        return self.engine.missing_clues(self.collected_clues)

    def accuse(self, choice_id: str) -> Dict[str, Any]:
        if not self.can_deduct:
            self.last_event = {
                "type": "accuse",
                "verdict": "locked",
                "feedback": "关键线索还没齐。先做完小实验，再来选道理。",
                "attempts": self.deduction_attempts,
            }
            return self.last_event
        self.deduction_attempts += 1
        verdict = self.engine.judge(choice_id)
        verdict["attempts"] = self.deduction_attempts
        if verdict.get("verdict") == "correct":
            self.stage = STAGE_WON
            self.final_verdict = verdict
            self.score += 300
            self.energy = ENERGY_MAX
            self.journal.append("🏅 案情说通了！金蛋回到展台。")
        else:
            self.energy = max(0, self.energy - 15)
            self.score = max(0, self.score - 20)
            self.journal.append("🤔 这条道理和证据对不上，再想想。")
        self.last_event = {"type": "accuse", **verdict}
        return self.last_event

    @property
    def won(self) -> bool:
        return self.stage == STAGE_WON

    def progress_ratio(self) -> float:
        required = self.engine.required_clues()
        if not required:
            return 1.0
        return len([c for c in required if self.has_clue(c)]) / len(required)

    def summary(self) -> Dict[str, Any]:
        return {
            "player": self.player_name,
            "stage": self.stage,
            "energy": self.energy,
            "score": self.score,
            "steps": self.steps,
            "clues": len(self.collected_clues),
            "required_clues": self.engine.required_clues(),
            "confessed": list(self.confessed),
            "guilt": dict(self.guilt),
            "facts_learned": list(self.facts_learned),
            "can_deduct": self.can_deduct,
        }


__all__ = [
    "GameState",
    "ChatTurn",
    "STAGE_PLAYING",
    "STAGE_DEDUCTION",
    "STAGE_WON",
    "MAX_GUILT",
    "ENERGY_MAX",
    "GUILT_CAP_BEFORE_EXPERIMENT",
]

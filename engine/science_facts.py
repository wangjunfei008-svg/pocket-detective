"""科学原理数据库与道具实验触发逻辑。

所有案情数据来自 data/scenario.json（相对路径读取），本模块负责：
- 加载与校验案情
- 道具 × 嫌疑人 × 场景热点 的实验判定
- 线索收集度与结案判定
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCENARIO_PATH = os.path.join("data", "scenario.json")

OUTCOME_SUCCESS = "success"
OUTCOME_WRONG_ITEM = "wrong_item"
OUTCOME_NOTHING = "nothing"
OUTCOME_ALREADY = "already"


def scenario_path(path: Optional[str] = None) -> str:
    """把案情文件解析成绝对路径，始终以工程根目录为基准（创空间安全）。"""
    if path and os.path.isabs(path):
        return path
    return os.path.join(PACKAGE_ROOT, path or DEFAULT_SCENARIO_PATH)


def load_scenario(path: Optional[str] = None) -> Dict[str, Any]:
    """读取案情 JSON；文件缺失或损坏时返回内置最小案情，保证界面不白屏。"""
    target = scenario_path(path)
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or "suspects" not in data:
            raise ValueError("scenario.json 结构不完整")
        return data
    except Exception as exc:
        fallback = _fallback_scenario()
        fallback.setdefault("meta", {})["load_error"] = f"{type(exc).__name__}: {exc}"[:200]
        return fallback


def _fallback_scenario() -> Dict[str, Any]:
    """极端情况下（文件被误删）也能跑通一局的兜底案情。"""
    return {
        "meta": {"title": "口袋小神探：梧桐小学的消失金蛋", "version": "fallback"},
        "story": {
            "opening": "科学教室的金蛋不见了。",
            "brief": "",
            "sparky_intro": "咕叽！我来帮你！",
            "safety_note": "案情文件没有加载好。",
            "parent_note": "",
        },
        "scenes": [{"id": "lab", "name": "科学教室", "emoji": "🔬", "desc": "展台空了。", "hotspots": []}],
        "clues": {},
        "items": [
            {"id": "magnifier", "name": "神探放大镜", "emoji": "🔍", "usage": "勘查现场。", "science_note": "", "targets": ["scene", "suspect"]},
            {"id": "iodine_swab", "name": "碘伏棉签", "emoji": "🧪", "usage": "检测淀粉。", "science_note": "", "targets": ["suspect"]},
            {"id": "flashlight", "name": "迷你手电筒", "emoji": "🔦", "usage": "照射玻璃。", "science_note": "", "targets": ["suspect", "scene"]},
            {"id": "salt_bag", "name": "食用盐袋", "emoji": "🧂", "usage": "加盐做浮力实验。", "science_note": "", "targets": ["suspect", "scene"]},
        ],
        "science_facts": [],
        "suspects": [],
        "sparky": {"name": "鸡飞飞", "emoji": "🐤", "help_lines": {"general": "咕叽！一看二闻三提问！"}, "charge_lines": ["咕叽！"]},
        "deduction": {"required_clues": [], "final_answer": {"culprit": "", "explanation": ""}, "options": []},
        "ending": {"title": "🏅 梧桐街金牌小神探科学勋章", "medal_name": "梧桐街金牌小神探", "narration": "", "sparky_bye": "", "takeaways": [], "safety_reminder": ""},
    }


@dataclass
class ExperimentResult:
    """一次『出示道具做小实验』的判定结果。"""

    outcome: str
    suspect_id: str
    item_id: str
    reply: str = ""
    clue_id: Optional[str] = None
    guilt_delta: int = 0
    science_fact_id: Optional[str] = None
    energy_delta: int = 0
    title: str = ""
    detail: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.outcome == OUTCOME_SUCCESS


@dataclass
class InspectResult:
    """一次现场勘查的判定结果。"""

    outcome: str
    hotspot_id: str
    title: str = ""
    text: str = ""
    clue_id: Optional[str] = None
    energy_delta: int = 0
    science_fact_id: Optional[str] = None
    requires_item: Optional[str] = None


class ScienceEngine:
    """科学原理数据库 + 实验/线索判定核心（无状态，可被 UI 与测试复用）。"""

    def __init__(self, scenario: Optional[Dict[str, Any]] = None):
        self.scenario = scenario or load_scenario()
        self._clues: Dict[str, Dict[str, Any]] = dict(self.scenario.get("clues") or {})
        self._items: Dict[str, Dict[str, Any]] = {i["id"]: i for i in self.scenario.get("items") or []}
        self._suspects: Dict[str, Dict[str, Any]] = {s["id"]: s for s in self.scenario.get("suspects") or []}
        self._facts: Dict[str, Dict[str, Any]] = {f["id"]: f for f in self.scenario.get("science_facts") or []}
        self._scenes: Dict[str, Dict[str, Any]] = {s["id"]: s for s in self.scenario.get("scenes") or []}

    # ------------------------------------------------------------------ 元数据
    @property
    def meta(self) -> Dict[str, Any]:
        return self.scenario.get("meta") or {}

    @property
    def story(self) -> Dict[str, Any]:
        return self.scenario.get("story") or {}

    @property
    def sparky(self) -> Dict[str, Any]:
        return self.scenario.get("sparky") or {}

    @property
    def ending(self) -> Dict[str, Any]:
        return self.scenario.get("ending") or {}

    @property
    def deduction(self) -> Dict[str, Any]:
        return self.scenario.get("deduction") or {}

    def items(self) -> List[Dict[str, Any]]:
        return list(self._items.values())

    def item(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self._items.get(item_id)

    def item_label(self, item_id: str) -> str:
        item = self._items.get(item_id)
        return f"{item['emoji']} {item['name']}" if item else f"❓ {item_id}"

    def suspects(self) -> List[Dict[str, Any]]:
        return list(self._suspects.values())

    def suspect(self, suspect_id: str) -> Optional[Dict[str, Any]]:
        return self._suspects.get(suspect_id)

    def suspect_label(self, suspect_id: str) -> str:
        suspect = self._suspects.get(suspect_id)
        return f"{suspect['emoji']} {suspect['name']}" if suspect else suspect_id

    def clue(self, clue_id: str) -> Optional[Dict[str, Any]]:
        return self._clues.get(clue_id)

    def clues(self) -> List[Dict[str, Any]]:
        return list(self._clues.values())

    def fact(self, fact_id: Optional[str]) -> Optional[Dict[str, Any]]:
        return self._facts.get(fact_id) if fact_id else None

    def facts(self) -> List[Dict[str, Any]]:
        return list(self._facts.values())

    def scene(self, scene_id: str = "lab") -> Dict[str, Any]:
        return self._scenes.get(scene_id) or (self._scenes.get("lab") if self._scenes else {"hotspots": []})

    def hotspots(self, scene_id: str = "lab") -> List[Dict[str, Any]]:
        return list(self.scene(scene_id).get("hotspots") or [])

    # ------------------------------------------------------------------ 勘查
    def inspect(self, hotspot_id: str, item_id: Optional[str] = None) -> InspectResult:
        """勘查现场热点：徒手只能看到模糊印象，出示【神探放大镜】才能收录线索。"""
        for spot in self.hotspots():
            if spot.get("id") != hotspot_id:
                continue
            clue_id = spot.get("clue_id")
            clue = self._clues.get(clue_id) if clue_id else None
            if clue is None:
                return InspectResult(OUTCOME_NOTHING, hotspot_id, title=spot.get("name", ""), text=spot.get("hint", ""))
            if item_id != "magnifier":
                return InspectResult(
                    OUTCOME_NOTHING,
                    hotspot_id,
                    title=spot.get("name", ""),
                    text=f"{spot.get('hint', '')} 光用眼睛看不够，从科学小背包里请出🔍 神探放大镜再试一次吧。",
                    requires_item="magnifier",
                )
            return InspectResult(
                OUTCOME_SUCCESS,
                hotspot_id,
                title=clue.get("name", ""),
                text=clue.get("desc", ""),
                clue_id=clue_id,
                energy_delta=20,
                science_fact_id=clue.get("related_fact"),
            )
        return InspectResult(OUTCOME_NOTHING, hotspot_id, text="这里什么特别的东西都没有。")

    # ------------------------------------------------------------------ 实验
    def experiment(self, suspect_id: str, item_id: str, already_solved: Optional[List[str]] = None) -> ExperimentResult:
        """对嫌疑人出示道具：命中其科学机制则推进心虚度并解锁关键线索。"""
        suspect = self._suspects.get(suspect_id)
        if suspect is None:
            return ExperimentResult(OUTCOME_NOTHING, suspect_id, item_id, reply="这位小朋友还不在教室里哦。")
        experiment = suspect.get("experiment") or {}
        already = set(already_solved or [])
        correct_item = experiment.get("item_id")
        clue_id = experiment.get("success_clue")

        if item_id == correct_item:
            if clue_id and clue_id in already:
                return ExperimentResult(
                    OUTCOME_ALREADY,
                    suspect_id,
                    item_id,
                    reply="（他愣了一下）「这个……你不是已经知道了嘛，还问。」",
                    clue_id=clue_id,
                    science_fact_id=suspect.get("science_fact_id"),
                )
            fact = self._facts.get(suspect.get("science_fact_id")) or {}
            return ExperimentResult(
                OUTCOME_SUCCESS,
                suspect_id,
                item_id,
                reply=experiment.get("success_reply", ""),
                clue_id=clue_id,
                guilt_delta=int(experiment.get("success_guilt", 40)),
                science_fact_id=suspect.get("science_fact_id"),
                energy_delta=40,
                title=f"小实验成功！{self.item_label(item_id)} 起了作用",
                detail=fact.get("kid_explanation", ""),
                notes=list(fact.get("experiment_steps") or []),
            )

        if item_id == "magnifier":
            return ExperimentResult(
                OUTCOME_NOTHING,
                suspect_id,
                item_id,
                reply=f"（你注意到一个小动作）{self._tell_body_language(suspect_id)}",
                guilt_delta=6,
                energy_delta=10,
                science_fact_id=suspect.get("science_fact_id"),
                title="放大镜观察：发现小动作",
            )

        return ExperimentResult(
            OUTCOME_WRONG_ITEM,
            suspect_id,
            item_id,
            reply=experiment.get("wrong_item_reply", "（他困惑地看着你手里的东西）「这个……跟案子有关系吗？」"),
            science_fact_id=suspect.get("science_fact_id"),
            title="实验没有现象",
        )

    def _tell_body_language(self, suspect_id: str) -> str:
        suspect = self._suspects.get(suspect_id) or {}
        return suspect.get("body_language") or "他看起来有点紧张。"

    def correct_item_for(self, suspect_id: str) -> Optional[str]:
        suspect = self._suspects.get(suspect_id) or {}
        return (suspect.get("experiment") or {}).get("item_id")

    # ------------------------------------------------------------------ 结案
    def required_clues(self) -> List[str]:
        return list(self.deduction.get("required_clues") or [])

    def can_deduct(self, collected: List[str]) -> bool:
        needed = set(self.required_clues())
        return needed.issubset(set(collected))

    def missing_clues(self, collected: List[str]) -> List[Dict[str, Any]]:
        have = set(collected)
        return [self._clues[c] for c in self.required_clues() if c in self._clues and c not in have]

    def judge(self, choice_id: str) -> Dict[str, Any]:
        """结案判定：必须选中带科学道理的选项，只点人名不算答对。"""
        answer = self.deduction.get("final_answer") or {}
        correct = answer.get("culprit")
        chosen = None
        for option in self.deduction.get("options") or []:
            if option.get("id") == choice_id:
                chosen = option
                break
        if chosen is None:
            return {
                "choice_id": choice_id,
                "suspect_id": choice_id,
                "verdict": "wrong",
                "feedback": "要选一条完整的道理。只点一个人的名字，还不能结案。",
                "correct_suspect": correct,
                "explanation": "",
            }
        verdict = "correct" if chosen.get("verdict") == "correct" else "wrong"
        return {
            "choice_id": choice_id,
            "suspect_id": chosen.get("suspect_id"),
            "verdict": verdict,
            "feedback": chosen.get("feedback") or "再看看线索，哪一条说明金蛋真的换了地方？",
            "correct_suspect": correct,
            "explanation": answer.get("explanation", "") if verdict == "correct" else "",
            "fact_id": (self.deduction.get("culprit_by_fact") or {}).get(correct) if verdict == "correct" else None,
        }

    # ------------------------------------------------------------------ 求助
    def _pick_help_line(self, value: Any, tier: int) -> str:
        """提示分三档：先给现象，再给道理，最后才点工具。"""
        if isinstance(value, list):
            if not value:
                return ""
            index = max(0, min(int(tier), len(value) - 1))
            return str(value[index])
        return str(value or "")

    def sparky_help(
        self,
        suspect_id: Optional[str] = None,
        collected: Optional[List[str]] = None,
        tier: Optional[int] = None,
    ) -> str:
        """鸡飞飞的提示。tier 越小越含蓄；不传则给最具体的一档，方便直接调用。"""
        if tier is None:
            tier = 2
        lines = self.sparky.get("help_lines") or {}
        collected_set = set(collected or [])
        if suspect_id:
            suspect = self._suspects.get(suspect_id) or {}
            clue_id = (suspect.get("experiment") or {}).get("success_clue")
            if clue_id and clue_id not in collected_set:
                line = self._pick_help_line(lines.get(suspect.get("science_fact_id")), tier)
                if line:
                    return line
        missing = self.missing_clues(list(collected_set))
        if missing:
            fact_id = missing[0].get("related_fact")
            line = self._pick_help_line(lines.get(fact_id), tier)
            if line:
                return line
        general = self._pick_help_line(lines.get("general"), tier)
        return general or "咕叽！先看现场，再做小实验。"

    def sparky_charge(self, index: int = 0) -> str:
        lines = self.sparky.get("charge_lines") or ["咕叽！好奇心能量 +100！"]
        return lines[index % len(lines)]

    def takeaway_facts(self) -> List[Dict[str, Any]]:
        """结案卡片上的三个科学知识点。"""
        wanted = [f.get("related_fact") for f in (self._clues.get(c) for c in self.required_clues()) if f]
        ordered = [self._facts[w] for w in wanted if w in self._facts]
        if len(ordered) < 3:
            ordered += [f for f in self.facts() if f not in ordered]
        return ordered[:3]


__all__ = [
    "ScienceEngine",
    "ExperimentResult",
    "InspectResult",
    "load_scenario",
    "scenario_path",
    "OUTCOME_SUCCESS",
    "OUTCOME_WRONG_ITEM",
    "OUTCOME_NOTHING",
    "OUTCOME_ALREADY",
]

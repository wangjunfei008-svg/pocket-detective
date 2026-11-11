"""角色设定与童真语气规范。

每个角色 = 人设卡（persona）+ 语气规范（tone rules）+ 情绪表情映射。
`build_messages()` 负责把案情、心虚度、已收集线索拼成给大模型的角色扮演提示词，
保证 AI 生成的台词始终：适合 8-12 岁、不恐怖、不说教。
秘密只在小朋友做对实验之后才放进提示词，避免一问就泄底。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 情绪档位：驱动立绘切换与心虚度进度条
MOOD_NORMAL = "normal"
MOOD_SURPRISED = "surprised"
MOOD_NERVOUS = "nervous"
MOOD_CONFESS = "confess"

MOOD_LABELS = {
    MOOD_NORMAL: "神色如常",
    MOOD_SURPRISED: "吃了一惊",
    MOOD_NERVOUS: "心虚流汗",
    MOOD_CONFESS: "哇哇大哭招供",
}

MOOD_EMOJI = {
    MOOD_NORMAL: "🙂",
    MOOD_SURPRISED: "😮",
    MOOD_NERVOUS: "😅",
    MOOD_CONFESS: "😭",
}

# 儿童内容安全底线：写进 system prompt，任何后端都必须遵守
CHILD_SAFETY_RULES = """【儿童内容安全红线（必须严格遵守）】
1. 面向 8-12 岁小朋友，用词简单、句子短、语气温暖。
2. 绝对不出现：恐怖、血腥、暴力、死亡、武器、惊悚、恋爱、赌博、烟酒、恐怖袭击、宗教政治争议。
3. 嫌疑人只是撒了小谎，不是坏人。说完自己的事就可以，不要吓人。
4. 不出现真实品牌广告、不诱导消费、不索要任何个人信息（姓名、学校、住址、照片、电话一律不问）。
5. 涉及实验必须说「请家长陪同」，绝不建议品尝、吞食、点燃任何材料，绝不用激光笔照眼睛。
6. 每次回复控制在 40-110 个汉字，最多 2 句话，可带一个括号里的动作，例如（他挠了挠头）。
7. 不要跳出角色，不要说自己是 AI 或模型，不要输出英文句子，不要输出尖括号。"""

TONE_RULES: Dict[str, str] = {
    "pan": "你是潘小达，10 岁，贪吃、爱面子。口头禅是「我发誓」「这事儿跟我没关系」。一紧张就按住书包侧袋。被夸会开心。被问到口袋和白纸会躲。不要承认你进过教室，也不要说出纸上写了什么。",
    "zhou": "你是周晓晓，11 岁，科学课代表，戴圆眼镜。爱说「从科学角度讲」。一紧张就扶眼镜。被问到窗台、碗、水杯时会躲，但不要解释光怎样走路，也不要说金蛋在哪里。被夸会耳尖发红但嘴硬。",
    "zhang": "你是张爷爷，68 岁，学校看门人。说话慢，爱吹牛，一慌就摸胡子。被问到飞碟时你会把故事说得很神，再说完自己笑一下。不要承认盐和金蛋有关系，也不要说出金蛋在教室的哪个角落。",
    "sparky": "你是鸡飞飞，住在小侦探口袋里的圆圆黄球搭档。用「咕叽！」开头，语气轻快。你只给两步以内的提示：先说现象，再问一句为什么。不要说出是谁让金蛋换了地方，不要提任何电子产品品牌，也不要提飞船的能量是从哪台电脑来的。",
    "narrator": "你是儿童绘本的旁白，用温暖的短句描述科学教室，20-60 字，可以写到声音，不要制造害怕。",
}

# 只放孩子已经能从对话里知道的公开身份。秘密见 REVEAL_AFTER_EXPERIMENT。
PERSONA_CARD: Dict[str, str] = {
    "pan": "【你是谁】潘小达，10 岁，四年级，爱吃零食。"
           "你嘴上说：昨晚在操场吃烤肠，没进过科学教室。",
    "zhou": "【你是谁】周晓晓，11 岁，科学课代表，戴圆眼镜。"
            "你嘴上说：窗户是你锁的，七点就回家了，水槽当时是干的。",
    "zhang": "【你是谁】张爷爷，68 岁，学校看门人。"
             "你嘴上说：你在传达室修收音机，金蛋是飞碟吸走的。",
}

# 这些句子只有在对应实验已经做成之后才放进提示词。
REVEAL_AFTER_EXPERIMENT: Dict[str, str] = {
    "pan": "你溜进来想热烤肠，金蛋那时已经不在罩子里。米汤信是你掉的。那滩水不是我打翻的。不要说另外两个人的事。",
    "zhou": "你在练倒水看硬币。隔着水杯看，金蛋好像歪了，其实是光拐弯。离开时金蛋还在玻璃罩里。不要提盐，也不要提烤肠。",
    "zhang": "你倒了一整包盐，金蛋浮起来，去捞的时候手一滑，滚到架子后面。飞碟是你编的。不要说两个孩子的事。",
}

EMOTION_THRESHOLDS = ((100, MOOD_CONFESS), (55, MOOD_NERVOUS), (25, MOOD_SURPRISED), (0, MOOD_NORMAL))

_PUNCT = re.compile(r"[，。！？；：、,.!?;:\"'“”‘’（）()【】《》\s~…—\-·]+")


def _normalize_question(text: str) -> str:
    """去掉标点与空白并转小写，用于关键词命中（中英混排都友好）。"""
    return _PUNCT.sub("", (text or "").lower())


def mood_from_guilt(guilt: int, confessed: bool = False) -> str:
    """心虚度 → 情绪档位（驱动立绘与表情切换）。"""
    if confessed or guilt >= 100:
        return MOOD_CONFESS
    for threshold, mood in EMOTION_THRESHOLDS:
        if guilt >= threshold:
            return mood
    return MOOD_NORMAL


def _topic_lines(topics: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for topic in topics or []:
        keywords = "、".join(topic.get("keywords") or [])
        lines.append(f"- 当小朋友问到「{keywords}」时，参考台词：{topic.get('reply', '')}")
    return "\n".join(lines) if lines else "- （无预设话题，按人设自由发挥）"


def build_system_prompt(
    suspect: Dict[str, Any],
    *,
    guilt: int = 0,
    experiment_done: bool = False,
) -> str:
    """嫌疑人的 system prompt。没做对实验之前，不写入秘密。"""
    sid = suspect.get("id", "")
    press = list(suspect.get("press_lines") or [])
    shown = press if experiment_done else press[:2]
    press_hint = ""
    if shown:
        press_hint = "\n【越来越慌时可以参考的短句】\n" + "\n".join(
            f"{i + 1}. {line}" for i, line in enumerate(shown)
        )
    if experiment_done:
        reveal = (
            "\n【小朋友已经做对了你的小实验，可以用一两句实话承认】\n"
            + REVEAL_AFTER_EXPERIMENT.get(sid, "只承认你自己的那一件事。")
        )
    else:
        reveal = (
            "\n【还不能把秘密说完】小朋友还没做对你的小实验。"
            "你可以紧张、躲闪，但不要说出秘密，也不要说出金蛋现在在哪。"
            "请他先做个小实验。当前心虚度只供你调整语气："
            f"{int(guilt)}/100。"
        )
    return (
        "你正在儿童科学探案游戏《口袋小神探》里，"
        "扮演其中一个角色，和一位 8-12 岁的小侦探说话。\n\n"
        f"{PERSONA_CARD.get(sid, '')}\n\n"
        f"【语气】{TONE_RULES.get(sid, '')}\n\n"
        f"【你嘴上的说法】{suspect.get('alibi', '')}\n"
        f"【性格】{suspect.get('personality', '')}\n"
        f"【口头禅】{'、'.join(suspect.get('catchphrases') or [])}\n\n"
        f"【被问到这些时可以怎么躲】\n{_topic_lines(suspect.get('topics') or [])}\n"
        f"{press_hint}\n"
        f"{reveal}\n\n"
        "【说话规则】\n"
        "1. 不要把别人的秘密也说出来。\n"
        "2. 不要用列表和 Markdown，直接说台词。\n"
        "3. 不要输出英文句子，不要输出尖括号。\n\n"
        f"{CHILD_SAFETY_RULES}"
    )


def build_messages(
    suspect: Dict[str, Any],
    history: List[Dict[str, str]],
    *,
    guilt: int = 0,
    mood: str = MOOD_NORMAL,
    collected_clues: Optional[List[str]] = None,
    engine: Any = None,
    max_turns: int = 8,
) -> List[Dict[str, str]]:
    """拼装嫌疑人对话消息列表（含心虚度与线索上下文）。"""
    clue_id = (suspect.get("experiment") or {}).get("success_clue")
    experiment_done = bool(clue_id and collected_clues and clue_id in list(collected_clues))
    if mood == MOOD_CONFESS:
        experiment_done = True
    system = build_system_prompt(suspect, guilt=guilt, experiment_done=experiment_done)
    state_lines = [
        f"【当前状态】你的心虚度：{guilt}/100（{MOOD_LABELS.get(mood, '')}）。",
        f"【情绪要求】{mood_instruction(mood, suspect)}",
    ]
    if collected_clues and engine is not None:
        named = []
        for clue_id in collected_clues[-6:]:
            clue = engine.clue(clue_id)
            if clue:
                named.append(f"{clue.get('emoji', '')}{clue.get('name', '')}")
        if named:
            state_lines.append(f"【小侦探已经掌握的线索】{'、'.join(named)}（你有点慌，但不能承认）。")
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    messages.append({"role": "system", "content": "\n".join(state_lines)})
    messages.extend(history[-max_turns:])
    return messages


def mood_instruction(mood: str, suspect: Dict[str, Any]) -> str:
    press = suspect.get("press_lines") or []
    mapping = {
        MOOD_NORMAL: "现在你还算镇定，可以理直气壮地重复你的不在场证明，但要有一个小动作暴露你（比如摸鼻子、看别处）。",
        MOOD_SURPRISED: "你被问到了没准备的问题，明显吃了一惊，说话开始重复对方的词，回答变短。",
        MOOD_NERVOUS: "你非常心虚：流汗、结巴、重复口头禅、答非所问，可以不小心多说一个只有当事人才知道的细节。",
        MOOD_CONFESS: "你已经可以说实话了。只承认你自己做过的那一件事，语气后悔又诚实。不要讲别人的秘密。",
    }
    base = mapping.get(mood, mapping[MOOD_NORMAL])
    if press and mood in (MOOD_NERVOUS, MOOD_CONFESS):
        base += f" 可参考台词：{press[min(len(press) - 1, 2 if mood == MOOD_NERVOUS else 3)]}"
    return base


def build_sparky_messages(
    sparky: Dict[str, Any],
    question: str,
    *,
    context: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """鸡飞飞的求助提示词：启发式、不给答案。"""
    system = (
        f"你是{sparky.get('name', '鸡飞飞')}，{sparky.get('species', '外星萌宠')}，"
        f"住在小侦探口袋里，是他的搭档。\n"
        f"【语气规范】{TONE_RULES['sparky']}\n"
        f"【口头禅】{'、'.join(sparky.get('catchphrases') or [])}\n"
        f"【当前案情进度】{json_dumps_brief(context)}\n"
        f"【重要】用一句大白话启发小朋友，最多两步，不要说出是谁让金蛋换了地方。\n"
        f"{CHILD_SAFETY_RULES}"
    )
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question or "鸡飞飞，我卡住了，给我一点提示吧！"})
    return messages


def json_dumps_brief(data: Any, limit: int = 600) -> str:
    import json

    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        text = str(data)
    return text[:limit]


__all__ = [
    "MOOD_NORMAL",
    "MOOD_SURPRISED",
    "MOOD_NERVOUS",
    "MOOD_CONFESS",
    "MOOD_LABELS",
    "MOOD_EMOJI",
    "CHILD_SAFETY_RULES",
    "TONE_RULES",
    "PERSONA_CARD",
    "_normalize_question",
    "mood_from_guilt",
    "mood_instruction",
    "REVEAL_AFTER_EXPERIMENT",
    "build_system_prompt",
    "build_messages",
    "build_sparky_messages",
]

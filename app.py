"""口袋小神探：梧桐小学的消失金蛋
================================================
基于 DGX Spark 本地大模型的儿童安全伴学探案游戏
魔搭社区「AI+∞ 开发者创作大赛」第三期 · AI 造游戏赛道

启动：streamlit run app.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.characters import (  # noqa: E402
    MOOD_EMOJI,
    MOOD_LABELS,
    MOOD_NERVOUS,
    build_messages,
    build_sparky_messages,
)
from agents.game_state import ENERGY_MAX, ChatTurn, GameState  # noqa: E402
from assets.avatars import (  # noqa: E402
    avatar_svg,
    egg_svg,
    medal_svg,
    scene_svg,
)
from engine.llm_client import (  # noqa: E402
    MODE_CLOUD,
    MODE_LOCAL,
    MODE_MOCK,
    DEFAULT_CLOUD_BASE_URL,
    DEFAULT_LOCAL_BASE_URL,
    DEFAULT_LOCAL_MODEL,
    LLMClient,
)
from engine.science_facts import ScienceEngine  # noqa: E402

APP_TITLE = "口袋小神探：梧桐小学的消失金蛋"
APP_SUBTITLE = "基于 DGX Spark 本地大模型的儿童安全伴学探案游戏 · 6-12 岁 · 15-25 分钟"
STYLE_PATH = os.path.join("assets", "style.css")

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ======================================================================
#  资源加载
# ======================================================================
@st.cache_resource(show_spinner=False)
def load_engine() -> ScienceEngine:
    return ScienceEngine()


@st.cache_resource(show_spinner=False)
def build_client_signature() -> str:
    """仅用于提示环境变量是否就绪。"""
    from engine.llm_client import _env

    return ",".join(
        name for name in ("MODELSCOPE_API_TOKEN", "MODELSCOPE_API_KEY", "DASHSCOPE_API_KEY") if _env(name)
    )


def load_css() -> str:
    try:
        with open(STYLE_PATH, "r", encoding="utf-8") as handle:
            return handle.read()
    except Exception:
        return ""


def inject_css() -> None:
    css = load_css()
    extra = """
    <style>
    .stApp > div[data-testid="stAppViewContainer"] { position: relative; }
    div[data-testid="stSidebar"] .stButton > button { width: 100%; }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 12px; }
    img { image-rendering: auto; }
    </style>
    """
    st.markdown(f"<style>{css}</style>{extra}", unsafe_allow_html=True)


def md(html: str, **kwargs: Any) -> None:
    st.markdown(html, unsafe_allow_html=True, **kwargs)


# ======================================================================
#  会话状态
# ======================================================================
def init_state() -> GameState:
    if "game" not in st.session_state:
        st.session_state.game = GameState(load_engine())
    if "llm_settings" not in st.session_state:
        st.session_state.llm_settings = {
            "mode": "auto",
            "api_key": "",
            "local_base_url": DEFAULT_LOCAL_BASE_URL,
            "local_model": DEFAULT_LOCAL_MODEL,
            "cloud_base_url": DEFAULT_CLOUD_BASE_URL,
            # 留空：由 LLMClient 按 Key 形状自动匹配服务商默认模型
            "cloud_model": "",
        }
    if "pending_llm" not in st.session_state:
        st.session_state.pending_llm = []
    return st.session_state.game


def new_client(settings: Dict[str, Any]) -> LLMClient:
    mode = settings.get("mode") or "auto"
    explicit = {"local": MODE_LOCAL, "cloud": MODE_CLOUD, "mock": MODE_MOCK}.get(mode)
    return LLMClient(
        mode=explicit,
        api_key=settings.get("api_key", ""),
        local_base_url=settings.get("local_base_url") or DEFAULT_LOCAL_BASE_URL,
        local_model=settings.get("local_model") or DEFAULT_LOCAL_MODEL,
        cloud_base_url=settings.get("cloud_base_url") or DEFAULT_CLOUD_BASE_URL,
        # 原样传空串，交给 LLMClient 按 Key 形状选服务商默认模型
        cloud_model=settings.get("cloud_model", ""),
        force_mock=(mode == "mock"),
    )


def reset_game() -> None:
    """重开一局：开场剧情一并重置，保证第二次进入仍能从头体验。"""
    st.session_state.game = GameState(load_engine())
    st.session_state.pop("flash", None)
    st.session_state.pop("intro_seen", None)
    st.rerun()


def get_client() -> LLMClient:
    settings = st.session_state.llm_settings
    signature = repr(sorted(settings.items()))
    if st.session_state.get("_client_sig") != signature or "llm_client" not in st.session_state:
        st.session_state.llm_client = new_client(settings)
        st.session_state._client_sig = signature
    return st.session_state.llm_client


# ======================================================================
#  绘本风 UI 组件
# ======================================================================
def render_header(engine: ScienceEngine) -> None:
    md(
        f'<div class="pd-title">🕵️ {engine.meta.get("title", APP_TITLE)}</div>'
        f'<div class="pd-subtitle">{engine.meta.get("subtitle", APP_SUBTITLE)}</div>'
    )
    md(
        '<div class="pd-badge-bar">'
        '<span class="pd-badge pd-badge--spark">🛡️ NVIDIA DGX Spark 儿童绿色端侧算力守护</span>'
        '<span class="pd-badge">🔌 100% 离线绿色安全</span>'
        '<span class="pd-badge pd-badge--privacy">🧒 保护儿童隐私 · 无广告 · 无内购</span>'
        "</div>"
    )


def render_energy(game: GameState) -> None:
    ratio = max(0, min(ENERGY_MAX, game.energy))
    md(
        '<div class="pd-card pd-card--sky">'
        '<div class="pd-card-title">🚀 鸡飞飞的飞船电量（好奇心能量）</div>'
        f'<div class="pd-energy-track"><div class="pd-energy-fill" style="width:{ratio}%"></div></div>'
        f'<div class="pd-guilt-label"><span>提问、勘查、做实验都能充电</span><span>{ratio}%</span></div>'
        "</div>"
    )


def render_stage(suspect: Dict[str, Any], mood: str, guilt: int) -> None:
    """角色立绘舞台：立绘随情绪切换 + 心虚度进度条。"""
    who = suspect["id"]
    mood_class = {"nervous": " pd-mood-chip--nervous", "confess": " pd-mood-chip--confess"}.get(mood, "")
    md(
        '<div class="pd-stage">'
        f'{avatar_svg(who, mood, size=210)}'
        f'<div class="pd-stage-name">{suspect["emoji"]} {suspect["name"]}</div>'
        f'<div class="pd-stage-role">{suspect["role"]} · {suspect["age"]}</div>'
        f'<div class="pd-mood-chip{mood_class}">{MOOD_EMOJI.get(mood, "🙂")} {MOOD_LABELS.get(mood, "")}</div>'
        "</div>"
    )
    md(
        '<div class="pd-guilt-wrap">'
        '<div class="pd-guilt-label"><span>💗 心虚度（满格就哇哇大哭招供）</span>'
        f'<span>{guilt} / 100</span></div>'
        f'<div class="pd-guilt-track"><div class="pd-guilt-fill" style="width:{guilt}%"></div></div>'
        "</div>"
    )


def render_sparky_card(engine: ScienceEngine, energy: int) -> None:
    mood = MOOD_NERVOUS if energy < 30 else "normal"
    md(
        '<div class="pd-card pd-card--butter">'
        '<div class="pd-card-title">🐤 口袋伙伴 · 鸡飞飞·斯帕克</div>'
        f'{avatar_svg("sparky", mood, size=150)}'
        f'<div class="pd-hint" style="text-align:center">{engine.sparky.get("species", "")}</div>'
        "</div>"
    )


def render_bubble(
    text: str,
    *,
    kind: str = "suspect",
    speaker: str = "",
) -> None:
    if not text:
        return
    who_class = {
        "player": " pd-bubble-who--player",
        "sparky": " pd-bubble-who--sparky",
        "system": " pd-bubble-who--system",
    }.get(kind, "")
    label = speaker or {"player": "我", "sparky": "鸡飞飞", "system": "旁白"}.get(kind, "")
    chip = f'<span class="pd-bubble-who{who_class}">{label}</span><br/>' if label else ""
    md(f'<div class="pd-bubble pd-bubble--{kind}">{chip}{text}</div>')


def render_clue_book(game: GameState) -> None:
    engine = game.engine
    md('<div class="pd-card-title">📚 线索收集册</div>')
    required = set(engine.required_clues())
    if not game.collected_clues:
        md('<div class="pd-hint">还没有线索。用 🔍 神探放大镜 点击案发现场的热点，或对嫌疑人出示道具做小实验。</div>')
    for clue_id in game.collected_clues:
        clue = engine.clue(clue_id)
        if not clue:
            continue
        star = " ⭐" if clue_id in required else ""
        md(
            f'<div class="pd-clue"><div class="pd-clue-name">{clue.get("emoji", "🔎")} '
            f'{clue.get("name", "")}{star}</div>'
            f'<div class="pd-clue-desc">{clue.get("desc", "")}</div></div>'
        )
    missing = game.missing_clues()
    for clue in missing:
        md(
            f'<div class="pd-clue pd-clue--locked"><div class="pd-clue-name">❓ 尚未找到：{clue.get("name", "")}</div>'
            f'<div class="pd-clue-desc">{clue.get("science_hint", "")}</div></div>'
        )


def render_sci_backpack(game: GameState) -> None:
    md('<div class="pd-card-title">🎒 科学小背包</div>')
    md('<div class="pd-hint">点一下道具拿在手里，再去案发现场勘查，或对着嫌疑人「出示做小实验」。</div>')
    for item in game.items:
        selected = game.active_item == item["id"]
        label = f"{'✅ ' if selected else ''}{item['emoji']} {item['name']}"
        if st.button(label, key=f"item_{item['id']}", use_container_width=True):
            game.select_item(item["id"])
            st.session_state.pop("flash", None)
            st.rerun()
        if selected:
            md(f'<div class="pd-hint" style="margin:-2px 0 6px 4px">{item["usage"]}<br>💡 {item["science_note"]}</div>')
    md(f'<div class="pd-status"><span class="pd-dot"></span>手上拿着：{game.active_item_label}</div>')


def render_scene(game: GameState) -> None:
    engine = game.engine
    scene = engine.scene()
    md('<div class="pd-card pd-card--mint">')
    md(f'<div class="pd-card-title">{scene.get("emoji", "🔬")} {scene.get("name", "案发现场")}</div>')
    md(f'<div class="pd-hint">{scene.get("desc", "")}</div>')
    md(scene_svg(size=300))
    cols = st.columns(min(4, max(1, len(engine.hotspots()))))
    for index, spot in enumerate(engine.hotspots()):
        with cols[index % len(cols)]:
            found = spot.get("clue_id") in game.collected_clues
            label = f"{'✅ ' if found else ''}{spot.get('emoji', '🔎')} {spot.get('name', '')}"
            if st.button(label, key=f"spot_{spot['id']}", use_container_width=True):
                event = game.inspect(spot["id"])
                if event.get("added"):
                    game.charge(15)
                    st.session_state.flash = (
                        "success",
                        f"🔍 发现线索：{event.get('title', '')}\n\n{event.get('text', '')}",
                    )
                else:
                    st.session_state.flash = (
                        "info",
                        f"🔎 {event.get('title', '')}\n\n{event.get('text', '')}",
                    )
                st.rerun()
    md("</div>")


def render_fact_card(fact_id: Optional[str], engine: ScienceEngine) -> None:
    fact = engine.fact(fact_id)
    if not fact:
        return
    steps = "".join(f"<li>{step}</li>" for step in fact.get("experiment_steps") or [])
    md(
        '<div class="pd-fact">'
        f'<div class="pd-fact-title">{fact.get("emoji", "🔬")} 今日科学知识点：{fact.get("title", "")}</div>'
        f'<div class="pd-fact-body">{fact.get("kid_explanation", "")}</div>'
        f'<div class="pd-fact-body"><b>在家怎么做（请家长陪同）：</b><ol>{steps}</ol></div>'
        f'<div class="pd-fact-body"><b>生活里哪里能见到：</b>{fact.get("everyday_example", "")}<br>'
        f'<b>安全提示：</b>{fact.get("safety_tip", "")}</div>'
        "</div>"
    )


# ======================================================================
#  侧边栏
# ======================================================================
def render_sidebar(game: GameState) -> None:
    engine = game.engine
    with st.sidebar:
        md('<div class="pd-card pd-card--butter" style="text-align:center">'
           '<div style="font-size:1.25rem;font-weight:900">🕵️ 小侦探档案</div></div>')
        name = st.text_input("你的名字（不会上传，只显示在本机）", value=game.player_name, max_chars=12)
        if name and name != game.player_name:
            game.player_name = name

        render_sparky_card(engine, game.energy)
        st.text_input(
            "想问鸡飞飞什么？（留空则给你当前最需要的提示）",
            key="sparky_question",
            placeholder="例如：我该怎么让白纸上的字现形？",
        )
        if st.button("💬 点击求助鸡飞飞", key="ask_sparky", use_container_width=True):
            ask_sparky(game)
            st.rerun()
        for turn in game.sparky_history[-3:]:
            render_bubble(turn.text, kind="sparky", speaker="鸡飞飞")
        if st.button("🔋 给飞船充一点电（讲个科学小笑话）", key="charge_sparky", use_container_width=True):
            game.charge(8)
            st.session_state.flash = ("info", engine.sparky_charge(game.steps))
            st.rerun()

        md('<div class="pd-card pd-card--mint">')
        render_sci_backpack(game)
        md("</div>")

        md('<div class="pd-card pd-card--lilac">')
        render_clue_book(game)
        md(f'<div class="pd-hint">结案需要 3 条关键线索：已收集 '
           f'{len([c for c in engine.required_clues() if game.has_clue(c)])} / {len(engine.required_clues())}</div>')
        md("</div>")

        md('<div class="pd-card">')
        md('<div class="pd-card-title">📊 探案进度</div>')
        md(f'<div class="pd-hint">得分 <b>{game.score}</b> ｜ 行动 <b>{game.steps}</b> 次 ｜ '
           f'招供 <b>{len(game.confessed)}</b>/3 人</div>')
        if st.button("🔄 重新开始破案", key="reset_game", use_container_width=True):
            reset_game()
        md("</div>")

        render_compute_panel()
        md(f'<div class="pd-safety">🛡️ {engine.story.get("safety_note", "")}</div>')


def render_compute_panel() -> None:
    engine = load_engine()
    settings = st.session_state.llm_settings
    with st.expander("⚙️ 算力双模自适应（DGX Spark / 魔搭云端 / 童趣 Mock）", expanded=False):
        mode = st.selectbox(
            "算力模式",
            ["auto", "local", "cloud", "mock"],
            index=["auto", "local", "cloud", "mock"].index(settings.get("mode", "auto")),
            format_func=lambda key: {
                "auto": "🤖 自动（本地优先 → 云端 → 童趣 Mock）",
                "local": "⚡ DGX Spark 本地端侧推理",
                "cloud": "☁️ 魔搭云端 Qwen",
                "mock": "🎭 内置童趣智能 Mock 剧本",
            }[key],
            key="llm_mode",
        )
        settings["mode"] = mode
        if mode in ("auto", "cloud", "local"):
            api_key = st.text_input(
                "模型服务 API Key（可选，留空则用环境变量或自动 Mock）",
                value=settings.get("api_key", ""),
                type="password",
                key="llm_key",
            )
            settings["api_key"] = api_key
        if mode in ("auto", "local"):
            settings["local_base_url"] = st.text_input("DGX Spark 端点", value=settings.get("local_base_url"), key="llm_local_url")
            settings["local_model"] = st.text_input("本地模型名", value=settings.get("local_model"), key="llm_local_model")
        if mode in ("auto", "cloud"):
            settings["cloud_model"] = st.text_input(
                "云端模型名（留空自动匹配服务商）",
                value=settings.get("cloud_model", ""),
                placeholder="魔搭如 Qwen/Qwen3-32B；DashScope 如 qwen-plus",
                key="llm_cloud_model",
            )
        if st.button("🔁 重新探测算力", key="probe_llm", use_container_width=True):
            st.session_state.pop("_client_sig", None)
            get_client().refresh()
            st.rerun()

        client = get_client()
        info = client.health_check()
        dot = {"dgx_spark_local": "pd-dot", "modelscope_cloud": "pd-dot--cloud", "mock_script": "pd-dot--mock"}[info["mode"]]
        md(f'<div class="pd-status"><span class="pd-dot {dot}"></span>{info["label"]}</div>')
        md(f'<div class="pd-hint">{info["detail"]}</div>')
        if info.get("model"):
            md(f'<div class="pd-hint">模型：{info["model"]} ｜ 端点：{info["base_url"]}</div>')
        if info["mode"] == "dgx_spark_local":
            md('<div class="pd-hint">⚡ 端侧极速推理，小朋友的对话<b>零数据外泄</b>，全部留在你的 DGX Spark 里。</div>')
        elif info["mode"] == "mock_script":
            md('<div class="pd-hint">🎭 当前为内置童趣剧本模式：不联网也能完整通关，评审老师可直接体验全部剧情与三个科学实验。</div>')
        if info.get("error"):
            md(f'<div class="pd-hint">最近一次算力提示：{info["error"][:120]}</div>')
        ready = build_client_signature()
        if ready:
            md(f'<div class="pd-hint">已检测到环境变量：{ready}</div>')
        md(f'<div class="pd-hint">案情数据：{len(engine.clues())} 条线索 ｜ {len(engine.facts())} 个科学知识点</div>')


# ======================================================================
#  鸡飞飞求助
# ======================================================================
def ask_sparky(game: GameState) -> None:
    engine = game.engine
    question = st.session_state.get("sparky_question", "")
    context = {
        "suspect_id": game.active_suspect,
        "collected": game.collected_clues,
        "energy": game.energy,
        "missing": [c.get("name") for c in game.missing_clues()],
        "confessed": game.confessed,
        "guilt": game.guilt,
    }
    hint = engine.sparky_help(game.active_suspect, game.collected_clues)
    client = get_client()
    if client.backend.mode != MODE_MOCK and question:
        try:
            hint = client.chat(
                build_sparky_messages(engine.sparky, question, context=context),
                role_hint="sparky",
                context=context,
            )
        except Exception:
            hint = engine.sparky_help(game.active_suspect, game.collected_clues)
    game.sparky_history.append(ChatTurn(role="sparky", text=hint, speaker="鸡飞飞", kind="help"))
    game.charge(10)


# ======================================================================
#  嫌疑人对话
# ======================================================================
def suspect_reply(game: GameState, suspect_id: str, question: str) -> str:
    """优先用大模型扮演角色；无算力时回落到预设话题 + 童趣 Mock 剧本。"""
    engine = game.engine
    suspect = engine.suspect(suspect_id) or {}
    event = game.ask(suspect_id, question)
    scripted = event.get("reply", "")
    client = get_client()
    if client.backend.mode != MODE_MOCK:
        history = [
            {"role": "assistant" if turn.role == "suspect" else "user", "content": turn.text}
            for turn in game.history.get(suspect_id, [])[-8:]
        ]
        try:
            reply = client.chat(
                build_messages(
                    suspect,
                    history,
                    guilt=game.guilt_of(suspect_id),
                    mood=game.mood_of(suspect_id),
                    collected_clues=game.collected_clues,
                    engine=engine,
                ),
                role_hint="suspect",
                context={"suspect_id": suspect_id, "guilt": game.guilt_of(suspect_id)},
            )
            if reply:
                game.record_reply(suspect_id, reply, fact_id=suspect.get("science_fact_id"))
                game.charge(6)
                return reply
        except Exception:
            pass
    reply = scripted or client.chat(
        [{"role": "user", "content": question}],
        role_hint="suspect",
        context={"suspect_id": suspect_id, "guilt": game.guilt_of(suspect_id)},
    )
    game.record_reply(suspect_id, reply, fact_id=suspect.get("science_fact_id"))
    game.charge(6)
    return reply


def render_suspect_tab(game: GameState, suspect: Dict[str, Any]) -> None:
    engine = game.engine
    suspect_id = suspect["id"]
    left, right = st.columns([1, 1.35], gap="large")

    with left:
        render_stage(suspect, game.mood_of(suspect_id), game.guilt_of(suspect_id))
        md('<div class="pd-card pd-card--sky" style="margin-top:12px">'
           f'<div class="pd-card-title">🗣️ 他的说辞</div>'
           f'<div class="pd-hint">{suspect.get("alibi", "")}</div></div>')
        md('<div class="pd-card pd-card--butter">'
           '<div class="pd-card-title">🧪 对他出示道具做小实验</div>'
           '<div class="pd-hint">先从科学小背包选一个道具拿在手里，再点下面的按钮。</div>')
        if st.button(f"🔬 对{suspect['name']}出示 {game.active_item_label}", key=f"exp_{suspect_id}", use_container_width=True):
            game.active_suspect = suspect_id
            event = game.run_experiment(suspect_id)
            outcome = event.get("outcome")
            if outcome == "no_item":
                st.session_state.flash = ("warning", event.get("text", ""))
            elif outcome == "success":
                title = event.get("title", "小实验成功")
                body = event.get("reply", "")
                detail = event.get("detail", "")
                st.session_state.flash = ("success", f"{title}\n\n{body}\n\n🔬 {detail}")
            else:
                st.session_state.flash = ("info", event.get("reply", ""))
            st.rerun()
        md("</div>")

    with right:
        md('<div class="pd-card">')
        md('<div class="pd-card-title">💬 问问他</div>')
        turns = game.history.get(suspect_id, [])
        if not turns:
            render_bubble(f"（{suspect['name']}站在科学教室里，双手背在身后，眼睛不敢看你……）", kind="system", speaker="旁白")
            render_bubble(suspect.get("alibi", ""), kind="suspect", speaker=suspect["name"])
        for turn in turns[-14:]:
            kind = {"player": "player", "suspect": "suspect"}.get(turn.role, "system")
            if turn.kind == "confession":
                kind = "confession"
            elif turn.kind == "experiment":
                kind = "experiment"
            render_bubble(turn.text, kind=kind, speaker=turn.speaker or ("我" if turn.role == "player" else suspect["name"]))
        md("</div>")

        md('<div class="pd-card pd-card--mint">')
        question = st.text_input(
            f"想问{suspect['name']}什么？（想到什么问什么，越具体越好）",
            key=f"q_{suspect_id}",
            placeholder="例如：你昨晚到底在哪里？",
        )
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🎤 提问", key=f"ask_{suspect_id}", use_container_width=True):
                if question and question.strip():
                    game.active_suspect = suspect_id
                    suspect_reply(game, suspect_id, question.strip())
                    st.rerun()
                else:
                    st.session_state.flash = ("warning", "先输入你想问的话呀，小侦探。")
                    st.rerun()
        with col2:
            quick = suspect.get("quick_replies") or []
            pick = st.selectbox("或者选一句现成的", ["（自己输入）"] + quick, key=f"quick_{suspect_id}")
            if st.button("📣 就说这句", key=f"quickgo_{suspect_id}", use_container_width=True):
                if pick != "（自己输入）":
                    game.active_suspect = suspect_id
                    suspect_reply(game, suspect_id, pick)
                    st.rerun()
        md("</div>")

        last_fact = next((t.fact_id for t in reversed(turns) if t.fact_id), None)
        if last_fact:
            render_fact_card(last_fact, engine)


# ======================================================================
#  结案指认与通关仪式
# ======================================================================
def render_deduction(game: GameState) -> None:
    engine = game.engine
    md('<div class="pd-card pd-card--butter">')
    md('<div class="pd-card-title">⚖️ 结案时刻：是谁让金蛋消失的？</div>')
    if not game.can_deduct:
        missing = "、".join(c.get("name", "") for c in game.missing_clues())
        md(f'<div class="pd-hint">还差关键线索：<b>{missing}</b>。先找齐 3 条 ⭐ 关键线索，才能正式指认哦。</div>')
    md('<div class="pd-hint">提示：三个人都撒了谎，但只有一个人让金蛋<b>真的移动了位置</b>。</div>')
    cols = st.columns(3)
    for index, suspect in enumerate(engine.suspects()):
        with cols[index]:
            if st.button(
                f"{suspect['emoji']} 我指认{suspect['name']}",
                key=f"accuse_{suspect['id']}",
                use_container_width=True,
                disabled=not game.can_deduct,
            ):
                verdict = game.accuse(suspect["id"])
                st.session_state.flash = (
                    "success" if verdict["verdict"] == "correct" else "warning",
                    verdict.get("feedback", ""),
                )
                st.rerun()
    md("</div>")


def render_victory(game: GameState) -> None:
    """全屏通关仪式：勋章 + 三个科学知识点 + 鸡飞飞告别。"""
    engine = game.engine
    ending = engine.ending
    facts = engine.takeaway_facts()
    confetti = "".join(
        f'<span class="pd-confetti" style="left:{(i * 7) % 100}%;animation-duration:{2.6 + (i % 5) * 0.7}s;'
        f'animation-delay:{(i % 7) * 0.35}s">{e}</span>'
        for i, e in enumerate(["🎉", "⭐", "🥚", "✨", "🎊", "🏅", "🐤", "🧂", "🔦", "🧪", "🍀", "🌟"])
    )
    fact_cards = "".join(
        f'<div class="pd-takeaway"><b>知识点 {index + 1}｜{fact.get("emoji", "")} {fact.get("title", "")}</b>'
        f'<div>{fact.get("kid_explanation", "")}</div></div>'
        for index, fact in enumerate(facts)
    )
    verdict = game.final_verdict or {}
    md(
        '<div class="pd-victory-overlay">'
        f'{confetti}'
        '<div class="pd-victory-card">'
        f'{medal_svg(size=230)}'
        f'<div class="pd-victory-title">{ending.get("title", "🏅 通关啦！")}</div>'
        f'<div class="pd-victory-sub">恭喜 {game.player_name}！得分 {game.score} ｜ 行动 {game.steps} 次 ｜ '
        f'飞船电量 {game.energy}%</div>'
        f'{egg_svg(size=110)}'
        f'<div class="pd-takeaway"><b>🔍 案情真相</b><div>{verdict.get("explanation", "")}</div></div>'
        f'<div class="pd-takeaway"><b>📖 结案故事</b><div>{ending.get("narration", "")}</div></div>'
        f'{fact_cards}'
        f'<div class="pd-takeaway"><b>🐤 鸡飞飞说</b><div>{ending.get("sparky_bye", "")}</div></div>'
        f'<div class="pd-safety">⚠️ {ending.get("safety_reminder", "")}</div>'
        "</div></div>"
    )
    st.markdown('<div style="height:56vh"></div>')
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 再破一次案", key="again", use_container_width=True):
            reset_game()


def render_intro(game: GameState) -> None:
    engine = game.engine
    if st.session_state.get("intro_seen"):
        return
    md('<div class="pd-card pd-card--butter">')
    md('<div class="pd-card-title">📖 第一章 · 会发光的金蛋不见了</div>')
    md(f'<div class="pd-hint">{engine.story.get("opening", "")}</div>')
    md(f'<div class="pd-hint" style="margin-top:6px">{engine.story.get("brief", "")}</div>')
    md("</div>")
    md('<div class="pd-card pd-card--mint">')
    md('<div class="pd-card-title">🐤 口袋里的外星搭档</div>')
    md(f'<div class="pd-hint">{engine.story.get("sparky_intro", "")}</div>')
    md("</div>")
    md('<div class="pd-card pd-card--sky">')
    md('<div class="pd-card-title">🧭 小侦探攻略（三步破案法）</div>')
    md(
        '<div class="pd-hint">'
        '<b>第一步 勘查现场</b>：点🔍神探放大镜，再点案发现场的四个热点，收齐线索。<br>'
        '<b>第二步 提问 + 做实验</b>：找三个嫌疑人聊天，把<b>对的道具</b>给<b>对的人</b>——'
        '🧪碘伏棉签找潘小达的白纸、🔦手电筒照周晓晓的水槽、🧂食用盐袋查张爷爷的盐。'
        '心虚度满格他就会哭着招供。<br>'
        '<b>第三步 结案指认</b>：集齐 3 条 ⭐ 关键线索后，在下方指认真正让金蛋移动的人。'
        "</div>"
    )
    md("</div>")
    if st.button("🕵️ 我准备好啦，开始破案！", key="start_game", use_container_width=True):
        st.session_state.intro_seen = True
        game.charge(10)
        st.rerun()


def render_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    level, text = flash
    if not text:
        return
    mapping = {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}
    mapping.get(level, st.info)(text)


# ======================================================================
#  主程序
# ======================================================================
def main() -> None:
    inject_css()
    game = init_state()
    engine = game.engine

    render_header(engine)
    render_sidebar(game)
    render_flash()

    if game.won:
        render_victory(game)
        return

    render_intro(game)
    if not st.session_state.get("intro_seen"):
        return

    render_energy(game)
    render_scene(game)

    md('<div class="pd-card-title" style="margin-top:6px">🕵️‍♂️ 找嫌疑人问话（三个都撒了谎）</div>')
    tabs = st.tabs([f"{s['emoji']} {s['name']} · {s['nickname']}" for s in engine.suspects()])
    for tab, suspect in zip(tabs, engine.suspects()):
        with tab:
            render_suspect_tab(game, suspect)

    render_deduction(game)

    md('<div class="pd-safety" style="margin-top:14px">🧪 本游戏所有实验均为虚拟演示；小朋友自己动手做实验时，'
       "请一定请老师或家长陪同。游戏不收集任何个人信息。</div>")


if __name__ == "__main__":
    main()

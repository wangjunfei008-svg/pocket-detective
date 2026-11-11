"""口袋小神探：梧桐小学的消失金蛋
================================================
儿童科学探案游戏。本地模型、云端模型和离线剧本三种方式都能玩。
魔搭社区「AI+∞ 开发者创作大赛」第三期 · AI 造游戏赛道

启动：streamlit run app.py
"""

from __future__ import annotations

import html
import os
import sys
from typing import Any, Dict, Optional

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.characters import (  # noqa: E402
    MOOD_EMOJI,
    MOOD_LABELS,
    MOOD_NERVOUS,
    build_messages,
    build_sparky_messages,
)
from agents.game_state import (  # noqa: E402
    ENERGY_MAX,
    GUILT_CAP_BEFORE_EXPERIMENT,
    ChatTurn,
    GameState,
)
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
APP_SUBTITLE = "科学教室探案 · 8-12 岁 · 大约 15 分钟"
STYLE_PATH = os.path.join("assets", "style.css")
ENDPOINT_CONFIG_ENV = "POCKET_DETECTIVE_ALLOW_ENDPOINT_CONFIG"

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


def md(html_text: str, **kwargs: Any) -> None:
    st.markdown(html_text, unsafe_allow_html=True, **kwargs)


def esc(value: Any) -> str:
    """放进 unsafe_allow_html 之前，先把动态文字转成纯文本。"""
    return html.escape("" if value is None else str(value), quote=True)


def endpoint_config_enabled() -> bool:
    """公开页面默认不能改服务器的网址和密钥。大人用环境变量打开。"""
    return os.environ.get(ENDPOINT_CONFIG_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def case_is_playable(engine: ScienceEngine) -> bool:
    return bool(engine.suspects()) and bool(engine.items())


def privacy_lines(mode: str) -> Dict[str, str]:
    """按真正在用的后端写隐私说明，不把离线话说成永远成立。"""
    if mode == MODE_LOCAL:
        return {
            "badge": "🏠 对话留在这台电脑上",
            "detail": "现在用的是你自己电脑上的模型，话不会发到网上。别告诉游戏你的真名、学校和电话。",
            "parent": "当前是本地模式：对话发到本机的模型服务，不经过作者的服务器。",
        }
    if mode == MODE_CLOUD:
        return {
            "badge": "☁️ 对话会发给云端模型",
            "detail": "现在用的是云端模型，话会发到网上。别输入真名、学校、住址或电话。",
            "parent": "当前是云端模式：对话会发送到你配置的模型服务（例如魔搭或 DashScope）。请使用自己的密钥，并提醒孩子不要输入个人信息。",
        }
    return {
        "badge": "🔌 离线剧本 · 不联网",
        "detail": "现在是内置剧本，不联网，也不调用大模型。说的话不会发到网上。",
        "parent": "当前是离线剧本：不需要密钥，也不会把对话发给任何模型服务。",
    }


def bubble_html(text: str, *, kind: str = "suspect", speaker: str = "") -> str:
    if not text:
        return ""
    who_class = {
        "player": " pd-bubble-who--player",
        "sparky": " pd-bubble-who--sparky",
        "system": " pd-bubble-who--system",
    }.get(kind, "")
    label = speaker or {"player": "我", "sparky": "鸡飞飞", "system": "旁白"}.get(kind, "")
    safe = esc(text).replace("\n", "<br/>")
    chip = f'<span class="pd-bubble-who{who_class}">{esc(label)}</span><br/>' if label else ""
    return f'<div class="pd-bubble pd-bubble--{esc(kind)}">{chip}{safe}</div>'


def victory_card_html(game: GameState) -> str:
    """通关页只留短句，名字和模型句子都先转义。"""
    engine = game.engine
    ending = engine.ending
    verdict = game.final_verdict or {}
    confetti = "".join(
        f'<span class="pd-confetti" style="left:{(i * 7) % 100}%;animation-duration:{2.6 + (i % 5) * 0.7}s;'
        f'animation-delay:{(i % 7) * 0.35}s">{e}</span>'
        for i, e in enumerate(["🎉", "⭐", "🥚", "✨", "🎊", "🏅", "🐤", "🧂", "🔦", "🧪", "🍀", "🌟"])
    )
    cards = "".join(
        f'<div class="pd-takeaway"><b>知识点 {index + 1}</b><div>{esc(line)}</div></div>'
        for index, line in enumerate(ending.get("takeaways") or [])
    )
    return (
        '<div class="pd-victory-overlay">'
        f"{confetti}"
        '<div class="pd-victory-card">'
        f"{medal_svg(size=230)}"
        f'<div class="pd-victory-title">{esc(ending.get("title", "🏅 通关啦！"))}</div>'
        f'<div class="pd-victory-sub">恭喜 {esc(game.player_name)}！得分 {int(game.score)} ｜ '
        f"行动 {int(game.steps)} 次</div>"
        f"{egg_svg(size=110)}"
        f'<div class="pd-takeaway"><b>案情真相</b><div>{esc(verdict.get("explanation", ""))}</div></div>'
        f"{cards}"
        f'<div class="pd-takeaway"><b>鸡飞飞说</b><div>{esc(ending.get("sparky_bye", ""))}</div></div>'
        f'<div class="pd-safety">{esc(ending.get("safety_reminder", ""))}</div>'
        "</div></div>"
    )


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
    """公开部署忽略侧边栏里的网址和密钥，只认环境变量。"""
    if not endpoint_config_enabled():
        return LLMClient()
    mode = settings.get("mode") or "auto"
    explicit = {"local": MODE_LOCAL, "cloud": MODE_CLOUD, "mock": MODE_MOCK}.get(mode)
    return LLMClient(
        mode=explicit,
        api_key=settings.get("api_key", ""),
        local_base_url=settings.get("local_base_url") or DEFAULT_LOCAL_BASE_URL,
        local_model=settings.get("local_model") or DEFAULT_LOCAL_MODEL,
        cloud_base_url=settings.get("cloud_base_url") or DEFAULT_CLOUD_BASE_URL,
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
def render_header(engine: ScienceEngine, mode: str) -> None:
    lines = privacy_lines(mode)
    md(
        f'<div class="pd-title">🕵️ {esc(engine.meta.get("title", APP_TITLE))}</div>'
        f'<div class="pd-subtitle">{esc(engine.meta.get("subtitle", APP_SUBTITLE))}</div>'
    )
    md(
        '<div class="pd-badge-bar">'
        f'<span class="pd-badge">{esc(lines["badge"])}</span>'
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
        f'<div class="pd-stage-name">{esc(suspect["emoji"])} {esc(suspect["name"])}</div>'
        f'<div class="pd-stage-role">{esc(suspect["role"])} · {esc(suspect["age"])}</div>'
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
        f'<div class="pd-hint" style="text-align:center">{esc(engine.sparky.get("species", ""))}</div>'
        "</div>"
    )


def render_bubble(
    text: str,
    *,
    kind: str = "suspect",
    speaker: str = "",
) -> None:
    html_text = bubble_html(text, kind=kind, speaker=speaker)
    if html_text:
        md(html_text)


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
            f'<div class="pd-clue"><div class="pd-clue-name">{esc(clue.get("emoji", "🔎"))} '
            f'{esc(clue.get("name", ""))}{star}</div>'
            f'<div class="pd-clue-desc">{esc(clue.get("desc", ""))}</div></div>'
        )
    missing = game.missing_clues()
    if missing:
        md(
            f'<div class="pd-clue pd-clue--locked"><div class="pd-clue-name">❓ 还差 {len(missing)} 条关键线索</div>'
            f'<div class="pd-clue-desc">做对小实验才会出现。这里先不说是什么。</div></div>'
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
            md(
                f'<div class="pd-hint" style="margin:-2px 0 6px 4px">{esc(item["usage"])}<br>💡 {esc(item["science_note"])}</div>'
            )
    md(f'<div class="pd-status"><span class="pd-dot"></span>手上拿着：{esc(game.active_item_label)}</div>')


def render_scene(game: GameState) -> None:
    engine = game.engine
    scene = engine.scene()
    md('<div class="pd-card pd-card--mint">')
    md(f'<div class="pd-card-title">{esc(scene.get("emoji", "🔬"))} {esc(scene.get("name", "案发现场"))}</div>')
    md(f'<div class="pd-hint">{esc(scene.get("desc", ""))}</div>')
    md(scene_svg(size=300))
    cols = st.columns(min(4, max(1, len(engine.hotspots()))))
    for index, spot in enumerate(engine.hotspots()):
        with cols[index % len(cols)]:
            found = spot.get("clue_id") in game.collected_clues
            label = f"{'✅ ' if found else ''}{spot.get('emoji', '🔎')} {spot.get('name', '')}"
            if st.button(label, key=f"spot_{spot['id']}", use_container_width=True):
                event = game.inspect(spot["id"])
                if event.get("added"):
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
    steps = "".join(f"<li>{esc(step)}</li>" for step in fact.get("experiment_steps") or [])
    md(
        '<div class="pd-fact">'
        f'<div class="pd-fact-title">{esc(fact.get("emoji", "🔬"))} {esc(fact.get("title", ""))}</div>'
        f'<div class="pd-fact-body">{esc(fact.get("kid_explanation", ""))}</div>'
        f'<div class="pd-fact-body"><b>在家可以这样试（请家长陪同）：</b><ol>{steps}</ol></div>'
        f'<div class="pd-fact-body"><b>生活里：</b>{esc(fact.get("everyday_example", ""))}<br>'
        f'<b>安全：</b>{esc(fact.get("safety_tip", ""))}</div>'
        "</div>"
    )


# ======================================================================
#  侧边栏
# ======================================================================
def render_sidebar(game: GameState, mode: str) -> None:
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
        found = len([c for c in engine.required_clues() if game.has_clue(c)])
        md(f'<div class="pd-hint">关键线索：{found} / {len(engine.required_clues())}</div>')
        md("</div>")

        md('<div class="pd-card">')
        md('<div class="pd-card-title">📊 探案进度</div>')
        md(f'<div class="pd-hint">得分 <b>{game.score}</b> ｜ 行动 <b>{game.steps}</b> 次 ｜ '
           f'招供 <b>{len(game.confessed)}</b>/3 人</div>')
        if st.button("🔄 重新开始破案", key="reset_game", use_container_width=True):
            reset_game()
        md("</div>")

        render_compute_panel(mode)
        render_parent_panel(engine, mode)
        md(f'<div class="pd-safety">{esc(privacy_lines(mode)["detail"])} {esc(engine.story.get("safety_note", ""))}</div>')


def render_parent_panel(engine: ScienceEngine, mode: str) -> None:
    """给家长看的实验清单和隐私说明，默认折起来，不增加孩子的阅读量。"""
    with st.expander("家长和老师看这里"):
        st.markdown(privacy_lines(mode)["parent"])
        st.markdown(engine.story.get("parent_note") or "在家做实验，请大人陪在旁边。")
        for fact in engine.facts():
            st.markdown(f"**{fact.get('emoji', '')} {fact.get('title', '')}** · {fact.get('home_level', '必须家长陪同')}")
            for step in fact.get("experiment_steps") or []:
                st.markdown(f"- {step}")
            if fact.get("safety_tip"):
                st.caption(fact["safety_tip"])
        st.markdown("本地模型由大人在环境变量里配置。孩子的页面不能填写网址和密钥。")


def _render_backend_status(info: Dict[str, Any], *, show_endpoint: bool) -> None:
    dot = {"dgx_spark_local": "pd-dot", "modelscope_cloud": "pd-dot--cloud", "mock_script": "pd-dot--mock"}[info["mode"]]
    md(f'<div class="pd-status"><span class="pd-dot {dot}"></span>{esc(info["label"])}</div>')
    md(f'<div class="pd-hint">{esc(info["detail"])}</div>')
    if show_endpoint and info.get("model"):
        md(f'<div class="pd-hint">模型：{esc(info["model"])} ｜ 端点：{esc(info["base_url"])}</div>')
    if show_endpoint and info.get("error"):
        md(f'<div class="pd-hint">最近一次提示：{esc(str(info["error"])[:120])}</div>')


def render_compute_panel(mode: str) -> None:
    engine = load_engine()
    settings = st.session_state.llm_settings
    if not endpoint_config_enabled():
        with st.expander("现在用的是哪种回答", expanded=False):
            client = get_client()
            _render_backend_status(client.health_check(), show_endpoint=False)
            md(f'<div class="pd-hint">{esc(privacy_lines(mode)["detail"])}</div>')
            md(f'<div class="pd-hint">{len(engine.facts())} 个科学知识点。网址和密钥不在这里改。</div>')
        return

    with st.expander("大人设置：模型与端点", expanded=False):
        selected = st.selectbox(
            "算力模式",
            ["auto", "local", "cloud", "mock"],
            index=["auto", "local", "cloud", "mock"].index(settings.get("mode", "auto")),
            format_func=lambda key: {
                "auto": "自动（本地优先 → 云端 → 离线剧本）",
                "local": "本地模型",
                "cloud": "云端模型",
                "mock": "离线剧本",
            }[key],
            key="llm_mode",
        )
        settings["mode"] = selected
        if selected in ("auto", "cloud", "local"):
            api_key = st.text_input(
                "模型服务 API Key（可选，留空则用环境变量或离线剧本）",
                value=settings.get("api_key", ""),
                type="password",
                key="llm_key",
            )
            settings["api_key"] = api_key
        if selected in ("auto", "local"):
            settings["local_base_url"] = st.text_input(
                "本地模型端点", value=settings.get("local_base_url"), key="llm_local_url"
            )
            settings["local_model"] = st.text_input("本地模型名", value=settings.get("local_model"), key="llm_local_model")
        if selected in ("auto", "cloud"):
            settings["cloud_base_url"] = st.text_input(
                "云端端点（留空则按密钥自动选择）",
                value=settings.get("cloud_base_url", ""),
                key="llm_cloud_url",
            )
            settings["cloud_model"] = st.text_input(
                "云端模型名（留空自动匹配服务商）",
                value=settings.get("cloud_model", ""),
                placeholder="魔搭如 Qwen/Qwen3-32B；DashScope 如 qwen-plus",
                key="llm_cloud_model",
            )
        if st.button("重新探测", key="probe_llm", use_container_width=True):
            st.session_state.pop("_client_sig", None)
            get_client().refresh()
            st.rerun()

        client = get_client()
        info = client.health_check()
        _render_backend_status(info, show_endpoint=True)
        ready = build_client_signature()
        if ready:
            md(f'<div class="pd-hint">已检测到环境变量名：{esc(ready)}</div>')
        md('<div class="pd-hint">本地模式可以接家里的 DGX Spark，或其他 OpenAI 兼容服务。孩子的主界面不放这段说明。</div>')
        md(f'<div class="pd-hint">{len(engine.clues())} 条线索 ｜ {len(engine.facts())} 个科学知识点</div>')


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
        "missing_count": len(game.missing_clues()),
        "confessed": game.confessed,
        "guilt": game.guilt,
    }
    tier = min(2, len(game.sparky_history))
    hint = engine.sparky_help(game.active_suspect, game.collected_clues, tier=tier)
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
           f'<div class="pd-hint">{esc(suspect.get("alibi", ""))}</div></div>')
        if (
            game.guilt_of(suspect_id) >= GUILT_CAP_BEFORE_EXPERIMENT
            and suspect_id not in game.confessed
            and not game.experiment_done(suspect_id)
        ):
            md('<div class="pd-hint">他已经很慌了。先做对小实验，他才肯把秘密说完。</div>')
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
    md('<div class="pd-card-title">⚖️ 哪一句和证据对得上？</div>')
    if not game.can_deduct:
        md(
            f'<div class="pd-hint">还差 {len(game.missing_clues())} 条关键线索。'
            "找齐以后，再选一条你能解释的道理。</div>"
        )
        md("</div>")
        return
    md('<div class="pd-hint">三个人都说过谎。请选一句你能用线索解释的话。</div>')
    for option in engine.deduction.get("options") or []:
        if st.button(option.get("label", "这条道理"), key=f"accuse_{option.get('id')}", use_container_width=True):
            verdict = game.accuse(option.get("id", ""))
            st.session_state.flash = (
                "success" if verdict.get("verdict") == "correct" else "warning",
                verdict.get("feedback", ""),
            )
            st.rerun()
    md("</div>")


def render_victory(game: GameState) -> None:
    """通关页：短真相 + 三句知识点。完整故事放在折叠里。"""
    md(victory_card_html(game))
    with st.expander("想听完整结局"):
        st.write(game.engine.ending.get("narration", ""))
    col1, _col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 再破一次案", key="again", use_container_width=True):
            reset_game()


def render_intro(game: GameState) -> None:
    engine = game.engine
    if st.session_state.get("intro_seen"):
        return
    md('<div class="pd-card pd-card--butter">')
    md('<div class="pd-card-title">📖 金蛋不见了</div>')
    md(f'<div class="pd-hint">{esc(engine.story.get("opening", ""))}</div>')
    md(f'<div class="pd-hint" style="margin-top:6px">{esc(engine.story.get("brief", ""))}</div>')
    md(f'<div class="pd-hint" style="margin-top:6px">{esc(engine.story.get("sparky_intro", ""))}</div>')
    md("</div>")
    md('<div class="pd-card pd-card--sky">')
    md('<div class="pd-card-title">🧭 三步</div>')
    md(
        '<div class="pd-hint">'
        "<b>1. 看</b>：拿出放大镜，点现场的四个地方。<br>"
        "<b>2. 试</b>：选一件道具，给一位同学做实验。没有现象就换人。<br>"
        "<b>3. 讲</b>：关键线索齐了，选一句你能用证据解释的话。"
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

    client = get_client()
    render_header(engine, client.backend.mode)
    render_sidebar(game, client.backend.mode)
    render_flash()

    if not case_is_playable(engine):
        st.error("案情没有加载成功。请让大人检查 data/scenario.json 是不是还在。")
        return

    if game.won:
        render_victory(game)
        return

    render_intro(game)
    if not st.session_state.get("intro_seen"):
        return

    render_energy(game)
    render_scene(game)

    md('<div class="pd-card-title" style="margin-top:6px">找他们问一问</div>')
    tabs = st.tabs([f"{s['emoji']} {s['name']} · {s['nickname']}" for s in engine.suspects()])
    for tab, suspect in zip(tabs, engine.suspects()):
        with tab:
            render_suspect_tab(game, suspect)

    render_deduction(game)

    md(
        '<div class="pd-safety" style="margin-top:14px">'
        + esc(privacy_lines(client.backend.mode)["detail"])
        + " 在家做实验，请家长陪同。"
        "</div>"
    )


if __name__ == "__main__":
    main()

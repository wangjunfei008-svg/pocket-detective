"""游戏逻辑与科学交互单元测试。

运行：pytest -q      （或 python -m pytest tests -q）
覆盖：案情数据完整性、勘查/实验判定、心虚状态机、结案判定、
      算力双模降级、角色提示词与儿童安全红线。
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(ROOT, "app.py")
sys.path.insert(0, ROOT)

from agents.characters import (  # noqa: E402
    CHILD_SAFETY_RULES,
    MOOD_CONFESS,
    MOOD_NERVOUS,
    MOOD_NORMAL,
    MOOD_SURPRISED,
    build_messages,
    build_sparky_messages,
    build_system_prompt,
    mood_from_guilt,
)
from agents.game_state import ENERGY_MAX, MAX_GUILT, GameState  # noqa: E402
from assets.avatars import MOODS, avatar_data_uri, avatar_svg, medal_svg  # noqa: E402
from engine.llm_client import (  # noqa: E402
    DEFAULT_CLOUD_BASE_URL,
    MODE_CLOUD,
    MODE_LOCAL,
    MODE_MOCK,
    LLMClient,
    _probe,
    mock_reply,
)
from engine.science_facts import (  # noqa: E402
    OUTCOME_NOTHING,
    OUTCOME_SUCCESS,
    OUTCOME_WRONG_ITEM,
    ScienceEngine,
    load_scenario,
)


@pytest.fixture()
def engine() -> ScienceEngine:
    return ScienceEngine()


@pytest.fixture()
def game(engine: ScienceEngine) -> GameState:
    return GameState(engine)


def _collect_all_key_clues(game: GameState) -> None:
    for suspect_id, item_id in (("pan", "iodine_swab"), ("zhou", "flashlight"), ("zhang", "salt_bag")):
        game.select_item(item_id)
        game.run_experiment(suspect_id)


# ---------------------------------------------------------------- 案情数据
def test_scenario_loads_and_is_complete(engine: ScienceEngine) -> None:
    assert [s["id"] for s in engine.suspects()] == ["pan", "zhou", "zhang"]
    assert len(engine.facts()) == 3
    assert [i["id"] for i in engine.items()] == ["magnifier", "iodine_swab", "flashlight", "salt_bag"]
    assert set(engine.required_clues()) == {"clue_hidden_text", "clue_refilm", "clue_saltbag"}


def test_every_suspect_has_experiment_and_confession(engine: ScienceEngine) -> None:
    item_ids = {i["id"] for i in engine.items()}
    fact_ids = {f["id"] for f in engine.facts()}
    for suspect in engine.suspects():
        experiment = suspect.get("experiment") or {}
        assert experiment.get("item_id") in item_ids
        assert engine.clue(experiment["success_clue"]), suspect["id"]
        assert experiment.get("confession") and experiment.get("success_reply")
        assert suspect.get("topics") and suspect.get("press_lines")
        assert suspect["science_fact_id"] in fact_ids


def test_required_clues_all_exist(engine: ScienceEngine) -> None:
    for clue_id in engine.required_clues():
        clue = engine.clue(clue_id)
        assert clue and clue.get("desc") and clue.get("science_hint")


def test_fallback_scenario_when_file_missing(tmp_path) -> None:
    scenario = load_scenario(os.path.join(tmp_path, "nope.json"))
    assert scenario["suspects"] == []
    assert scenario["items"], "兜底案情必须仍有道具"
    assert ScienceEngine(scenario).sparky_help("nobody")


def test_all_science_facts_are_kid_safe() -> None:
    scenario = load_scenario()
    banned = ["恐怖", "血腥", "枪", "毒品", "赌博", "自杀"]
    for fact in scenario["science_facts"]:
        blob = fact["kid_explanation"] + fact.get("safety_tip", "")
        assert not any(word in blob for word in banned)
        assert fact["experiment_steps"] and fact["adult_note"]


# ---------------------------------------------------------------- 勘查
def test_inspect_requires_magnifier(game: GameState) -> None:
    event = game.inspect("hs_crystals")
    assert event["outcome"] == OUTCOME_NOTHING
    assert event["requires_item"] == "magnifier"
    assert not game.collected_clues

    game.select_item("magnifier")
    event = game.inspect("hs_crystals")
    assert event["outcome"] == OUTCOME_SUCCESS and event["added"]
    assert "clue_crystals" in game.collected_clues
    assert game.energy > 0


def test_inspect_is_idempotent(game: GameState) -> None:
    game.select_item("magnifier")
    game.inspect("hs_note")
    score = game.score
    game.inspect("hs_note")
    assert game.collected_clues.count("clue_note") == 1
    assert game.score == score


def test_inspect_unknown_hotspot(game: GameState) -> None:
    game.select_item("magnifier")
    assert game.inspect("hs_not_exist")["outcome"] == OUTCOME_NOTHING


# ---------------------------------------------------------------- 实验
@pytest.mark.parametrize(
    "suspect_id,item_id,clue_id",
    [
        ("pan", "iodine_swab", "clue_hidden_text"),
        ("zhou", "flashlight", "clue_refilm"),
        ("zhang", "salt_bag", "clue_saltbag"),
    ],
)
def test_correct_item_unlocks_key_clue(game: GameState, suspect_id: str, item_id: str, clue_id: str) -> None:
    game.select_item(item_id)
    event = game.run_experiment(suspect_id)
    assert event["outcome"] == OUTCOME_SUCCESS
    assert event["clue_id"] == clue_id and event["added"]
    assert game.guilt_of(suspect_id) >= 40
    assert fact_learned(game, suspect_id)
    assert event["detail"], "成功实验要给出童趣科学解释"


def fact_learned(game: GameState, suspect_id: str) -> bool:
    suspect = game.engine.suspect(suspect_id) or {}
    return suspect.get("science_fact_id") in game.facts_learned


@pytest.mark.parametrize(
    "suspect_id,wrong_item",
    [("pan", "salt_bag"), ("zhou", "iodine_swab"), ("zhang", "flashlight")],
)
def test_wrong_item_gives_no_reaction(game: GameState, suspect_id: str, wrong_item: str) -> None:
    game.select_item(wrong_item)
    event = game.run_experiment(suspect_id)
    assert event["outcome"] == OUTCOME_WRONG_ITEM
    assert event["reply"]
    assert not game.collected_clues


def test_experiment_without_item_is_blocked(game: GameState) -> None:
    assert game.run_experiment("pan")["outcome"] == "no_item"


def test_magnifier_on_suspect_reveals_body_language(game: GameState) -> None:
    game.select_item("magnifier")
    event = game.run_experiment("pan")
    assert event["outcome"] == OUTCOME_NOTHING
    assert event["guilt"] > 0
    text = game.history["pan"][-1].text
    assert any(cue in text for cue in ("书包侧袋", "指纹", "胶带", "白色粉末", "盐粒")), text


def test_repeating_solved_experiment_does_not_refarm(game: GameState) -> None:
    game.select_item("iodine_swab")
    game.run_experiment("pan")
    clues = list(game.collected_clues)
    event = game.run_experiment("pan")
    assert event["outcome"] == "already"
    assert game.collected_clues == clues


# ---------------------------------------------------------------- 心虚状态机
def test_guilt_clamps_and_drives_moods(game: GameState) -> None:
    assert game.add_guilt("pan", 10) == 10
    assert game.mood_of("pan") == MOOD_NORMAL
    game.add_guilt("pan", 20)
    assert game.mood_of("pan") == MOOD_SURPRISED
    game.add_guilt("pan", 30)
    assert game.mood_of("pan") == MOOD_NERVOUS
    game.add_guilt("pan", 999)
    assert game.guilt_of("pan") == MAX_GUILT
    assert game.mood_of("pan") == MOOD_CONFESS
    assert "pan" in game.confessed
    assert game.add_guilt("pan", -50) == MAX_GUILT, "招供后不能倒退"


def test_confession_recorded_once(game: GameState) -> None:
    game.select_item("iodine_swab")
    game.run_experiment("pan")
    game.add_guilt("pan", 60)
    assert game.confessed.count("pan") == 1
    confessions = [t for t in game.history["pan"] if t.kind == "confession"]
    assert len(confessions) == 1 and "烤肠" in confessions[0].text
    # 招供必须发生在实验反应之后，孩子才能看懂因果
    assert game.history["pan"][-1].kind == "confession"


def test_pure_questioning_also_triggers_confession(game: GameState) -> None:
    """实验 + 反复追问可以问满格并招供（不依赖 UI 层补写台词）。"""
    game.select_item("iodine_swab")
    game.run_experiment("pan")
    assert game.guilt_of("pan") < MAX_GUILT, "一次实验不该直接问满，孩子还得动嘴"
    for _ in range(6):
        game.ask("pan", "你口袋里那张白纸是什么")
    assert game.guilt_of("pan") == MAX_GUILT
    assert game.mood_of("pan") == MOOD_CONFESS
    assert any(t.kind == "confession" for t in game.history["pan"])


def test_mood_thresholds_boundaries() -> None:
    assert mood_from_guilt(0) == MOOD_NORMAL
    assert mood_from_guilt(24) == MOOD_NORMAL
    assert mood_from_guilt(25) == MOOD_SURPRISED
    assert mood_from_guilt(55) == MOOD_NERVOUS
    assert mood_from_guilt(99) == MOOD_NERVOUS
    assert mood_from_guilt(100) == MOOD_CONFESS
    assert mood_from_guilt(0, confessed=True) == MOOD_CONFESS


def test_energy_never_exceeds_max(game: GameState) -> None:
    for _ in range(30):
        game.charge(20)
    assert game.energy == ENERGY_MAX


# ---------------------------------------------------------------- 对话
def test_ask_matches_scripted_topic(game: GameState) -> None:
    event = game.ask("zhang", "飞碟？真的有飞碟吗？")
    assert event["topic_id"] == "zhang_ufo"
    assert "绿光" in event["reply"]
    assert game.guilt_of("zhang") > 0


def test_ask_unknown_question_falls_back_to_llm(game: GameState) -> None:
    event = game.ask("zhou", "你觉得外星人吃什么")
    assert event["needs_llm"] is True
    assert game.history["zhou"][-1].role == "player"


# ---------------------------------------------------------------- 结案
def test_cannot_deduct_without_key_clues(game: GameState) -> None:
    assert not game.can_deduct
    assert len(game.missing_clues()) == 3


def test_wrong_accusation_keeps_game_running(game: GameState) -> None:
    _collect_all_key_clues(game)
    verdict = game.accuse("pan")
    assert verdict["verdict"] == "wrong" and verdict["feedback"]
    assert game.stage == "playing" and not game.won
    assert game.deduction_attempts == 1


def test_correct_accusation_wins_and_awards(game: GameState) -> None:
    _collect_all_key_clues(game)
    verdict = game.accuse("zhang")
    assert verdict["verdict"] == "correct"
    assert game.won and game.energy == ENERGY_MAX
    assert "盐" in verdict["explanation"]
    assert game.score >= 300


def test_full_playthrough_is_winnable(game: GameState) -> None:
    """端到端：只靠放大镜 + 三个正确道具，就能从开局走到通关。"""
    game.select_item("magnifier")
    for spot in game.engine.hotspots():
        game.inspect(spot["id"])
    _collect_all_key_clues(game)
    for suspect_id in ("pan", "zhou", "zhang"):
        game.add_guilt(suspect_id, 60)
    assert game.can_deduct
    game.accuse("zhang")
    assert game.won
    assert len(game.engine.takeaway_facts()) == 3


# ---------------------------------------------------------------- 算力双模
def test_client_falls_back_to_mock_without_credentials(monkeypatch) -> None:
    for name in ("MODELSCOPE_API_TOKEN", "MODELSCOPE_API_KEY", "DASHSCOPE_API_KEY", "POCKET_DETECTIVE_FORCE_MOCK"):
        monkeypatch.delenv(name, raising=False)
    client = LLMClient(local_base_url="http://127.0.0.1:1/v1")
    client.refresh()
    assert client.backend.mode == MODE_MOCK
    assert client.chat([{"role": "user", "content": "你是谁"}], role_hint="sparky")


def test_client_uses_cloud_when_token_present(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "ms-test-token")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    client = LLMClient(local_base_url="http://127.0.0.1:1/v1")
    client.refresh()
    assert client.backend.mode == MODE_CLOUD
    assert "modelscope" in client.backend.base_url


@pytest.mark.parametrize(
    "api_key,cloud_base_url,expected_host,expected_model",
    [
        # 侧边栏手填 DashScope 的 sk- key：即使端点框里预填着魔搭，也要路由到 DashScope
        ("sk-dash-key", DEFAULT_CLOUD_BASE_URL, "dashscope.aliyuncs.com", "qwen-plus"),
        # 魔搭 token 走魔搭
        ("ms-token-key", DEFAULT_CLOUD_BASE_URL, "modelscope.cn", "Qwen/Qwen3-32B"),
        # 用户显式改过端点：完全尊重用户，不再猜服务商
        ("sk-dash-key", "https://my-vllm.local/v1", "my-vllm.local", "Qwen/Qwen3-32B"),
        # 自定义端点 + 自定义模型
        ("sk-dash-key", "https://my-vllm.local/v1", "my-vllm.local", "qwen-max"),
    ],
)
def test_cloud_provider_routing(api_key, cloud_base_url, expected_host, expected_model) -> None:
    client = LLMClient(api_key=api_key, cloud_base_url=cloud_base_url)
    if expected_model == "qwen-max":
        client.cloud_model = "qwen-max"
    base, model, key = client._cloud_credentials()
    assert expected_host in base, base
    assert model == expected_model
    assert key == api_key


def test_cloud_key_priority_is_user_then_env(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "ms-env")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-env")
    assert LLMClient()._cloud_credentials()[2] == "ms-env"
    assert LLMClient(api_key="sk-user-typed")._cloud_credentials()[2] == "sk-user-typed"


def test_client_prefers_local_when_reachable(monkeypatch) -> None:
    import engine.llm_client as llm

    monkeypatch.setattr(llm, "_probe", lambda url, api_key="", timeout=2.0: (True, 12))
    client = LLMClient()
    client.refresh()
    assert client.backend.mode == MODE_LOCAL
    assert "DGX Spark" in client.backend.label


# ------------------------------------------------------- 算力探测的严谨性
class _OpenAIHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            body = json.dumps({"object": "list", "data": [{"id": "Qwen3-32B", "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        else:
            body = b"nope"
            self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _JunkHandler(BaseHTTPRequestHandler):
    """本机 8000 端口上可能跑着的非 OpenAI 服务：返回 200 + HTML。"""

    def do_GET(self):  # noqa: N802
        body = b"<html>automation backend, definitely not openai</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_probe_only_trusts_real_openai_endpoints() -> None:
    """状态牌不能骗人：非 OpenAI 服务绝不能被标成「DGX Spark 端侧推理」。"""
    from engine import llm_client as llm

    openai_srv, openai_url = _serve(_OpenAIHandler)
    junk_srv, junk_url = _serve(_JunkHandler)
    try:
        llm._PROBE_CACHE.clear()
        assert _probe(openai_url)[0] is True
        assert _probe(junk_url)[0] is False, "200+HTML 的杂服务必须判为离线"
        assert _probe("http://127.0.0.1:1/v1")[0] is False

        client = LLMClient(local_base_url=openai_url)
        client.refresh()
        assert client.backend.mode == MODE_LOCAL

        client = LLMClient(local_base_url=junk_url)
        client.refresh()
        assert client.backend.mode == MODE_MOCK
    finally:
        openai_srv.shutdown()
        junk_srv.shutdown()


@pytest.mark.parametrize(
    "api_key,expected_label",
    [("sk-dashscope-key", "DashScope"), ("ms-modelscope-token", "ModelScope")],
)
def test_cloud_status_label_names_the_actual_provider(api_key: str, expected_label: str) -> None:
    client = LLMClient(api_key=api_key, mode="cloud")
    client.refresh()
    assert expected_label in client.backend.label, client.backend.label


def test_cloud_failure_degrades_to_mock_without_raising(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "ms-broken")
    client = LLMClient(local_base_url="http://127.0.0.1:1/v1")
    client.refresh()

    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(client, "_chat_openai", boom)
    reply = client.chat(
        [{"role": "user", "content": "你昨晚去哪了"}],
        role_hint="suspect",
        context={"suspect_id": "pan"},
    )
    assert reply and client.backend.mode == MODE_MOCK


def test_stream_chat_falls_back_to_mock() -> None:
    client = LLMClient(force_mock=True)
    chunks = list(client.stream_chat([{"role": "user", "content": "金蛋去哪了"}], role_hint="sparky"))
    assert chunks and "".join(chunks)


def test_mock_replies_are_never_empty() -> None:
    for suspect_id in ("pan", "zhou", "zhang"):
        for question in ("你昨晚在哪", "纸条是什么", "盐", "飞碟", "窗户", "你好", "asdfgh"):
            text = mock_reply(
                [{"role": "user", "content": question}],
                role_hint="suspect",
                context={"suspect_id": suspect_id},
            )
            assert text.strip() and len(text) <= 220
    assert mock_reply([{"role": "user", "content": "给我提示"}], role_hint="sparky")
    assert mock_reply([{"role": "user", "content": "描述现场"}], role_hint="narrator")


@pytest.mark.parametrize(
    "suspect_id,question,acceptable",
    [
        ("pan", "你口袋里那张白纸是什么", ("纸", "口袋")),
        ("pan", "烤肠好吃吗", ("烤肠", "零食", "饼干")),
        ("pan", "你好", ("零食", "虎牙", "嘿嘿")),
        ("zhou", "窗户真的是你锁的吗", ("窗户", "门锁")),
        ("zhou", "水槽里有什么特别的", ("水槽", "玻璃")),
        ("zhou", "你真聪明", ("脸红", "血管")),
        ("zhang", "飞碟？真的有飞碟吗", ("绿光", "飞碟")),
        ("zhang", "您为什么要撒盐", ("盐", "糖")),
        ("zhang", "想当年您发明过什么", ("扫地机", "当年")),
        ("zhang", "谢谢爷爷", ("糖", "嘴真甜")),
    ],
)
def test_mock_uses_the_right_topic_for_the_question(suspect_id: str, question: str, acceptable: tuple) -> None:
    """Mock 剧本必须答到点子上：命中最相关话题，而不是随便背一句台词。"""
    text = mock_reply(
        [{"role": "user", "content": question}],
        role_hint="suspect",
        context={"suspect_id": suspect_id, "guilt": 0},
    )
    assert any(word in text for word in acceptable), f"{suspect_id} 对「{question}」答非所问：{text}"


def test_mock_respects_guilt_and_energy_context() -> None:
    nervous = mock_reply(
        [{"role": "user", "content": "你到底去没去实验室"}],
        role_hint="suspect",
        context={"suspect_id": "pan", "guilt": 90},
    )
    assert any(cue in nervous for cue in ("发抖", "忍不住", "我招")), nervous
    calm = mock_reply(
        [{"role": "user", "content": "你到底去没去实验室"}],
        role_hint="suspect",
        context={"suspect_id": "pan", "guilt": 0},
    )
    assert "发誓" in calm or "操场" in calm or "实验室" in calm, calm
    assert "电量" in mock_reply(
        [{"role": "user", "content": "飞船电量多少"}],
        role_hint="sparky",
        context={"energy": 40},
    )


# ---------------------------------------------------------------- 角色与安全
def test_system_prompt_embeds_safety_and_persona(engine: ScienceEngine) -> None:
    for suspect in engine.suspects():
        prompt = build_system_prompt(suspect)
        assert "儿童内容安全红线" in prompt
        assert suspect["alibi"][:12] in prompt
        assert "6-12 岁" in CHILD_SAFETY_RULES


def test_build_messages_carries_guilt_and_clues(engine: ScienceEngine) -> None:
    suspect = engine.suspect("zhou")
    messages = build_messages(
        suspect,
        [{"role": "user", "content": "水槽里有什么"}],
        guilt=70,
        mood=MOOD_NERVOUS,
        collected_clues=["clue_water", "clue_crystals"],
        engine=engine,
    )
    joined = " ".join(m["content"] for m in messages)
    assert messages[0]["role"] == "system"
    assert "心虚度：70/100" in joined
    assert "一滩凉凉的清水" in joined


def test_sparky_never_gives_the_answer_away(engine: ScienceEngine) -> None:
    for suspect_id in ("pan", "zhou", "zhang", None):
        hint = engine.sparky_help(suspect_id, [])
        assert "张爷爷是凶手" not in hint and "指认张爷爷" not in hint
        assert len(hint) > 10
    messages = build_sparky_messages(engine.sparky, "是谁偷了金蛋", context={"energy": 50})
    assert "绝不直接说出" in messages[0]["content"]


def test_sparky_help_targets_the_missing_experiment(engine: ScienceEngine) -> None:
    assert "棉签" in engine.sparky_help("pan", [])
    assert "手电筒" in engine.sparky_help("zhou", [])
    assert "盐" in engine.sparky_help("zhang", [])
    solved = ["clue_hidden_text", "clue_refilm"]
    assert "盐" in engine.sparky_help("pan", solved)


# ---------------------------------------------------------------- 立绘
@pytest.mark.parametrize("who", ["sparky", "pan", "zhou", "zhang"])
@pytest.mark.parametrize("mood", MOODS)
def test_avatars_render_valid_svg(who: str, mood: str) -> None:
    svg = avatar_svg(who, mood, size=200)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "None" not in svg and "nan" not in svg.lower()


def test_unknown_avatar_falls_back_to_sparky() -> None:
    assert avatar_svg("nobody", "weird") == avatar_svg("sparky", "normal", 220)


def test_avatar_data_uri_and_medal() -> None:
    assert avatar_data_uri("pan", "nervous").startswith("data:image/svg+xml;base64,")
    assert "梧桐街金牌小神探" in medal_svg()


# ---------------------------------------------------------------- 资源与规范
def test_relative_paths_only() -> None:
    """创空间规范：不得出现绝对路径读取。"""
    for name in ("app.py", "engine/science_facts.py", "engine/llm_client.py", "agents/game_state.py"):
        text = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert 'open("/' not in text, name
        assert 'Path("/' not in text, name


def test_requirements_cover_imports() -> None:
    text = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read().lower()
    for pkg in ("streamlit", "requests", "openai"):
        assert pkg in text


def test_app_module_imports_cleanly() -> None:
    import app

    assert app.APP_TITLE.startswith("口袋小神探")
    assert callable(app.main)


# -------------------------------------------------- 端到端 UI（评审体验保障）
def _click(at, label: str) -> None:
    for button in at.button:
        if button.label == label:
            button.click().run()
            return
    raise AssertionError(f"找不到按钮「{label}」，现有：{[b.label for b in at.button]}")


def _start(at) -> None:
    _click(at, "🕵️ 我准备好啦，开始破案！")
    assert not at.exception, at.exception


def test_app_boots_without_exception_and_shows_safety_badge() -> None:
    """评审零配置点开 Space：不得白屏、不得抛异常，安全勋章必须在场。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    text = " ".join(m.value for m in at.markdown)
    for probe in ("DGX Spark", "100% 离线绿色安全", "保护儿童隐私", "科学小背包", "鸡飞飞"):
        assert probe in text, probe
    labels = [b.label for b in at.button]
    for item in ("🧪 碘伏棉签", "🔦 迷你手电筒", "🧂 食用盐袋", "🔍 神探放大镜"):
        assert item in labels, item


def test_full_ui_playthrough_reaches_medal_screen() -> None:
    """从开场到颁发勋章的完整点击路径（纯 Mock 算力，无网络）。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    _start(at)

    engine = at.session_state["game"].engine
    _click(at, "🔍 神探放大镜")
    for spot in engine.hotspots():
        _click(at, f"{spot.get('emoji', '🔎')} {spot.get('name', '')}")

    for item, who in (("🧪 碘伏棉签", "潘小达"), ("🔦 迷你手电筒", "周晓晓"), ("🧂 食用盐袋", "张爷爷")):
        _click(at, item)
        _click(at, f"🔬 对{who}出示 {item}")

    game = at.session_state["game"]
    assert game.can_deduct, game.collected_clues

    at.text_input(key="q_pan").set_value("你口袋里那张白纸是什么").run()
    at.button(key="ask_pan").click().run()
    assert game.history["pan"], "提问后应有对话记录"

    _click(at, "💬 点击求助鸡飞飞")
    assert game.sparky_history and game.energy > 0

    _click(at, "👦 我指认潘小达")
    assert not game.won, "错误指认不能通关"
    assert at.warning, "错误指认要给出鼓励式提示"

    _click(at, "👴 我指认张爷爷")
    assert game.won
    text = " ".join(m.value for m in at.markdown)
    for probe in ("梧桐街金牌小神探", "知识点 1", "知识点 2", "知识点 3", "淀粉", "折射", "浮力"):
        assert probe in text, probe
    assert any(b.label == "🔄 再破一次案" for b in at.button)
    assert not at.exception, [e.value for e in at.exception]


def test_wrong_item_shows_no_reaction_but_keeps_playing() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    _start(at)
    _click(at, "🧂 食用盐袋")
    _click(at, "🔬 对潘小达出示 🧂 食用盐袋")
    game = at.session_state["game"]
    assert not game.collected_clues
    assert not game.won
    assert not at.exception, [e.value for e in at.exception]


def test_replay_resets_to_a_fresh_case() -> None:
    """通关后「再破一次案」必须回到全新开局（含开场剧情），不能残留上一局线索。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    _start(at)
    _click(at, "🔍 神探放大镜")
    _click(at, "💧 水槽边的一滩清水")
    game = at.session_state["game"]
    assert game.collected_clues, "勘查后应已有线索"

    _click(at, "🔄 重新开始破案")
    fresh = at.session_state["game"]
    assert not fresh.collected_clues and fresh.score == 0 and not fresh.won
    assert not at.session_state.get("intro_seen"), "重开后应重新播放开场剧情"
    assert not at.exception, [e.value for e in at.exception]

"""科学一致性、引用完整性、隐私文案、HTML 转义和游戏平衡。"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents.characters import (  # noqa: E402
    CHILD_SAFETY_RULES,
    REVEAL_AFTER_EXPERIMENT,
    TONE_RULES,
    build_messages,
    build_system_prompt,
)
from agents.game_state import GUILT_CAP_BEFORE_EXPERIMENT, MAX_GUILT, GameState  # noqa: E402
from engine.llm_client import (  # noqa: E402
    COMPLETION_EXTRA_BODY,
    MODE_CLOUD,
    MODE_LOCAL,
    MODE_MOCK,
    LLMClient,
    child_output_ok,
    mock_reply,
    strip_think,
)
from engine.science_facts import ScienceEngine, load_scenario  # noqa: E402


@pytest.fixture()
def engine() -> ScienceEngine:
    return ScienceEngine()


@pytest.fixture()
def game(engine: ScienceEngine) -> GameState:
    return GameState(engine)


def _kid_blob(scenario: dict) -> str:
    """孩子能读到的文字。家长注释 adult_note 可以写更完整的公式。"""
    copied = json.loads(json.dumps(scenario, ensure_ascii=False))
    for fact in copied.get("science_facts") or []:
        fact.pop("adult_note", None)
    return json.dumps(copied, ensure_ascii=False)


def test_scenario_references_are_complete(engine: ScienceEngine) -> None:
    scenario = engine.scenario
    suspect_ids = {s["id"] for s in engine.suspects()}
    fact_ids = {f["id"] for f in engine.facts()}
    item_ids = {i["id"] for i in engine.items()}
    clue_ids = set(scenario["clues"])
    reachable = set()

    for spot in engine.hotspots():
        assert spot.get("clue_id") in clue_ids
        reachable.add(spot["clue_id"])
        assert "滑滑" not in spot.get("hint", "")
        assert "铅笔" not in spot.get("hint", "")
        assert "咸味" not in spot.get("hint", "")

    for suspect in engine.suspects():
        experiment = suspect["experiment"]
        assert experiment["item_id"] in item_ids
        assert experiment["success_clue"] in clue_ids
        reachable.add(experiment["success_clue"])
        bonus = experiment.get("confession_clue")
        if bonus:
            assert bonus in clue_ids
            reachable.add(bonus)
        assert suspect["science_fact_id"] in fact_ids
        assert suspect.get("body_language")

    for clue in scenario["clues"].values():
        assert clue.get("related_fact") in fact_ids
        assert clue.get("related_suspect") in suspect_ids
        assert clue.get("desc") and clue.get("science_hint")

    assert set(engine.required_clues()) <= clue_ids
    assert reachable == clue_ids

    culprit = scenario["deduction"]["final_answer"]["culprit"]
    assert culprit in suspect_ids
    options = scenario["deduction"]["options"]
    assert len({o["id"] for o in options}) == len(options)
    assert sum(o.get("verdict") == "correct" for o in options) == 1
    correct = next(o for o in options if o["verdict"] == "correct")
    assert correct["suspect_id"] == culprit
    for sid, fact_id in scenario["deduction"]["culprit_by_fact"].items():
        assert sid in suspect_ids
        assert fact_id in fact_ids
        assert engine.suspect(sid)["science_fact_id"] == fact_id
    assert len(scenario["ending"]["takeaways"]) == 3


def test_optics_is_refraction_a_child_can_try(engine: ScienceEngine) -> None:
    fact = engine.fact("light_refraction")
    kid = fact["kid_explanation"]
    assert "折射" in kid and "拐" in kid
    assert "全反射" not in kid
    assert "隐形" not in kid
    assert "膜" not in kid
    everyday = fact["everyday_example"]
    steps = "".join(fact["experiment_steps"])
    assert "潜望镜" not in everyday
    assert "硬币" in steps
    assert "激光笔" not in steps
    help_text = json.dumps(engine.sparky["help_lines"]["light_refraction"], ensure_ascii=False)
    assert "整个弹" not in help_text
    assert "全反射" not in help_text
    assert "拐" in engine.sparky_help("zhou", [], tier=0)


def test_buoyancy_and_story_agree(engine: ScienceEngine) -> None:
    fact = engine.fact("buoyancy_salt_water")
    kid = fact["kid_explanation"]
    assert "清水" in kid and "浓盐水" in kid
    assert "比水轻一点点" not in kid
    assert "浮力变大" not in kid
    assert "真金" in kid
    assert "等于" in kid
    everyday = fact["everyday_example"]
    assert "胀" in everyday
    assert "呛" in everyday or "大人" in everyday
    blob = _kid_blob(engine.scenario)
    for banned in ("淹不死", "通风口", "折射膜", "滑滑", "铅笔", "咸味", "DGX", "100% 离线"):
        assert banned not in blob, banned

    pan = engine.suspect("pan")["experiment"]["confession"]
    zhou = engine.suspect("zhou")["experiment"]["confession"]
    zhang = engine.suspect("zhang")["experiment"]["confession"]
    assert "不是我打翻" in pan and "已经不在" in pan
    assert "还在" in zhou and "罩" in zhou and "拐" in zhou
    assert "架子" in zhang and "盐" in zhang and "飞碟" in zhang
    explanation = engine.deduction["final_answer"]["explanation"]
    assert "架子" in explanation and "盐" in explanation
    assert "折射膜" not in explanation
    zhou_option = next(o for o in engine.deduction["options"] if o["id"] == "zhou_light")
    assert "还在水槽" not in zhou_option["feedback"]
    assert "罩" in zhou_option["feedback"]


def test_iodine_fact_stays_specific(engine: ScienceEngine) -> None:
    fact = engine.fact("starch_iodine")
    assert "淀粉" in fact["kid_explanation"] and "蓝紫" in fact["kid_explanation"]
    assert "白糖" in fact["everyday_example"] or "白糖" in fact["kid_explanation"]
    assert "品尝" not in fact["experiment_steps"][0]


def test_hint_ladder_starts_vague(engine: ScienceEngine) -> None:
    vague = engine.sparky_help("pan", [], tier=0)
    specific = engine.sparky_help("pan", [], tier=2)
    assert "棉签" not in vague
    assert "棉签" in specific
    assert "张爷爷是凶手" not in vague and "张爷爷是凶手" not in specific


def test_prompt_hides_secrets_until_the_experiment(engine: ScienceEngine) -> None:
    assert "DGX" not in TONE_RULES["sparky"]
    assert "品牌" in CHILD_SAFETY_RULES
    for suspect in engine.suspects():
        low = build_system_prompt(suspect, guilt=0, experiment_done=False)
        nervous = build_system_prompt(suspect, guilt=90, experiment_done=False)
        secret = REVEAL_AFTER_EXPERIMENT[suspect["id"]]
        assert secret not in low
        assert secret not in nervous
        assert "折射膜" not in low and "全反射" not in low and "DGX" not in low
        done = build_system_prompt(suspect, guilt=90, experiment_done=True)
        assert secret in done
        messages = build_messages(suspect, [], guilt=10, collected_clues=[], engine=engine)
        assert secret not in messages[0]["content"]


def test_questions_do_not_farm_guilt(game: GameState) -> None:
    first = game.ask("zhang", "这些白色小颗粒是盐吗")["guilt"]
    second = game.ask("zhang", "盐是你撒的吗")["guilt"]
    assert first == second == 25
    for _ in range(25):
        game.ask("pan", "今天语文作业多吗")
    assert game.guilt_of("pan") == 0
    assert "pan" not in game.confessed


def test_questions_alone_never_confess(game: GameState) -> None:
    questions = [
        "你昨晚去过科学教室吗",
        "口袋里的白纸是什么",
        "烤肠好吃吗",
        "地上的水怎么来的",
        "金蛋是你拿的吗",
        "你好呀",
    ]
    for _ in range(3):
        for question in questions:
            game.ask("pan", question)
    assert "pan" not in game.confessed
    assert game.guilt_of("pan") == GUILT_CAP_BEFORE_EXPERIMENT


def test_confession_needs_the_experiment(game: GameState) -> None:
    game.ask("pan", "口袋里的白纸是什么")
    game.ask("pan", "烤肠好吃吗")
    assert "pan" not in game.confessed
    game.select_item("iodine_swab")
    game.run_experiment("pan")
    assert "pan" in game.confessed
    assert game.history["pan"][-1].kind == "confession"

    fresh = GameState(game.engine)
    fresh.select_item("salt_bag")
    fresh.run_experiment("zhang")
    assert fresh.guilt_of("zhang") < MAX_GUILT
    assert "zhang" not in fresh.confessed
    fresh.ask("zhang", "这些白色小颗粒是盐吗")
    assert "zhang" not in fresh.confessed
    fresh.ask("zhang", "真的有飞碟吗")
    assert "zhang" in fresh.confessed
    assert "clue_egg_found" in fresh.collected_clues


def test_magnifier_and_inspect_do_not_double_count(game: GameState) -> None:
    game.select_item("magnifier")
    game.inspect("hs_note")
    assert game.energy == 20
    game.inspect("hs_crystals")
    assert game.energy == 40
    before = game.energy
    game.run_experiment("zhou")
    guilt = game.guilt_of("zhou")
    assert guilt == 6
    assert game.energy == before + 10
    game.run_experiment("zhou")
    assert game.guilt_of("zhou") == guilt
    assert game.energy == before + 10


def test_wrong_reason_is_not_a_win(game: GameState) -> None:
    game.select_item("magnifier")
    game.inspect("hs_rack")
    for suspect_id, item_id in (("pan", "iodine_swab"), ("zhou", "flashlight"), ("zhang", "salt_bag")):
        game.select_item(item_id)
        game.run_experiment(suspect_id)
    energy = game.energy
    score = game.score
    named_only = game.accuse("zhang")
    assert named_only["verdict"] == "wrong"
    assert not game.won
    missed = game.accuse("zhou_light")
    assert missed["verdict"] == "wrong"
    assert "光" in missed["feedback"]
    assert game.energy == energy - 30
    assert game.score == score - 40
    won = game.accuse("zhang_salt")
    assert won["verdict"] == "correct"
    assert game.won
    assert "通风口" not in won["explanation"]
    assert "架子" in won["explanation"]


def test_fallback_case_is_not_playable() -> None:
    import app

    scenario = load_scenario(os.path.join(ROOT, "missing-scenario.json"))
    assert scenario["suspects"] == []
    assert scenario["meta"].get("load_error")
    assert app.case_is_playable(ScienceEngine(scenario)) is False


def test_privacy_copy_follows_the_backend() -> None:
    import app

    offline = app.privacy_lines(MODE_MOCK)
    local = app.privacy_lines(MODE_LOCAL)
    cloud = app.privacy_lines(MODE_CLOUD)
    assert "离线" in offline["badge"] and "不联网" in offline["detail"]
    assert "云端" not in offline["badge"]
    assert "100% 离线" not in cloud["badge"]
    assert "云" in cloud["badge"]
    assert "网上" in cloud["detail"] or "发送" in cloud["parent"]
    assert "电脑" in local["badge"] or "本机" in local["parent"]
    assert "100% 离线" not in local["badge"]
    story = json.dumps(load_scenario()["story"], ensure_ascii=False)
    assert "一句话都不用发到天上" not in story
    assert "100% 离线" not in story


def test_dynamic_html_is_escaped(game: GameState) -> None:
    import app

    bubble = app.bubble_html("<img src=x onerror=alert(1)>", kind="player", speaker="</span><script>")
    assert "<img" not in bubble
    assert "<script>" not in bubble
    assert "&lt;img" in bubble
    game.player_name = "<b>小侦探</b>"
    game.final_verdict = {"explanation": "<script>alert(1)</script>金蛋在架子后面"}
    card = app.victory_card_html(game)
    assert "<script>" not in card
    assert "<b>小侦探</b>" not in card
    assert "&lt;b&gt;小侦探&lt;/b&gt;" in card
    assert "&lt;script&gt;" in card


def test_public_mode_ignores_sidebar_endpoint(monkeypatch) -> None:
    import app

    monkeypatch.setattr("engine.llm_client._probe", lambda *args, **kwargs: (False, 0))
    client = app.new_client(
        {
            "mode": "cloud",
            "api_key": "sk-visitor",
            "local_base_url": "http://169.254.169.254/latest",
            "local_model": "stolen",
            "cloud_base_url": "http://evil.example/v1",
            "cloud_model": "x",
        }
    )
    assert client.api_key == ""
    assert "evil.example" not in client.local_base_url
    assert "169.254" not in client.local_base_url
    assert client.backend.mode == MODE_MOCK

    monkeypatch.setenv("POCKET_DETECTIVE_ALLOW_ENDPOINT_CONFIG", "1")
    opened = app.new_client(
        {
            "mode": "local",
            "api_key": "",
            "local_base_url": "http://127.0.0.1:9/v1",
            "local_model": "demo",
            "cloud_base_url": "",
            "cloud_model": "",
        }
    )
    assert opened.local_base_url == "http://127.0.0.1:9/v1"
    assert app.endpoint_config_enabled() is True


def test_model_output_is_checked_per_request(monkeypatch) -> None:
    monkeypatch.setenv("MODELSCOPE_API_TOKEN", "ms-test")
    client = LLMClient(local_base_url="http://127.0.0.1:1/v1")
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection refused")
        if calls["n"] == 2:
            return "<think>先把秘密写在这里</think>This answer is entirely in English and should be dropped."
        return "<think>内部推理</think>咕叽！光斜着走进水里会拐弯。"

    monkeypatch.setattr(client, "_chat_openai", flaky)
    first = client.chat([{"role": "user", "content": "提示"}], role_hint="sparky", context={"energy": 10})
    assert client.backend.mode == MODE_CLOUD
    assert "咕叽" in first
    second = client.chat([{"role": "user", "content": "为什么"}], role_hint="sparky")
    assert "English" not in second
    assert "think" not in second.lower()
    assert client.backend.mode == MODE_CLOUD
    third = client.chat([{"role": "user", "content": "光"}], role_hint="sparky")
    assert "内部推理" not in third
    assert "拐弯" in third
    assert client.backend.mode == MODE_CLOUD


def test_openai_request_disables_thinking(monkeypatch) -> None:
    captured = {}

    class Fake:
        def __init__(self):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured.update(kwargs)
            content = "<think>不要给孩子看</think>咕叽！看一看水面是不是拐弯了。"
            message = type("M", (), {"content": content})()
            choice = type("C", (), {"message": message})()
            return type("R", (), {"choices": [choice]})()

    client = LLMClient(mode=MODE_CLOUD, api_key="ms-abc")
    monkeypatch.setattr(client, "_openai_client", lambda *args, **kwargs: Fake())
    text = client.chat([{"role": "user", "content": "为什么水面会弯"}], role_hint="sparky")
    assert "不要给孩子看" not in text
    assert "拐弯" in text
    extra = captured["extra_body"]
    assert extra["chat_template_kwargs"]["enable_thinking"] is False
    assert COMPLETION_EXTRA_BODY["chat_template_kwargs"]["enable_thinking"] is False


def test_stream_chat_strips_think_without_degrading(monkeypatch) -> None:
    class Delta:
        def __init__(self, content):
            self.content = content

    class Chunk:
        def __init__(self, content):
            choice = type("C", (), {"delta": Delta(content)})()
            self.choices = [choice]

    class Fake:
        def __init__(self):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            assert kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
            return iter([Chunk("<think>草稿</think>"), Chunk("咕叽！先看碗里的硬币。")])

    client = LLMClient(mode=MODE_CLOUD, api_key="ms-abc")
    monkeypatch.setattr(client, "_openai_client", lambda *args, **kwargs: Fake())
    text = "".join(client.stream_chat([{"role": "user", "content": "怎么办"}], role_hint="sparky"))
    assert "草稿" not in text
    assert "硬币" in text
    assert client.backend.mode == MODE_CLOUD


def test_strip_and_validate_helpers() -> None:
    assert strip_think("<think>秘密</think>咕叽") == "咕叽"
    assert strip_think("<THINK>没写完") == ""
    assert child_output_ok("咕叽！看水面。")
    assert not child_output_ok("<b>不好</b>")
    assert not child_output_ok("This is an English sentence without Chinese characters at all.")
    assert not child_output_ok("咕叽！" * 80)
    safe_mock = mock_reply([{"role": "user", "content": "给我提示"}], role_hint="sparky", context={"energy": 20})
    assert child_output_ok(safe_mock, role_hint="sparky")


def test_offline_playthrough_reaches_a_consistent_ending(game: GameState) -> None:
    """不连模型，用内置规则走完一局。"""
    game.select_item("magnifier")
    for spot in game.engine.hotspots():
        game.inspect(spot["id"])
    assert "clue_rack_glow" in game.collected_clues
    game.select_item("iodine_swab")
    game.run_experiment("pan")
    game.ask("pan", "口袋里的白纸是什么")
    game.ask("pan", "烤肠好吃吗")
    assert "pan" in game.confessed
    game.select_item("flashlight")
    game.run_experiment("zhou")
    game.ask("zhou", "窗台上的碗里有硬币吗")
    game.ask("zhou", "你昨晚几点回家")
    assert "zhou" in game.confessed
    game.select_item("salt_bag")
    game.run_experiment("zhang")
    game.ask("zhang", "这些白色小颗粒是盐吗")
    game.ask("zhang", "真的有飞碟吗")
    assert "zhang" in game.confessed
    assert game.can_deduct
    assert game.accuse("ufo")["verdict"] == "wrong"
    assert not game.won
    verdict = game.accuse("zhang_salt")
    assert verdict["verdict"] == "correct"
    assert game.won
    explanation = verdict["explanation"]
    assert "浓盐" in explanation or "盐" in explanation
    assert "架子" in explanation
    assert "通风口" not in explanation
    assert "折射膜" not in explanation

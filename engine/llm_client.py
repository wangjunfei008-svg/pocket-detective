"""算力双模自适应引擎。

三种算力后端，按优先级自动降级，任何情况下都不抛异常、不白屏：
1. DGX Spark 本地端侧模式  —— OpenAI 兼容服务（默认 http://localhost:8000/v1）
2. 魔搭创空间云端模式       —— ModelScope / DashScope 的 Qwen 兼容端点
3. 内置童趣智能 Mock 剧本   —— 零依赖兜底，评审点开 Space 也能完整通关

对外只暴露 `LLMClient.chat()` / `LLMClient.stream_chat()` 与 `describe_backend()`。
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

MODE_LOCAL = "dgx_spark_local"
MODE_CLOUD = "modelscope_cloud"
MODE_MOCK = "mock_script"

DEFAULT_LOCAL_BASE_URL = "http://localhost:8000/v1"
DEFAULT_LOCAL_MODEL = "Qwen3-32B"
DEFAULT_CLOUD_BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_CLOUD_MODEL = "Qwen/Qwen3-32B"
DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"

_PROBE_CACHE: Dict[str, tuple] = {}
_PROBE_TTL = 30.0


@dataclass
class BackendInfo:
    mode: str
    label: str
    base_url: str = ""
    model: str = ""
    detail: str = ""
    online: bool = True
    latency_ms: int = 0

    @property
    def is_local(self) -> bool:
        return self.mode == MODE_LOCAL

    @property
    def is_mock(self) -> bool:
        return self.mode == MODE_MOCK


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _truthy(value: Optional[str]) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _probe(url: str, api_key: str = "", timeout: float = 2.0) -> tuple:
    """探测 OpenAI 兼容服务是否可用（带 TTL 缓存，避免每次交互都联网）。

    只认 `/models` 返回的 OpenAI 形状 JSON（含非空 data 列表）：
    否则本机 8000 端口上跑着的其它服务（如创空间后端）会被误判成 DGX Spark。
    """
    key = f"{url}|{bool(api_key)}"
    cached = _PROBE_CACHE.get(key)
    now = time.time()
    if cached and now - cached[2] < _PROBE_TTL:
        return cached[0], cached[1]
    online, latency = False, 0
    started = time.perf_counter()
    try:
        import requests

        headers = {"Authorization": f"Bearer {api_key or 'EMPTY'}"}
        target = url.rstrip("/") + "/models"
        response = requests.get(target, headers=headers, timeout=timeout)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code < 400:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            online = isinstance(payload, dict) and isinstance(payload.get("data"), list) and bool(payload["data"])
    except Exception:
        online, latency = False, 0
    _PROBE_CACHE[key] = (online, latency, now)
    return online, latency


def invalidate_probe_cache() -> None:
    _PROBE_CACHE.clear()


class LLMClient:
    """儿童探案游戏的对话大脑：本地端侧 → 云端 → 童趣 Mock 三级自适应。"""

    def __init__(
        self,
        mode: Optional[str] = None,
        api_key: Optional[str] = None,
        local_base_url: Optional[str] = None,
        local_model: Optional[str] = None,
        cloud_base_url: Optional[str] = None,
        cloud_model: Optional[str] = None,
        temperature: float = 0.9,
        max_tokens: int = 512,
        timeout: float = 20.0,
        force_mock: bool = False,
    ):
        self.explicit_mode = mode
        self.api_key = (api_key or "").strip()
        self.local_base_url = (local_base_url or _env("DGX_SPARK_BASE_URL", "LOCAL_LLM_BASE_URL", default=DEFAULT_LOCAL_BASE_URL)).rstrip("/")
        self.local_model = local_model or _env("DGX_SPARK_MODEL", "LOCAL_LLM_MODEL", default=DEFAULT_LOCAL_MODEL)
        self.cloud_base_url = (cloud_base_url or "").rstrip("/")
        self.cloud_model = cloud_model or ""
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.force_mock = force_mock or _truthy(_env("POCKET_DETECTIVE_FORCE_MOCK"))
        self.last_error: str = ""
        self._client_cache: Dict[str, Any] = {}
        self._backend: Optional[BackendInfo] = None

    # ------------------------------------------------------------ 模式选择
    def _cloud_credentials(self) -> tuple:
        """解析 (base_url, model, api_key)。

        优先级：侧边栏手填 Key > MODELSCOPE_API_TOKEN > DASHSCOPE_API_KEY。
        服务商按 Key 形状推断：`sk-` 开头视为 DashScope，否则视为魔搭；
        用户在侧边栏显式改过端点时，完全尊重用户填写的端点。
        """
        token = _env("MODELSCOPE_API_TOKEN", "MODELSCOPE_API_KEY")
        dash = _env("DASHSCOPE_API_KEY")
        key = self.api_key or token or dash
        if not key:
            return "", "", ""

        endpoint_overridden = bool(self.cloud_base_url) and self.cloud_base_url != DEFAULT_CLOUD_BASE_URL
        if endpoint_overridden:
            base = self.cloud_base_url
        elif key.startswith("sk-") or key == dash:
            base = DEFAULT_DASHSCOPE_BASE_URL
        else:
            base = DEFAULT_CLOUD_BASE_URL

        default_model = DEFAULT_DASHSCOPE_MODEL if base == DEFAULT_DASHSCOPE_BASE_URL else DEFAULT_CLOUD_MODEL
        return base, (self.cloud_model or default_model), key

    def _cloud_label(self, base: str) -> str:
        if DEFAULT_DASHSCOPE_BASE_URL.rstrip("/").split("//")[-1] in base:
            return "☁️ 阿里云 DashScope · Qwen"
        if "modelscope" in base:
            return "☁️ 魔搭 ModelScope · Qwen"
        return "☁️ 自定义云端 OpenAI 兼容服务"

    def resolve_backend(self) -> BackendInfo:
        """决定当前算力后端；显式指定优先，否则自动探测并降级到 Mock。"""
        if self.force_mock:
            return BackendInfo(MODE_MOCK, "🎭 内置童趣智能 Mock 剧本", detail="离线剧本模式，零网络依赖，评审可完整通关")

        mode = self.explicit_mode
        if mode == MODE_CLOUD:
            base, model, key = self._cloud_credentials()
            if key:
                return BackendInfo(MODE_CLOUD, self._cloud_label(base), base_url=base, model=model, detail="使用您自己的密钥调用云端大模型")
            return BackendInfo(MODE_MOCK, "🎭 内置童趣智能 Mock 剧本", detail="未检测到云端密钥，已自动切换离线剧本")

        if mode == MODE_LOCAL:
            online, latency = _probe(self.local_base_url)
            return BackendInfo(
                MODE_LOCAL if online else MODE_MOCK,
                "⚡ NVIDIA DGX Spark 端侧推理" if online else "🎭 内置童趣智能 Mock 剧本",
                base_url=self.local_base_url,
                model=self.local_model,
                detail="100% 本地推理，数据不出机器" if online else f"未检测到本地服务 {self.local_base_url}，已自动切换离线剧本",
                online=online,
                latency_ms=latency,
            )

        # 自动模式：本地优先 → 云端 → Mock
        online, latency = _probe(self.local_base_url)
        if online:
            return BackendInfo(MODE_LOCAL, "⚡ NVIDIA DGX Spark 端侧推理", base_url=self.local_base_url, model=self.local_model, detail="100% 本地推理，数据不出机器", online=True, latency_ms=latency)
        base, model, key = self._cloud_credentials()
        if key:
            return BackendInfo(MODE_CLOUD, self._cloud_label(base), base_url=base, model=model, detail="使用您自己的密钥调用云端大模型")
        return BackendInfo(MODE_MOCK, "🎭 内置童趣智能 Mock 剧本", detail="未配置密钥且本地服务未启动，已自动切换离线剧本（不影响通关）")

    @property
    def backend(self) -> BackendInfo:
        if self._backend is None:
            self._backend = self.resolve_backend()
        return self._backend

    def refresh(self) -> BackendInfo:
        invalidate_probe_cache()
        self._backend = None
        self._client_cache.clear()
        return self.backend

    def describe_backend(self) -> str:
        info = self.backend
        parts = [info.label]
        if info.model:
            parts.append(f"模型：{info.model}")
        if info.base_url:
            parts.append(f"端点：{info.base_url}")
        if info.latency_ms:
            parts.append(f"延迟：{info.latency_ms} ms")
        if info.detail:
            parts.append(info.detail)
        return " · ".join(parts)

    # ------------------------------------------------------------ 调用
    def _openai_client(self, base_url: str, api_key: str):
        cache_key = f"{base_url}|{api_key[-6:] if api_key else ''}"
        if cache_key not in self._client_cache:
            from openai import OpenAI

            self._client_cache[cache_key] = OpenAI(base_url=base_url, api_key=api_key or "EMPTY", timeout=self.timeout, max_retries=1)
        return self._client_cache[cache_key]

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        role_hint: str = "",
        context: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """生成一条回复；任何后端异常都会安静地回落到 Mock 剧本。"""
        info = self.backend
        if info.mode != MODE_MOCK:
            try:
                text = self._chat_openai(info, messages, temperature, max_tokens)
                if text and text.strip():
                    return text.strip()
                self.last_error = "模型返回空内容"
            except Exception as exc:  # 网络/密钥/超时全部安全降级
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._backend = self.resolve_backend()
                if self._backend.mode != MODE_MOCK:
                    self._backend = BackendInfo(
                        MODE_MOCK,
                        "🎭 内置童趣智能 Mock 剧本",
                        detail=f"算力后端临时不可用（{self.last_error[:60]}），已自动切换离线剧本",
                    )
        return mock_reply(messages, role_hint=role_hint, context=context or {})

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        *,
        role_hint: str = "",
        context: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterable[str]:
        """流式输出；失败时整段回落到 Mock 剧本。"""
        info = self.backend
        if info.mode != MODE_MOCK:
            try:
                client = self._openai_client(info.base_url, self._api_key_for(info))
                stream = client.chat.completions.create(
                    model=info.model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                    max_tokens=self.max_tokens if max_tokens is None else max_tokens,
                    stream=True,
                )
                emitted = False
                buffer = ""
                for chunk in stream:
                    delta = getattr(chunk.choices[0].delta, "content", None) if chunk.choices else None
                    if delta:
                        emitted = True
                        buffer += delta
                        if len(buffer) >= 12:
                            yield buffer
                            buffer = ""
                if buffer:
                    yield buffer
                if emitted:
                    return
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
        yield mock_reply(messages, role_hint=role_hint, context=context or {})

    def _api_key_for(self, info: BackendInfo) -> str:
        if info.mode == MODE_CLOUD:
            _, _, key = self._cloud_credentials()
            return key
        return "EMPTY"

    def _chat_openai(self, info: BackendInfo, messages: List[Dict[str, str]], temperature: Optional[float], max_tokens: Optional[int]) -> str:
        client = self._openai_client(info.base_url, self._api_key_for(info))
        response = client.chat.completions.create(
            model=info.model,
            messages=messages,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens if max_tokens is None else max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    # ------------------------------------------------------------ 健康检查
    def health_check(self) -> Dict[str, Any]:
        info = self.backend
        return {
            "mode": info.mode,
            "label": info.label,
            "base_url": info.base_url,
            "model": info.model,
            "online": info.online,
            "latency_ms": info.latency_ms,
            "detail": info.detail,
            "error": self.last_error,
        }


# ======================================================================
#  内置童趣智能 Mock 剧本（零网络依赖，保证评审在线体验绝不白屏）
# ======================================================================
_STRIP = re.compile(r"[，。！？；：、,.!?;:\"'“”‘’（）()【】\s~…—\-·?？!！]+")


def _normalize(text: str) -> str:
    return _STRIP.sub("", (text or "").lower())


def _pick(options: List[str], seed: str = "") -> str:
    if not options:
        return "咕叽！"
    rng = random.Random(seed) if seed else random
    return rng.choice(options)


def mock_reply(messages: List[Dict[str, str]], *, role_hint: str = "", context: Optional[Dict[str, Any]] = None) -> str:
    """离线童趣剧本：按角色 + 关键词命中，永远返回一句适合小朋友的话。"""
    context = context or {}
    user_text = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_text = message.get("content", "")
            break
    text = _normalize(user_text)
    suspect_id = context.get("suspect_id", "")
    guilt = int(context.get("guilt", 0))

    if role_hint == "sparky":
        return _mock_sparky(text, context)
    if role_hint == "narrator":
        return _mock_narrator(text, context)
    return _mock_suspect(suspect_id, text, guilt, context)


_MOCK_FALLBACK = {
    "pan": [
        "（他咽了咽口水）「我、我什么都没干！你别用那种眼神看我，我手心都出汗了。」",
        "「这事儿跟我没关系！再说了，我口袋里只有零食，你查不出花来的！」",
        "「你问这么多干嘛呀……烤肠都要凉了！」",
    ],
    "zhou": [
        "（她扶了扶圆眼镜）「从科学角度讲，你的问题缺少可验证的证据。」",
        "「哼，我可是科学课代表，才不会做那种事。你、你别乱猜。」",
        "「我需要一点时间整理思路，你这个问题不太符合逻辑。」",
    ],
    "zhang": [
        "（他摸了摸胡子）「哎呀呀，小孩子别瞎猜，爷爷我在传达室修收音机呢。」",
        "「这事儿啊，跟飞碟有关系！……啊不是，跟爷爷没关系。」",
        "「想当年爷爷我啊，什么案子没见过。你这个小侦探，再问问？」",
    ],
}


def _mock_suspect(suspect_id: str, text: str, guilt: int, context: Dict[str, Any]) -> str:
    table: Dict[str, Dict[str, List[str]]] = {
        "pan": {
            "alibi": ["（他把手背在身后，眼睛往旁边瞟）「我昨晚一直在操场边吃烤肠！一口都没进过实验室！我发誓，用我的三根烤肠发誓！」", "「实验室？什么实验室？我连科学教室的门朝哪开都不太记得……嘿嘿。」"],
            "note": ["（他猛地捂住口袋）「没、没什么！就是一张白纸！上面什么都没有！我手心都出汗了……」", "「那张纸不是我的！……啊，它怎么在我口袋里，奇怪奇怪。」"],
            "water": ["「水？地上有水吗？那是窗户漏雨吧！九月份怎么会漏雨啊……我不是那个意思！」", "「我、我只是去洗了个手！真的！」"],
            "food": ["（他眼睛一亮）「烤肠！校门口王爷爷家的最好吃！等等——你套我话！我什么都没说！」", "「饼干、薯片、辣条、果冻……啊不是，我在说什么！」"],
            "egg": ["「金蛋那么重我搬不动的！我连一箱牛奶都搬不动，你让我搬金蛋？」", "「我偷它干嘛，又不能烤着吃！」"],
            "praise": ["（他咧嘴一笑，露出小虎牙）「嘿嘿，你人还怪好嘞。不过别想分我的零食，一根都不行！」", "「你夸我？那我可就不客气地收下啦，嘿嘿。」"],
        },
        "zhou": {
            "window": ["（她推了推圆眼镜）「窗户是我亲手锁的，锁扣扣得好好的。从科学角度讲，外人根本进不来。」", "「门锁状态我检查过三遍，你要看我的检查记录表吗？」"],
            "tank": ["（她飞快瞟了一眼水槽，把手背到身后）「水槽里干干净净，连一只苍蝇都飞不进去！你问水槽干什么？」", "「水槽……水槽很正常！就是、就是玻璃有点反光而已。」"],
            "egg": ["「金蛋是我们班最珍贵的展品！它不见了，我比谁都难过，你听明白了吗？」", "「为了它我做了两周的清洁计划表，我怎么会伤害它！」"],
            "home": ["「我昨晚七点整就回家了，作业本上有我妈的签字，精确到分钟。」", "「……七点半我给李博士发了条消息，问他金蛋睡不睡觉。这跟案子没关系！」"],
            "praise": ["（她的耳尖红了）「哼，我才没有脸红。被表扬时面部血管扩张是正常的生理反应……你继续问吧。」"],
        },
        "zhang": {
            "alibi": ["「爷爷我一整晚都在传达室，哪也没去！」他拍着胸脯，老收音机突然『刺啦』响了一声。", "「我？我在修收音机喽。小侦探，你信不信爷爷，爷爷就信你。」"],
            "ufo": ["（他胡子一抖）「昨晚一道绿光！嗖——金蛋就飞上去啦！爷爷我看了四十年大门，从没见过这么邪门的事！」说完自己先打了个哈哈。", "「飞碟的事你们小孩别问，爷爷我亲眼见的！……好吧，收音机里也是这么说的。」"],
            "salt": ["（他下意识摸胡子）「白白的？那是糖吧！爷爷我最爱吃糖喽。哎呀呀，小孩子别瞎猜。」", "「盐？爷爷的鞋上怎么会有盐……早上踩到雪了吧，九月的雪，嘿嘿。」"],
            "lastnight": ["「我一整晚都在传达室修老收音机，哪也没去！」收音机突然『刺啦』响了一声，他赶紧按下旋钮。", "「传达室、收音机、茶缸子，爷爷的活动范围就这么大。」"],
            "egg": ["「金蛋？爷爷疼它还来不及呢！那孩子长得俊还会发光，是我们梧桐小学的脸面呐。」", "「你说它咋就不见了呢，啧啧……爷爷的浮蛋实验还没做完喽。」"],
            "story": ["「想当年爷爷我用自行车链条和旧电扇，给全校做过自动扫地机！科学这东西，动手比动嘴重要喽。」"],
            "kind": ["「哎呀呀，你这小娃娃嘴真甜。」他眯眼笑着摸出一颗水果糖塞给你，「拿着，爷爷兜里永远有糖。」"],
        },
    }
    buckets = table.get(suspect_id) or {}
    keyword_map = {
        "alibi": ["昨晚", "昨天", "几点", "在哪", "哪里", "去过", "实验室", "不在场", "证明", "嫌疑"],
        "note": ["纸条", "信", "白纸", "无字", "口袋", "米汤", "密信", "写字", "淀粉", "碘"],
        "water": ["水", "打翻", "湿", "地上", "水槽", "玻璃", "膜", "反光", "隐形", "手电筒", "折射"],
        "food": ["烤肠", "零食", "吃", "饿", "好吃", "饼干", "电磁炉", "加热"],
        "egg": ["金蛋", "蛋", "偷", "拿", "芯片", "发光", "展品", "浮", "实验"],
        "window": ["窗户", "锁", "门锁", "门", "钥匙", "窗台", "苍蝇"],
        "tank": ["水槽", "玻璃", "透明", "膜", "隐形", "手电筒", "折射", "光"],
        "home": ["回家", "作业", "签字", "妈妈", "家", "班长", "课代表"],
        "praise": ["你好", "厉害", "聪明", "棒", "漂亮", "喜欢", "谢谢", "可爱", "帅"],
        "ufo": ["飞碟", "外星人", "ufo", "绿光", "天花板", "吸上去"],
        "salt": ["盐", "白色", "晶体", "咸", "倒", "一包", "糖水", "浮力", "密度"],
        "lastnight": ["传达室", "收音机", "修", "看门", "大门"],
        "story": ["当年", "发明", "机械", "古董", "故事", "扫地机"],
        "kind": ["爷爷", "您", "辛苦", "朋友", "同学"],
    }
    hit: List[str] = []
    best_hits = 0
    best_bucket = ""
    for bucket, words in keyword_map.items():
        if bucket not in buckets:
            continue  # 该角色没有这个话题，不能让它抢走匹配
        hits = sum(1 for word in words if _normalize(word) and _normalize(word) in text)
        if hits > best_hits:
            best_bucket, best_hits = bucket, hits
    if best_bucket:
        hit = list(buckets.get(best_bucket) or [])
    if not hit:
        hit = list(_MOCK_FALLBACK.get(suspect_id) or ["「我……我没什么可说的啦。」"])
    if guilt >= 70:
        # 心虚度满格前最后一档：必须表现出慌，不能还淡定地背台词
        hit = [
            "（他的声音开始发抖）「我……我可能、可能是隐瞒了一点点小事。」",
            "（他低下头，脚尖在地上画圈）「你别再问了嘛……我、我会忍不住说出来的。」",
            "（他后退半步，手紧紧按着口袋）「别再问了！我、我招还不行嘛……」",
        ]
    return _pick(hit, seed=text + suspect_id)


def _mock_sparky(text: str, context: Dict[str, Any]) -> str:
    if "电量" in text or "充电" in text or "飞船" in text:
        energy = int(context.get("energy", 0))
        if energy >= 80:
            return "「咕叽！飞船电量满格啦！都是小侦探用科学知识给我充的电，我们布思考斯星的人都记得你的好！」"
        return f"「咕叽！现在飞船电量 {energy}%。你每问一个好问题、每做一次小实验，我就能充上一格电，加油加油！」"
    if "怎么" in text or "提示" in text or "帮" in text or "不知道" in text or "卡" in text:
        return "「咕叽！布思考斯星侦探口诀：一看二闻三提问，动手做个小实验！先用🔍放大镜在现场找线索，再拿对的道具去找对的小朋友——道具和秘密是要配对的哟！」"
    if "科学" in text or "为什么" in text or "原理" in text:
        return "「咕叽！科学就是勇敢地问『为什么』。淀粉遇碘变蓝紫、光会拐弯、盐水浮力大——你今天已经比很多大人厉害啦！」"
    return _pick(
        [
            "「咕叽！我闻到案子的气味了，是好奇心的味道！」",
            "「小侦探真棒！我的螺旋桨都要开心得转起来啦～」",
            "「记住哦，遇到奇怪的事别急着害怕，先问一句『为什么』，那就是科学的开始！」",
        ],
        seed=text,
    )


def _mock_narrator(text: str, context: Dict[str, Any]) -> str:
    return _pick(
        [
            "科学教室里静悄悄的，只有仪器架上的试管轻轻碰了一下，发出『叮』的一声。",
            "窗外的银杏叶沙沙作响，好像也在替金蛋着急。",
            "阳光斜斜地照进水槽，水面闪了一下，像是在给你发暗号。",
        ],
        seed=text,
    )


__all__ = ["LLMClient", "BackendInfo", "MODE_LOCAL", "MODE_CLOUD", "MODE_MOCK", "mock_reply", "invalidate_probe_cache"]

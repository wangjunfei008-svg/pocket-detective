# 口袋小神探：梧桐小学的消失金蛋

儿童科学探案游戏，界面是中文，适合 **8–12 岁**。小朋友在科学教室里问话、做三个小实验，再用证据选择一条说得通的道理。

魔搭社区「AI+∞ 开发者创作大赛」第三期 · AI 造游戏赛道。

本地如果接了 OpenAI 兼容服务（例如家里的 DGX Spark），对话留在那台机器上。没有本地服务时，可以用你自己的云端密钥，或者完全不联网，用内置剧本把案子玩完。

---

## 玩什么，学什么

仿生金蛋从展台上不见了。三个人都撒了谎，但只有一个人让金蛋真正换了地方。

| 知识点 | 游戏里怎么遇到 | 在家可以怎么试 |
|---|---|---|
| 淀粉遇到碘会变蓝紫 | 碘伏棉签涂在看不出字的纸上 | 米汤写字，晾干后涂碘伏。白糖水和盐水不变色 |
| 光的折射 | 手电筒斜着照窗台上的硬币碗 | 硬币放进不透明的空碗，倒水后重新看见；水杯里的吸管像断了 |
| 清水里沉，浓盐水里浮 | 空盐袋和架子后面的光 | 先选一颗在清水里会沉的葡萄或鸡蛋，再分次加盐 |

这枚金蛋是空心道具，不是真金。它比同样大小的清水重一点，比浓盐水轻。浮在水面上时，水托它的力等于它的重量。光拐弯只改变看起来的位置，不会把东西搬走。

---

## 怎么运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

仓库里的 `.streamlit/config.toml` 把端口设成 **7860**，这是魔搭创空间的入口。本机想用另一套地址：

```bash
./run.sh          # macOS / Linux，默认 http://127.0.0.1:8501
run.bat           # Windows
```

不填密钥也能通关。魔搭部署请加上 `POCKET_DETECTIVE_FORCE_MOCK=1`，这样一定走内置剧本，不访问外网。

### 测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

当前 **102** 项测试，包含科学内容、案情引用、HTML 转义、隐私文案、心虚度规则，以及一条从开场点到勋章页的界面路径。测试会清掉环境里的密钥，不依赖你本机有没有配置 API Key。GitHub Actions 在 `.github/workflows/test.yml`，推送和拉取请求时跑同一条命令。

---

## 三种回答方式

程序按这个顺序自己选，某一次调用失败只会让这一句改用剧本，不会把后面的对话永久切走。

| 模式 | 什么时候用 | 隐私 |
|---|---|---|
| 本地 | `http://localhost:8000/v1` 上有 OpenAI 兼容服务，或你设置了 `DGX_SPARK_BASE_URL` | 对话发到你自己的机器，不发给作者 |
| 云端 | 环境里有 `MODELSCOPE_API_TOKEN`、`MODELSCOPE_API_KEY` 或 `DASHSCOPE_API_KEY` | 对话会发给这个密钥对应的服务。请提醒孩子不要输入真名、学校和电话 |
| 离线剧本 | 上面都没有，或设置了 `POCKET_DETECTIVE_FORCE_MOCK=1` | 不调用大模型，不联网 |

`sk-` 开头的密钥会走 DashScope，其他密钥走魔搭。Qwen3 的请求带 `chat_template_kwargs.enable_thinking=false`，返回里的 `<think>` 会被去掉。太长、满是英文或带危险词的句子，这一句改用剧本。

### 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `POCKET_DETECTIVE_FORCE_MOCK` | 设为 `1` 时只用离线剧本 | 关 |
| `POCKET_DETECTIVE_ALLOW_ENDPOINT_CONFIG` | 设为 `1` 时，侧边栏才允许填写网址、模型和密钥 | **关**。公开页面不能把服务器指到任意地址 |
| `DGX_SPARK_BASE_URL` / `LOCAL_LLM_BASE_URL` | 本地服务地址 | `http://localhost:8000/v1` |
| `DGX_SPARK_MODEL` / `LOCAL_LLM_MODEL` | 本地模型名 | `Qwen3-32B` |
| `MODELSCOPE_API_TOKEN` 或 `MODELSCOPE_API_KEY` | 魔搭密钥 | 空 |
| `DASHSCOPE_API_KEY` | DashScope 密钥 | 空 |
| `PORT` / `HOST` | 只影响 `run.sh` / `run.bat` | `8501` / `127.0.0.1` |

公开部署不要打开端点面板。密钥放在空间的环境变量里，不要写进页面。

本地服务示例：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-32B --port 8000 --max-model-len 8192
```

---

## 给家长

适合 8–12 岁，大约 15 分钟。游戏里的实验是虚拟的。在家做米汤显字、倒水看硬币、盐水浮鸡蛋时，请大人在旁边：不要品尝，碘伏会染色，用手电筒就够，不要用激光笔照眼睛。

侧边栏有一条折起来的「家长和老师看这里」，里面是三步操作和当前模式的隐私说明。孩子的主界面不放品牌广告。顶部的小牌子会跟着真正的模式变：离线、留在这台电脑，或会发给云端。不会在用云端的时候还写「100% 离线」。

---

## 怎么破案

游戏开场只说三步：看现场、拿道具试、最后选一句说得通的话。道具和人的对应关系不写在开场里。

| 步骤 | 做什么 |
|---|---|
| 看 | 先点放大镜，再点现场四个地方 |
| 试 | 碘伏棉签、手电筒、盐袋，分别对三个嫌疑人出示。不对就没有现象 |
| 问 | 同一个问题只让对方心虚一次。没做对他的实验，他不会把秘密说完 |
| 选 | 四条关键线索齐了，在四句结论里选。选错会扣一点能量和分数 |

真相在游戏通关页用短句写出来。这里留给想核对科学的大人：金蛋没有被风吹走，也没有被膜变没。张爷爷做了盐水实验，捞的时候手滑，金蛋沿着桌面滚到架子后面。潘小达是后来进来热烤肠的，那滩盐水不是他打翻的。周晓晓在练「倒水让硬币出现」，光拐弯让金蛋看起来像挪了位置，她离开时金蛋还在玻璃罩里。

---

## 目录

```text
app.py                      # Streamlit 界面
engine/science_facts.py     # 读 scenario.json，判定实验和结案
engine/llm_client.py        # 本地 / 云端 / 离线剧本
agents/game_state.py        # 背包、线索、心虚度（不依赖 Streamlit）
agents/characters.py        # 角色语气；秘密在实验做成之后才放进提示词
data/scenario.json          # 案情和科学说明
assets/                     # SVG 立绘和样式
tests/                      # 102 项测试
requirements.txt            # 运行依赖，版本已固定
requirements-dev.txt        # 再加 pytest
.streamlit/config.toml      # 创空间端口 7860
.github/workflows/test.yml
```

`GameState` 和 `ScienceEngine` 是纯 Python。换一桩案子，主要改 `data/scenario.json`。文件坏了不会白屏，页面会告诉大人去检查这个文件。

---

## 许可

代码可以学习参考。游戏里的实验是虚拟演示，小朋友自己动手时请家长或老师陪同。

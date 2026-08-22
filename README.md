# Interview Pilot — AI 面试模拟器

根据「简历 + 岗位 JD」生成定制化 AI 模拟面试：面试官流式提问、自适应追问，支持**语音问答**（用户语音输入 STT、面试官语音播报 TTS），结束后生成多维度评估报告，并可回看历史面试。

## 功能

- **JD 解析与面试计划**：粘贴完整 JD（+ 选填公司介绍）→ 结构化岗位画像 → 生成定制面试计划；公司调研使用百度搜索。
- **简历解析**：上传 PDF / Word，提取候选人画像，面试官据此结合真实经历追问。
- **流式对话**：WebSocket token 级流式输出，前端原位渲染。
- **语音输入（STT）**：讯飞语音听写，最长 5 分钟录音，服务端自动切分转写，微信式语音条 + 「转文字」。
- **语音播报（TTS）**：讯飞超拟人音色，音色/语速可选、手动点播、试听；自动过滤 `（笑）（停顿）` 等语气词。
- **评估报告**：五维度评分（专业深度/实践经验/结构化思维/沟通表达/学习能力）+ 亮点/薄弱点/学习建议。
- **历史记录**：面试记录持久化，可回放对话、查看报告、回放语音回答。

## 技术栈

- **后端**：FastAPI + WebSocket + Uvicorn
- **LLM 应用**：LangChain + DeepSeek（`langchain-openai`，OpenAI 兼容接口；也兼容 Anthropic/OpenAI key）
- **语音**：讯飞开放平台（STT 语音听写 + TTS 超拟人语音合成）
- **存储**：SQLite（`aiosqlite`），音频文件落盘
- **前端**：原生 HTML/CSS/JS 单文件

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env`，填入你的 key：

```env
# LLM（任选其一，推荐 DeepSeek）
DEEPSEEK_API_KEY=sk-xxx
# DEEPSEEK_MODEL=deepseek-chat
# DEEPSEEK_BASE_URL=https://api.deepseek.com

# 讯飞开放平台（STT + TTS 共用，注册后获取）
IFLYTEK_APP_ID=
IFLYTEK_API_KEY=
IFLYTEK_API_SECRET=

# 面试官 TTS 默认音色/语速（超拟人发音人 vcn；语速 0-100）
TTS_VOICE=x5_lingxiaotang_flow
TTS_SPEED=50
```

> 讯飞超拟人音色需在讯飞控制台「超拟人语音合成」里开通并添加发音人（免费版有字符额度）。不填 `IFLYTEK_*` 时，文本面试照常可用，仅语音功能不可用。

### 3. 启动

```bash
cd backend
python run_server.py
```

（等价于 `uvicorn main:app --host 0.0.0.0 --port 8000 --ws-max-size 67108864`，`run_server.py` 已内置 64MB WebSocket 上限以支持 5 分钟录音上传。）

### 4. 打开浏览器

访问 http://localhost:8000

> 语音输入（麦克风）需要 **HTTPS 或 localhost** 安全上下文；裸 IP 的 `http://` 下浏览器会禁用麦克风。

## 项目结构

```
interview-pilot/
├── backend/
│   ├── main.py              # FastAPI 入口（HTTP + WebSocket）
│   ├── run_server.py        # 启动脚本（内置 ws_max_size）
│   ├── config.py            # 集中配置（.env）
│   ├── requirements.txt
│   ├── .env.example
│   ├── agent/
│   │   ├── interviewer.py   # 面试官 LLM 链 + 评估
│   │   ├── prompts.py       # Prompt 模板
│   │   └── tools.py
│   ├── models/
│   │   └── interview.py     # 面试状态模型
│   ├── services/
│   │   ├── llm.py           # LLM 服务（DeepSeek/OpenAI/Anthropic）
│   │   ├── jd.py            # JD 解析 + 公司调研（百度）
│   │   ├── resume.py        # 简历解析（PDF/Word）
│   │   ├── asr.py           # 讯飞 STT（长录音切分转写）
│   │   ├── tts.py           # 讯飞超拟人 TTS
│   │   ├── session.py       # 会话管理（内存态）
│   │   └── history.py       # 历史持久化（SQLite）
│   └── data/
│       ├── scenarios/       # 面试场景
│       ├── interviews.db    # 历史数据库
│       └── audio/           # 语音回答音频
└── frontend/
    └── index.html           # 前端界面（单文件）
```

## 已知限制

- 会话状态在内存（单进程），重启即丢；需 `--workers 1`。
- 暂未做用户鉴权/多用户隔离。
- 讯飞超拟人 TTS 有字符额度，手动点播以节省额度。

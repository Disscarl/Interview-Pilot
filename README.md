# Interview Pilot — AI 面试模拟器

根据「简历 + 岗位 JD」生成定制化 AI 模拟面试：面试官流式提问、自适应追问，支持**语音问答**（用户语音输入 STT、面试官语音播报 TTS），结束后生成多维度评估报告，并可回看历史面试。支持**注册/登录（JWT）与多用户数据隔离**。

## 功能

- **JD 解析与面试计划**：粘贴完整 JD（+ 选填公司介绍）→ 结构化岗位画像 → 生成定制面试计划；公司调研使用百度搜索。
- **简历解析**：上传 PDF / Word，提取候选人画像，面试官据此结合真实经历追问。
- **流式对话**：WebSocket token 级流式输出，前端原位渲染；断线自动重连并恢复会话。
- **自适应追问（回答质量评分）**：每轮回答后由 LLM 快速评分（1-5）并注入下一题提示，评分低引导细节、评分高升级到架构/方案层难度。
- **工具调用（Function Calling）**：面试官通过 `bind_tools` 调用真实工具——按关键词检索候选人简历片段、查询公司调研资料，让追问基于真实经历而非凭空猜测（工具执行与结果回填可见于日志）。
- **语音输入（STT）**：讯飞语音听写，最长 5 分钟录音，服务端自动切分转写，微信式语音条 + 「转文字」。
- **语音播报（TTS）**：讯飞超拟人音色，音色/语速可选、手动点播、试听；自动过滤 `（笑）（停顿）` 等语气词。
- **评估报告**：多维度评分（进度条 + 雷达图）+ 亮点/薄弱点/学习建议。
- **历史记录**：面试记录持久化（按用户隔离），可回放对话、查看报告、回放语音回答。
- **进步趋势**：历史页按「岗位+公司」分组，展示多轮面试的总分趋势折线与最新一轮维度雷达图。
- **用户系统**：注册/登录（PBKDF2 密码哈希 + HS256 JWT），历史/音频/会话均按用户隔离。

## 技术栈

- **后端**：FastAPI + WebSocket + Uvicorn（单进程 `--workers 1`）
- **LLM 应用**：LangChain + DeepSeek（`langchain-openai`，OpenAI 兼容接口；也兼容 Anthropic/OpenAI key）
- **Agent 编排**：LangGraph 面试状态图（每轮一步：`score_answer → route → generate_question / evaluate`，用户回答即人工输入点；WS 协议不变）+ `bind_tools` 工具调用闭环
- **语音**：讯飞开放平台（STT 语音听写 + TTS 超拟人语音合成）
- **存储**：SQLite（`aiosqlite`），音频文件落盘，TTS 结果磁盘缓存
- **前端**：Vue 3 + Vite + TypeScript（组件化，见 `frontend/src/`）

## 快速开始

### 1. 后端依赖与配置

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入你的 key
```

`.env` 关键项：

```env
# LLM（任选其一，推荐 DeepSeek）
DEEPSEEK_API_KEY=sk-xxx
# DEEPSEEK_MODEL=deepseek-chat
# DEEPSEEK_BASE_URL=https://api.deepseek.com

# JWT 密钥（务必修改；INTERVIEW_PILOT_ENV=prod 时缺失会拒绝启动）
JWT_SECRET=请改成一段足够长的随机字符串

# 讯飞开放平台（STT + TTS 共用，注册后获取）
IFLYTEK_APP_ID=
IFLYTEK_API_KEY=
IFLYTEK_API_SECRET=

# 面试官 TTS 默认音色/语速（超拟人发音人 vcn；语速 0-100）
TTS_VOICE=x5_lingxiaotang_flow
TTS_SPEED=50
```

> 讯飞超拟人音色需在讯飞控制台「超拟人语音合成」里开通并添加发音人（免费版有字符额度）。不填 `IFLYTEK_*` 时，文本面试照常可用，仅语音功能不可用。

### 2. 前端构建（生产模式）

```bash
cd frontend
npm install
npm run build        # 产出 frontend/dist/
npm run typecheck    # 可选：TypeScript 类型检查
```

后端会在每次请求时探测 `frontend/dist/index.html`：一旦构建产物存在，`/` 即返回新版前端（无需重启）；未构建时回退到 `frontend/legacy.html`（自包含旧版界面）。

前端开发调试可另开终端 `cd frontend && npm run dev`（Vite 开发服务器代理 `/api`、`/ws` 到 :8000）。

### 3. 启动后端

```bash
cd backend
python run_server.py
```

（等价于 `uvicorn main:app --host 0.0.0.0 --port 8000 --ws-max-size 67108864`，`run_server.py` 已内置 64MB WebSocket 上限以支持 5 分钟录音上传。）

### 4. 打开浏览器

访问 http://localhost:8000 ，注册账号后开始面试。

> 语音输入（麦克风）需要 **HTTPS 或 localhost** 安全上下文；裸 IP 的 `http://` 下浏览器会禁用麦克风。

## 项目结构

```
interview-pilot/
├── backend/
│   ├── main.py              # FastAPI 入口（HTTP + WebSocket + 静态服务）
│   ├── run_server.py        # 启动脚本（内置 ws_max_size）
│   ├── config.py            # 集中配置（.env）
│   ├── requirements.txt
│   ├── .env.example
│   ├── agent/
│   │   ├── interviewer.py   # 面试官 LLM 链 + 评估（结构化输出）
│   │   ├── graph.py         # LangGraph 面试步骤状态图（评分→路由→出题/评估）
│   │   └── prompts.py       # Prompt 模板
│   ├── models/
│   │   └── interview.py     # 面试状态模型
│   ├── services/
│   │   ├── auth.py          # 密码哈希 + JWT
│   │   ├── ratelimit.py     # 内存限流
│   │   ├── llm.py           # LLM 服务（DeepSeek/OpenAI/Anthropic）
│   │   ├── jd.py            # JD 解析 + 公司调研（百度）
│   │   ├── resume.py        # 简历解析（PDF/Word）
│   │   ├── asr.py           # 讯飞 STT（长录音切分转写）
│   │   ├── tts.py           # 讯飞超拟人 TTS + 磁盘缓存
│   │   ├── session.py       # 会话管理（内存态，TTL 清理）
│   │   └── history.py       # 历史持久化（SQLite）
│   ├── tests/               # unittest 测试（离线、确定性）
│   └── data/
│       ├── scenarios/       # 面试场景
│       ├── interviews.db    # 历史数据库（gitignore）
│       └── audio/           # 语音回答音频（gitignore）
├── frontend/
│   ├── index.html           # Vite 入口
│   ├── package.json / vite.config.ts / tsconfig.json
│   ├── src/                 # Vue3 + TS 源码（组件/视图/store/api）
│   └── legacy.html          # 未构建时的自包含回退页
└── .github/workflows/ci.yml # 后端 unittest + 前端构建/类型检查
```

## 测试

```bash
cd backend
python -m unittest discover -s tests -t . -v
```

CI（GitHub Actions）会运行后端测试 + 前端 `npm run build` / `npm run typecheck`。

## 评测（LLM-as-judge）

```bash
cd backend
python evals/eval_interviewer.py   # 需配置 LLM key
```

输出三项指标：**追问相关性**（1-5 平均分）、**回答评分稳定性**（同一回答多次评分的最大差值）、**报告字段完整性**（必填字段/分数范围/摘要）。评估与评分使用 `with_structured_output`（Pydantic schema，DeepSeek 走 function calling），不再依赖手写 JSON 解析。

每次 LLM 调用会在后端日志打印 prompt 摘要与 token 数（本地可观测，无需 LangSmith）。

## 已知限制

- 会话状态在内存（单进程），重启即丢；需 `--workers 1`。
- 讯飞超拟人 TTS 有字符额度，手动点播以节省额度。
- 部署上线建议：Docker + HTTPS 反向代理（麦克风需安全上下文）、多进程/Redis 限流。

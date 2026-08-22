# Interview Pilot 待办清单

> 分区说明：**当前先不处理**「公网部署发布」和「发到 git 仓库」相关事项，已移入 🔮 未来计划。
> 状态：`[ ]` 未开始 / `[x]` 已完成。

## ✅ 已完成
- [x] Phase 1 工程基础：`.gitignore`、`config.py` 集中配置 + `.env.example`、结构化日志、音频清理（删除联动 + 孤儿清理）、README 重写、`requirements.txt` 补全
- [x] H1 会话内存泄漏（WS 处理器 `finally` 中删除会话）
- [x] N1 删除未鉴权的 `/api/sessions/{id}/report`（死代码 + transcript 泄露）
- [x] N2 登录/注册加 per-IP 限流（10/min）
- [x] N3 注册用户名/密码长度上限（2-64 / 4-128）

---

## 🔴 Blocker（当前待办 · 上线前必须）
- [x] **B1 鉴权与多用户隔离**（已处理：JWT 注册/登录 + `users` 表 + 历史/音频/WS 按 `user_id` 隔离；前端登录视图 + token）
  - 位置：`backend/main.py`、`services/auth.py`（stdlib JWT + PBKDF2）、`services/history.py`（users 表 + user_id）、`frontend/index.html`（登录视图）。
  - 说明：旧历史数据 `user_id=NULL` 登录后不可见；音频用 `?token=` query 授权（`<audio>` 无法带头）。
- [x] **B2 限流与输入长度上限**（已处理：新增 `services/ratelimit.py` 内存固定窗口限流；jd/tts/resume/stt 各自限流 + 文本/文件/音频大小上限）
  - 位置：`backend/services/ratelimit.py`、`backend/main.py`。
  - 说明：jd=10/min、tts=30/min、resume=30/min、stt=20/min（per user）；JD 文本≤20000、TTS 文本≤500、简历文件≤10MB、语音≤15MB。
- [x] **B3 删除 `fetch_url_text` 死代码（SSRF 隐患）**（已处理：删 `fetch_url_text`/`is_blocked`/`_BLOCK_MARKERS`，保留 `_BROWSER_HEADERS`/`strip_html` 给百度搜索用）
  - 位置：`backend/services/jd.py`。
  - 说明：URL 抓取功能已移除，该函数无调用方；未来重新暴露即 SSRF，故删除。

## 🟠 高优先级（当前待办 · 正确性/生命周期）
- [x] **H2 死代码清理 + 修正"Agent"措辞**（已处理：删 tools.py 三个 @tool、删 `record_score`/`scores`/`topics_covered`、README/注释改为"LLM 应用/LLM 链"）
  - 位置：`agent/tools.py`、`models/interview.py`、`agent/prompts.py`、`agent/interviewer.py`。
  - 说明：当前是普通 LLM 链而非工具调用 Agent；`topics_covered` 因需每问一次额外 LLM 抽取话题（成本）而直接移除，改用对话历史提供上下文。
- [x] **H3 音频异步写盘**（已处理：`await asyncio.to_thread(_write_bytes, ...)`）
  - 位置：`backend/main.py` WS `answer_audio`。
  - 影响：5 分钟 WAV（约 9.6MB）同步写盘阻塞事件循环。
  - 方案：`await asyncio.to_thread(...)` 或 `aiofiles`。
- [x] **H4 百度搜索 title/snippet 错位**（已处理：按 `<h3>` 切块，标题与摘要同块配对）
  - 位置：`backend/services/jd.py` `_search_baidu`。
  - 影响：标题与摘要按下标独立配对，数量/顺序不一致会张冠李戴。
  - 方案：按单个结果块同时抽取 title + snippet 配对。
- [x] **H5 WebSocket 断线重连**（已处理：前端指数退避重连 + 服务端 `resume` 会话恢复；会话改为 TTL 清理、断线暂留 10 分钟）
  - 位置：`frontend/index.html`、`backend/main.py`、`backend/services/session.py`。
  - 说明：正常结束立即删会话；异常断线保留会话供重连（TTL 600s，`create` 时惰性清扫，避免 H1 回归）。
- [x] **H6 评估报告 transcript 长度控制**（已处理：`_limit_transcript` 保留首 2000 + 尾 6000 字，中间省略）
  - 位置：`backend/agent/interviewer.py`。

## 🟡 建议（当前待办 · 可维护性）
- [ ] **S1 前端 Vue3/Vite/TS 重构** — 替代单文件 1580+ 行的 `index.html`。
- [ ] **S2 单元测试 + CI** — pytest 覆盖 `clean_tts_text`/ASR 切分/`_pcm_from_wav`/历史 CRUD + GitHub Actions。
- [x] **S3 清理未使用代码**（已处理：删 `Message` 模型 + `pydantic.BaseModel/Field` 导入）
  - 位置：`backend/models/interview.py`。
  - 说明：消息是裸 dict，`Message` 模型从未使用。

---

## 🔮 未来计划（暂不处理）

### 公网部署发布
- [ ] **S6 Docker + HTTPS 部署**：Dockerfile + docker-compose + Caddy 自动 HTTPS（解决裸 IP `http://` 下麦克风不可用）。
- [ ] **S5 CSP 响应头**：公网 web 安全加固（纵深防御 XSS）。
- [ ] 部署运维：secrets 注入（不打包进镜像）、日志轮转、数据库/音频备份、监控告警、（如需要）域名与备案。

### Git 仓库发布
- [ ] **S4 密钥与敏感数据审计**：push 前确认 `.env`、`data/interviews.db`、`data/audio/` 不入库（`.gitignore` 已加，做一次发布前复核）。
- [ ] LICENSE 选择与补充。
- [ ] （可选）公开前清理仓库内真实敏感数据（历史记录/音频）。

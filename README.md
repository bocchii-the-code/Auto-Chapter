# 视频自动转写 · 摘要 · 章节生成器

一个从【视频】自动生成【转写 + 摘要 + 章节大纲】的小工具，支持：

- 命令行模式：直接用 `pipeline.py` 处理本地视频
- Web 页面：上传视频 + 在线查看时间轴和章节结构

底层依赖：

- FFmpeg：抽取音频、按固定时长切片
- OpenAI Whisper：语音转写（默认 `whisper-1`）
- OpenAI / 兼容 API：使用 GPT‑4o 等模型生成摘要和章节信息

> 典型场景：课程视频、讲座、会议录播、播客、访谈等长视频的快速理解与结构化整理。

---

## 功能概览

- **自动抽取音频**
  - 从输入视频中提取单声道 16kHz 音频
- **自动分片 + 转写（Whisper）**
  - 按配置时长（默认 600 秒 / 10 分钟）分片
  - 对每一片调用 Whisper 转写，内置重试与指数退避
- **生成结构化转写**
  - `transcript.txt`：带起止时间的可读转写文本
  - `segments.json`：包含 `start / end / text` 的片段列表
- **生成摘要与章节（GPT‑4o 或兼容模型）**
  - `summary.md`：整段视频的 Markdown 摘要
  - `chapters.json`：每个章节的起止时间、标题、描述、关键要点
  - `chapters.md`：适合人类阅读的 Markdown 章节大纲
- **Web UI 可视化**
  - 浏览器上传视频，后端调用现有 `pipeline.py`
  - 页面内直接填写 API Key 和 Base URL（支持 OpenAI 兼容网关）
  - 时间轴上图形化展示章节块 + 下方章节卡片列表
  - 字幕预览（只展示前几千字符，完整字幕保存在服务器）

---

## 目录结构

```text
.
├─ pipeline.py        # 主处理流程：视频 -> 转写 -> 摘要 & 章节
├─ api_config.py      # OpenAI 兼容 API 配置（Key / Base URL / 模型名）
├─ web_app.py         # FastAPI 后端：包装 pipeline.py + 提供 HTTP 接口
├─ run_web_ui.py      # 一键启动 Web UI（启动 uvicorn + 自动打开浏览器）
├─ run_web_ui.bat     # Windows 下双击即可启动 Web UI 的批处理脚本
├─ static/
│  └─ index.html      # 单页前端：上传 + 时间轴 + 章节列表 + 字幕预览
├─ requirements.txt   # Python 依赖
├─ README.md          # 本说明文件
├─ LICENSE            # MIT License
└─ output/            # 默认输出目录（运行后生成）
   ├─ transcript.txt
   ├─ segments.json
   ├─ summary.md
   ├─ chapters.json
   ├─ chapters.md
   └─ _tmp/           # 中间文件：音频、分片（默认会被删除）
```

通过 Web UI 运行时，每次处理会在 `output/` 下新建一个子目录，例如：

```text
output/web_1700000000_ab12cd34/...
```

这样不同任务的结果不会互相覆盖。

---

## 环境要求

- 操作系统：Windows / macOS / Linux
- Python：建议 3.10+（3.8+ 理论上也支持）
- FFmpeg / ffprobe：
  - 已安装并在 `PATH` 中
  - 终端中可以运行 `ffmpeg -version`、`ffprobe -version`
- 网络：能访问你配置的 OpenAI / 兼容 API 网关

---

## 安装依赖

在项目根目录执行：

```bash
pip install -r requirements.txt
```

推荐使用虚拟环境：

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.\.venv\Scripts\activate

pip install -r requirements.txt
```

---

## API 配置方式

本项目支持两种方式配置 OpenAI 兼容 API：

1. **环境变量 / `.env` 文件（全局默认）**
2. **Web 页面中填写 API Key / Base URL（仅对当前请求生效）**

### 1. 环境变量 / `.env`

`api_config.py` 会尝试从同目录的 `.env` 中加载配置，再读取系统环境变量。

支持的变量：

- `OPENAI_API_KEY`：API 密钥（必填，否则会报错）
- `OPENAI_BASE_URL`：Base URL，例如：
  - `https://api.openai.com/v1`（官方）
  - 或者你自己的兼容网关
- `OPENAI_GPT_MODEL`：用于摘要 / 章节的模型名（默认 `gpt-4o`）
- `OPENAI_WHISPER_MODEL`：用于转写的模型名（默认 `whisper-1`）

示例 `.env` 文件：

```ini
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_GPT_MODEL=gpt-4o
OPENAI_WHISPER_MODEL=whisper-1
```

> 说明：如果同时设置了环境变量和 `.env`，以及 Web 页面里的 Key，
> **优先级从高到低为：Web 页面表单 > 系统环境变量 / `.env` > `api_config.py` 默认值**。

### 2. Web 页面中填写

在 Web UI 左侧上传区域下方，有两个输入框：

- `API key`：如 `sk-...`
- `API base URL`：如 `https://api.openai.com/v1`

你在页面里填写后，每次点击「Start analysis」：

- 这两个值会随表单一起 POST 到后端 `/api/process`
- 后端在调用 `pipeline.py` 时，将它们写入子进程的环境变量：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
- 浏览器会把你的 Key 和 URL 缓存在 `localStorage` 中（只保存在本机浏览器），刷新页面仍然存在，方便多次使用。

---

## 命令行使用（pipeline.py）

最基础的用法：

```bash
python pipeline.py --video "C:\path\to\lecture.mp4"
```

常用参数：

- `--video`（必选）：输入视频路径
- `--outdir`：输出目录（默认：脚本同级的 `output`）
- `--chunk-seconds`：分片长度（秒），默认 `600`
- `--keep-tmp`：保留中间文件（音频 / 分片），调试时很有用

示例：

```bash
python pipeline.py ^
  --video "C:\videos\lecture.mp4" ^
  --outdir "output\lecture_01" ^
  --chunk-seconds 600
```

运行完成后，控制台会打印类似信息：

```text
[done] 处理完成。输出文件：
 - output/transcript.txt
 - output/segments.json
 - output/summary.md
 - output/chapters.json
 - output/chapters.md
```

---

## Web 界面使用

Web UI 在命令行管线之上提供了一个简单的可视化界面。

### 1. 启动 Web UI

在项目根目录执行：

```bash
python run_web_ui.py
```

或在 Windows 文件管理器中**双击**：

- `run_web_ui.bat`

该脚本会：

1. 切换到项目目录
2. 如果存在 `.venv`，自动激活虚拟环境
3. 运行 `python run_web_ui.py`

`run_web_ui.py` 会启动 `uvicorn`（加载 `web_app:app`），并自动打开浏览器访问：

- <http://127.0.0.1:8000/>

### 2. 在页面中操作

1. 在左侧设置 API：
   - `API key`：填入你的 Key（不会被写入代码，只在本机浏览器保存）
   - `API base URL`：填你的网关地址（可为空，则使用环境变量 / 默认值）
2. 拖拽视频到页面中间的区域，或点击「Choose file」选择一个视频文件
3. 用滑块设置 `Chunk length`（300–1200 秒，默认 600）
4. 点击 **Start analysis / RUN PIPELINE**

前端会显示当前状态：

- 等待上传 / 正在上传 + 分析 / 完成 / 错误信息

分析结束后，右侧会展示：

- **Summary**
  - 由 `summary.md` 生成的整体摘要
- **Timeline and chapters**
  - 顶部一条时间轴，每个章节对应一段彩色块（长度按时间占比）
  - 下方章节列表：
    - `[开始 - 结束] 标题`
    - 描述文本
    - 若有 `key_points`，以小标签形式展示
- **Transcript preview**
  - `transcript.txt` 的前几千字符预览
  - 底部一行简单统计：章节数、估计总时长

---

## 输出文件说明

无论是命令行还是 Web UI，最终都会得到同样的核心输出文件：

- `transcript.txt`
  - 全部转写文本，按时间顺序排列
  - 每行格式类似：
    - `[HH:MM:SS - HH:MM:SS] 文本内容...`

- `segments.json`
  - 结构化的语音片段列表，示意结构：

    ```json
    {
      "segments": [
        { "start": 0.0, "end": 12.3, "text": "..." },
        { "start": 12.3, "end": 25.8, "text": "..." }
      ]
    }
    ```

- `summary.md`
  - 使用 GPT 模型生成的 Markdown 摘要
  - 第一行通常是 `# Summary`，Web UI 会去掉这个标题，只展示正文

- `chapters.json`
  - 结构化章节信息，适合二次开发 / 入库，例如：

    ```json
    {
      "chapters": [
        {
          "start": "00:00:00",
          "end": "00:05:30",
          "title": "Introduction",
          "description": "What this lecture covers...",
          "key_points": [
            "Context of the topic",
            "Objectives of the session"
          ]
        }
      ]
    }
    ```

- `chapters.md`
  - 适合人类直接阅读的 Markdown 章节大纲，例如：

    ```markdown
    # Chapters

    - [00:00:00 - 00:05:30] Introduction
      - 简要描述……
      - 关键要点 1
      - 关键要点 2
    ```

中间过程使用的音频和分片文件默认存在 `output/_tmp/` 或对应子目录下，处理完成后会自动删除（除非命令行传入 `--keep-tmp`）。

---

## 常见问题（FAQ）

- **Q: 支持中文视频吗？**  
  A: Whisper 模型本身支持多语言，包括中文。当前提示词偏向英文摘要 / 章节，但你可以在 `pipeline.py` 中调整系统提示和用户提示来生成中文摘要和章节标题。

- **Q: API Key 会不会写死在代码里？**  
  A: 不会。Key 可以通过环境变量、`.env` 或 Web 页面输入三种方式提供，代码中没有硬编码任何真实 Key。  
  Web 页面中填写的 Key 只会：
  - 本地存在浏览器 `localStorage`
  - 发送到你自己的后端（本机运行的 FastAPI）

- **Q: 转写 / 摘要质量不理想怎么办？**  
  - 尽量保证音频清晰、背景噪声较低  
  - 可以适当缩短 `--chunk-seconds`，让每段更短  
  - 可以通过环境变量切换到更强的模型（例如自定义 `OPENAI_GPT_MODEL`）

---

## 许可证

本项目使用 **MIT License** 开源协议，详见仓库根目录下的 `LICENSE` 文件。

你可以自由地使用、修改、复制和分发本项目代码（包括商用），
只需在分发时保留原始版权声明和许可文本。


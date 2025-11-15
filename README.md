# Automated Video Analysis & Chapter Generation

一个从【视频】自动生成【英文转写 + 摘要 + 章节大纲】的小工具，基于：

- FFmpeg：抽取音频、按固定时长分片
- OpenAI Whisper：语音转写（默认 `whisper-1`）
- OpenAI GPT-4o：根据转写生成总结和带时间戳的章节信息

> 典型场景：课程视频、讲座、演讲、访谈等长视频的快速理解与结构化整理。  

---

## 功能概览

- **自动抽取音频**：从输入视频中用 FFmpeg 抽出音频（单声道、16kHz）。
- **自动分片转写**：
  - 按配置时长（默认 600 秒 / 10 分钟）分割音频。
  - 针对每个分片调用 Whisper 转写，自动重试和指数退避。
- **生成结构化转写**：
  - `transcript.txt`：带时间戳的可读转写。
  - `segments.json`：包含 `start/end/text` 的结构化片段列表。
- **生成摘要与章节**（GPT-4o）：
  - `summary.md`：整段视频的英文概要。
  - `chapters.json`：每个章节的起止时间、标题、描述、关键要点。
  - `chapters.md`：适合人读的 Markdown 目录，可直接贴进文档/知识库。
- **临时文件管理**：
  - 默认自动删除中间产物（音频、切片），也支持通过参数保留调试。

---

## 目录结构

```text
.
├─ pipeline.py        # 主流程脚本（视频 -> 转写 -> 摘要 & 章节）
├─ api_config.py      # OpenAI 兼容 API 配置（Key / Base URL / 模型）
├─ requirements.txt   # Python 依赖
├─ README.md          # 项目说明（本文件）
├─ LICENSE            # 开源许可证（MIT）
└─ output/            # 默认输出目录（运行后生成）
   ├─ transcript.txt
   ├─ segments.json
   ├─ summary.md
   ├─ chapters.json
   ├─ chapters.md
   └─ _tmp/           # 中间文件：音频、分片（默认会被删除）
```

---

## 环境要求

- **操作系统**：Windows / macOS / Linux
- **Python**：推荐 Python 3.10+（3.8+ 理论上也可）
- **FFmpeg / ffprobe**：已安装并在 `PATH` 中可用  
  - 命令行中能执行 `ffmpeg -version`、`ffprobe -version` 即表示可用。
- **网络**：能够访问配置的 OpenAI 兼容 API（官方或自建网关）。

---

## 安装依赖

在项目根目录打开终端，执行：

```bash
pip install -r requirements.txt
```

如使用虚拟环境（推荐）：

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# 或
.\.venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

---

## 配置 API（安全使用）

项目支持通过环境变量或 `.env` 文件配置 OpenAI 兼容 API。  
**默认不会在代码中硬编码任何真实 Key**，你只需要配置环境即可。

### 1. 支持的环境变量

- `OPENAI_API_KEY`：必填，API 密钥
- `OPENAI_BASE_URL`：可选，Base URL  
  - 例如：`https://api.openai.com/v1`（官方）  
  - 或你的自建代理 / 网关地址
- `OPENAI_GPT_MODEL`：可选，默认为 `gpt-4o`
- `OPENAI_WHISPER_MODEL`：可选，默认为 `whisper-1`

### 2. 可选：使用 `.env` 文件（开发友好）

在 `api_config.py` 同目录下创建 `.env` 文件：

```env
OPENAI_API_KEY=sk-xxxxxx_your_real_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_GPT_MODEL=gpt-4o
OPENAI_WHISPER_MODEL=whisper-1
```

`api_config.py` 会自动尝试读取同目录下的 `.env` 并加载以上环境变量。

> 注意：  
> - 项目中 `api_config.py` 里的 `API_KEY = ""` 只是一个默认空值占位，不建议在代码里填入真实 Key。  
> - 上传到 GitHub 前，确保 `.env` 已加入 `.gitignore`，不要提交任何真实密钥。

---

## 使用方法

### 基本命令

假设你有一个视频 `C:\path\to\lecture.mp4`，在终端执行：

```bash
python pipeline.py --video "C:\\path\\to\\lecture.mp4"
```

常用参数：

- `--video`（必填）：输入视频文件路径（支持常见格式，如 MP4 等）。
- `--outdir`（可选）：输出目录，默认在脚本目录创建 `output/`。
- `--chunk-seconds`（可选）：音频分片长度（秒），默认 `600`（10 分钟）。
- `--keep-tmp`（可选）：是否保留临时文件（`output/_tmp/`），用于调试。

示例：

```bash
# 使用默认输出目录和分片时长
python pipeline.py --video "C:\\videos\\lecture.mp4"

# 指定输出目录
python pipeline.py --video "C:\\videos\\lecture.mp4" --outdir "C:\\analysis\\lecture1"

# 调试时保留临时音频与分片
python pipeline.py --video "C:\\videos\\lecture.mp4" --keep-tmp
```

---

## 输出说明

运行完成后，控制台会打印类似信息：

```text
[done] 处理完成。输出文件：
 - output/transcript.txt
 - output/segments.json
 - output/summary.md
 - output/chapters.json
 - output/chapters.md
```

各文件意义如下：

- `transcript.txt`  
  - 全部英文转写，按时间顺序排列。  
  - 每行格式：`[HH:MM:SS - HH:MM:SS] 文本内容`。

- `segments.json`  
  - 结构化语音片段数据，示意结构：
  ```json
  {
    "segments": [
      { "start": 0.0, "end": 12.3, "text": "..." },
      { "start": 12.3, "end": 25.8, "text": "..." }
    ]
  }
  ```

- `summary.md`  
  - GPT-4o 生成的英文总结，Markdown 格式：
  ```markdown
  # Summary

  （数段简洁的英文概述）
  ```

- `chapters.json`  
  - 结构化章节信息，用于做前端展示、知识库入库等：
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
  - 人类可读的 Markdown 目录，适合作为大纲：
  ```markdown
  # Chapters

  - [00:00:00 - 00:05:30] Introduction
    - 简要描述
    - 关键要点 1
    - 关键要点 2

  - [00:05:30 - 00:12:10] Topic A ...
  ```

---

## 常见问题（FAQ）

- **Q: 支持中文视频吗？**  
  A: Whisper 模型本身支持多语种，理论上可以识别中文。但本项目后续的摘要与章节提示词使用的是英文，当前设计主要偏向英文输出；如果你想支持中文摘要/章节，可以调整 `pipeline.py` 中 `system_prompt` / `user_prompt` 内容。

- **Q: 是否会硬编码 API Key？**  
  A: 默认不会。所有真实密钥通过环境变量或 `.env` 提供。  


- **Q: 转写/摘要质量不好怎么办？**  
  - 确保音频清晰、背景噪音相对较低。  
  - 可以适当缩短 `--chunk-seconds`，让每段更短。  
  - 可尝试更强的模型（如自定义 `OPENAI_GPT_MODEL`）。

---

## 版权与许可（License）

本项目采用 **MIT License** 开源许可证，详见仓库根目录下的 `LICENSE` 文件。  
简要说明：

- 你可以自由使用、复制、修改、合并、发布本项目的代码，用于个人或商业场景。
- 使用时需要保留原始版权声明和许可证文本。
- 本项目按“现状”提供，不对任何形式的损失或风险承担责任。

如需在论文、博客或产品中引用本项目，欢迎在合适位置标注仓库链接。

---

## 后续规划建议（可选）

- 支持多语言摘要与章节（中英双语）。
- 输出 SRT / VTT 字幕文件，方便导入剪辑软件或播放器。
- 简易 Web UI，用于上传视频并在线查看结果。
- 与知识库系统集成（例如直接写入向量库）。


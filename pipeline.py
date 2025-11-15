import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any

from api_config import load_settings


try:
    from openai import OpenAI
except Exception as e:  # pragma: no cover
    OpenAI = None  # type: ignore


@dataclass
class Segment:
    start: float
    end: float
    text: str


def run_cmd(cmd: List[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Unable to parse duration from ffprobe output: {result.stdout}")


def extract_audio(video_path: Path, out_audio_path: Path) -> None:
    out_audio_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "128k",
        "-f",
        "mp3",
        str(out_audio_path),
    ]
    run_cmd(cmd)


def split_audio(audio_path: Path, chunk_seconds: int, chunks_dir: Path) -> List[Dict[str, Any]]:
    chunks_dir.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(audio_path)
    num_chunks = int(math.ceil(duration / float(chunk_seconds)))
    created: List[Dict[str, Any]] = []
    for idx in range(num_chunks):
        start = idx * chunk_seconds
        remaining = max(0.0, duration - start)
        this_len = min(chunk_seconds, int(math.ceil(remaining)))
        out_file = chunks_dir / f"chunk_{idx:04d}_{start}s.mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-t",
            str(this_len),
            "-i",
            str(audio_path),
            "-acodec",
            "copy",
            str(out_file),
        ]
        run_cmd(cmd)
        created.append({"index": idx, "path": str(out_file), "offset": float(start), "duration": float(this_len)})
    return created


def seconds_to_hms(seconds: float) -> str:
    total_seconds = int(round(seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def build_client():
    settings = load_settings()
    if not settings.api_key:
        raise RuntimeError("请在环境变量 OPENAI_API_KEY 或 5701/api_config.py 中配置 API Key")
    if OpenAI is None:
        raise RuntimeError("缺少 openai 包，请先安装: pip install -r 5701/requirements.txt")
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    return client, settings


def transcribe_chunk(client, settings, chunk_path: Path, temperature: float = 0.0, max_retries: int = 5) -> Dict[str, Any]:
    # 请求 Whisper-1，期望返回 verbose_json 包含 segments
    for attempt in range(max_retries):
        try:
            with open(chunk_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=settings.whisper_model,
                    file=f,
                    response_format="verbose_json",
                    language="en",
                    temperature=temperature,
                )
            # openai 1.x 返回对象可转字典
            return json.loads(resp.model_dump_json())  # type: ignore
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            sleep_s = 2 ** attempt
            print(f"[warn] 转写失败，重试 {attempt+1}/{max_retries}，{sleep_s}s 后重试: {e}")
            time.sleep(sleep_s)
    raise RuntimeError("Unreachable")


def transcribe_chunks(client, settings, chunks_meta: List[Dict[str, Any]]) -> List[Segment]:
    all_segments: List[Segment] = []
    for meta in chunks_meta:
        chunk_file = Path(meta["path"])
        offset = float(meta["offset"])  # seconds
        print(f"[info] 正在转写: {chunk_file.name} (offset={offset}s)")
        data = transcribe_chunk(client, settings, chunk_file)
        # 期望 data 中包含 segments
        segments = data.get("segments") or []
        if not isinstance(segments, list):
            # 回退：没有 segments，则将全文视作一个段
            text = data.get("text") or ""
            if text:
                all_segments.append(Segment(start=offset, end=offset + float(meta.get("duration", 0.0)), text=text))
            continue
        for seg in segments:
            try:
                start = float(seg.get("start", 0.0)) + offset
                end = float(seg.get("end", 0.0)) + offset
                text = (seg.get("text") or "").strip()
                if text:
                    all_segments.append(Segment(start=start, end=end, text=text))
            except Exception:
                continue
    return all_segments


def save_segments(out_dir: Path, segments: List[Segment]) -> None:
    out_path = out_dir / "segments.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"segments": [asdict(s) for s in segments]}, f, ensure_ascii=False, indent=2)


def save_transcript(out_dir: Path, segments: List[Segment]) -> str:
    out_path = out_dir / "transcript.txt"
    lines: List[str] = []
    for s in segments:
        lines.append(f"[{seconds_to_hms(s.start)} - {seconds_to_hms(s.end)}] {s.text}")
    content = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def llm_summarize_and_chapterize(client, settings, transcript_lines: str, segments: List[Segment]) -> Dict[str, Any]:
    # 将带时间戳的转写作为输入，要求输出 JSON（summary + chapters）
    compact_input = truncate_text(transcript_lines, 120000)
    system_prompt = (
        "You are an expert lecture analyzer. Generate a concise English summary and well-structured chapters. "
        "Chapters must have human-friendly titles and ISO HH:MM:SS start times aligned with the transcript timestamps. "
        "Ensure coverage of the whole talk and avoid hallucination."
    )
    user_prompt = (
        "Input transcript with timestamps (format: [HH:MM:SS - HH:MM:SS] text). "
        "Identify topic shifts and produce chapters. Output JSON with fields: 'summary' (string), 'chapters' (array of objects: {start: string HH:MM:SS, end: string HH:MM:SS or null, title: string, description: string, key_points: string[]}).\n\n"
        + compact_input
    )

    # JSON mode
    resp = client.chat.completions.create(
        model=settings.gpt_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    text = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 回退：尝试再次请求不强制 JSON
        resp2 = client.chat.completions.create(
            model=settings.gpt_model,
            messages=[
                {"role": "system", "content": system_prompt + " Always answer in valid JSON."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        text2 = resp2.choices[0].message.content or "{}"
        data = json.loads(text2)
    return data


def save_summary_and_chapters(out_dir: Path, result: Dict[str, Any]) -> None:
    summary = result.get("summary") or ""
    chapters = result.get("chapters") or []

    with open(out_dir / "summary.md", "w", encoding="utf-8") as f:
        f.write("# Summary\n\n" + summary.strip() + "\n")

    with open(out_dir / "chapters.json", "w", encoding="utf-8") as f:
        json.dump({"chapters": chapters}, f, ensure_ascii=False, indent=2)

    # 生成可读 Markdown 目录
    lines = ["# Chapters", ""]
    for ch in chapters:
        start = ch.get("start") or "00:00:00"
        end = ch.get("end") or None
        title = (ch.get("title") or "").strip()
        desc = (ch.get("description") or "").strip()
        key_points = ch.get("key_points") or []
        if end:
            lines.append(f"- [{start} - {end}] {title}")
        else:
            lines.append(f"- [{start}] {title}")
        if desc:
            lines.append(f"  - {desc}")
        if key_points:
            for kp in key_points:
                lines.append(f"  - {kp}")
        lines.append("")
    with open(out_dir / "chapters.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Automated Video Analysis & Chapter Generation (Whisper + GPT-4o)")
    parser.add_argument("--video", required=True, help="输入视频文件路径")
    parser.add_argument("--outdir", default="output", help="输出目录，在 5701 下创建")
    parser.add_argument("--chunk-seconds", type=int, default=600, help="分片长度（秒），默认 600")
    parser.add_argument("--keep-tmp", action="store_true", help="保留临时文件")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    # 默认将输出写到脚本目录下的 5701/output
    script_dir = Path(__file__).parent
    if args.outdir == "output":
        out_dir = (script_dir / "output").resolve()
    else:
        out_dir = Path(args.outdir).resolve()
    if not video_path.exists():
        print(f"[error] 视频不存在: {video_path}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir / "_tmp"
    chunks_dir = tmp_dir / "chunks"

    client, settings = build_client()

    # 1) 抽取音频
    audio_path = tmp_dir / "audio.mp3"
    print("[info] 抽取音频...")
    extract_audio(video_path, audio_path)

    # 2) 分片
    print("[info] 分片音频...")
    chunks_meta = split_audio(audio_path, args.chunk_seconds, chunks_dir)

    # 3) 转写
    print("[info] Whisper 转写...")
    segments = transcribe_chunks(client, settings, chunks_meta)
    # 按起始时间排序
    segments.sort(key=lambda s: (s.start, s.end))

    # 4) 保存转写与段落
    print("[info] 保存转写与分段...")
    save_segments(out_dir, segments)
    transcript_lines = save_transcript(out_dir, segments)

    # 5) 使用 GPT-4o 生成摘要与章节
    print("[info] 生成摘要与章节 (GPT-4o)...")
    result = llm_summarize_and_chapterize(client, settings, transcript_lines, segments)
    save_summary_and_chapters(out_dir, result)

    # 6) 清理临时文件
    if not args.keep_tmp:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    print("[done] 处理完成。输出文件：")
    print(f" - {out_dir / 'transcript.txt'}")
    print(f" - {out_dir / 'segments.json'}")
    print(f" - {out_dir / 'summary.md'}")
    print(f" - {out_dir / 'chapters.json'}")
    print(f" - {out_dir / 'chapters.md'}")


if __name__ == "__main__":
    main()



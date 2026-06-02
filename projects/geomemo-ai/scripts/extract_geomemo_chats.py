"""Extract GeoMemo-related conversations from a ChatGPT data export.

The raw ChatGPT export can contain private conversations unrelated to this
portfolio project. This script keeps all extracted output under an ignored local
folder by default.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_KEYWORDS = (
    "geomemo",
    "geo memo",
    "감정",
    "감정분석",
    "추천",
    "인사이트",
    "mq",
    "amazon mq",
    "rabbitmq",
    "프로젝트 분석",
    "프로젝트 정리",
)


def _message_text(message: dict[str, Any] | None) -> str:
    if not message:
        return ""
    content = message.get("content") or {}
    parts = content.get("parts")
    if isinstance(parts, list):
        return "\n".join(str(part) for part in parts if isinstance(part, str))
    text = content.get("text")
    return text if isinstance(text, str) else ""


def _iter_messages(conversation: dict[str, Any]) -> Iterable[dict[str, str]]:
    mapping = conversation.get("mapping") or {}
    nodes = list(mapping.values()) if isinstance(mapping, dict) else []

    def sort_key(node: dict[str, Any]) -> float:
        message = node.get("message") or {}
        create_time = message.get("create_time")
        if isinstance(create_time, (int, float)):
            return float(create_time)
        return 0.0

    for node in sorted(nodes, key=sort_key):
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        role = ((message.get("author") or {}).get("role") or "unknown").strip()
        text = _message_text(message).strip()
        if text:
            yield {"role": role, "text": text}


def _matches(
    conversation: dict[str, Any], keywords: tuple[str, ...], title_only: bool = False
) -> bool:
    title = str(conversation.get("title") or "")
    if title_only:
        haystack = title.lower()
        return any(keyword.lower() in haystack for keyword in keywords)

    chunks = [title]
    for msg in _iter_messages(conversation):
        chunks.append(msg["text"][:2000])
    haystack = "\n".join(chunks).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _format_time(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def build_markdown(
    conversations: list[dict[str, Any]],
    keywords: tuple[str, ...],
    max_chars_per_message: int,
    title_only: bool,
    conversation_template_id: str | None,
) -> str:
    if conversation_template_id:
        matched = [
            conv
            for conv in conversations
            if conv.get("conversation_template_id") == conversation_template_id
        ]
    else:
        matched = [
            conv for conv in conversations if _matches(conv, keywords, title_only)
        ]
    matched.sort(key=lambda conv: conv.get("create_time") or 0)

    lines = [
        "# GeoMemo ChatGPT 대화 추출본",
        "",
        "이 파일은 ChatGPT export에서 GeoMemo 관련 대화만 로컬로 추출한 자료입니다.",
        "공개 저장소에 커밋하지 않습니다.",
        "",
        f"- matched conversations: {len(matched)}",
        f"- keywords: {', '.join(keywords)}",
        f"- title_only: {title_only}",
        f"- conversation_template_id: {conversation_template_id or ''}",
        "",
    ]

    for idx, conv in enumerate(matched, 1):
        title = str(conv.get("title") or f"Conversation {idx}")
        created = _format_time(conv.get("create_time"))
        updated = _format_time(conv.get("update_time"))
        lines.extend(
            [
                f"## {idx}. {title}",
                "",
                f"- created: {created or 'unknown'}",
                f"- updated: {updated or 'unknown'}",
                "",
            ]
        )
        for msg in _iter_messages(conv):
            text = msg["text"]
            if len(text) > max_chars_per_message:
                text = text[:max_chars_per_message].rstrip() + "\n...[truncated]"
            lines.extend([f"### {msg['role']}", "", text, ""])
    return "\n".join(lines).rstrip() + "\n"


def load_conversations(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_dir():
        paths = sorted(input_path.glob("conversations*.json"))
    else:
        paths = [input_path]

    conversations: list[dict[str, Any]] = []
    for path in paths:
        if path.name == "shared_conversations.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Expected {path} to contain a list")
        conversations.extend(data)
    return conversations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="private_chat_exports/conversations.json",
        help="Path to ChatGPT export conversations.json",
    )
    parser.add_argument(
        "--output",
        default="private_chat_exports/geomemo_conversations.md",
        help="Ignored local markdown output path",
    )
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated keywords used to select conversations",
    )
    parser.add_argument(
        "--max-chars-per-message",
        type=int,
        default=6000,
        help="Truncate long messages in the extracted markdown",
    )
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="Match keywords against conversation titles only",
    )
    parser.add_argument(
        "--conversation-template-id",
        default="",
        help="Extract conversations with this ChatGPT project/template id",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    keywords = tuple(item.strip() for item in args.keywords.split(",") if item.strip())

    conversations = load_conversations(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_markdown(
            conversations,
            keywords,
            args.max_chars_per_message,
            args.title_only,
            args.conversation_template_id.strip() or None,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

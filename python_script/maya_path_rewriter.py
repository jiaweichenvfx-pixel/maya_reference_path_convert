#!/usr/bin/env python3
"""只读建立资产查找表，并安全替换 Maya ASCII 中的 .ma 引用路径。"""

from __future__ import annotations

import argparse
import codecs
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, NamedTuple


# =============================================================================
# 用户配置区
# 复制整个项目到其他电脑后，通常只需要修改下面这些值。
# =============================================================================

# 扫描服务器文件时，当前电脑实际能够访问的目录。
# macOS 示例：r"/Volumes/projects/JDZ/VFX/Assets/CGassets"
# Windows 示例：r"P:\JDZ\VFX\Assets\CGassets"
SERVER_SCAN_ROOT = r"/Volumes/projects/JDZ/VFX/Assets/CGassets"

# 写入查找表和 Maya 文件中的 Windows 目标根路径。
# 可以使用 Windows 反斜杠，脚本输出时会自动转换为 Maya 使用的正斜杠。
WINDOWS_TARGET_ROOT = r"P:\JDZ\VFX\Assets\CGassets"

# 项目内部目录和查找表文件名。全部相对于项目根目录。
DATA_FOLDER = "data"
INPUT_FOLDER = "ori"
OUTPUT_FOLDER = "output"
FULL_TABLE_FILENAME = "server_files.json"
MA_TABLE_FILENAME = "ma_file.json"

# =============================================================================
# 程序默认路径。通常不需要修改此区域。
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAC_SERVER_ROOT = Path(SERVER_SCAN_ROOT)
DEFAULT_WINDOWS_SERVER_ROOT = WINDOWS_TARGET_ROOT
DEFAULT_TABLE_PATH = PROJECT_ROOT / DATA_FOLDER / FULL_TABLE_FILENAME
DEFAULT_MA_TABLE_PATH = PROJECT_ROOT / DATA_FOLDER / MA_TABLE_FILENAME
DEFAULT_REWRITE_TABLE_PATH = DEFAULT_MA_TABLE_PATH
DEFAULT_INPUT_DIR = PROJECT_ROOT / INPUT_FOLDER
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / OUTPUT_FOLDER
IGNORED_FILENAMES = {".ds_store", "thumbs.db"}
PUBLISH_DIRECTORIES = {"work", "approve", "publish"}
COPY_NUMBER_SUFFIX = re.compile(r"\{\d+\}$")
CODESET_PATTERN = re.compile(rb"(?m)^//Codeset:\s*([^\r\n]+)")
REFERENCE_FLAG_PATTERN = re.compile(rb"(?:^|\s)-(?:r|rdi)(?=\s|$)")
HEADER_END_COMMANDS = (
    b"requires ",
    b"currentUnit ",
    b"fileInfo ",
    b"createNode ",
    b"select ",
    b"rename ",
)
MAX_REFERENCE_HEADER_BYTES = 16 * 1024 * 1024
COPY_CHUNK_SIZE = 1024 * 1024


class PathOccurrence(NamedTuple):
    """一个可替换的 Maya 路径字符串及其精确字符范围。"""

    path: str
    start: int
    end: int
    kind: str
    line: int


class MatchResult(NamedTuple):
    """旧路径在本地查找表中的匹配结果。"""

    status: str
    path: str | None
    candidates: tuple[str, ...] = ()
    score: int | None = None


def maya_path(path: str) -> str:
    """返回 Maya 友好的正斜杠路径。"""
    return path.replace("\\", "/")


def normalize_windows_root(path: str) -> str:
    normalized = maya_path(path).rstrip("/")
    if not normalized:
        raise ValueError("Windows 服务器根路径不能为空")
    return normalized


def scan_server(
    mac_root: Path = DEFAULT_MAC_SERVER_ROOT,
    windows_root: str = DEFAULT_WINDOWS_SERVER_ROOT,
) -> dict[str, Any]:
    """只读取服务器目录元数据，不打开或改动服务器文件。"""
    root = mac_root.expanduser().absolute()
    if not root.is_dir():
        raise FileNotFoundError(f"服务器目录不存在或不可访问: {root}")

    target_root = normalize_windows_root(windows_root)
    files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if not (current_path / name).is_symlink()
        ]

        for name in names:
            if name.casefold() in IGNORED_FILENAMES:
                continue

            source = current_path / name
            if source.is_symlink():
                continue

            try:
                stat = source.stat()
                relative = source.relative_to(root)
            except OSError as exc:
                errors.append({"path": str(source), "error": str(exc)})
                continue

            relative_path = maya_path(str(relative))
            files.append(
                {
                    "name": name,
                    "name_key": name.casefold(),
                    "windows_path": f"{target_root}/{relative_path}",
                    "relative_path": relative_path,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )

    files.sort(key=lambda item: item["windows_path"].casefold())
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mac_root": str(root),
        "windows_root": target_root,
        "file_count": len(files),
        "error_count": len(errors),
        "files": files,
        "errors": errors,
    }


def filter_table_by_extension(
    table: dict[str, Any],
    extension: str,
) -> dict[str, Any]:
    """返回只包含指定扩展名的查找表。"""
    normalized_extension = extension.casefold()
    files = [
        item
        for item in table["files"]
        if item["name_key"].endswith(normalized_extension)
    ]
    filtered = dict(table)
    filtered["filter_extension"] = normalized_extension
    filtered["file_count"] = len(files)
    filtered["files"] = files
    return filtered


def _is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.expanduser().absolute()
    resolved_parent = parent.expanduser().absolute()
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def save_table(table: dict[str, Any], output: Path, server_root: Path) -> None:
    """把查找表保存在本地，禁止写入被扫描的服务器目录。"""
    destination = output.expanduser().absolute()
    if _is_within(destination, server_root):
        raise ValueError("查找表不能写入被扫描的服务器目录")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    payload = json.dumps(table, ensure_ascii=False, indent=2)
    temporary.write_text(payload + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def read_reference_header(
    source: Path,
    max_bytes: int = MAX_REFERENCE_HEADER_BYTES,
) -> tuple[bytes, int]:
    """只读取文件头引用区，返回头部字节和正文起始偏移。"""
    chunks: list[bytes] = []
    seen_reference = False

    with source.expanduser().open("rb") as handle:
        while True:
            line_start = handle.tell()
            line = handle.readline()
            if not line:
                return b"".join(chunks), line_start

            stripped = line.lstrip()
            if seen_reference and stripped.startswith(HEADER_END_COMMANDS):
                return b"".join(chunks), line_start

            chunks.append(line)
            if (
                stripped.startswith(b"file ")
                and REFERENCE_FLAG_PATTERN.search(stripped)
            ):
                seen_reference = True

            if handle.tell() > max_bytes:
                raise ValueError(
                    f"文件头引用区超过安全上限 {max_bytes} 字节，"
                    "已停止，未扫描正文"
                )


def detect_maya_encoding(header: bytes) -> str:
    """根据 Maya 文件头 Codeset 选择头部编码。"""
    match = CODESET_PATTERN.search(header)
    if match:
        codeset = match.group(1).decode("ascii", errors="ignore").strip()
        normalized = codeset.casefold().replace("_", "-")
        aliases = {
            "936": "cp936",
            "65001": "utf-8",
            "utf8": "utf-8",
            "utf-8": "utf-8",
        }
        candidate = aliases.get(normalized)
        if candidate is None and normalized.isdigit():
            candidate = f"cp{normalized}"
        if candidate is None:
            candidate = normalized
        try:
            codecs.lookup(candidate)
        except LookupError as exc:
            raise ValueError(f"不支持的 Maya Codeset: {codeset}") from exc
        return candidate

    try:
        header.decode("utf-8")
    except UnicodeDecodeError:
        return "cp936"
    return "utf-8"


def _iter_maya_statements(text: str) -> Iterator[tuple[int, int, str]]:
    """按双引号和行注释之外的分号切分 Maya ASCII 语句。"""
    start = 0
    index = 0
    in_string = False
    escaped = False
    in_line_comment = False

    while index < len(text):
        character = text[index]

        if in_line_comment:
            if character in "\r\n":
                in_line_comment = False
            index += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == "/" and index + 1 < len(text) and text[index + 1] == "/":
            in_line_comment = True
            index += 2
            continue

        if character == '"':
            in_string = True
        elif character == ";":
            end = index + 1
            yield start, end, text[start:end]
            start = end
        index += 1

    if start < len(text):
        yield start, len(text), text[start:]


def _leading_code(statement: str) -> str:
    """跳过语句前的空白和整行注释，返回实际 MEL 命令。"""
    index = 0
    while index < len(statement):
        while index < len(statement) and statement[index].isspace():
            index += 1
        if statement.startswith("//", index):
            newline = statement.find("\n", index + 2)
            if newline == -1:
                return ""
            index = newline + 1
            continue
        return statement[index:]
    return ""


def _quoted_spans(
    statement: str,
    statement_start: int,
) -> list[tuple[int, int, str]]:
    """返回语句中每个双引号字符串的内容范围和原始文本。"""
    spans: list[tuple[int, int, str]] = []
    index = 0

    while index < len(statement):
        if statement[index] != '"':
            index += 1
            continue

        content_start = index + 1
        index = content_start
        escaped = False
        while index < len(statement):
            character = statement[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                spans.append(
                    (
                        statement_start + content_start,
                        statement_start + index,
                        statement[content_start:index],
                    )
                )
                index += 1
                break
            index += 1

    return spans


def _decode_maya_string(value: str) -> str:
    """只解开路径匹配需要的 Maya 引号和反斜杠转义。"""
    return value.replace(r"\\", "\\").replace(r"\"", '"')


def _looks_like_ma_path(value: str) -> bool:
    normalized = COPY_NUMBER_SUFFIX.sub("", maya_path(value).strip())
    return normalized.casefold().endswith(".ma")


def _path_occurrence(
    text: str,
    spans: list[tuple[int, int, str]],
    kind: str,
) -> PathOccurrence | None:
    for start, end, raw_value in reversed(spans):
        value = _decode_maya_string(raw_value)
        if _looks_like_ma_path(value):
            return PathOccurrence(
                path=value,
                start=start,
                end=end,
                kind=kind,
                line=text.count("\n", 0, start) + 1,
            )
    return None


def scan_maya_text(text: str) -> list[PathOccurrence]:
    """扫描 Maya ASCII，只定位场景引用和 reference 节点的 .ma 路径。"""
    occurrences: list[PathOccurrence] = []
    current_node_type: str | None = None

    for statement_start, _statement_end, statement in _iter_maya_statements(text):
        code = _leading_code(statement)
        if not code:
            continue

        create_match = re.match(r"createNode\s+([^\s;]+)", code)
        if create_match:
            current_node_type = create_match.group(1).casefold()
            continue

        if re.match(r"file\b", code) and re.search(
            r"(?:^|\s)-(?:r|rdi)(?=\s|$)",
            code,
        ):
            occurrence = _path_occurrence(
                text,
                _quoted_spans(statement, statement_start),
                "file-reference",
            )
            if occurrence is not None:
                occurrences.append(occurrence)
            continue

        if current_node_type != "reference" or not re.match(r"setAttr\b", code):
            continue

        spans = _quoted_spans(statement, statement_start)
        if not spans:
            continue
        attribute = _decode_maya_string(spans[0][2])
        if not re.fullmatch(r"\.fn(?:\[\d+\])?", attribute):
            continue

        occurrence = _path_occurrence(text, spans[1:], "reference-node")
        if occurrence is not None:
            occurrences.append(occurrence)

    return occurrences


def _filename_key(path: str) -> str:
    normalized = maya_path(path).rstrip("/")
    filename = normalized.rsplit("/", 1)[-1]
    return COPY_NUMBER_SUFFIX.sub("", filename).casefold()


def _parent_parts(path: str, strip_publish_directory: bool) -> list[str]:
    normalized = COPY_NUMBER_SUFFIX.sub("", maya_path(path).strip())
    parts = [part.casefold() for part in normalized.split("/") if part]
    parents = parts[:-1]
    if strip_publish_directory:
        while parents and parents[-1] in PUBLISH_DIRECTORIES:
            parents.pop()
    return parents


def _suffix_score(old_path: str, candidate_path: str) -> int:
    old_parts = _parent_parts(old_path, strip_publish_directory=False)
    candidate_parts = _parent_parts(candidate_path, strip_publish_directory=True)
    score = 0
    for old_part, candidate_part in zip(
        reversed(old_parts),
        reversed(candidate_parts),
    ):
        if old_part != candidate_part:
            break
        score += 1
    return score


def match_asset(old_path: str, table: dict[str, Any]) -> MatchResult:
    """按文件名匹配；重名时用父目录尾部判断，仍并列则不修改。"""
    filename_key = _filename_key(old_path)
    unique_candidates: dict[str, str] = {}

    for item in table.get("files", []):
        item_key = str(item.get("name_key") or item.get("name", "")).casefold()
        if item_key != filename_key:
            continue
        candidate = maya_path(str(item["windows_path"]))
        unique_candidates.setdefault(candidate.casefold(), candidate)

    candidates = tuple(
        sorted(unique_candidates.values(), key=lambda value: value.casefold())
    )
    if not candidates:
        return MatchResult(status="missing", path=None)
    if len(candidates) == 1:
        return MatchResult(
            status="matched",
            path=candidates[0],
            candidates=candidates,
        )

    scored = [(_suffix_score(old_path, candidate), candidate) for candidate in candidates]
    highest_score = max(score for score, _candidate in scored)
    winners = [
        candidate
        for score, candidate in scored
        if score == highest_score
    ]
    if len(winners) != 1:
        approve_winners = [
            candidate
            for candidate in winners
            if "approve" in _parent_parts(
                candidate,
                strip_publish_directory=False,
            )
        ]
        if len(approve_winners) == 1:
            return MatchResult(
                status="matched",
                path=approve_winners[0],
                candidates=candidates,
                score=highest_score,
            )
        return MatchResult(
            status="conflict",
            path=None,
            candidates=candidates,
            score=highest_score,
        )

    return MatchResult(
        status="matched",
        path=winners[0],
        candidates=candidates,
        score=highest_score,
    )


def rewrite_maya_text(
    text: str,
    table: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """只替换已确认路径的字符范围，返回新文本和完整报告。"""
    occurrences = scan_maya_text(text)
    replacements: list[tuple[int, int, str]] = []
    cache: dict[str, MatchResult] = {}
    items: list[dict[str, Any]] = []
    counts = {"matched": 0, "conflict": 0, "missing": 0}

    for occurrence in occurrences:
        cache_key = occurrence.path.casefold()
        result = cache.get(cache_key)
        if result is None:
            result = match_asset(occurrence.path, table)
            cache[cache_key] = result

        counts[result.status] += 1
        if result.status == "matched" and result.path is not None:
            replacements.append((occurrence.start, occurrence.end, result.path))

        items.append(
            {
                "line": occurrence.line,
                "kind": occurrence.kind,
                "old_path": occurrence.path,
                "status": result.status,
                "new_path": result.path,
                "candidates": list(result.candidates),
                "score": result.score,
            }
        )

    rewritten = text
    for start, end, replacement in sorted(replacements, reverse=True):
        rewritten = rewritten[:start] + replacement + rewritten[end:]

    report: dict[str, Any] = {
        "scanned": len(occurrences),
        "matched": counts["matched"],
        "conflict": counts["conflict"],
        "missing": counts["missing"],
        "changed": sum(
            1
            for item in items
            if item["status"] == "matched"
            and item["new_path"] != item["old_path"]
        ),
        "items": items,
    }
    return rewritten, report


def load_table(path: Path) -> dict[str, Any]:
    """读取本地 JSON 查找表。"""
    table = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(table, dict) or not isinstance(table.get("files"), list):
        raise ValueError(f"查找表格式无效: {path}")
    return table


def _status_label(status: str) -> str:
    return {
        "matched": "匹配",
        "conflict": "冲突",
        "missing": "缺失",
    }[status]


def _group_report_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    """按状态和路径合并同一文件内的重复操作。"""
    grouped: dict[
        tuple[str, str, str | None, tuple[str, ...]],
        dict[str, Any],
    ] = {}
    for item in report["items"]:
        key = (
            item["status"],
            item["old_path"],
            item["new_path"],
            tuple(item["candidates"]),
        )
        group = grouped.setdefault(
            key,
            {
                "count": 0,
                "lines": [],
                "status": item["status"],
                "old_path": item["old_path"],
                "new_path": item["new_path"],
                "candidates": item["candidates"],
            },
        )
        group["count"] += 1
        group["lines"].append(item["line"])
    return list(grouped.values())


def print_rewrite_report(report: dict[str, Any]) -> None:
    """用中文打印按旧路径合并后的替换报告。"""
    grouped: dict[
        tuple[str, str, str | None, tuple[str, ...]],
        dict[str, Any],
    ] = {}
    for item in report["items"]:
        key = (
            item["status"],
            item["old_path"],
            item["new_path"],
            tuple(item["candidates"]),
        )
        group = grouped.setdefault(
            key,
            {
                "count": 0,
                "lines": [],
                "status": item["status"],
                "old_path": item["old_path"],
                "new_path": item["new_path"],
                "candidates": item["candidates"],
            },
        )
        group["count"] += 1
        group["lines"].append(item["line"])

    if "scanned_bytes" in report:
        print(
            f"只扫描文件头 {report['scanned_bytes']} 字节，"
            f"编码 {report['encoding']}；后续正文不解析"
        )
    print(
        "扫描到 {scanned} 处 .ma 路径：匹配 {matched}，"
        "冲突 {conflict}，缺失 {missing}，实际修改 {changed}".format(**report)
    )
    for group in grouped.values():
        lines = ", ".join(str(line) for line in group["lines"])
        print(
            f"[{_status_label(group['status'])}] "
            f"{group['old_path']}  (出现 {group['count']} 次，行 {lines})"
        )
        if group["new_path"]:
            print(f"  -> {group['new_path']}")
        elif group["candidates"]:
            for candidate in group["candidates"]:
                print(f"  候选: {candidate}")


def rewrite_file(
    source: Path,
    table_path: Path = DEFAULT_REWRITE_TABLE_PATH,
    output: Path | None = None,
    dry_run: bool = False,
    table: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """读取本地 .ma，生成新文件；永不覆盖源文件或写入服务器。"""
    source_path = source.expanduser().absolute()
    destination = (
        output.expanduser().absolute()
        if output is not None
        else (DEFAULT_OUTPUT_DIR / source_path.name).absolute()
    )

    if destination == source_path:
        raise ValueError("输出路径不能与原文件相同")
    if _is_within(destination, DEFAULT_MAC_SERVER_ROOT):
        raise ValueError("输出文件不能写入服务器资产目录")

    header_bytes, body_offset = read_reference_header(source_path)
    encoding = detect_maya_encoding(header_bytes)
    text = header_bytes.decode(encoding)
    lookup_table = table if table is not None else load_table(table_path)
    rewritten, report = rewrite_maya_text(text, lookup_table)
    rewritten_header = rewritten.encode(encoding)
    report["encoding"] = encoding
    report["scanned_bytes"] = len(header_bytes)
    report["body_offset"] = body_offset

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            with source_path.open("rb") as source_handle:
                source_handle.seek(body_offset)
                with temporary.open("wb") as output_handle:
                    output_handle.write(rewritten_header)
                    shutil.copyfileobj(
                        source_handle,
                        output_handle,
                        length=COPY_CHUNK_SIZE,
                    )
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    return destination, report


def rewrite_directory(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    table_path: Path = DEFAULT_REWRITE_TABLE_PATH,
    dry_run: bool = False,
) -> dict[str, Any]:
    """递归批量处理目录中的 .ma 文件，并保留相对目录结构。"""
    source_root = input_dir.expanduser().absolute()
    destination_root = output_dir.expanduser().absolute()
    if not source_root.is_dir():
        raise FileNotFoundError(f"输入目录不存在: {source_root}")
    if destination_root == source_root or _is_within(destination_root, source_root):
        raise ValueError("输出目录不能等于或位于输入目录内部")
    if _is_within(destination_root, DEFAULT_MAC_SERVER_ROOT):
        raise ValueError("输出目录不能位于服务器资产目录")

    lookup_table = load_table(table_path)
    sources = sorted(
        (
            path
            for path in source_root.rglob("*")
            if path.is_file() and path.suffix.casefold() == ".ma"
        ),
        key=lambda path: str(path.relative_to(source_root)).casefold(),
    )
    summary: dict[str, Any] = {
        "input_dir": str(source_root),
        "output_dir": str(destination_root),
        "found": len(sources),
        "processed": 0,
        "failed": 0,
        "matched": 0,
        "conflict": 0,
        "missing": 0,
        "changed": 0,
        "files": [],
    }

    for source in sources:
        relative = source.relative_to(source_root)
        destination = destination_root / relative
        try:
            _output, report = rewrite_file(
                source=source,
                table_path=table_path,
                output=destination,
                dry_run=dry_run,
                table=lookup_table,
            )
        except Exception as exc:
            summary["failed"] += 1
            summary["files"].append(
                {
                    "source": str(source),
                    "output": str(destination),
                    "relative": maya_path(str(relative)),
                    "status": "error",
                    "error": str(exc),
                }
            )
            continue

        summary["processed"] += 1
        for key in ("matched", "conflict", "missing", "changed"):
            summary[key] += report[key]
        summary["files"].append(
            {
                "source": str(source),
                "output": str(destination),
                "relative": maya_path(str(relative)),
                "status": "ok",
                "report": report,
            }
        )

    return summary


def print_batch_report(summary: dict[str, Any], dry_run: bool) -> None:
    """打印批处理逐文件结果和总计。"""
    for item in summary["files"]:
        if item["status"] == "error":
            print(f"[失败] {item['relative']}: {item['error']}")
            continue
        report = item["report"]
        label = "预览" if dry_run else "完成"
        print(
            f"[{label}] {item['relative']}"
        )
        print(
            f"  文件汇总："
            f"修改 {report['changed']}，缺失 {report['missing']}，"
            f"冲突 {report['conflict']}，扫描路径 {report['scanned']}"
        )
        print(
            f"  扫描范围：文件头 {report['scanned_bytes']} 字节，"
            f"编码 {report['encoding']}；正文不解析"
        )

        for group in _group_report_items(report):
            lines = ", ".join(str(line) for line in group["lines"])
            location = f"出现 {group['count']} 次，行 {lines}"
            if group["status"] == "matched":
                if group["new_path"] == group["old_path"]:
                    print(f"  [无需修改] {group['old_path']}  ({location})")
                else:
                    print(f"  [替换] {group['old_path']}  ({location})")
                    print(f"    -> {group['new_path']}")
                continue

            if group["status"] == "missing":
                print(f"  [缺失] {group['old_path']}  ({location})")
                print("    -> 查找表中没有同名文件，保留原路径")
                continue

            print(f"  [冲突] {group['old_path']}  ({location})")
            print("    -> 无法唯一确认，保留原路径")
            for candidate in group["candidates"]:
                print(f"    候选: {candidate}")
        print()

    print(
        "批处理汇总：发现 {found}，成功 {processed}，失败 {failed}，"
        "修改 {changed}，缺失 {missing}，冲突 {conflict}".format(**summary)
    )
    if dry_run:
        print("试运行完成：没有写入任何文件")
    else:
        print(f"输出目录: {summary['output_dir']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只读建立资产查找表，并安全替换 Maya ASCII 引用路径",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan-server",
        help="只读扫描服务器并在本地生成 JSON 查找表",
    )
    scan_parser.add_argument(
        "--mac-root",
        type=Path,
        default=DEFAULT_MAC_SERVER_ROOT,
        help=f"macOS 挂载路径，默认: {DEFAULT_MAC_SERVER_ROOT}",
    )
    scan_parser.add_argument(
        "--windows-root",
        default=DEFAULT_WINDOWS_SERVER_ROOT,
        help=f"查找表中的 Windows 根路径，默认: {DEFAULT_WINDOWS_SERVER_ROOT}",
    )
    scan_parser.add_argument(
        "--table",
        type=Path,
        default=DEFAULT_TABLE_PATH,
        help=f"本地 JSON 输出路径，默认: {DEFAULT_TABLE_PATH}",
    )
    scan_parser.add_argument(
        "--ma-table",
        type=Path,
        default=DEFAULT_MA_TABLE_PATH,
        help=f"仅包含 .ma 文件的 JSON 输出路径，默认: {DEFAULT_MA_TABLE_PATH}",
    )

    scan_ma_parser = subparsers.add_parser(
        "scan-ma",
        help="只扫描本地 Maya ASCII 文件中的 .ma 引用路径",
    )
    scan_ma_parser.add_argument("source", type=Path, help="要扫描的 .ma 文件")

    rewrite_parser = subparsers.add_parser(
        "rewrite",
        help="按本地查找表替换可安全确认的 .ma 引用路径",
    )
    rewrite_parser.add_argument("source", type=Path, help="要处理的 .ma 文件")
    rewrite_parser.add_argument(
        "--table",
        type=Path,
        default=DEFAULT_REWRITE_TABLE_PATH,
        help=f".ma 查找表，默认: {DEFAULT_REWRITE_TABLE_PATH}",
    )
    rewrite_parser.add_argument(
        "--output",
        type=Path,
        help=f"输出文件，默认写入: {DEFAULT_OUTPUT_DIR}",
    )
    rewrite_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示匹配报告，不生成输出文件",
    )

    batch_parser = subparsers.add_parser(
        "batch",
        help="递归批量处理 ori 目录中的所有 .ma 文件",
    )
    batch_parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"输入目录，默认: {DEFAULT_INPUT_DIR}",
    )
    batch_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录，默认: {DEFAULT_OUTPUT_DIR}",
    )
    batch_parser.add_argument(
        "--table",
        type=Path,
        default=DEFAULT_REWRITE_TABLE_PATH,
        help=f".ma 查找表，默认: {DEFAULT_REWRITE_TABLE_PATH}",
    )
    batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只显示批处理结果，不生成输出文件",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan-server":
        table = scan_server(args.mac_root, args.windows_root)
        ma_table = filter_table_by_extension(table, ".ma")
        save_table(table, args.table, args.mac_root)
        save_table(ma_table, args.ma_table, args.mac_root)
        print(f"扫描完成: {table['file_count']} 个文件")
        print(f"其中 .ma 文件: {ma_table['file_count']} 个")
        print(f"读取错误: {table['error_count']}")
        print(f"Windows 根路径: {table['windows_root']}")
        print(f"完整查找表: {args.table.expanduser().absolute()}")
        print(f".ma 查找表: {args.ma_table.expanduser().absolute()}")
        return 0

    if args.command == "scan-ma":
        header_bytes, body_offset = read_reference_header(args.source)
        encoding = detect_maya_encoding(header_bytes)
        text = header_bytes.decode(encoding)
        occurrences = scan_maya_text(text)
        print(
            f"只扫描文件头 {len(header_bytes)} 字节，编码 {encoding}；"
            f"正文从字节 {body_offset} 开始，不解析"
        )
        print(f"扫描到 {len(occurrences)} 处 .ma 引用路径")
        for occurrence in occurrences:
            print(
                f"行 {occurrence.line} [{occurrence.kind}] "
                f"{occurrence.path}"
            )
        return 0

    if args.command == "rewrite":
        destination, report = rewrite_file(
            source=args.source,
            table_path=args.table,
            output=args.output,
            dry_run=args.dry_run,
        )
        print_rewrite_report(report)
        if args.dry_run:
            print("试运行完成：没有写入任何文件")
        else:
            print(f"输出文件: {destination}")
        return 0

    if args.command == "batch":
        summary = rewrite_directory(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            table_path=args.table,
            dry_run=args.dry_run,
        )
        print_batch_report(summary, args.dry_run)
        return 0 if summary["failed"] == 0 else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

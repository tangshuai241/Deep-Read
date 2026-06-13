#!/usr/bin/env python3
"""
validate_analysis.py — 4D 拆解产物验证器

验证 analysis/ 目录下 6 份 JSON 产物是否存在、可解析，
输出验证清单或写入 analysis_manifest.json。

用法:
  python 4d_pipeline/validate_analysis.py <analysis_dir>
  python 4d_pipeline/validate_analysis.py <analysis_dir> --json
  python 4d_pipeline/validate_analysis.py <analysis_dir> --write-manifest
  python 4d_pipeline/validate_analysis.py <analysis_dir> --write-manifest --force

退出码:
  0 — ok 或 degraded（全部或部分有效）
  1 — invalid 或 manifest 覆盖被拒绝
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"
MANIFEST_FILENAME = "analysis_manifest.json"
REQUIRED_ANALYSIS_FILES = [
    "preprocess_output.json",
    "agent_a_skeleton.json",
    "agent_b_thought.json",
    "agent_c_argument.json",
    "agent_d_narrative.json",
    "summary_verification.json",
]


def _iso_timestamp():
    """Return ISO 8601 timestamp with seconds precision and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_file_list(resolved_dir):
    """Validate each required file and return (files_info, valid_count)."""
    files_info = []
    valid_count = 0

    for fname in REQUIRED_ANALYSIS_FILES:
        fpath = os.path.join(resolved_dir, fname)
        info = {
            "name": fname,
            "present": False,
            "valid": False,
            "size_bytes": 0,
            "error": None,
        }

        if os.path.isfile(fpath):
            info["present"] = True
            info["size_bytes"] = os.path.getsize(fpath)
            try:
                with open(fpath, encoding="utf-8") as f:
                    json.load(f)
                info["valid"] = True
                valid_count += 1
            except json.JSONDecodeError as e:
                info["error"] = f"JSON decode error: {e}"
            except Exception as e:
                info["error"] = f"read error: {e}"
        else:
            info["error"] = "file not found"

        files_info.append(info)

    return files_info, valid_count


def _build_empty_file_list():
    """Return a file list for when the analysis dir is inaccessible."""
    return [
        {
            "name": fname,
            "present": False,
            "valid": False,
            "size_bytes": 0,
            "error": "analysis directory does not exist",
        }
        for fname in REQUIRED_ANALYSIS_FILES
    ]


def validate_analysis_dir(analysis_dir):
    """Validate all required JSON files in the analysis directory.

    Args:
        analysis_dir: Path to the analysis directory.

    Returns:
        dict: Manifest with schema_version, validated_at, analysis_dir,
              book_name, status, warnings, and files list.
    """
    resolved_dir = os.path.abspath(analysis_dir)
    book_name = os.path.basename(os.path.dirname(resolved_dir))
    ts = _iso_timestamp()
    warnings = []
    if os.path.basename(resolved_dir) != "analysis":
        warnings.append("分析目录名称不是 'analysis'，book_name 可能不准确")

    # --- Validate the analysis directory itself ---
    if not os.path.exists(resolved_dir):
        return {
            "schema_version": SCHEMA_VERSION,
            "validated_at": ts,
            "analysis_dir": resolved_dir,
            "book_name": book_name,
            "status": "invalid",
            "warnings": warnings + [f"分析目录不存在: {resolved_dir}"],
            "files": _build_empty_file_list(),
        }

    if not os.path.isdir(resolved_dir):
        return {
            "schema_version": SCHEMA_VERSION,
            "validated_at": ts,
            "analysis_dir": resolved_dir,
            "book_name": book_name,
            "status": "invalid",
            "warnings": warnings + [f"路径不是目录: {resolved_dir}"],
            "files": _build_empty_file_list(),
        }

    # --- Validate each required file ---
    files_info, valid_count = _build_file_list(resolved_dir)

    # --- Determine overall status ---
    total = len(REQUIRED_ANALYSIS_FILES)
    if valid_count == total:
        status = "ok"
    elif valid_count > 0:
        status = "degraded"
    else:
        status = "invalid"

    # --- Build warnings ---
    if status == "degraded":
        missing = [f["name"] for f in files_info if not f["present"]]
        corrupt = [f["name"] for f in files_info if f["present"] and not f["valid"]]
        if missing:
            warnings.append(f"缺少文件: {', '.join(missing)}")
        if corrupt:
            warnings.append(f"文件解析失败: {', '.join(corrupt)}")

    return {
        "schema_version": SCHEMA_VERSION,
        "validated_at": ts,
        "analysis_dir": resolved_dir,
        "book_name": book_name,
        "status": status,
        "warnings": warnings,
        "files": files_info,
    }


def format_human(manifest):
    """Format manifest as human-readable Chinese output (concise)."""
    status_map = {"ok": "正常", "degraded": "降级", "invalid": "无效"}
    status_cn = status_map.get(manifest["status"], manifest["status"])

    lines = [f"验证状态: {status_cn}"]
    lines.append(f"书籍: {manifest['book_name']}")
    lines.append(f"分析目录: {manifest['analysis_dir']}")
    lines.append(f"验证时间: {manifest['validated_at']}")

    if manifest["warnings"]:
        lines.append("")
        lines.append("警告:")
        for w in manifest["warnings"]:
            lines.append(f"  [!] {w}")

    lines.append("")
    lines.append("文件清单:")
    for f in manifest["files"]:
        icon = "[OK]" if f["valid"] else "[NG]"
        present = "存在" if f["present"] else "缺失"
        size = f" ({f['size_bytes']} bytes)" if f["present"] else ""
        err = f" - {f['error']}" if f["error"] else ""
        lines.append(f"  {icon} {f['name']} [{present}]{size}{err}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="4D 拆解产物验证器")
    parser.add_argument("analysis_dir", help="分析产物目录路径 (analysis/)")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="写入 analysis_manifest.json 到分析目录",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已有 manifest",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 格式输出（机器可读）",
    )
    args = parser.parse_args()

    # --- Build manifest ---
    manifest = validate_analysis_dir(args.analysis_dir)

    # --- Handle --write-manifest ---
    if args.write_manifest:
        resolved = os.path.abspath(args.analysis_dir)
        manifest_path = os.path.join(resolved, MANIFEST_FILENAME)

        # Refuse to overwrite without --force
        if os.path.exists(manifest_path) and not args.force:
            result = {
                "ok": False,
                "error": f"Manifest 已存在: {manifest_path}",
                "warning": "使用 --force 覆盖",
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"[!] Manifest 已存在: {manifest_path}")
                print("   使用 --force 覆盖")
            return 1

        # Ensure parent directory exists
        if not os.path.isdir(resolved):
            result = {
                "ok": False,
                "error": f"目录不存在: {resolved}",
            }
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"[!] 目录不存在: {resolved}")
            return 1

        # Write manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        if args.json:
            output = dict(manifest)
            output["manifest_written"] = manifest_path
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(format_human(manifest))
            print(f"\n[OK] Manifest 已写入: {manifest_path}")
    else:
        # Just output the manifest
        if args.json:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            print(format_human(manifest))

    # Exit code: 0 if ok or degraded; 1 if invalid
    return 0 if manifest["status"] in ("ok", "degraded") else 1


if __name__ == "__main__":
    sys.exit(main())

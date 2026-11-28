#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submit every original report page to visual LLM review in bounded groups."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import pymupdf

VisualSubmit = Callable[[str, list[dict[str, Any]]], Awaitable[str]]
Progress = Callable[[dict[str, Any]], Awaitable[None]]
PAGE_MARKER = re.compile(r"(?m)^## Page (\d+)\s*$")
GROUP_SIZE = 8
RENDER_DPI = 144
VISUAL_HEADING = re.compile(r"(?m)^### Page (\d+)\s*$")


def _save_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _split_pages(report_text: str, page_count: int) -> dict[int, str]:
    matches = list(PAGE_MARKER.finditer(report_text))
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        if page_number < 1 or page_number > page_count or page_number in pages:
            raise ValueError(f"Invalid or duplicate page marker: {page_number}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(report_text)
        pages[page_number] = report_text[match.start():end].rstrip()
    missing = [number for number in range(1, page_count + 1) if number not in pages]
    if missing:
        raise ValueError("Visual review is missing page markers: " + ", ".join(map(str, missing[:10])))
    return pages


def _validate_response(raw: Any, pages: list[int], context_pages: list[int]) -> str:
    """Check per-page response structure only; page interpretations stay with the LLM."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Visual response is empty")
    matches = list(VISUAL_HEADING.finditer(raw))
    found = [int(match.group(1)) for match in matches]
    if found != pages:
        missing = [page for page in pages if found.count(page) == 0]
        duplicates = [page for page in set(found) if found.count(page) > 1]
        unexpected = [page for page in found if page not in pages]
        raise ValueError(
            f"Visual page headings must exactly cover {pages} once in order; "
            f"missing={missing}, duplicates={duplicates}, unexpected={unexpected} "
            f"(context pages are not coverage: {context_pages})"
        )
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        if not raw[match.end():end].strip():
            raise ValueError(f"Visual page section {pages[index]} has empty content")
    return raw


def _render_pages(pdf_path: Path, page_numbers: list[int], dpi: int = RENDER_DPI) -> list[dict[str, Any]]:
    """Render selected one-based PDF pages as separate PNG payloads."""
    images = []
    with pymupdf.open(pdf_path) as pdf:
        for page_number in page_numbers:
            if page_number < 1 or page_number > pdf.page_count:
                raise ValueError(f"Requested image page is outside the PDF: {page_number}")
            page = pdf[page_number - 1]
            data = page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
            images.append({
                "data": data,
                "media_type": "image/png",
                "identifier": f"page-{page_number}",
                "page": page_number,
            })
    return images


def _load_complete_cache(
    cache_dir: Path | None, page_count: int, dpi: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read a structurally complete visual cache from one prior attempt directory."""
    if cache_dir is None:
        return None, None
    cache_dir = Path(cache_dir).resolve()
    manifest_path = cache_dir / "visual.json"
    try:
        raw_bytes = manifest_path.read_bytes()
        manifest = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(manifest, dict) or manifest.get("status") != "complete":
        return None, None
    try:
        cached_pages = int(manifest.get("page_count"))
        cached_dpi = int(manifest.get("render_dpi"))
        cached_group_size = int(manifest.get("group_size"))
    except (TypeError, ValueError):
        return None, None
    if cached_pages != page_count or cached_dpi != dpi or cached_group_size != GROUP_SIZE:
        return None, None

    expected_page_numbers = list(range(1, page_count + 1))
    pages = manifest.get("pages")
    if not isinstance(pages, list) or [item.get("page") if isinstance(item, dict) else None for item in pages] != expected_page_numbers:
        return None, None
    if any(item.get("status") != "complete" for item in pages if isinstance(item, dict)):
        return None, None
    expected_groups: list[tuple[int, list[int], list[int]]] = []
    for start in range(1, page_count + 1, GROUP_SIZE):
        group_number = len(expected_groups) + 1
        group_pages = list(range(start, min(start + GROUP_SIZE, page_count + 1)))
        context = [start - 1] if start > 1 else []
        expected_groups.append((group_number, group_pages, context))
    groups = manifest.get("groups")
    if not isinstance(groups, list) or len(groups) != len(expected_groups):
        return None, None
    for cached_group, (number, group_pages, context_pages) in zip(groups, expected_groups):
        if (not isinstance(cached_group, dict)
                or cached_group.get("group") != number
                or cached_group.get("status") != "complete"
                or cached_group.get("pages") != group_pages
                or cached_group.get("context_pages") != context_pages):
            return None, None
    return manifest, hashlib.sha256(raw_bytes).hexdigest()


def _cached_response(
    cache_dir: Path | None,
    cache_manifest: dict[str, Any] | None,
    cache_manifest_sha256: str | None,
    *,
    group_number: int,
    pages: list[int],
    context_pages: list[int],
    prompt_sha256: str,
    image_records: list[dict[str, Any]],
) -> tuple[Path, str, dict[str, Any]] | None:
    """Return a prior group response only when prompt, rendered pages, and raw format match."""
    if cache_dir is None or cache_manifest is None or cache_manifest_sha256 is None:
        return None
    cached_groups = cache_manifest.get("groups")
    if not isinstance(cached_groups, list) or group_number < 1 or group_number > len(cached_groups):
        return None
    source_group = cached_groups[group_number - 1]
    if (not isinstance(source_group, dict)
            or source_group.get("group") != group_number
            or source_group.get("status") != "complete"
            or source_group.get("pages") != pages
            or source_group.get("context_pages") != context_pages):
        return None
    source_prompt_sha256 = source_group.get("input_prompt_sha256")
    if not source_prompt_sha256:
        attempts = source_group.get("attempts")
        if not isinstance(attempts, list) or not attempts or not isinstance(attempts[0], dict):
            return None
        source_prompt_sha256 = attempts[0].get("prompt_sha256")
    if source_prompt_sha256 != prompt_sha256:
        return None
    cached_images = source_group.get("images")
    if not isinstance(cached_images, list):
        return None
    try:
        current_image_fingerprints = [(item["page"], item["sha256"]) for item in image_records]
        cached_image_fingerprints = [(item["page"], item["sha256"]) for item in cached_images]
    except (KeyError, TypeError):
        return None
    if current_image_fingerprints != cached_image_fingerprints:
        return None

    response_name = source_group.get("completed_response_file")
    if not isinstance(response_name, str) or not response_name.strip():
        return None
    source_root = Path(cache_dir).resolve()
    response_path = (source_root / response_name).resolve()
    try:
        response_path.relative_to(source_root)
    except ValueError:
        return None
    if not response_path.is_file():
        return None
    try:
        response_bytes = response_path.read_bytes()
        response = response_bytes.decode("utf-8")
        _validate_response(response, pages, context_pages)
    except (OSError, UnicodeError, ValueError):
        return None
    response_sha256 = hashlib.sha256(response_bytes).hexdigest()
    recorded_response_sha256 = source_group.get("response_sha256")
    if recorded_response_sha256 and recorded_response_sha256 != response_sha256:
        return None
    source = {
        "attempt_dir": str(source_root),
        "manifest_file": "visual.json",
        "manifest_sha256": cache_manifest_sha256,
        "group": group_number,
        "response_file": response_path.relative_to(source_root).as_posix(),
        "response_sha256": response_sha256,
    }
    return response_path, response, source


def _build_visual_prompt(
    page_text: str,
    pages: list[int],
    context_pages: list[int],
    *,
    page_count: int = 0,
    rules_dir: Path | None = None,
) -> str:
    from audit_project_prompts import build_visual_prompt
    return build_visual_prompt(page_text, pages, context_pages, page_count=page_count, rules_dir=rules_dir)


async def _emit(
    callback: Progress | None, completed: int, total: int, message: str,
) -> None:
    if callback is None:
        return
    result = callback({"stage": "visual", "completed": completed, "total": total, "message": message})
    if inspect.isawaitable(result):
        await result


async def inspect_report(
    pdf_path: Path,
    report_text: str,
    submit_visual: VisualSubmit,
    output_dir: Path,
    on_progress: Progress | None = None,
    *,
    rules_dir: Path | None = None,
    visual_cache_dir: Path | None = None,
    visual_dpi: int = RENDER_DPI,
) -> list[dict[str, Any]]:
    """Render and submit every page in groups of eight, adding prior-page context.

    The local workflow handles page slicing, image rendering, metadata, raw
    response retention, and coverage only. All visible content interpretation
    and audit judgments belong to the visual model.
    """
    pdf_path, output_dir = Path(pdf_path), Path(output_dir)
    visual_dpi = int(visual_dpi)
    if visual_dpi < 1:
        raise ValueError("Visual render DPI must be a positive integer")
    output_dir.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf_path) as pdf:
        page_count = pdf.page_count
    if page_count < 1:
        raise ValueError("Visual review requires a non-empty PDF")
    text_pages = _split_pages(report_text, page_count)
    cache_manifest, cache_manifest_sha256 = _load_complete_cache(visual_cache_dir, page_count, visual_dpi)
    groups: list[dict[str, Any]] = []
    for start in range(1, page_count + 1, GROUP_SIZE):
        page_numbers = list(range(start, min(start + GROUP_SIZE, page_count + 1)))
        context_pages = [start - 1] if start > 1 else []
        groups.append({
            "group": len(groups) + 1,
            "pages": page_numbers,
            "context_pages": context_pages,
            "status": "pending",
            "response_file": f"visual/{len(groups) + 1:03d}-raw.md",
            "prompt_sha256": None,
            "input_prompt_sha256": None,
            "prompt_characters": None,
            "images": [],
            "attempts": [],
            "submitted": False,
            "reused": False,
            "cache_source": None,
            "error_type": None,
        })
    manifest: dict[str, Any] = {
        "status": "running",
        "page_count": page_count,
        "render_dpi": visual_dpi,
        "group_size": GROUP_SIZE,
        "pages": [{"page": page, "status": "pending", "group": (page - 1) // GROUP_SIZE + 1}
                  for page in range(1, page_count + 1)],
        "groups": groups,
    }
    manifest_path = output_dir / "visual.json"
    semaphore = asyncio.Semaphore(2)
    completed = 0
    _save_json(manifest_path, manifest)

    async def review_group(group: dict[str, Any]) -> dict[str, Any]:
        nonlocal completed
        page_numbers = list(group["pages"])
        context_pages = list(group["context_pages"])
        image_pages = context_pages + page_numbers
        async with semaphore:
            try:
                images = await asyncio.to_thread(_render_pages, pdf_path, image_pages, visual_dpi)
                page_text = "\n\n".join(text_pages[number] for number in image_pages)
                prompt = await asyncio.to_thread(
                    _build_visual_prompt, page_text, page_numbers, context_pages,
                    page_count=page_count, rules_dir=rules_dir,
                )
                group["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                group["input_prompt_sha256"] = group["prompt_sha256"]
                group["prompt_characters"] = len(prompt)
                group["images"] = [
                    {"page": image["page"], "identifier": image["identifier"],
                     "media_type": image["media_type"],
                     "sha256": hashlib.sha256(image["data"]).hexdigest(),
                     "bytes": len(image["data"])}
                    for image in images
                ]
                prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                cached = _cached_response(
                    visual_cache_dir,
                    cache_manifest,
                    cache_manifest_sha256,
                    group_number=int(group["group"]),
                    pages=page_numbers,
                    context_pages=context_pages,
                    prompt_sha256=prompt_sha256,
                    image_records=group["images"],
                )
                if cached is not None:
                    cached_path, _cached_response_text, cache_source = cached
                    response_path = output_dir / str(group["response_file"])
                    response_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copyfile(cached_path, response_path)
                        copied_bytes = response_path.read_bytes()
                        copied_sha256 = hashlib.sha256(copied_bytes).hexdigest()
                        if copied_sha256 != cache_source["response_sha256"]:
                            raise ValueError("Copied cached visual response hash changed")
                        copied_response = _validate_response(
                            copied_bytes.decode("utf-8"), page_numbers, context_pages,
                        )
                    except (OSError, UnicodeError, ValueError):
                        response_path.unlink(missing_ok=True)
                    else:
                        group.update(
                            status="complete",
                            prompt_sha256=prompt_sha256,
                            input_prompt_sha256=prompt_sha256,
                            prompt_characters=len(prompt),
                            reused=True,
                            cache_source=cache_source,
                            completed_response_file=response_path.relative_to(output_dir).as_posix(),
                            response_sha256=cache_source["response_sha256"],
                        )
                        for page_number in page_numbers:
                            manifest["pages"][page_number - 1]["status"] = "complete"
                        _save_json(manifest_path, manifest)
                        return {
                            "pages": page_numbers,
                            "context_pages": context_pages,
                            "markdown": copied_response,
                            "response_file": group["completed_response_file"],
                            "reused": True,
                            "submitted": False,
                            "cache_source": cache_source,
                        }
                image_payload = [
                    {key: image[key] for key in ("data", "media_type", "identifier", "page")}
                    for image in images
                ]
                response_path: Path | None = None
                last_format_error: ValueError | None = None
                previous_raw = ""
                for attempt_number in range(2):
                    response_name = (
                        f"visual/{group['group']:03d}-raw.md" if attempt_number == 0
                        else f"visual/{group['group']:03d}-retry-raw.md"
                    )
                    if attempt_number == 0:
                        attempt_prompt = prompt
                    else:
                        from audit_project_prompts import build_visual_retry_prompt
                        attempt_prompt = build_visual_retry_prompt(prompt, str(last_format_error), previous_raw)
                    attempt = {
                        "response_file": response_name,
                        "status": "running",
                        "prompt_sha256": hashlib.sha256(attempt_prompt.encode("utf-8")).hexdigest(),
                        "prompt_characters": len(attempt_prompt),
                    }
                    group["attempts"].append(attempt)
                    group["status"] = "running"
                    group["submitted"] = True
                    group["prompt_sha256"] = attempt["prompt_sha256"]
                    group["prompt_characters"] = attempt["prompt_characters"]
                    _save_json(manifest_path, manifest)
                    try:
                        raw = await submit_visual(attempt_prompt, image_payload)
                    except asyncio.CancelledError:
                        attempt["status"] = "cancelled"
                        raise
                    except Exception as exc:
                        attempt["status"] = "failed"
                        attempt["error_type"] = type(exc).__name__
                        raise
                    response_path = output_dir / response_name
                    response_path.parent.mkdir(parents=True, exist_ok=True)
                    if isinstance(raw, str):
                        response_path.write_text(raw, encoding="utf-8")
                        previous_raw = raw
                    else:
                        response_path.write_text("", encoding="utf-8")
                    try:
                        _validate_response(raw, page_numbers, context_pages)
                        attempt["status"] = "complete"
                        break
                    except ValueError as exc:
                        attempt["status"] = "invalid_format"
                        attempt["error_type"] = type(exc).__name__
                        last_format_error = exc
                        group["completed_response_file"] = response_name
                        _save_json(manifest_path, manifest)
                        if attempt_number:
                            raise
                if response_path is None:
                    raise ValueError("Visual model response is missing")
                completed_response = _validate_response(
                    response_path.read_text(encoding="utf-8"), page_numbers, context_pages,
                )
                group["status"] = "complete"
                group["reused"] = False
                group["completed_response_file"] = response_path.relative_to(output_dir).as_posix()
                group["response_sha256"] = hashlib.sha256(response_path.read_bytes()).hexdigest()
                for page_number in page_numbers:
                    manifest["pages"][page_number - 1]["status"] = "complete"
                _save_json(manifest_path, manifest)
                return {
                    "pages": page_numbers,
                    "context_pages": context_pages,
                    "markdown": completed_response,
                    "response_file": group["completed_response_file"],
                    "reused": False,
                    "submitted": True,
                }
            except asyncio.CancelledError:
                group["status"] = "cancelled"
                for page_number in page_numbers:
                    manifest["pages"][page_number - 1]["status"] = "cancelled"
                raise
            except Exception as exc:
                group["status"] = "failed"
                group["error_type"] = type(exc).__name__
                for page_number in page_numbers:
                    manifest["pages"][page_number - 1]["status"] = "failed"
                raise
            finally:
                completed += 1
                _save_json(manifest_path, manifest)
                await _emit(on_progress, completed, len(groups),
                            f"视觉页组 {group['group']} 技术处理结束")

    try:
        await _emit(on_progress, 0, len(groups), "正在开始视觉页面核查")
        results = await asyncio.gather(*(review_group(group) for group in groups), return_exceptions=True)
        if any(isinstance(result, asyncio.CancelledError) for result in results):
            manifest["status"] = "cancelled"
            _save_json(manifest_path, manifest)
            raise next(result for result in results if isinstance(result, asyncio.CancelledError))
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            manifest["status"] = "failed"
            _save_json(manifest_path, manifest)
            first = failures[0]
            raise RuntimeError(
                f"visual review failed ({type(first).__name__}); no complete audit should be published"
            ) from first
        manifest["status"] = "complete"
        _save_json(manifest_path, manifest)
        await _emit(on_progress, len(groups), len(groups), "所有页面视觉核查已完成")
        return [result for result in results if isinstance(result, dict)]
    except asyncio.CancelledError:
        manifest["status"] = "cancelled"
        _save_json(manifest_path, manifest)
        raise
    except Exception:
        if manifest["status"] == "running":
            manifest["status"] = "failed"
        _save_json(manifest_path, manifest)
        raise

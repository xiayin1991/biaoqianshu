# -*- coding: utf-8 -*-
from __future__ import annotations

import colorsys
import json
import math
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image, ImageDraw, ImageFont

try:
    import pypdfium2 as pdfium
except Exception:
    pdfium = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document
except Exception:
    Document = None

try:
    from pptx import Presentation
except Exception:
    Presentation = None

APP_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = APP_DIR / 'Projects'
ASSETS_DIR = APP_DIR / 'assets'
APP_VERSION = '1.7.1'


def now_ts() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name[:80] or 'project'


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def font_path() -> Optional[str]:
    candidates = [
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\msyhbd.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\simsun.ttc',
        r'C:\Windows\Fonts\arial.ttf',
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def load_font(size: int) -> ImageFont.FreeTypeFont:
    fp = font_path()
    if fp:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


@dataclass
class Question:
    qid: str
    index: int
    image: str
    source: str = ''
    page: int = 0
    bbox: Optional[list] = None
    description: str = ''
    tags: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class ProjectData:
    name: str
    root: str
    source_file: str
    created_at: str
    version: str = APP_VERSION
    questions: list[Question] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def root_path(self) -> Path:
        return Path(self.root)

    @property
    def project_file(self) -> Path:
        return self.root_path / 'project.json'

    def save(self) -> None:
        data = asdict(self)
        self.project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def load(project_file: Path) -> 'ProjectData':
        project_file = Path(project_file).resolve()
        project_root = project_file.parent
        data = json.loads(project_file.read_text(encoding='utf-8'))
        old_root = str(data.get('root', ''))
        data['root'] = str(project_root)
        data['questions'] = [Question(**q) for q in data.get('questions', [])]
        settings = data.setdefault('settings', {})
        migrated = False
        if int(settings.get('layout_revision', 1)) < 4:
            settings['left_width'] = 55.0
            settings['layout_revision'] = 4
            migrated = True
        project = ProjectData(**data)
        if migrated or old_root != str(project_root):
            project.save()
        return project

    def question_by_index(self, idx: int) -> Optional[Question]:
        if 0 <= idx < len(self.questions):
            return self.questions[idx]
        return None


@dataclass
class TreeNode:
    code: str
    label: str
    path: tuple[str, ...]
    children: list['TreeNode'] = field(default_factory=list)
    count: int = 0
    score: float = 0.0
    x: float = 0.0
    y: float = 0.0
    color: tuple[int, int, int] = (80, 80, 80)


class TagTree:
    def __init__(self):
        self.root = TreeNode('0', 'ROOT', ())

    def add_path(self, path: Iterable[str], score: float = 0.0) -> TreeNode:
        parts = [p.strip() for p in path if p and p.strip()]
        weight = float(score or 0.0)
        node = self.root
        for part in parts:
            found = next((c for c in node.children if c.label == part), None)
            if found is None:
                found = TreeNode('', part, node.path + (part,))
                node.children.append(found)
                self._renumber()
            node = found
            node.count += 1
            node.score += weight
        return node

    def _renumber(self) -> None:
        def walk(node: TreeNode, code: str):
            node.code = code
            for i, child in enumerate(node.children, start=1):
                walk(child, code + str(i))
        walk(self.root, '0')

    def recompute_counts(self) -> None:
        def calc(node: TreeNode) -> int:
            if not node.children:
                node.count = 1
                return 1
            node.count = sum(calc(child) for child in node.children)
            return node.count
        calc(self.root)
    def all_nodes(self) -> list[TreeNode]:
        out = []
        def walk(n: TreeNode):
            out.append(n)
            for c in n.children:
                walk(c)
        walk(self.root)
        return out

    def leaf_count(self, node: TreeNode) -> int:
        if not node.children:
            return 1
        return sum(self.leaf_count(c) for c in node.children)

    def layout(self, width: float, height: float, left_margin: float = 90, top_margin: float = 70) -> None:
        self._renumber()
        max_depth = max((len(n.path) for n in self.all_nodes()), default=1)
        leaves = max(1, self.leaf_count(self.root))
        max_depth = max(1, max_depth)
        depth_gap = max(90, (width - 2 * left_margin) / max(1, max_depth))
        y_gap = max(42, (height - 2 * top_margin) / max(1, leaves - 1)) if leaves > 1 else 0
        cursor = {'y': top_margin}

        def walk(node: TreeNode, depth: int):
            node.x = left_margin + depth * depth_gap
            if not node.children:
                node.y = cursor['y']
                cursor['y'] += y_gap
            else:
                for child in node.children:
                    walk(child, depth + 1)
                node.y = sum(c.y for c in node.children) / len(node.children)

        walk(self.root, 0)

    def assign_colors(self, depth_limit: int = 2) -> None:
        top_count = max(1, len(self.root.children))

        def code_color(code: str):
            raw_code = str(code)[1:] if str(code).startswith('0') else str(code)
            digits = [int(ch) for ch in raw_code if ch.isdigit()] or [1]
            top_index = max(0, digits[0] - 1)
            hue = (top_index * 360.0 / top_count + 8) % 360
            level = max(0, len(digits) - 1)
            if depth_limit > 1 and len(digits) > 1:
                offset = 0
                for idx in range(1, min(len(digits), depth_limit)):
                    offset += (((digits[idx] - 1) % 3) - 1) * 8
                hue = (hue + offset) % 360
            light = max(38, 66 - min(level, 4) * 6)
            sat = max(54, 76 - min(level, 3) * 5)
            r, g, b = colorsys.hls_to_rgb(hue / 360.0, light / 100.0, sat / 100.0)
            return int(r * 255), int(g * 255), int(b * 255)

        self._renumber()
        self.root.color = (20, 24, 32)
        for node in self.all_nodes():
            if node is not self.root:
                node.color = code_color(node.code)
    def export_markdown(self) -> str:
        lines = ['# 标签树标签列表', '']
        def walk(n: TreeNode, indent: int = 0):
            if n.path:
                lines.append('  ' * indent + f'- ({n.code}) {n.label}')
            for c in n.children:
                walk(c, indent + 1)
        walk(self.root)
        return '\n'.join(lines) + '\n'


def question_markers(text: str) -> list[tuple[int, str]]:
    marks = []
    pattern = re.compile(r'(?m)^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[\.\)、]\s+')
    for m in pattern.finditer(text):
        marks.append((m.start(), m.group(1)))
    return marks


def render_pdf_questions(pdf_path: Path, preview_dir: Path, qid_prefix: str) -> list[Question]:
    if pdfium is None:
        raise RuntimeError('缺少 pypdfium2，无法导入 PDF')
    doc = pdfium.PdfDocument(str(pdf_path))
    questions: list[Question] = []
    seq = 0
    for page_index in range(len(doc)):
        page = doc[page_index]
        bitmap = page.render(scale=2.0)
        img = bitmap.to_pil().convert('RGB')
        text = ''
        starts = []
        scale = 2.0
        page_width, page_height = page.get_size()
        try:
            tp = page.get_textpage()
            text = tp.get_text_range() or ''
            if text and tp.count_chars() > 0:
                for pos, _num in question_markers(text):
                    try:
                        box = tp.get_charbox(pos)
                        if box and len(box) == 4:
                            y_px = (page_height - box[3]) * scale
                            starts.append(max(0.0, min(float(img.height), float(y_px))))
                    except Exception:
                        pass
        except Exception:
            text = ''
        starts = sorted(set(round(x, 1) for x in starts))
        merged = []
        for top in starts:
            if merged and abs(top - merged[-1]) < 4:
                continue
            merged.append(top)
        ranges = []
        if merged:
            for i, top in enumerate(merged):
                y2 = merged[i + 1] if i + 1 < len(merged) else float(img.height)
                y1 = max(0, int(top))
                y2 = min(img.height, int(y2))
                if y2 - y1 >= 20:
                    ranges.append((y1, y2))
        if not ranges:
            ranges = [(0, img.height)]
        for y1, y2 in ranges:
            seq += 1
            crop = img.crop((0, y1, img.width, y2))
            out = preview_dir / f'q_{seq:04d}.png'
            crop.save(out, 'PNG')
            questions.append(Question(
                qid=f'{qid_prefix}_Q{seq:03d}',
                index=seq,
                image=str(out.relative_to(preview_dir.parent)),
                source=pdf_path.name,
                page=page_index + 1,
                bbox=[0, y1, img.width, y2],
            ))
    doc.close()
    return questions


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines = []
    for raw in text.splitlines() or ['']:
        if not raw:
            lines.append('')
            continue
        current = ''
        for ch in raw:
            test = current + ch
            if draw.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def text_to_preview(text: str, out_path: Path, title: str = '') -> None:
    width = 1240
    margin = 70
    font = load_font(34)
    title_font = load_font(42)
    tmp = Image.new('RGB', (width, 100), 'white')
    d = ImageDraw.Draw(tmp)
    lines = wrap_text(d, text, font, width - margin * 2)
    line_h = 48
    height = max(500, margin * 2 + (80 if title else 0) + max(1, len(lines)) * line_h)
    img = Image.new('RGB', (width, height), 'white')
    d = ImageDraw.Draw(img)
    y = margin
    if title:
        d.text((margin, y), title, font=title_font, fill=(20, 24, 32))
        y += 80
    for line in lines:
        d.text((margin, y), line, font=font, fill=(20, 24, 32))
        y += line_h
    img.save(out_path, 'PNG')


def split_text_segments(text: str) -> list[str]:
    matches = list(re.finditer(r'(?m)^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[\.\)、]\s+', text))
    if not matches:
        return [text.strip()] if text.strip() else []
    segments = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        seg = text[start:end].strip()
        if seg:
            segments.append(seg)
    return segments


def render_docx_questions(docx_path: Path, preview_dir: Path, qid_prefix: str) -> list[Question]:
    if Document is None:
        raise RuntimeError('缺少 python-docx，无法导入 DOCX')
    doc = Document(str(docx_path))
    text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    segments = split_text_segments(text) or [text]
    questions = []
    for i, seg in enumerate(segments, start=1):
        out = preview_dir / f'q_{i:04d}.png'
        text_to_preview(seg, out, title=f'Question {i}')
        questions.append(Question(qid=f'{qid_prefix}_Q{i:03d}', index=i, image=str(out.relative_to(preview_dir.parent)), source=docx_path.name))
    return questions


def render_pptx_questions(pptx_path: Path, preview_dir: Path, qid_prefix: str) -> list[Question]:
    if Presentation is None:
        raise RuntimeError('缺少 python-pptx，无法导入 PPTX')
    prs = Presentation(str(pptx_path))
    questions = []
    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, 'text') and shape.text and shape.text.strip():
                texts.append(shape.text.strip())
        out = preview_dir / f'q_{i:04d}.png'
        text_to_preview('\n'.join(texts) or f'[Slide {i}]', out, title=f'Slide {i}')
        questions.append(Question(qid=f'{qid_prefix}_Q{i:03d}', index=i, image=str(out.relative_to(preview_dir.parent)), source=pptx_path.name))
    return questions


def render_image_questions(image_paths: list[Path], preview_dir: Path, qid_prefix: str) -> list[Question]:
    questions = []
    for i, src in enumerate(image_paths, start=1):
        out = preview_dir / f'q_{i:04d}.png'
        try:
            img = Image.open(src).convert('RGB')
            img.save(out, 'PNG')
        except Exception:
            continue
        questions.append(Question(qid=f'{qid_prefix}_Q{i:03d}', index=i, image=str(out.relative_to(preview_dir.parent)), source=src.name))
    return questions


def render_pdf_pages(pdf_path: Path, pages_dir: Path, prefix: str) -> list[dict]:
    if pdfium is None:
        raise RuntimeError('缺少 pypdfium2，无法导入 PDF')
    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            img = page.render(scale=2.0).to_pil().convert('RGB')
            out = pages_dir / f'page_{page_index + 1:04d}.png'
            img.save(out, 'PNG')
            pages.append({'index': page_index + 1, 'image': str(out.relative_to(pages_dir.parent)), 'source': pdf_path.name})
    finally:
        doc.close()
    return pages


def render_docx_pages(docx_path: Path, pages_dir: Path, prefix: str) -> list[dict]:
    if Document is None:
        raise RuntimeError('缺少 python-docx，无法导入 DOCX')
    doc = Document(str(docx_path))
    text = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    out = pages_dir / 'page_0001.png'
    text_to_preview(text, out, title=docx_path.stem)
    return [{'index': 1, 'image': str(out.relative_to(pages_dir.parent)), 'source': docx_path.name}]


def render_pptx_pages(pptx_path: Path, pages_dir: Path, prefix: str) -> list[dict]:
    if Presentation is None:
        raise RuntimeError('缺少 python-pptx，无法导入 PPTX')
    prs = Presentation(str(pptx_path))
    pages = []
    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, 'text') and shape.text and shape.text.strip():
                texts.append(shape.text.strip())
        out = pages_dir / f'page_{i:04d}.png'
        text_to_preview('\n'.join(texts) or f'[Slide {i}]', out, title=f'Slide {i}')
        pages.append({'index': i, 'image': str(out.relative_to(pages_dir.parent)), 'source': pptx_path.name})
    return pages


def render_image_pages(image_paths: list[Path], pages_dir: Path, prefix: str) -> list[dict]:
    pages = []
    for i, src in enumerate(image_paths, start=1):
        try:
            img = Image.open(src).convert('RGB')
        except Exception:
            continue
        out = pages_dir / f'page_{i:04d}.png'
        img.save(out, 'PNG')
        pages.append({'index': i, 'image': str(out.relative_to(pages_dir.parent)), 'source': src.name})
    return pages


def create_project(source_paths: list[Path], projects_root: Path = PROJECTS_DIR) -> ProjectData:
    if not source_paths:
        raise ValueError('没有选择文件')
    ensure_dir(projects_root)
    first = source_paths[0]
    display = safe_name(first.stem)
    root = ensure_dir(projects_root / f'{display}_{now_ts()}')
    source_dir = ensure_dir(root / 'source')
    pages_dir = ensure_dir(root / 'pages')
    ensure_dir(root / 'questions')
    for src in source_paths:
        shutil.copy2(src, source_dir / src.name)
    copied = source_dir / first.name
    ext = copied.suffix.lower()
    qid_prefix = safe_name(copied.stem)
    if ext == '.pdf':
        pages = render_pdf_pages(copied, pages_dir, qid_prefix)
    elif ext == '.docx':
        pages = render_docx_pages(copied, pages_dir, qid_prefix)
    elif ext == '.pptx':
        pages = render_pptx_pages(copied, pages_dir, qid_prefix)
    elif ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
        pages = render_image_pages(source_paths, pages_dir, qid_prefix)
    else:
        raise ValueError(f'暂不支持的文件格式：{ext}')
    project = ProjectData(
        name=display,
        root=str(root),
        source_file=str(copied),
        created_at=datetime.now().isoformat(timespec='seconds'),
        questions=[],
        pages=pages,
        settings={'color_depth': 2, 'left_width': 55, 'preview_height': 72, 'layout_revision': 4},
    )
    project.save()
    return project


def crop_question(project: ProjectData, page_index: int, bbox: list[float], question_number: Optional[str] = None, score: float = 0.0) -> Question:
    if page_index < 0 or page_index >= len(project.pages):
        raise ValueError('页码超出范围')
    page = project.pages[page_index]
    page_path = project.root_path / page['image']
    img = Image.open(page_path).convert('RGB')
    x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
    x1, x2 = sorted((max(0, min(img.width, x1)), max(0, min(img.width, x2))))
    y1, y2 = sorted((max(0, min(img.height, y1)), max(0, min(img.height, y2))))
    if x2 - x1 < 10 or y2 - y1 < 10:
        raise ValueError('框选区域太小：请重新拖拽一个更大的矩形')
    if not question_number:
        raise ValueError('请输入题号，例如 P2-17')
    qid = normalize_question_id(question_number)
    if any(q.qid == qid for q in project.questions):
        raise ValueError(f'题号 {qid} 已存在')
    seq = len(project.questions) + 1
    out_dir = ensure_dir(project.root_path / 'questions')
    out = out_dir / f'{qid}.png'
    img.crop((x1, y1, x2, y2)).save(out, 'PNG')
    q = Question(
        qid=qid,
        index=seq,
        image=str(out.relative_to(project.root_path)),
        source=Path(project.source_file).name,
        page=page_index + 1,
        bbox=[x1, y1, x2, y2],
        score=float(score or 0),
    )
    project.questions.append(q)
    project.save()
    return q


def normalize_question_id(question_number: Optional[str]) -> str:
    if not question_number:
        raise ValueError('请输入题号，例如 P2-17')
    raw = str(question_number).strip().upper()
    m = re.fullmatch(r'P([12])-(\d{1,3})', raw)
    if not m:
        raise ValueError('题号格式错误，请使用 P2-17 或 P1-03')
    return f'P{m.group(1)}-{int(m.group(2)):02d}'


def update_question(project: ProjectData, qid: str, question_number: Optional[str] = None, score: Optional[float] = None) -> Question:
    q = next((item for item in project.questions if item.qid == qid), None)
    if q is None:
        raise ValueError('找不到题目')

    if question_number is not None:
        new_qid = normalize_question_id(question_number)
        if any(item is not q and item.qid == new_qid for item in project.questions):
            raise ValueError(f'题号 {new_qid} 已存在')
        q.qid = new_qid

    if score is not None:
        try:
            new_score = float(score)
        except (TypeError, ValueError):
            raise ValueError('分值必须是大于 0 的数字')
        if not math.isfinite(new_score) or new_score <= 0:
            raise ValueError('分值必须是大于 0 的数字')
        q.score = new_score

    project.save()
    return q

def build_tag_tree(project: ProjectData) -> TagTree:
    tree = TagTree()
    for q in project.questions:
        for tag in q.tags:
            tree.add_path(tag.split('/'), score=q.score)
    tree.root.count = sum(child.count for child in tree.root.children)
    tree.root.score = sum(child.score for child in tree.root.children)
    tree.root.label = project.name
    tree.assign_colors(int(project.settings.get('color_depth', 2)))
    return tree


def tree_to_dict(tree: TagTree) -> dict:
    def walk(n: TreeNode) -> dict:
        return {
            'code': n.code,
            'label': n.label,
            'path': list(n.path),
            'count': n.count,
            'score': n.score,
            'children': [walk(c) for c in n.children],
        }
    return walk(tree.root)


def render_tree_png(tree: TagTree, out_path: Path, color_depth: int = 2, width: int = 2400, height: int = 1600, metric: str = 'count') -> None:
    tree.assign_colors(color_depth)
    nodes = tree.all_nodes()
    max_depth = max((len(n.path) for n in nodes), default=1)
    leaves = max(1, tree.leaf_count(tree.root))
    height = max(height, 420 + leaves * 52)
    width = max(width, 1100 + max_depth * 360)
    left, right, top, bottom = 90, 90, 90, 100
    depth_gap = max(170, (height - top - bottom) / max(1, max_depth + 1))
    leaf_gap = max(54, (width - left - right) / max(1, leaves - 1)) if leaves > 1 else 0
    cursor = {'x': left}
    def walk(node: TreeNode, depth: int):
        node.y = height - bottom - depth * depth_gap
        if not node.children:
            node.x = cursor['x']
            cursor['x'] += leaf_gap
        else:
            for child in node.children:
                walk(child, depth + 1)
            node.x = sum(c.x for c in node.children) / len(node.children)
    walk(tree.root, 0)
    img = Image.new('RGB', (width, int(height)), 'white')
    draw = ImageDraw.Draw(img)
    node_font = load_font(24)
    label_font = load_font(20)
    root_font = load_font(28)
    def metric_value(node: TreeNode) -> float:
        return float(node.score if metric == 'score' else node.count)

    for n in nodes:
        for c in n.children:
            thickness = max(1, min(12, int((metric_value(c) or 1) ** 0.5 * 2)))
            draw.line((n.x, n.y, c.x, c.y), fill=c.color, width=thickness)
    for n in nodes:
        x, y = n.x, n.y
        value = metric_value(n)
        radius = max(10, min(26, int(7 + math.sqrt(max(1, value)) * 2.2)))
        if n is tree.root:
            radius = max(15, radius)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=n.color, outline='white', width=3)
        value_label = format_export_score(value) if metric == 'score' else str(int(round(value)))
        label = f'{n.label} ({value_label})'
        font = root_font if n is tree.root else (node_font if len(n.path) <= 2 else label_font)
        tw = draw.textlength(label, font=font)
        tx = x - tw / 2
        ty = y + radius + 6
        if ty + 30 > height:
            ty = y - radius - 32
        draw.text((tx, ty), label, font=font, fill=(27, 41, 59))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, 'PNG')


def format_export_score(value: object) -> str:
    number = float(value or 0)
    if math.isclose(number, round(number), abs_tol=1e-9):
        return str(int(round(number)))
    return f'{number:.2f}'.rstrip('0').rstrip('.')


def _md_cell(value: object) -> str:
    text = '' if value is None else str(value)
    return text.replace('|', '\\|').replace('\n', '<br>')


def _md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        '| ' + ' | '.join(_md_cell(value) for value in headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
    ]
    for row in rows:
        lines.append('| ' + ' | '.join(_md_cell(value) for value in row) + ' |')
    return '\n'.join(lines)


def _question_tag_paths(question: Question) -> list[tuple[str, ...]]:
    paths = []
    for tag in question.tags or []:
        parts = tuple(part.strip() for part in str(tag).split('/') if part.strip())
        if parts:
            paths.append(parts)
    return paths


def _node_questions(project: ProjectData, node: TreeNode) -> list[Question]:
    target = tuple(node.path)
    if not target:
        return list(project.questions)
    matched = []
    for question in project.questions:
        if any(len(path) >= len(target) and path[:len(target)] == target for path in _question_tag_paths(question)):
            matched.append(question)
    return matched


def _export_node_stats(project: ProjectData, tree: TagTree) -> list[dict]:
    stats = []
    for node in tree.all_nodes():
        if node is tree.root:
            continue
        questions = _node_questions(project, node)
        total_score = sum(float(question.score or 0) for question in questions)
        stats.append({
            'node': node,
            'code': node.code,
            'path': ' / '.join(node.path),
            'hits': node.count,
            'question_count': len(questions),
            'score': total_score,
            'qids': [question.qid for question in questions],
        })
    return stats


def _tree_svg_code(tree: TagTree, color_depth: int = 2) -> str:
    tree.assign_colors(color_depth)
    nodes = tree.all_nodes()
    max_depth = max((len(node.path) for node in nodes), default=1)
    leaves = max(1, tree.leaf_count(tree.root))
    width = max(1500, 320 + max_depth * 260)
    height = max(700, 180 + leaves * 56)
    tree.layout(width, height)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}">',
        '  <style>text { font-family: "Microsoft YaHei", sans-serif; }</style>',
    ]
    for node in nodes:
        for child in node.children:
            color = '#%02x%02x%02x' % child.color
            lines.append(f'  <line x1="{node.x:.1f}" y1="{node.y:.1f}" x2="{child.x:.1f}" y2="{child.y:.1f}" stroke="{color}" stroke-width="3" stroke-linecap="round"/>')
    for node in nodes:
        color = '#%02x%02x%02x' % node.color
        radius = 13 if node is tree.root else 10
        lines.append(f'  <circle cx="{node.x:.1f}" cy="{node.y:.1f}" r="{radius}" fill="{color}" stroke="#fff" stroke-width="2"><title>{html_escape(" / ".join(node.path) if node.path else node.label)}</title></circle>')
        lines.append(f'  <text x="{node.x:.1f}" y="{node.y - radius - 7:.1f}" text-anchor="middle" font-size="18" font-weight="700" fill="#1b3147">{html_escape(node.label)} ({node.count})</text>')
    lines.append('</svg>')
    return ''.join(lines)


def _tree_mermaid_code(tree: TagTree) -> str:
    lines = ['flowchart TD']

    def walk(node: TreeNode):
        node_id = f'T{node.code or "0"}'
        label = f'{node.label}<br/>{node.count}题 / {format_export_score(node.score)}分'
        safe_label = label.replace('"', "'").replace('\n', '<br/>')
        lines.append(f'  {node_id}["{safe_label}"]')
        for child in node.children:
            child_id = f'T{child.code}'
            walk(child)
            lines.append(f'  {node_id} --> {child_id}')

    walk(tree.root)
    return '\n'.join(lines)


def _tree_details_html(tree: TagTree) -> str:
    def render(node: TreeNode, depth: int) -> str:
        indent = '  ' * depth
        summary = f'{html_escape(node.label)} · {node.count}题 / {format_export_score(node.score)}分'
        if not node.children:
            return f'{indent}<li>{summary}</li>'
        children = '\n'.join(render(child, depth + 2) for child in node.children)
        return (
            f'{indent}<li><details open><summary><strong>{summary}</strong></summary>\n'
            f'{indent}  <ul>\n{children}\n{indent}  </ul>\n{indent}</details></li>'
        )

    return '<ul>\n' + render(tree.root, 1) + '\n</ul>'


def build_export_markdown(project: ProjectData, tree: TagTree) -> str:
    stats = _export_node_stats(project, tree)
    stats_by_path = {tuple(item['node'].path): item for item in stats}
    all_nodes = tree.all_nodes()
    total_score = sum(float(question.score or 0) for question in project.questions)
    tagged_questions = sum(1 for question in project.questions if question.tags)
    leaf_tags = sum(1 for node in all_nodes if node is not tree.root and not node.children)

    question_rows = [
        [question.qid, format_export_score(question.score), len(question.tags or []), '<br>'.join(question.tags or [])]
        for question in project.questions
    ]
    hit_rows = [
        [item['code'], item['path'], item['hits'], item['question_count'], format_export_score(item['score']), '<br>'.join(item['qids'])]
        for item in sorted(stats, key=lambda item: (-item['hits'], -item['score'], item['path']))
    ]
    score_rows = [
        [item['path'], format_export_score(item['score']), item['question_count'], format_export_score(item['score'] / item['question_count'] if item['question_count'] else 0)]
        for item in sorted(stats, key=lambda item: (-item['score'], -item['hits'], item['path']))
    ]
    parent_rows = []
    for item in sorted([entry for entry in stats if entry['node'].children], key=lambda entry: (-entry['score'], -entry['hits'], entry['path'])):
        children = item['node'].children
        child_summary = '<br>'.join(
            f'{child.label}: {child.count}题 / {format_export_score(child.score)}分'
            for child in children
        )
        parent_rows.append([
            item['path'],
            item['question_count'],
            format_export_score(item['score']),
            len(children),
            child_summary,
        ])
    top_rows = []
    for child in tree.root.children:
        item = stats_by_path.get(tuple(child.path), {'question_count': 0, 'score': 0})
        top_rows.append([
            child.label,
            child.count,
            item['question_count'],
            format_export_score(item['score']),
            f'{item["score"] / total_score * 100:.1f}%' if total_score else '0.0%',
        ])
    level2_rows = [
        [item['path'], item['hits'], item['question_count'], format_export_score(item['score'])]
        for item in sorted([entry for entry in stats if len(entry['node'].path) == 2], key=lambda entry: (-entry['score'], -entry['hits'], entry['path']))
    ]
    level3_rows = [
        [item['path'], format_export_score(item['score']), item['question_count'], format_export_score(item['score'] / item['question_count'] if item['question_count'] else 0), '<br>'.join(item['qids'])]
        for item in sorted([entry for entry in stats if len(entry['node'].path) == 3], key=lambda entry: (-entry['score'], -entry['hits'], entry['path']))
    ]

    lines = [
        f'# {project.name} · 标签树导出', '',
        f'- 项目版本：`{project.version}`',
        f'- 创建时间：{project.created_at}',
        f'- 原始文件：`{project.source_file}`',
        f'- 已框题目：{len(project.questions)}', '',
        '## 总览统计', '',
        _md_table(
            ['指标', '数值'],
            [
                ['题目总数', len(project.questions)],
                ['已打标题目数', tagged_questions],
                ['已打标题目覆盖率', f'{tagged_questions / len(project.questions) * 100:.1f}%' if project.questions else '0.0%'],
                ['标签节点总数', len(stats)],
                ['叶子标签数', leaf_tags],
                ['全卷总分', format_export_score(total_score)],
            ],
        ), '',
        '## 标签树图形代码', '',
        '### SVG 图形（直接渲染）', '',
        _tree_svg_code(tree, int(project.settings.get('color_depth', 2))),
        '', '',
        '### Mermaid 图形（Obsidian 直接渲染）', '',
        '```mermaid',
        _tree_mermaid_code(tree),
        '```', '',
        '## 可折叠分层标签树', '',
        _tree_details_html(tree), '',
        '## 题目明细', '',
        _md_table(['题目ID', '分值', '标签数', '标签路径'], question_rows), '',
        '## 标签到题目映射（按命中次数降序）', '',
        _md_table(['代码', '标签路径', '命中次数', '关联题目数（去重）', '总分值', '题目ID'], hit_rows), '',
        '## 标签分值排行（按总分值降序）', '',
        _md_table(['标签路径', '总分值', '关联题目数（去重）', '平均分值'], score_rows), '',
        '## 一级分支统计', '',
        _md_table(['一级标签', '命中次数', '关联题目数（去重）', '总分值', '全卷分值占比'], top_rows), '',
        '## 二级分支统计', '',
        _md_table(['二级标签路径', '命中次数', '关联题目数（去重）', '总分值'], level2_rows), '',
        '## 三级分值统计表', '',
        _md_table(['三级标签路径', '总分值', '关联题目数（去重）', '平均分值', '题目ID'], level3_rows), '',
        '## 父级聚类统计', '',
        _md_table(['父级路径', '关联题目数（去重）', '总分值', '直接子节点数', '子节点命中与分值'], parent_rows), '',
        '> 说明：跨分支多标签题会分别计入各一级分支，因此一级分支分值占比之和可能超过 100%。', '',
        '## 分层文本列表', '',
        tree.export_markdown().strip(),
    ]
    return '\n'.join(lines) + '\n'


def export_markdown(project: ProjectData, tree: TagTree, out_path: Path) -> None:
    out_path.write_text(build_export_markdown(project, tree), encoding='utf-8')


def pdf_font_markup(text: str) -> str:
    from xml.sax.saxutils import escape
    s = escape(str(text))
    parts = re.findall(r'[\x00-\x7F]+|[^\x00-\x7F]+', s)
    out = []
    for part in parts:
        if all(ord(ch) < 128 for ch in part):
            out.append(f'<font name="Helvetica">{part}</font>')
        else:
            out.append(f'<font name="STSong-Light">{part}</font>')
    return ''.join(out)


def export_pdf(project: ProjectData, tree: TagTree, tree_count_png: Path, tree_score_png: Path, out_path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    styles = getSampleStyleSheet()
    base = ParagraphStyle('BaseCN', parent=styles['Normal'], fontName='STSong-Light', fontSize=9, leading=14)
    h1 = ParagraphStyle('H1CN', parent=styles['Heading1'], fontName='STSong-Light', fontSize=18, leading=26)
    h2 = ParagraphStyle('H2CN', parent=styles['Heading2'], fontName='STSong-Light', fontSize=13, leading=20)
    h3 = ParagraphStyle('H3CN', parent=styles['Heading3'], fontName='STSong-Light', fontSize=11, leading=17)

    stats = _export_node_stats(project, tree)
    stats_by_path = {tuple(item['node'].path): item for item in stats}
    total_score = sum(float(question.score or 0) for question in project.questions)
    tagged_questions = sum(1 for question in project.questions if question.tags)
    leaf_tags = sum(1 for node in tree.all_nodes() if node is not tree.root and not node.children)

    def paragraph(text: object, style=base):
        text = '' if text is None else str(text)
        return Paragraph(pdf_font_markup(text), style)

    def rich_paragraph(text: object, style=base):
        text = '' if text is None else str(text)
        pieces = text.split('<br/>')
        return Paragraph('<br/>'.join(pdf_font_markup(piece) for piece in pieces), style)

    def make_table(headers: list[str], rows: list[list[object]], widths: list[float]) -> Table:
        data = [[paragraph(header, h3) for header in headers]]
        for row in rows:
            data.append([rich_paragraph(value) for value in row])
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3a5f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cad3df')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return table

    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=14*mm, bottomMargin=14*mm)
    story = [paragraph(f'{project.name} · 标签树导出', h1), Spacer(1, 6*mm)]
    max_w = A4[0] - 28*mm
    max_h = A4[1] - 40*mm
    for title, image_path in [('标签树图形（题数版）', tree_count_png), ('标签树图形（分值版）', tree_score_png)]:
        img = RLImage(str(image_path))
        iw, ih = img.imageWidth, img.imageHeight
        scale = min(max_w / iw, max_h / ih, 1.0)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        story.extend([paragraph(title, h2), img, PageBreak()])

    first_section = True
    def start_section(title: str) -> None:
        nonlocal first_section
        if not first_section:
            story.append(PageBreak())
        first_section = False
        story.append(paragraph(title, h2))

    overview_rows = [
        ['题目总数', len(project.questions)],
        ['已打标题目数', tagged_questions],
        ['已打标题目覆盖率', f'{tagged_questions / len(project.questions) * 100:.1f}%' if project.questions else '0.0%'],
        ['标签节点总数', len(stats)],
        ['叶子标签数', leaf_tags],
        ['全卷总分', format_export_score(total_score)],
    ]
    start_section('总览统计')
    story.extend([make_table(['指标', '数值'], overview_rows, [55*mm, 127*mm]), Spacer(1, 6*mm)])

    question_rows = [
        [question.qid, format_export_score(question.score), len(question.tags or []), '<br/>'.join(question.tags or [])]
        for question in project.questions
    ]
    start_section('题目明细')
    story.extend([make_table(['题目ID', '分值', '标签数', '标签路径'], question_rows, [24*mm, 18*mm, 20*mm, 120*mm]), Spacer(1, 6*mm)])

    hit_rows = [
        [item['code'], item['path'], item['hits'], item['question_count'], format_export_score(item['score']), '<br/>'.join(item['qids'])]
        for item in sorted(stats, key=lambda item: (-item['hits'], -item['score'], item['path']))
    ]
    start_section('标签到题目映射（按命中次数降序）')
    story.extend([make_table(['代码', '标签路径', '命中次数', '去重题数', '总分值', '题目ID'], hit_rows, [18*mm, 46*mm, 20*mm, 22*mm, 22*mm, 54*mm]), Spacer(1, 6*mm)])

    score_rows = [
        [item['path'], format_export_score(item['score']), item['question_count'], format_export_score(item['score'] / item['question_count'] if item['question_count'] else 0)]
        for item in sorted(stats, key=lambda item: (-item['score'], -item['hits'], item['path']))
    ]
    start_section('标签分值排行（按总分值降序）')
    story.extend([make_table(['标签路径', '总分值', '去重题数', '平均分值'], score_rows, [76*mm, 28*mm, 32*mm, 46*mm]), Spacer(1, 6*mm)])

    top_rows = []
    for child in tree.root.children:
        item = stats_by_path.get(tuple(child.path), {'question_count': 0, 'score': 0})
        top_rows.append([
            child.label,
            child.count,
            item['question_count'],
            format_export_score(item['score']),
            f'{item["score"] / total_score * 100:.1f}%' if total_score else '0.0%',
        ])
    start_section('一级分支统计')
    story.extend([make_table(['一级标签', '命中次数', '去重题数', '总分值', '全卷分值占比'], top_rows, [42*mm, 24*mm, 26*mm, 34*mm, 56*mm]), Spacer(1, 6*mm)])

    level2_rows = [
        [item['path'], item['hits'], item['question_count'], format_export_score(item['score'])]
        for item in sorted([entry for entry in stats if len(entry['node'].path) == 2], key=lambda entry: (-entry['score'], -entry['hits'], entry['path']))
    ]
    start_section('二级分支统计')
    story.extend([make_table(['二级标签路径', '命中次数', '去重题数', '总分值'], level2_rows, [70*mm, 28*mm, 32*mm, 52*mm]), Spacer(1, 6*mm)])

    level3_rows = [
        [item['path'], format_export_score(item['score']), item['question_count'], format_export_score(item['score'] / item['question_count'] if item['question_count'] else 0), '<br/>'.join(item['qids'])]
        for item in sorted([entry for entry in stats if len(entry['node'].path) == 3], key=lambda entry: (-entry['score'], -entry['hits'], entry['path']))
    ]
    start_section('三级分值统计表')
    story.extend([make_table(['三级标签路径', '总分值', '去重题数', '平均分值', '题目ID'], level3_rows, [56*mm, 24*mm, 24*mm, 26*mm, 52*mm]), Spacer(1, 6*mm)])

    parent_rows = []
    for item in sorted([entry for entry in stats if entry['node'].children], key=lambda entry: (-entry['score'], -entry['hits'], entry['path'])):
        children = item['node'].children
        child_summary = '<br/>'.join(
            f'{child.label}: {child.count}题 / {format_export_score(child.score)}分'
            for child in children
        )
        parent_rows.append([item['path'], item['question_count'], format_export_score(item['score']), len(children), child_summary])
    start_section('父级聚类统计')
    story.extend([make_table(['父级路径', '去重题数', '总分值', '直接子节点数', '子节点命中与分值'], parent_rows, [52*mm, 24*mm, 24*mm, 28*mm, 54*mm]), Spacer(1, 6*mm)])

    start_section('分层文本列表')

    def add_tree_nodes(node: TreeNode, depth: int):
        if node is not tree.root:
            story.append(paragraph(f'{"　" * depth}{node.label}（{node.count}题 / {format_export_score(node.score)}分）'))
        for child in node.children:
            add_tree_nodes(child, depth + 1)

    add_tree_nodes(tree.root, 0)
    doc.build(story)







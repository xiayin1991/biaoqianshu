# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import mimetypes
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import APP_DIR, PROJECTS_DIR, ProjectData, build_tag_tree, create_project, crop_question, ensure_dir, export_markdown, export_pdf, render_tree_png, tree_to_dict, update_question


class AppService:
    def __init__(self):
        self.project: ProjectData | None = None
        self.lock = threading.RLock()

    def import_files(self, paths: list[str]) -> ProjectData:
        project = create_project([Path(p) for p in paths], PROJECTS_DIR)
        with self.lock:
            self.project = project
        return project

    def open_project(self, project_file: str) -> ProjectData:
        project = ProjectData.load(Path(project_file))
        with self.lock:
            self.project = project
        return project

    def require_project(self) -> ProjectData:
        if not self.project:
            raise ValueError('尚未导入或打开项目')
        return self.project

    def add_tag(self, qid: str, tag: str) -> None:
        tag = '/'.join([p.strip() for p in str(tag).split('/') if p.strip()])
        if not tag:
            return
        with self.lock:
            p = self.require_project()
            q = next((x for x in p.questions if x.qid == qid), None)
            if q is None:
                raise ValueError('找不到题目')
            if tag not in q.tags:
                q.tags.append(tag)
            p.save()

    def remove_tag(self, qid: str, tag: str) -> None:
        with self.lock:
            p = self.require_project()
            q = next((x for x in p.questions if x.qid == qid), None)
            if q is None:
                raise ValueError('找不到题目')
            q.tags = [t for t in q.tags if t != tag]
            p.save()

    def set_description(self, qid: str, description: str) -> None:
        with self.lock:
            p = self.require_project()
            q = next((x for x in p.questions if x.qid == qid), None)
            if q is None:
                raise ValueError('找不到题目')
            q.description = description
            p.save()

    def set_layout(self, left_width: float, preview_height: float) -> None:
        with self.lock:
            p = self.require_project()
            p.settings['left_width'] = max(30, min(75, float(left_width)))
            p.settings['preview_height'] = max(45, min(85, float(preview_height)))
            p.settings['layout_revision'] = 4
            p.save()

    def set_color_depth(self, depth: int) -> None:
        with self.lock:
            p = self.require_project()
            p.settings['color_depth'] = max(1, min(10, int(depth)))
            p.save()

    def crop_question(self, page_index: int, bbox: list[float], question_number: str | None = None, score: float = 0.0) -> None:
        with self.lock:
            p = self.require_project()
            crop_question(p, int(page_index), bbox, question_number, score)
            p.save()

    def update_question(self, qid: str, question_number: str | None = None, score: float | None = None) -> None:
        with self.lock:
            p = self.require_project()
            update_question(p, qid, question_number, score)

    def state_payload(self) -> dict:
        with self.lock:
            if not self.project:
                return {'ok': True, 'has_project': False}
            p = self.project
            tree = build_tag_tree(p)
            tag_assignment_total = sum(len(q.tags or []) for q in p.questions)
            tag_unique_total = len({str(tag).strip() for q in p.questions for tag in (q.tags or []) if str(tag).strip()})
            return {
                'ok': True,
                'has_project': True,
                'project': {
                    'name': p.name,
                    'root': p.root,
                    'source_file': p.source_file,
                    'version': p.version,
                    'created_at': p.created_at,
                    'settings': p.settings,
                },
                'tag_total': tag_assignment_total,
                'tag_assignment_total': tag_assignment_total,
                'tag_unique_total': tag_unique_total,
                'pages': p.pages,
                'questions': [
                    {
                        'qid': q.qid,
                        'index': q.index,
                        'image': q.image,
                        'page': q.page,
                        'description': q.description,
                        'tags': q.tags,
                        'score': q.score,
                    }
                    for q in p.questions
                ],
                'tree': tree_to_dict(tree),
            }

    def export_tree_png(self, out_path: str) -> str:
        paths = self.export_tree_pngs(Path(out_path).parent)
        return paths[0]

    def export_tree_pngs(self, export_dir: Path) -> list[str]:
        with self.lock:
            p = self.require_project()
            export_dir = ensure_dir(Path(export_dir))
            tree = build_tag_tree(p)
            count_path = export_dir / '标签树全图-题数.png'
            score_path = export_dir / '标签树全图-分值.png'
            color_depth = int(p.settings.get('color_depth', 2))
            render_tree_png(tree, count_path, color_depth, metric='count')
            render_tree_png(tree, score_path, color_depth, metric='score')
            return [str(count_path), str(score_path)]

    def export_tree_md(self, out_path: str) -> str:
        with self.lock:
            p = self.require_project()
            tree = build_tag_tree(p)
            export_markdown(p, tree, Path(out_path))
            return out_path

    def export_tree_pdf(self, out_path: str) -> str:
        with self.lock:
            p = self.require_project()
            export_dir = ensure_dir(Path(p.root) / 'exports')
            tree_count_png = export_dir / '标签树全图-题数.png'
            tree_score_png = export_dir / '标签树全图-分值.png'
            tree_md = export_dir / '标签树导出.md'
            tree = build_tag_tree(p)
            color_depth = int(p.settings.get('color_depth', 2))
            render_tree_png(tree, tree_count_png, color_depth, metric='count')
            render_tree_png(tree, tree_score_png, color_depth, metric='score')
            export_markdown(p, tree, tree_md)
            export_pdf(p, tree, tree_count_png, tree_score_png, Path(out_path))
            return out_path


class ApiHandler(BaseHTTPRequestHandler):
    service: AppService = None
    web_root: Path = None

    def log_message(self, fmt, *args):
        return

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/state':
            try:
                self._json(self.service.state_payload())
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
            return
        if parsed.path == '/api/page':
            try:
                page_index = int(parse_qs(parsed.query).get('index', ['0'])[0])
                p = self.service.require_project()
                if page_index < 0 or page_index >= len(p.pages):
                    self.send_error(404)
                    return
                img = Path(p.root) / p.pages[page_index]['image']
                data = img.read_bytes()
                mime = mimetypes.guess_type(str(img))[0] or 'image/png'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(404)
            return
        if parsed.path == '/api/image':
            try:
                qid = parse_qs(parsed.query).get('qid', [''])[0]
                p = self.service.require_project()
                q = next((x for x in p.questions if x.qid == qid), None)
                if not q:
                    self.send_error(404)
                    return
                img = Path(p.root) / q.image
                data = img.read_bytes()
                mime = mimetypes.guess_type(str(img))[0] or 'image/png'
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(404)
            return
        self._serve_static(parsed.path)

    def do_POST(self):
        try:
            data = self._read_json()
            path = urlparse(self.path).path
            if path == '/api/tag/add':
                self.service.add_tag(data.get('qid', ''), data.get('tag', ''))
            elif path == '/api/tag/remove':
                self.service.remove_tag(data.get('qid', ''), data.get('tag', ''))
            elif path == '/api/question/description':
                self.service.set_description(data.get('qid', ''), data.get('description', ''))
            elif path == '/api/settings/color':
                self.service.set_color_depth(int(data.get('depth', 2)))
            elif path == '/api/question/crop':
                self.service.crop_question(int(data.get('page_index', 0)), data.get('bbox', []), data.get('question_number', ''), float(data.get('score', 0)))
            elif path == '/api/question/update':
                raw_score = data.get('score')
                self.service.update_question(data.get('qid', ''), data.get('question_number'), None if raw_score is None else float(raw_score))
            elif path == '/api/settings/layout':
                self.service.set_layout(float(data.get('left_width', 60)), float(data.get('preview_height', 72)))
            else:
                self._json({'ok': False, 'error': '未知接口'}, 404)
                return
            self._json(self.service.state_payload())
        except Exception as e:
            self._json({'ok': False, 'error': str(e)}, 500)

    def _serve_static(self, path: str):
        rel = 'index.html' if path in ('', '/') else path.lstrip('/')
        target = (self.web_root / rel).resolve()
        try:
            target.relative_to(self.web_root.resolve())
        except Exception:
            self.send_error(403)
            return
        if not target.exists() or not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        charset = '; charset=utf-8' if mime.startswith('text/') or 'javascript' in mime else ''
        self.send_response(200)
        self.send_header('Content-Type', mime + charset)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_server(service: AppService, web_root: Path, host: str = '127.0.0.1', port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    ApiHandler.service = service
    ApiHandler.web_root = web_root
    httpd = ThreadingHTTPServer((host, port), ApiHandler)
    actual_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f'http://{host}:{actual_port}'








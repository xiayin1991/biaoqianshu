# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from core import APP_DIR, APP_VERSION, PROJECTS_DIR, ensure_dir
from server import AppService, start_server

try:
    import webview
except Exception:
    webview = None

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None


class NativeBridge:
    def __init__(self, service: AppService):
        self.service = service

    def _dialog_parent(self):
        if tk is None:
            return None
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        return root

    def import_paper(self):
        root = self._dialog_parent()
        if root is None:
            return {'ok': False, 'error': '无法打开文件选择窗口'}
        try:
            paths = filedialog.askopenfilenames(
                parent=root,
                title='导入试卷',
                filetypes=[
                    ('试卷文件', '*.pdf *.docx *.pptx *.png *.jpg *.jpeg *.webp *.bmp'),
                    ('PDF', '*.pdf'),
                    ('Word', '*.docx'),
                    ('PowerPoint', '*.pptx'),
                    ('图片', '*.png *.jpg *.jpeg *.webp *.bmp'),
                    ('所有文件', '*.*'),
                ],
            )
            if not paths:
                return {'ok': False, 'cancelled': True}
            project = self.service.import_files(list(paths))
            return {'ok': True, 'project': project.name, 'state': self.service.state_payload()}
        except Exception as e:
            messagebox.showerror('导入失败', str(e), parent=root)
            return {'ok': False, 'error': str(e)}
        finally:
            root.destroy()

    def open_project(self):
        root = self._dialog_parent()
        if root is None:
            return {'ok': False, 'error': '无法打开文件选择窗口'}
        try:
            ensure_dir(PROJECTS_DIR)
            p = filedialog.askopenfilename(parent=root, title='打开标签树项目', initialdir=str(PROJECTS_DIR), filetypes=[('标签树项目', 'project.json'), ('JSON', '*.json')])
            if not p:
                return {'ok': False, 'cancelled': True}
            self.service.open_project(p)
            return {'ok': True, 'state': self.service.state_payload()}
        except Exception as e:
            messagebox.showerror('打开失败', str(e), parent=root)
            return {'ok': False, 'error': str(e)}
        finally:
            root.destroy()

    def _reveal_path(self, path):
        try:
            subprocess.Popen(['explorer', '/select,', str(Path(path).resolve())])
        except Exception:
            try:
                os.startfile(str(Path(path).resolve().parent))
            except Exception:
                pass

    def _export_auto(self, filename: str, exporter):
        root = self._dialog_parent()
        try:
            project = self.service.require_project()
            out = ensure_dir(Path(project.root) / 'exports') / filename
            exporter(str(out))
            self._reveal_path(out)
            return {'ok': True, 'path': str(out)}
        except Exception as e:
            if root:
                messagebox.showerror('导出失败', str(e), parent=root)
            return {'ok': False, 'error': str(e)}
        finally:
            if root:
                root.destroy()

    def export_png(self):
        root = self._dialog_parent()
        try:
            project = self.service.require_project()
            export_dir = ensure_dir(Path(project.root) / 'exports')
            paths = self.service.export_tree_pngs(export_dir)
            self._reveal_path(paths[0])
            return {'ok': True, 'paths': paths}
        except Exception as e:
            if root:
                messagebox.showerror('导出失败', str(e), parent=root)
            return {'ok': False, 'error': str(e)}
        finally:
            if root:
                root.destroy()

    def export_md(self):
        return self._export_auto('标签树导出.md', self.service.export_tree_md)

    def export_pdf(self):
        return self._export_auto('标签树导出.pdf', self.service.export_tree_pdf)

def run_browser(url: str):
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main():
    service = AppService()
    if '--self-test' in sys.argv:
        resource_root = Path(getattr(sys, '_MEIPASS', APP_DIR))
        web_root = resource_root / 'web'
        httpd, url = start_server(service, web_root)
        import urllib.request
        urllib.request.urlopen(url + '/api/state', timeout=5).read()
        httpd.shutdown()
        return
    web_root = APP_DIR / 'web'
    httpd, url = start_server(service, web_root)
    bridge = NativeBridge(service)
    try:
        if webview is None:
            run_browser(url)
        else:
            webview.create_window(
                f'标签树 v{APP_VERSION}',
                url,
                js_api=bridge,
                width=1500,
                height=950,
                min_size=(1180, 760),
                text_select=True,
            )
            webview.start(debug=False)
    finally:
        httpd.shutdown()


if __name__ == '__main__':
    main()








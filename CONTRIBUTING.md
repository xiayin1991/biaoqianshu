# 开发与发布约定

## 分支与提交

- 主分支：`main`，始终保持可发布状态。
- 功能与修复使用独立分支，完成后合并到 `main`。
- 提交信息建议采用 `feat:`、`fix:`、`docs:`、`chore:` 前缀。
- 不提交 `.venv`、构建目录、运行项目数据、日志或临时文件。

## 版本发布

1. 更新 `src/core.py`、`src/web/index.html`、打包脚本和 README 中的版本号。
2. 完成本地运行、EXE 启动、自检和旧项目迁移验证。
3. 更新 `CHANGELOG.md`，新增 `docs/RELEASE_NOTES_vX.Y.Z.md`。
4. 提交源码与文档，创建对应版本标签。
5. 构建 Windows 便携包，计算 SHA-256。
6. 在 GitHub Releases 创建版本，上传 ZIP 和校验值。
7. 仓库中保留源码、说明和版本记录；安装包作为 Release 附件分发。

## 项目迁移验收

每次涉及项目数据结构或运行目录的改动，至少验证：

- 复制一个旧版本项目文件夹到新版本 `_internal\Projects`。
- 题目、标签、分值和题图均可读取。
- 编辑后能够正常保存。
- `project.json` 中的项目根路径自动更新。

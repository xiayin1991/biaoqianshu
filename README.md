# 标签树

为教研工作设计的试卷框题、分层打标与统计导出工具。把纸质或电子试卷转成可检索、可统计、可持续维护的题目标签数据。

当前稳定版：**v1.7.1**

首发日期：**2026-11-18**

> v1.7.1 是标签树的第一个实测可用版本，也是后续持续迭代的基线版本。

## 下载与运行

1. 前往 [GitHub Releases](https://github.com/xiayin1991/biaoqianshu/releases/tag/v1.7.1) 下载 `biaoqianshu-Portable-v1.7.1.zip`。
2. 解压压缩包。
3. 双击 `标签树.exe` 启动，无需安装。

安装包 SHA-256：

```text
0918292E03FA67A2B9A503AB667D654F49E78C43F7DA87759C122830FC7153BF
```

## 核心能力

- 导入 PDF、DOCX、PPTX、PNG、JPG、JPEG、WEBP、BMP，逐页预览试卷。
- 在页面上拖拽框选题目，录入题号和分值，题号自动查重。
- 题号、分值、标签实时保存，可随时切换已框题目继续编辑。
- 以 `/` 表示标签层级，例如 `平面几何/三角形/面积`。
- 标签输入支持模糊检索：字符不要求位于开头、连续或按原顺序出现。
- 标签树从下向上生长；节点大小和连线粗细反映关联题目的数量。
- 同时显示“标签累计”和“去重标签”两个指标。
- 整卷/单题视图、题数/分值视图可通过滑块切换。
- 导出题数版与分值版 PNG、完整 Markdown 统计报告和整合版 PDF。
- Markdown 包含 SVG、Mermaid、默认展开的折叠标签树、题目明细、标签统计和父级聚合统计。
- 项目保存在本地 `Projects` 文件夹，复制整个项目文件夹即可在后续版本中继续使用。

## 界面与工作流

1. 点击“导入试卷”，创建项目并生成整份试卷的页面预览。
2. 点击“框题”，在页面上拖拽黄色选框，确认题号和分值。
3. 在右下角输入标签；从下拉列表中选择候选标签后按回车或鼠标点击填入。
4. 使用“页”切换原试卷，使用“题”切换已框题目。
5. 在题号或分值文本框内直接修改，修改后自动保存。
6. 按需导出 PNG、Markdown 或 PDF。

## 仓库结构

```text
.
├─ assets/                   早期界面设计参考资料
├─ docs/                     版本说明与开发文档
├─ releases/v1.7.1/          当前版本的说明与校验值
├─ src/                      完整源码、运行脚本和打包脚本
├─ CHANGELOG.md              版本变更记录
├─ CONTRIBUTING.md           后续迭代与发布约定
└─ README.md
```

便携安装包通过 GitHub Releases 发布，不重复提交到 Git 历史，以便后续版本持续迭代时保持仓库轻量。

## 本地开发

环境：Windows、Python 3.11 或更高版本。

```powershell
cd src
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run.ps1
```

重新打包：

```powershell
cd src
.\build_portable.ps1 -PythonExe "python.exe"
```

打包输出：

```text
src\dist-v171\标签树\标签树.exe
src\dist\标签树-Portable-v1.7.1.zip
```

## 项目数据

```text
Projects/<试卷名>_<时间>/
├─ source/         原始试卷
├─ pages/          原试卷逐页预览 PNG
├─ questions/      框选后的题目 PNG
├─ exports/        导出结果
└─ project.json    页码、题目、标签和参数
```

迁移旧项目时，将旧版本 `Projects` 下的整个项目文件夹复制到新版本对应的 `_internal\Projects` 目录。首次打开时，程序会自动更新项目根路径。

## 版本约定

- 版本号采用 `主版本.次版本.修订号`。
- `v1.7.1` 固定作为首个实测可用版本。
- 后续版本更新源码、变更记录和文档，并将安装包作为新的 GitHub Release 附件发布。
- 详细流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 已知边界

- 当前正式流程采用人工框题，优先保证扫描版试卷和复杂版式的稳定性。
- DOCX/PPTX 会转换为整页预览，复杂公式或版式可能无法完全还原。
- PDF 自动切题仍属于后续能力，不影响人工框题和打标主流程。

更完整的功能说明见 [src/README.md](src/README.md) 和 [v1.7.1 版本说明](docs/RELEASE_NOTES_v1.7.1.md)。

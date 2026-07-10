# Maya 资产引用路径批量转换工具

这个工具用于批量修改 Maya ASCII（`.ma`）文件头部的资产引用路径。

它会先扫描服务器文件，生成本地 JSON 查找表；之后转换 `.ma` 文件时只读取查找表，不再搜索服务器。

## 目录结构

```text
maya_path_trans/
├── README.md
├── data/
│   ├── server_files.json
│   └── ma_file.json
├── ori/
│   └── 放入需要转换的原始 .ma 文件
├── output/
│   └── 转换后的 .ma 文件
└── python_script/
    └── maya_path_rewriter.py
```

整个项目使用相对目录。可以直接复制 `maya_path_trans` 文件夹到其他电脑运行。

## 环境要求

- Python 3.10 或更高版本
- 不需要安装第三方 Python 库
- 扫描查找表时，需要当前电脑能够读取服务器目录
- 转换 `.ma` 文件时，不需要连接服务器，只需要 `data/ma_file.json`

## 修改服务器路径

打开：

```text
python_script/maya_path_rewriter.py
```

在脚本顶部找到“用户配置区”：

```python
SERVER_SCAN_ROOT = r"/Volumes/projects/JDZ/VFX/Assets/CGassets"
WINDOWS_TARGET_ROOT = r"P:\JDZ\VFX\Assets\CGassets"
REFERENCE_DEFER_VALUE = 0
PREFERRED_REFERENCE_FOLDERS = ("Publish", "Approve")

DATA_FOLDER = "data"
INPUT_FOLDER = "ori"
OUTPUT_FOLDER = "output"
FULL_TABLE_FILENAME = "server_files.json"
MA_TABLE_FILENAME = "ma_file.json"
```

### `SERVER_SCAN_ROOT`

当前电脑实际访问服务器文件的路径。

macOS 示例：

```python
SERVER_SCAN_ROOT = r"/Volumes/projects/JDZ/VFX/Assets/CGassets"
```

Windows 示例：

```python
SERVER_SCAN_ROOT = r"P:\JDZ\VFX\Assets\CGassets"
```

### `WINDOWS_TARGET_ROOT`

最终写入查找表和 Maya 引用中的 Windows 根路径：

```python
WINDOWS_TARGET_ROOT = r"P:\JDZ\VFX\Assets\CGassets"
```

脚本会自动转换为 Maya 使用的正斜杠格式：

```text
P:/JDZ/VFX/Assets/CGassets/...
```

### `REFERENCE_DEFER_VALUE`

控制实际 `file -r` 引用命令中的 `-dr` 参数：

```python
REFERENCE_DEFER_VALUE = 0
```

- `0`：把已有的 `-dr 1` 改为 `-dr 0`，打开 Maya 时自动加载引用。
- `1`：把已有的 `-dr 0` 改为 `-dr 1`，打开 Maya 时延迟加载引用。
- `None`：完全保留原始 `.ma` 文件中的 `-dr` 设置。

推荐配置：

```python
REFERENCE_DEFER_VALUE = 0
```

脚本只修改实际的 `file -r` 引用命令，不会修改 `file -rdi` 信息记录。
原本没有 `-dr` 参数的引用会保持不变；Maya 默认会自动加载这类引用。

### `PREFERRED_REFERENCE_FOLDERS`

同名文件的父目录得分仍然并列时，按这里的顺序选择发布目录：

```python
PREFERRED_REFERENCE_FOLDERS = ("Publish", "Approve")
```

默认规则：

1. 优先选择唯一的 `Publish` 文件。
2. 没有 `Publish` 候选时，选择唯一的 `Approve` 文件。
3. 首选目录中仍有多个候选时，保留原路径并报告冲突。

目录名匹配不区分大小写，可以根据其他项目的目录规范修改这个元组。

## 第一步：生成查找表

在项目根目录运行。

macOS：

```bash
python3 python_script/maya_path_rewriter.py scan-server
```

Windows：

```bat
python python_script\maya_path_rewriter.py scan-server
```

该命令只读取服务器目录和文件元数据，不读取资产文件内容，也不会修改服务器。

它会生成：

```text
data/server_files.json
data/ma_file.json
```

- `server_files.json`：服务器中的完整文件列表。
- `ma_file.json`：只包含 `.ma` 文件，默认用于路径替换。

建议每次批量转换前重新运行一次 `scan-server`，确保查找表是最新的。

## 第二步：放入原始 Maya 文件

把需要转换的 `.ma` 文件放入：

```text
ori/
```

支持子目录。例如：

```text
ori/
├── seq01/shot010.ma
└── seq02/shot020.ma
```

脚本会递归扫描所有 `.ma` 文件，并在 `output/` 中保留相同的相对目录结构。

原始 `ori/` 文件永远不会被覆盖。

## 第三步：批处理预览

正式转换前建议先预览：

macOS：

```bash
python3 python_script/maya_path_rewriter.py batch --dry-run
```

Windows：

```bat
python python_script\maya_path_rewriter.py batch --dry-run
```

预览会打印每个文件的详细信息：

- 找到多少条引用路径
- 替换了多少条
- 缺失多少条
- 冲突多少条
- 每一条旧路径和新路径
- 路径出现次数和所在行号
- 缺失或冲突时为什么保留原路径
- `-dr 1` 和 `-dr 0` 的修改数量与所在行号

`--dry-run` 不会生成或修改任何 `.ma` 文件。

## 第四步：正式批量转换

macOS：

```bash
python3 python_script/maya_path_rewriter.py batch
```

Windows：

```bat
python python_script\maya_path_rewriter.py batch
```

转换后的文件会写入：

```text
output/
```

再次运行时，同名输出文件会被安全更新，但不会修改 `ori/` 原文件。

## 单文件转换

macOS：

```bash
python3 python_script/maya_path_rewriter.py rewrite ori/example.ma
```

Windows：

```bat
python python_script\maya_path_rewriter.py rewrite ori\example.ma
```

默认输出到：

```text
output/example.ma
```

单文件预览：

```bash
python3 python_script/maya_path_rewriter.py rewrite ori/example.ma --dry-run
```

## 处理规则

1. 只处理 `.ma` 引用路径。
2. 只解析 Maya 文件头部引用区域，后续场景正文不解析。
3. 场景正文以原始二进制字节复制，避免大型文件被整体解码。
4. 按不区分大小写的文件名查找目标文件。
5. 同名文件优先使用父目录尾部与旧路径最接近的候选。
6. 最高分候选仍并列时，按照 `PREFERRED_REFERENCE_FOLDERS` 依次选择，默认优先 `Publish`，其次 `Approve`。
7. 找不到文件时，保留原路径并打印“缺失”。
8. 仍然无法唯一确认时，保留原路径并打印候选列表。
9. 根据 `REFERENCE_DEFER_VALUE` 修改实际引用命令的延迟加载状态。
10. `file -rdi` 信息记录不会被加载状态规则修改。
11. `.DS_Store` 和 `Thumbs.db` 不会写入查找表。

## `data`、`ori` 和 `output` 的用途

### `data/`

保存服务器扫描结果。

可以把已经生成的 `data/ma_file.json` 一起复制到没有服务器访问权限的电脑，然后直接执行路径转换。

### `ori/`

保存原始 `.ma` 文件。

脚本只读取这个目录，不会覆盖其中的文件。

### `output/`

保存转换后的 `.ma` 文件。

建议先在 Maya 中测试 `output/` 文件，确认引用加载正确后，再用于正式工作。

## 安全说明

- `scan-server` 只读取服务器目录。
- 转换阶段只读取本地 JSON 查找表。
- 不会修改服务器上的任何文件。
- 不会覆盖 `ori/` 原文件。
- 输出路径不能设置在服务器资产目录中。
- 单个文件转换失败时，批处理会继续处理其他文件，并在最后打印失败信息。

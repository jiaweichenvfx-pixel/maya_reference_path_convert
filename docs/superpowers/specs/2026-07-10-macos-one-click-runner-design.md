# macOS 双一键入口设计

## 目标

在项目根目录保留两个 `.command` 入口：

- `一键更新查找表.command`：无需输入 `python3 ... scan-server`，即可只读扫描服务器并更新 `data/` 查找表。
- `一键更新ma文件路径.command`：无需输入 `python3 ... batch`，即可批量处理 `ori/` 中的 `.ma` 文件，并把结果写入 `output/`。

## 行为

1. 根据 `.command` 文件自身位置定位项目根目录，不依赖终端当前目录。
2. 检查系统是否存在 `python3`。
3. 分别调用 `python_script/maya_path_rewriter.py scan-server` 或 `python_script/maya_path_rewriter.py batch`。
4. 完整保留现有中文逐文件报告、缺失报告和冲突报告。
5. 转换成功或失败后显示退出状态，并等待用户按回车，避免双击运行后窗口立即关闭。

## 边界

- 不修改 Python 脚本现有命令行结构。
- 不修改 `ori/` 原始文件。
- 不自动扫描服务器；继续使用现有 `data/ma_file.json`。
- 不清空已有 `output/` 文件。

## 验证

- 从项目目录之外启动，确认仍能正确定位脚本。
- 确认命令实际执行批处理模式。
- 确认失败时返回非零状态并保留提示窗口。
- 确认入口文件具有 macOS 可执行权限。

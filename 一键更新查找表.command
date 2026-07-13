#!/bin/zsh

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/python_script/maya_path_rewriter.py"

echo "Maya 资产查找表更新"
echo "项目目录: $SCRIPT_DIR"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[失败] 未找到 python3，请先安装 Python 3.10 或更高版本。"
    echo
    read -r "REPLY?按回车关闭窗口..."
    exit 1
fi

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "[失败] 找不到转换脚本: $PYTHON_SCRIPT"
    echo
    read -r "REPLY?按回车关闭窗口..."
    exit 1
fi

python3 "$PYTHON_SCRIPT" scan-server
exit_code=$?

echo
if [[ $exit_code -eq 0 ]]; then
    echo "查找表更新完成，结果已写入 data 文件夹。"
else
    echo "[失败] 查找表更新程序退出，状态码: $exit_code"
fi

read -r "REPLY?按回车关闭窗口..."
exit $exit_code

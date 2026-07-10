# macOS One-Click Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS double-click entry point that runs the existing Maya batch conversion and keeps the result visible.

**Architecture:** A small root-level zsh `.command` wrapper resolves the project directory from its own location, validates `python3` and the converter script, invokes the existing `batch` command, then pauses before closing. The Python conversion logic remains unchanged.

**Tech Stack:** zsh, Python 3, Markdown

---

### Task 1: Add the macOS one-click runner

**Files:**
- Create: `一键转换.command`

- [ ] **Step 1: Verify the runner does not exist yet**

Run:

```bash
test ! -e "一键转换.command"
```

Expected: exit code `0`.

- [ ] **Step 2: Create the runner**

Create `一键转换.command` with:

```zsh
#!/bin/zsh

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/python_script/maya_path_rewriter.py"

echo "Maya 资产引用路径批量转换"
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

python3 "$PYTHON_SCRIPT" batch
exit_code=$?

echo
if [[ $exit_code -eq 0 ]]; then
    echo "转换完成，结果已写入 output 文件夹。"
else
    echo "[失败] 转换程序退出，状态码: $exit_code"
fi
read -r "REPLY?按回车关闭窗口..."
exit $exit_code
```

- [ ] **Step 3: Make the runner executable**

Run:

```bash
chmod +x "一键转换.command"
```

Expected: `test -x "一键转换.command"` exits with code `0`.

- [ ] **Step 4: Validate zsh syntax**

Run:

```bash
zsh -n "一键转换.command"
```

Expected: exit code `0` with no output.

### Task 2: Document one-click usage

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a macOS one-click section**

Add instructions explaining:

```text
1. Put source .ma files in ori/.
2. Double-click 一键转换.command.
3. Review the Chinese conversion report in Terminal.
4. Press Enter to close the window.
5. Find converted files in output/.
```

Also document that macOS may require Control-clicking the file and choosing “Open” the first time.

- [ ] **Step 2: Check documentation formatting**

Run:

```bash
git diff --check
```

Expected: exit code `0`.

### Task 3: Verify the complete entry point

**Files:**
- Verify: `一键转换.command`
- Verify: `python_script/maya_path_rewriter.py`
- Verify: `README.md`

- [ ] **Step 1: Verify the Python entry point**

Run:

```bash
python3 python_script/maya_path_rewriter.py batch --dry-run
```

Expected: the converter finds `.ma` files under `ori/`, prints per-file Chinese reports, and ends with `试运行完成：没有写入任何文件`.

- [ ] **Step 2: Verify permissions and referenced paths**

Run:

```bash
test -x "一键转换.command"
rg -n 'python3 "\$PYTHON_SCRIPT" batch|按回车关闭窗口' "一键转换.command"
```

Expected: both checks succeed and the two key runner behaviors are present.

- [ ] **Step 3: Commit the implementation**

Run:

```bash
git add "一键转换.command" README.md docs/superpowers/plans/2026-07-10-macos-one-click-runner.md
git commit -m "feat: add macOS one-click converter"
```

Expected: a commit containing the executable runner, documentation, and implementation plan.

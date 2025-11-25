import os
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def search_codebase(query: str) -> str:
    """在项目中进行简单文本搜索（最多返回前 10 行）"""
    if not isinstance(query, str) or not query.strip():
        return "No matches found."
    cmd = [
        "grep", "-rn",
        "--exclude-dir=node_modules",
        "--exclude-dir=.git",
        "--exclude-dir=dist",
        "--exclude=*.json",
        query, PROJECT_ROOT
    ]
    try:
        result = subprocess.check_output(cmd, text=True)
        lines = result.splitlines()[:10]
        return "\n".join(lines) if lines else "No matches found."
    except Exception:
        return "No matches found."

def list_files(directory: str = "") -> str:
    """列出指定目录的文件与子目录（最多 20 条）"""
    target_path = os.path.join(PROJECT_ROOT, directory)
    if not os.path.exists(target_path):
        return "Directory does not exist."
    try:
        items = os.listdir(target_path)
        items = [i for i in items if not i.startswith('.') and i != 'node_modules']
        return "\n".join(items[:20])
    except Exception as e:
        return str(e)

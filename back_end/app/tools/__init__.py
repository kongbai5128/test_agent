"""
导入所有工具模块以触发注册。
在此处 import 是必须的——模块级代码执行时会调用 register()。
"""
from . import calculator, search, weather, todo, read_docs, memory  # noqa: F401
from .registry import all_tools, execute, get_tool, register, to_openai_tools, ToolSpec  # noqa: F401

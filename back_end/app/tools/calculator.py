"""
calculator 工具 — 使用 AST 安全求值，避免 eval() 注入风险。
支持：加减乘除、幂运算、取模、整除、负号、括号、整数和浮点数。
"""
from __future__ import annotations

import ast
import operator

from .registry import ToolSpec, register

_BINOPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_UNOPS: dict = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"不支持的字面量类型: {type(node.value).__name__}")
        return node.value
    if isinstance(node, ast.BinOp):
        op_fn = _BINOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _UNOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    raise ValueError(f"不支持的表达式节点: {type(node).__name__}")


def _calculate(params: dict) -> str:
    expression: str = params.get("expression", "").strip()
    if not expression:
        return "错误：表达式不能为空"
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        # 整数结果不显示小数点
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"计算结果：{expression} = {result}"
    except ZeroDivisionError:
        return "错误：除数不能为零"
    except SyntaxError:
        return f"错误：表达式语法有误 → {expression}"
    except Exception as exc:
        return f"计算错误：{exc}"


register(
    ToolSpec(
        name="calculator",
        description=(
            "执行数学计算。支持加(+)、减(-)、乘(*)、除(/)、幂(**或^)、"
            "取模(%)、整除(//)及括号。输入一个数学表达式字符串。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "要计算的数学表达式，例如：'2 + 3 * 4'、"
                        "'(10 - 2) / 4'、'2 ** 10'、'17 % 5'"
                    ),
                }
            },
            "required": ["expression"],
        },
        handler=_calculate,
    )
)

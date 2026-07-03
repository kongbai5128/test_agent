"""
search 工具 — 模拟网络搜索，返回带标题、URL、摘要的搜索结果。
生产环境可替换为真实的搜索 API（Serper、Tavily 等）。
"""
from __future__ import annotations

from .registry import ToolSpec, register

# 模拟知识库：关键词 → 结果列表
_KNOWLEDGE_BASE: dict[str, list[dict]] = {
    "python": [
        {
            "title": "Python 官方文档",
            "url": "https://docs.python.org/zh-cn/3/",
            "snippet": "Python 是一种解释型、交互式、面向对象的编程语言，以代码可读性和简洁语法著称。",
        },
        {
            "title": "Python 教程 - 菜鸟教程",
            "url": "https://www.runoob.com/python3/python3-tutorial.html",
            "snippet": "Python3 基础教程，包含变量、控制流、函数、类、模块和文件操作等内容。",
        },
    ],
    "fastapi": [
        {
            "title": "FastAPI 官方文档",
            "url": "https://fastapi.tiangolo.com/zh/",
            "snippet": "FastAPI 是一个现代、高性能的 Python Web 框架，基于标准 Python 类型提示，自动生成 OpenAPI 文档。",
        },
        {
            "title": "FastAPI 入门教程",
            "url": "https://fastapi.tiangolo.com/zh/tutorial/",
            "snippet": "FastAPI 教程：路由、请求体、依赖注入、中间件、WebSocket、部署等完整指南。",
        },
    ],
    "vue": [
        {
            "title": "Vue.js 官方文档",
            "url": "https://cn.vuejs.org/",
            "snippet": "Vue.js 是一款用于构建用户界面的渐进式 JavaScript 框架，提供响应式数据绑定和组件化开发模式。",
        },
        {
            "title": "Vue 3 Composition API 指南",
            "url": "https://cn.vuejs.org/guide/extras/composition-api-faq.html",
            "snippet": "Composition API 是 Vue 3 的核心特性，使用 setup() 函数组织逻辑，提升代码复用性。",
        },
    ],
    "agent": [
        {
            "title": "LLM Agent 架构综述",
            "url": "https://lilianweng.github.io/posts/2023-06-23-agent/",
            "snippet": "LLM Agent 由规划（Planning）、记忆（Memory）和工具调用（Tool Use）三部分组成，能够自主完成复杂任务。",
        },
        {
            "title": "ReAct: 推理与行动的结合",
            "url": "https://arxiv.org/abs/2210.03629",
            "snippet": "ReAct 框架让 LLM 交替进行推理（Reasoning）和行动（Acting），显著提升工具调用的准确率。",
        },
    ],
    "deepseek": [
        {
            "title": "DeepSeek API 文档",
            "url": "https://platform.deepseek.com/api-docs/",
            "snippet": "DeepSeek 提供兼容 OpenAI 格式的 API，支持 deepseek-chat 和 deepseek-reasoner 模型。",
        },
    ],
    "天气": [
        {
            "title": "中国气象局天气预报",
            "url": "https://www.nmc.cn/",
            "snippet": "中国气象局官网提供全国各地区的实时天气、预报和气象数据。",
        },
    ],
    "待办": [
        {
            "title": "GTD 时间管理方法",
            "url": "https://gettingthingsdone.com/",
            "snippet": "Getting Things Done（GTD）是由 David Allen 提出的时间管理方法，通过捕捉、处理、组织任务提升效率。",
        },
    ],
}


def _search(params: dict) -> str:
    query: str = params.get("query", "").strip()
    num_results: int = min(params.get("num_results", 3), 5)

    if not query:
        return "错误：搜索关键词不能为空"

    # 模糊匹配知识库
    query_lower = query.lower()
    matched: list[dict] = []
    for keyword, items in _KNOWLEDGE_BASE.items():
        if keyword in query_lower or query_lower in keyword:
            matched.extend(items)

    # 去重（按 url）
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in matched:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduped.append(item)

    results = deduped[:num_results]

    # 若无匹配，返回通用结果
    if not results:
        results = [
            {
                "title": f"关于「{query}」的搜索结果",
                "url": f"https://www.baidu.com/s?wd={query}",
                "snippet": f"暂无关于「{query}」的本地知识，建议访问搜索引擎获取最新信息。",
            }
        ]

    lines = [f"搜索「{query}」的结果（共 {len(results)} 条）：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        lines.append(f"   链接：{r['url']}")
        lines.append(f"   摘要：{r['snippet']}")
        lines.append("")

    return "\n".join(lines).rstrip()


register(
    ToolSpec(
        name="search",
        description=(
            "搜索互联网信息（模拟数据）。返回相关网页的标题、URL 和内容摘要。"
            "适用于查找技术文档、资讯、定义等信息。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题，例如：'Python asyncio 教程'",
                },
                "num_results": {
                    "type": "integer",
                    "description": "返回结果数量，默认 3，最多 5",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
        handler=_search,
    )
)

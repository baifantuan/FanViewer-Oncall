"""知识检索工具 — 两阶段检索（粗检索 + 精排）

阶段1: Milvus 向量相似度粗检索 → Top-N (默认 rag_coarse_k=15)
阶段2: DashScope gte-rerank 精排 → Top-M (默认 rag_fine_k=4)

每个关键节点均有日志输出，方便调试确认机制生效。
"""

from typing import List, Tuple

from langchain_core.documents import Document
from langchain_core.tools import tool
from loguru import logger

from app.config import config
from app.services.vector_store_manager import vector_store_manager
from app.services.reranker_service import rerank_documents


@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> Tuple[str, List[Document]]:
    """从知识库中检索相关信息来回答问题（两阶段检索）

    当用户的问题涉及专业知识、文档内容或需要参考资料时，使用此工具。

    Args:
        query: 用户的问题或查询

    Returns:
        Tuple[str, List[Document]]: (格式化的上下文文本, 精排后的文档列表)
    """
    try:
        logger.info("=" * 60)
        logger.info(f"[RAG] 两阶段检索开始 | query='{query[:120]}{'...' if len(query) > 120 else ''}'")
        logger.info(f"[RAG] 配置: coarse_k={config.rag_coarse_k}, fine_k={config.rag_fine_k}, rerank_model={config.rerank_model}")

        # ═══════════════════════════════════════════════════
        # 阶段 1: 粗检索 — Milvus 向量相似度
        # ═══════════════════════════════════════════════════
        vector_store = vector_store_manager.get_vector_store()

        logger.info(f"[RAG] 阶段1-粗检索: 从 Milvus 检索 top-{config.rag_coarse_k} ...")
        retriever = vector_store.as_retriever(
            search_kwargs={"k": config.rag_coarse_k}
        )
        coarse_docs = retriever.invoke(query)

        if not coarse_docs:
            logger.warning("[RAG] 阶段1-粗检索: 未检索到任何文档，返回空")
            return "没有找到相关信息。", []

        logger.info(
            f"[RAG] 阶段1-粗检索: 返回 {len(coarse_docs)} 条文档 | "
            f"来源: {_summarize_sources(coarse_docs)}"
        )
        for i, doc in enumerate(coarse_docs):
            src = doc.metadata.get("_file_name", "?")
            preview = doc.page_content[:80].replace("\n", " ")
            logger.debug(f"[RAG]   粗排[{i}] | src={src} | {preview}...")

        # ═══════════════════════════════════════════════════
        # 阶段 2: 精排 — DashScope gte-rerank
        # ═══════════════════════════════════════════════════
        logger.info(
            f"[RAG] 阶段2-精排: 从 {len(coarse_docs)} 条中重排序 → top-{config.rag_fine_k}"
        )
        fine_docs = rerank_documents(
            query=query,
            docs=coarse_docs,
            top_n=config.rag_fine_k,
        )

        if not fine_docs:
            logger.warning("[RAG] 阶段2-精排: 结果为空，回退粗检索前几条")
            fine_docs = coarse_docs[: config.rag_fine_k]

        logger.info(
            f"[RAG] 阶段2-精排: 最终返回 {len(fine_docs)} 条文档 | "
            f"来源: {_summarize_sources(fine_docs)}"
        )

        # ═══════════════════════════════════════════════════
        # 格式化输出
        # ═══════════════════════════════════════════════════
        context = format_docs(fine_docs)
        logger.info(f"[RAG] 检索完成 | 最终文档数={len(fine_docs)}")
        logger.info("=" * 60)

        return context, fine_docs

    except Exception as e:
        logger.error(f"[RAG] 两阶段检索失败: {type(e).__name__}: {e}")
        return f"检索知识时发生错误: {str(e)}", []


def _summarize_sources(docs: List[Document]) -> str:
    """提取文档来源摘要（去重）"""
    sources = list(dict.fromkeys(
        d.metadata.get("_file_name", "?") for d in docs
    ))
    if len(sources) <= 3:
        return ", ".join(sources)
    return f"{sources[0]}, {sources[1]}, ...共 {len(sources)} 个文件"


def format_docs(docs: List[Document]) -> str:
    """格式化文档列表为上下文文本"""
    formatted_parts = []

    for i, doc in enumerate(docs, 1):
        metadata = doc.metadata
        source = metadata.get("_file_name", "未知来源")

        # 提取标题信息
        headers = []
        for key in ["h1", "h2", "h3"]:
            if key in metadata and metadata[key]:
                headers.append(metadata[key])

        header_str = " > ".join(headers) if headers else ""
        formatted = f"【参考资料 {i}】"
        if header_str:
            formatted += f"\n标题: {header_str}"
        formatted += f"\n来源: {source}"
        formatted += f"\n内容:\n{doc.page_content}\n"

        formatted_parts.append(formatted)

    return "\n".join(formatted_parts)

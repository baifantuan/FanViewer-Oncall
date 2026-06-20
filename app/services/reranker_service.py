"""精排服务 — 使用 DashScope Rerank API 对粗检索结果进行重排序

二阶段检索流程:
  阶段1 (粗检索): Milvus 向量相似度 → Top-N (默认 N=15)
  阶段2 (精排):   DashScope gte-rerank → Top-K (默认 K=4)

依赖:
  - dashscope.TextReRank
  - app.config 中的 rerank_model / rag_fine_k
"""

from typing import List

from dashscope import TextReRank
from langchain_core.documents import Document
from loguru import logger

from app.config import config


def rerank_documents(
    query: str,
    docs: List[Document],
    top_n: int | None = None,
    model: str | None = None,
) -> List[Document]:
    """对粗检索文档列表进行精排，返回 top-N。

    内部调用 DashScope TextReRank API；失败时回退到原始顺序并截断。

    Args:
        query: 用户原始查询
        docs: 粗检索返回的文档列表（需 ≥1 条）
        top_n: 精排后保留数，默认取 config.rag_fine_k
        model: 精排模型，默认取 config.rerank_model

    Returns:
        List[Document]: 精排后的文档，按相关性从高到低排列
    """
    top_n = top_n or config.rag_fine_k
    model = model or config.rerank_model

    if not docs:
        logger.warning("[Rerank] 粗检索结果为空，跳过精排")
        return []

    if len(docs) <= top_n:
        logger.info(
            f"[Rerank] 粗检索结果 ({len(docs)}) ≤ 精排目标 ({top_n})，跳过 API 调用"
        )
        return docs

    logger.info(
        f"[Rerank] 开始精排 | model={model} | "
        f"query='{query[:80]}{'...' if len(query) > 80 else ''}' | "
        f"candidates={len(docs)} → top_n={top_n}"
    )

    try:
        # 提取文档文本（DashScope 需要 List[str]）
        doc_texts = [d.page_content for d in docs]

        logger.debug(f"[Rerank] 调用 DashScope TextReRank API | model={model}")
        response = TextReRank.call(
            model=model,
            query=query,
            documents=doc_texts,
            top_n=top_n,
            return_documents=False,
            api_key=config.dashscope_api_key,
        )

        # 检查响应状态
        if response.status_code != 200:
            logger.error(
                f"[Rerank] API 返回失败 | status={response.status_code} "
                f"code={response.code} message={response.message}"
            )
            return _fallback(docs, top_n)

        # 按 relevance_score 从高到低重排
        ranked_results = response.output.results
        if not ranked_results:
            logger.warning("[Rerank] API 返回空结果，回退原始顺序")
            return _fallback(docs, top_n)

        reranked: List[Document] = []
        score_log_parts: List[str] = []
        for item in ranked_results:
            idx = item.index
            score = item.relevance_score
            reranked.append(docs[idx])
            score_log_parts.append(f"[{idx}]{score:.4f}")

        logger.info(
            f"[Rerank] 精排完成 | top-{len(reranked)} | 得分: {' > '.join(score_log_parts)}"
        )

        # 输出每条精排结果的摘要，方便 debug
        for rank, doc in enumerate(reranked, 1):
            source = doc.metadata.get("_file_name", "?")
            preview = doc.page_content[:100].replace("\n", " ")
            logger.debug(
                f"[Rerank]   #{rank} | source={source} | preview={preview}..."
            )

        return reranked

    except Exception as e:
        logger.error(f"[Rerank] 精排异常: {type(e).__name__}: {e} | 回退原始顺序")
        return _fallback(docs, top_n)


def _fallback(docs: List[Document], top_n: int) -> List[Document]:
    """精排失败时的回退策略：保持粗检索顺序，直接截断。"""
    logger.info(f"[Rerank] 回退: 保留粗检索前 {min(top_n, len(docs))} 条")
    return docs[:top_n]

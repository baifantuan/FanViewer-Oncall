"""测试两阶段检索 — qwen3-vl-rerank"""

from app.tools.knowledge_tool import retrieve_knowledge

query = "Prometheus 告警如何配置"
print("=" * 60)
print(f"Query: {query}")
print("=" * 60)

result = retrieve_knowledge.invoke({"query": query})

if isinstance(result, tuple):
    context, docs = result
else:
    context = result
    docs = []

print(f"\n最终: docs={len(docs)} | context_len={len(context)} chars")
for i, d in enumerate(docs, 1):
    src = d.metadata.get("_file_name", "?")
    preview = d.page_content[:100].replace("\n", " ")
    print(f"  [{i}] {src}")
    print(f"      {preview}...")
print()

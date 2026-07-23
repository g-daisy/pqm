"""Text-to-SQL service: generate → validate → execute."""
import asyncio
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.models.llm import create_chat_llm
from app.db.connection import fetch_all
from app.memory.short_term_memory import session_memory
from app.db.sql_validator import SQLValidator, SQLValidationError
from app.db.schema_loader import schema_loader
from app.utils.logger import get_logger

logger = get_logger(__name__)

_validator = SQLValidator()
_DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "documents"

# 进程级 schema 缓存
_schema_cache: dict = {}


def _get_schema_context() -> tuple[str, str]:
    if not _schema_cache:
        _schema_cache["schema"] = schema_loader.generate_schema_context()
        _schema_cache["synonyms"] = schema_loader.generate_synonym_context()
    return _schema_cache["schema"], _schema_cache["synonyms"]


SQL_GENERATION_PROMPT = """你是热压品质异常预测系统的 SQL 生成专家。

【数据库 Schema】
{schema_context}

【字段同义词映射】
{synonym_context}

【重要规则】
1. 只生成 SELECT 语句，禁止生成 INSERT/UPDATE/DELETE/DROP
2. 只有一张表: sip_records，禁止使用其他表名，禁止使用 JOIN
3. 字段名必须与 Schema 中完全一致
4. 字符串值用单引号包裹，如: customer = '比亚迪'
5. specification、inspection_method、inspection_frequency 均为 TEXT 普通字段，直接用 LIKE 查询
6. LIMIT 默认 100，最大不超过 100
7. 每次查询必须在 SELECT 中包含 document_id 字段，用于拼接 PDF 链接
8. 当用户提到工序名称，必须加 WHERE process = '工序名'，完整映射如下：
   - "来料" / "来料检验" / "IQC"  → process = '来料'
   - "热压" / "热压工序"          → process = '热压'
   - "镭射"                       → process = '镭射'
   - "落料"                       → process = '落料'
   - "抛丸"                       → process = '抛丸'
   - "全检"                       → process = '全检'
   - "出货" / "出货检验" / "OQC"  → process = '出货'
   - "冷冲"                       → process = '冷冲'
9. 【去重规则 - 必须遵守】当用户询问检验标准/要求/规范时，
   必须使用 DISTINCT ON (customer, part_name, process, inspection_item)
   并搭配 ORDER BY customer, part_name, process, inspection_item, version DESC
   以确保同一客户+零件+工序+检验项只返回最新版本的一条记录。
   这是默认行为，除非用户明确要求查看所有版本或所有文件。

【标准查询模板（询问标准/要求时使用）】
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    specification, inspection_method, inspection_frequency,
    version, document_id
FROM sip_records
WHERE <条件>
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100

【示例】
用户问题: 比亚迪前横梁的检查标准是什么？
SQL:
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    specification, inspection_method, inspection_frequency,
    version, document_id
FROM sip_records
WHERE customer = '比亚迪'
  AND part_name LIKE '%前横梁%'
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100

用户问题: 比亚迪前横梁来料外观检测标准是什么？
SQL:
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    specification, inspection_method, inspection_frequency,
    version, document_id
FROM sip_records
WHERE customer = '比亚迪'
  AND part_name LIKE '%前横梁%'
  AND process = '来料'
  AND inspection_item LIKE '%外观%'
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100

用户问题: 热压工序的检验项有哪些？
SQL:
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    specification, inspection_method, document_id
FROM sip_records
WHERE process = '热压'
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100

用户问题: AQL是0.65的检验项有哪些？
SQL:
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    inspection_frequency, document_id
FROM sip_records
WHERE inspection_frequency LIKE '%0.65%'
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100

用户问题: 前横梁的机械性能要求是什么？
SQL:
SELECT DISTINCT ON (customer, part_name, process, inspection_item)
    customer, part_name, process, inspection_item,
    specification, inspection_method, version, document_id
FROM sip_records
WHERE part_name LIKE '%前横梁%'
  AND inspection_item LIKE '%机械性能%'
ORDER BY customer, part_name, process, inspection_item, version DESC
LIMIT 100
"""


async def query(question: str, session_id: str = "default") -> dict:
    """完整 Text-to-SQL 管道：生成 SQL → 校验 → 执行 → 拼接 PDF 链接。

    Returns:
        {"success": True, "sql": str, "data": list, "count": int, "pdf_urls": list}
        or {"success": False, "error": str, "data": [], "count": 0}
    """
    # 1. 生成 SQL
    llm = create_chat_llm()
    schema_context, synonym_context = _get_schema_context()
    history_context = session_memory.get_context_for_llm(session_id, limit=3)

    prompt = SQL_GENERATION_PROMPT.format(
        schema_context=schema_context,
        synonym_context=synonym_context,
    )
    messages = [SystemMessage(content=prompt)]
    if history_context:
        messages.append(HumanMessage(
            content=f"【对话历史】\n{history_context}\n\n【用户问题】\n{question}"))
    else:
        messages.append(HumanMessage(content=f"用户问题: {question}"))

    sql = await asyncio.to_thread(llm.invoke, messages)
    sql = sql.strip() if sql else ""
    sql = re.sub(r"^```(?:sql)?\s*\n?", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\n?```\s*$", "", sql).strip()

    if not sql or sql == "INVALID_SQL":
        return {"success": False, "error": "无法生成有效 SQL", "data": [], "count": 0}

    # 2. 校验 SQL
    try:
        _validator.validate_and_sanitize(sql)
    except SQLValidationError as e:
        return {"success": False, "error": f"SQL 校验失败: {e}", "data": [], "count": 0}

    # 3. 执行 SQL
    try:
        data = await fetch_all(sql)
        if len(data) > 100:
            data = data[:100]

        seen_ids = dict.fromkeys(
            row.get("document_id") for row in data if row.get("document_id"))
        pdf_urls = [
            f"documents/{doc_id}.pdf"
            for doc_id in seen_ids
            if (_DOCUMENTS_DIR / f"{doc_id}.pdf").exists()
        ]

        logger.info(f"text2sql: {len(data)} rows, {len(pdf_urls)} PDFs")
        return {
            "success": True,
            "sql": sql,
            "data": data,
            "count": len(data),
            "pdf_urls": pdf_urls,
        }
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        return {"success": False, "error": str(e), "data": [], "count": 0}

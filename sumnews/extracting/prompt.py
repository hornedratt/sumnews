"""Собирает промпт извлечения из вотчлиста.

Рубрики категорий и приоритета живут в описаниях полей `Extraction` (LangChain передаёт их вместе
со схемой) — здесь не дублируются. Промпт лишь задаёт роль, называет отслеживаемых субъектов и
подставляет текст статьи.
"""

from langchain_core.prompts import ChatPromptTemplate

from sumnews.watchlist import Watchlist

_SYSTEM = """\
Ты извлекаешь структурированные метаданные о новостных статьях для аналитика, который отслеживает компанию «{company}».

Отслеживаемая компания: {company}{company_aliases}
Конкуренты: {competitors}

Опирайся только на текст статьи ниже — ничего не домысливай. Пиши на русском языке. Верни структурированный объект и ничего кроме него.
"""

_HUMAN = """\
Источник: {source_name} ({source_type})
URL: {url}
Опубликовано: {published_at}
Заголовок: {title}

{body}
"""


def build_prompt(watchlist: Watchlist) -> ChatPromptTemplate:
    """A `ChatPromptTemplate` with the watchlist baked in; call it with the per-article fields."""
    aliases = ", ".join(watchlist.company.aliases)
    competitors = ", ".join(company.name for company in watchlist.competitors) or "не заданы"
    prompt = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM), ("human", _HUMAN)]
    ).partial(
        company=watchlist.company.name,
        company_aliases=f" (также: {aliases})" if aliases else "",
        competitors=competitors,
    )
    return prompt

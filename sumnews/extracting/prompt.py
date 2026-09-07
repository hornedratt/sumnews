"""Собирает промпт извлечения из вотчлиста.

Рубрики категорий и приоритета продублированы в системном промпте — классификация по этим полям
заметно от них зависит; в описаниях полей `Extraction` они остаются как часть схемы, которую
LangChain передаёт вместе с запросом. Промпт также задаёт роль, называет отслеживаемых субъектов
и подставляет текст статьи.
"""

from langchain_core.prompts import ChatPromptTemplate

from sumnews.watchlist import Watchlist

_SYSTEM = """\
Ты извлекаешь структурированные метаданные о новостных статьях для аналитика, который отслеживает компанию «{company}».

Отслеживаемая компания: {company}{company_aliases}
Конкуренты: {competitors}

Категории (поле category):
- regulation: законы, регуляторы, лицензирование, штрафы, судебные разбирательства, комплаенс.
- reputation: общественное восприятие, PR-кризисы, скандалы, настроения клиентов или сотрудников, сбои в работе.
- competitors: продукты, сделки, финансирование, найм или рыночные шаги конкурента.
- trends: отраслевые сдвиги, технологии или рыночные данные, не привязанные к одной компании.
- promo: реклама, промо-акции или собственные заявления/пресс-релизы самой отслеживаемой компании, а не внешнее освещение о ней.

Приоритет (поле priority):
- high: действия регулятора, судебный иск или кризис, прямо называющий отслеживаемую компанию.
- medium: шаги конкурентов или регуляторные/отраслевые сдвиги с явным краткосрочным влиянием на отслеживаемую компанию.
- low: общие тренды и косвенные упоминания.

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

"""Benchmark the extraction pipeline against a hand-labelled Telegram dataset.

    make run-bench
    make run-bench ARGS='--dataset data/hand_written_tg_bench.json'

Does everything `scripts/run_ingest.py` does — build a `RawArticle`, keyword-filter it, run the
extraction chain, resolve category / priority / relevance — except the two things a benchmark
can't or shouldn't: Telegram posts are read from a labelled JSON file instead of being fetched,
and predictions are scored against the labels instead of being written to the database.

Writes `bench_predictions.json` (per-article prediction + target) and `bench_report.{json,md}`
to data/results/, and prints the report.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sumnews.extracting.chain import Extractor
from sumnews.loggers import configure_logging
from sumnews.parsing import keyword_filter
from sumnews.parsing.telegram import _title_from_text, normalize_channel
from sumnews.parsing.types import RawArticle
from sumnews.settings import get_settings
from sumnews.typed import Category, Priority, SourceType
from sumnews.watchlist import Watchlist, load_watchlist
from tqdm.asyncio import tqdm

_DEFAULT_DATASET = Path("data/hand_written_tg_bench.json")
_RESULTS_DIR = Path("data/results")


@dataclass(slots=True)
class BenchCase:
    """One labelled dataset row, turned into the `RawArticle` the pipeline would see."""

    url: str
    channel: str
    article: RawArticle
    target_is_relevant: bool
    target_category: Category
    target_priority: Priority


@dataclass(slots=True)
class BenchResult:
    """What the pipeline predicted for one case, plus the target, plus how long it took."""

    url: str
    channel: str
    title: str
    text: str
    llm_called: bool
    elapsed_s: float
    predicted_is_relevant: bool
    predicted_category: Category | None
    predicted_priority: Priority | None
    target_is_relevant: bool
    target_category: Category
    target_priority: Priority


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark extraction against a labelled dataset")
    parser.add_argument(
        "--dataset", type=Path, default=_DEFAULT_DATASET,
        help="labelled Telegram JSON (default: data/hand_written_tg_bench.json)",
    )
    return parser.parse_args()


def _load_cases(path: Path) -> list[BenchCase]:
    """Parse the labelled dataset into `BenchCase`s, mirroring `TelegramSource._fetch_channel`."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases: list[BenchCase] = []
    for entry in raw.values():
        message = entry["message"]
        text = (message["message"] or "").strip()
        channel = normalize_channel(entry["channel"])
        article = RawArticle(source_type=SourceType.TELEGRAM,
                             source_name=channel,
                             url=entry["url"],
                             title=_title_from_text(text),
                             published_at=datetime.fromisoformat(message["date"]),
                             body=text)
        case = BenchCase(url=entry["url"],
                         channel=channel,
                         article=article,
                         target_is_relevant=entry["is_relevant"],
                         target_category=Category(entry["category"]),
                         target_priority=Priority(entry["priority"]))
        cases.append(case)
    return cases


async def _run_case(
    case: BenchCase,
    extractor: Extractor,
    watchlist: Watchlist,
    llm_sem: asyncio.Semaphore,
) -> BenchResult:
    """Replicate `ingest._handle` minus the repo: keyword-filter, then extract if it's a candidate.

    `elapsed_s` is keyword-filter time plus, for candidates, the extraction call's own duration —
    time spent waiting on the concurrency semaphore is excluded so per-call timing stays honest.
    """
    filter_start = time.perf_counter()
    matched = keyword_filter.match(case.article, watchlist)
    elapsed = time.perf_counter() - filter_start

    if not matched:
        return BenchResult(url=case.url,
                           channel=case.channel,
                           title=case.article.title,
                           text=case.article.body or "",
                           llm_called=False,
                           elapsed_s=elapsed,
                           predicted_is_relevant=False,
                           predicted_category=None,
                           predicted_priority=None,
                           target_is_relevant=case.target_is_relevant,
                           target_category=case.target_category,
                           target_priority=case.target_priority)

    async with llm_sem:
        extract_start = time.perf_counter()
        extraction = await extractor.extract(case.article, case.article.body or "")
        elapsed += time.perf_counter() - extract_start

    return BenchResult(url=case.url,
                       channel=case.channel,
                       title=case.article.title,
                       text=case.article.body or "",
                       llm_called=True,
                       elapsed_s=elapsed,
                       predicted_is_relevant=extraction.is_relevant,
                       predicted_category=Category(extraction.category),
                       predicted_priority=Priority(extraction.priority),
                       target_is_relevant=case.target_is_relevant,
                       target_category=case.target_category,
                       target_priority=case.target_priority)


def _build_report(
    results: list[BenchResult],
    wall_elapsed: float,
    model: str,
    llm_verify_enabled: bool,
) -> dict[str, Any]:
    total = len(results)
    llm_results = [result for result in results if result.llm_called]
    # Category / priority are scored over every item the dataset marks relevant. If the
    # pipeline dropped one — keyword filter, or the LLM verify gate flagged it irrelevant —
    # its predicted bucket is wrong by definition, so it counts as a miss, not an exclusion.
    relevant_targets = [result for result in results if result.target_is_relevant]

    relevance_correct = sum(
        1 for result in results if result.predicted_is_relevant == result.target_is_relevant
    )
    category_correct = sum(
        1 for result in relevant_targets
        if result.predicted_is_relevant and result.predicted_category == result.target_category
    )
    priority_correct = sum(
        1 for result in relevant_targets
        if result.predicted_is_relevant and result.predicted_priority == result.target_priority
    )

    mean_time_all = sum(result.elapsed_s for result in results) / total if total else 0.0
    mean_time_llm = (
        sum(result.elapsed_s for result in llm_results) / len(llm_results) if llm_results else 0.0
    )

    report = {
        "model": model,
        "llm_verify_enabled": llm_verify_enabled,
        "dataset_size": total,
        "llm_calls": len(llm_results),
        "dataset_relevant": len(relevant_targets),
        "total_wall_s": round(wall_elapsed, 3),
        "mean_time_all_s": round(mean_time_all, 3),
        "mean_time_llm_s": round(mean_time_llm, 3),
        "relevance_accuracy": round(relevance_correct / total, 3) if total else None,
        "relevance_correct": relevance_correct,
        "category_accuracy": (
            round(category_correct / len(relevant_targets), 3) if relevant_targets else None
        ),
        "category_correct": category_correct,
        "priority_accuracy": (
            round(priority_correct / len(relevant_targets), 3) if relevant_targets else None
        ),
        "priority_correct": priority_correct,
    }
    return report


def _result_as_dict(result: BenchResult) -> dict[str, Any]:
    return {
        "url": result.url,
        "channel": result.channel,
        "title": result.title,
        "text": result.text,
        "llm_called": result.llm_called,
        "elapsed_s": round(result.elapsed_s, 3),
        "predicted": {
            "is_relevant": result.predicted_is_relevant,
            "category": result.predicted_category.value if result.predicted_category else None,
            "priority": result.predicted_priority.value if result.predicted_priority else None,
        },
        "target": {
            "is_relevant": result.target_is_relevant,
            "category": result.target_category.value,
            "priority": result.target_priority.value,
        },
        "correct": {
            "is_relevant": result.predicted_is_relevant == result.target_is_relevant,
            "category": (
                result.predicted_category == result.target_category if result.llm_called else None
            ),
            "priority": (
                result.predicted_priority == result.target_priority if result.llm_called else None
            ),
        },
    }


def _format_report(report: dict[str, Any]) -> str:
    lines = [
        "# sumnews extraction benchmark",
        "",
        f"- model: {report['model']}",
        f"- LLM verify enabled: {report['llm_verify_enabled']}",
        f"- dataset size: {report['dataset_size']}",
        f"- LLM calls: {report['llm_calls']} "
        f"(the other {report['dataset_size'] - report['llm_calls']} rejected by the keyword filter)",
        f"- dataset-relevant items: {report['dataset_relevant']} (scored for category / priority)",
        f"- total wall time: {report['total_wall_s']} s",
        "",
        "## Mean time per article",
        "",
        f"- all articles: {report['mean_time_all_s']} s",
        f"- articles that required an LLM call: {report['mean_time_llm_s']} s",
        "",
        "## Accuracy",
        "",
        f"- relevance (whole dataset): {report['relevance_accuracy']} "
        f"({report['relevance_correct']}/{report['dataset_size']})",
        f"- category (dataset-relevant items): {report['category_accuracy']} "
        f"({report['category_correct']}/{report['dataset_relevant']})",
        f"- priority (dataset-relevant items): {report['priority_accuracy']} "
        f"({report['priority_correct']}/{report['dataset_relevant']})",
        "",
    ]
    return "\n".join(lines)


def _write_outputs(results: list[BenchResult], report: dict[str, Any]) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    predictions = [_result_as_dict(result) for result in results]
    (_RESULTS_DIR / "bench_predictions.json").write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (_RESULTS_DIR / "bench_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (_RESULTS_DIR / "bench_report.md").write_text(_format_report(report), encoding="utf-8")


async def main() -> None:
    args = _parse_args()
    configure_logging()
    settings = get_settings()
    watchlist = load_watchlist(settings.WATCHLIST_PATH)
    cases = _load_cases(args.dataset)

    extractor = Extractor(settings, watchlist)
    llm_sem = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)

    wall_start = time.perf_counter()
    results: list[BenchResult] = await tqdm.gather(
        *(_run_case(case, extractor, watchlist, llm_sem) for case in cases),
        desc=f"extracting ({settings.LLM_MODEL})",
        unit="article",
    )
    wall_elapsed = time.perf_counter() - wall_start

    report = _build_report(
        results, wall_elapsed, settings.LLM_MODEL, settings.LLM_VERIFY_ENABLED
    )
    _write_outputs(results, report)

    print()
    print(_format_report(report))
    print(f"wrote {_RESULTS_DIR}/bench_predictions.json, bench_report.json, bench_report.md")


if __name__ == "__main__":
    asyncio.run(main())

import argparse
import argcomplete
import logging
from pathlib import Path

from src.workflow import run_crawl, run_translate, run_evaluate
from src.utils.restructure import restructure_directories
from src.core.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stack Overflow Collector: Crawl, Translate, and Evaluate."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    # Crawl Command
    crawl_parser = subparsers.add_parser(
        "crawl", help="Fetch questions from Stack Overflow"
    )
    crawl_parser.add_argument(
        "--tag", default="kubernetes", help="Stack Overflow tag to fetch."
    )
    crawl_parser.add_argument(
        "--limit", type=int, default=5, help="Number of questions to fetch."
    )
    crawl_parser.add_argument(
        "--out-dir",
        default="data",
        type=Path,
        help="Directory to store fetched content.",
    )
    crawl_parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Page size per Stack Exchange API call (max 100).",
    )
    crawl_parser.add_argument(
        "--stack-key",
        default=settings.STACK_API_KEY,
        help="Stack Exchange API key to increase quota.",
    )
    crawl_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Thread workers for fetching answers.",
    )
    crawl_parser.add_argument(
        "--checkpoint-file",
        type=Path,
        default=None,
        help="Path to checkpoint file.",
    )

    # Translate Command
    translate_parser = subparsers.add_parser(
        "translate", help="Translate fetched content"
    )
    translate_parser.add_argument(
        "--out-dir",
        default="data",
        type=Path,
        help="Directory containing fetched content.",
    )
    translate_parser.add_argument(
        "--model-url",
        default=settings.LOCAL_MODEL_URL,
        help="Base URL for the translation model endpoint.",
    )
    translate_parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY or "test-key",
        help="API key for translation model.",
    )
    translate_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Thread workers for translation.",
    )
    translate_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if translated files exist.",
    )
    translate_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少个目录（按加载顺序截断）。",
    )
    translate_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="跳过排序后的前 N 个目录，用于配合 limit 指定区间。",
    )

    # Evaluate Command
    eval_parser = subparsers.add_parser(
        "evaluate", help="Generate answers and evaluate them"
    )
    eval_parser.add_argument(
        "--out-dir",
        default="data",
        type=Path,
        help="Directory containing fetched content.",
    )
    eval_parser.add_argument(
        "--model",
        default=settings.DEFAULT_MODEL_ANSWER,
        help="Model to use for answering and evaluating.",
    )
    eval_parser.add_argument(
        "--mode",
        default="answer",
        help="Evaluation mode: 'answer' or 'evaluate'.",
    )
    eval_parser.add_argument(
        "--base-url",
        default=settings.OPENAI_BASE_URL,
        help="Base URL for evaluation and answer generation model endpoint.",
    )
    eval_parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY,
        help="API key for evaluation models.",
    )
    eval_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Thread workers for evaluation.",
    )
    eval_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-evaluate even if evaluation files exist.",
    )
    eval_parser.add_argument(
        "--reverse",
        action="store_true",
        help="Process directories in reverse order.",
    )
    eval_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少个目录（按加载顺序截断）。",
    )
    eval_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="跳过排序后的前 N 个目录，用于配合 limit 指定区间。",
    )

    # Restructure Command (Legacy/Utility)
    restructure_parser = subparsers.add_parser(
        "restructure", help="Restructure data directories"
    )
    restructure_parser.add_argument(
        "--out-dir", default="data", type=Path, help="Directory to restructure."
    )
    restructure_parser.add_argument(
        "--cleanup-old",
        action="store_true",
        help="Remove legacy files.",
    )

    argcomplete.autocomplete(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "crawl":
        run_crawl(
            tag=args.tag,
            limit=args.limit,
            out_dir=args.out_dir,
            stack_key=args.stack_key,
            workers=args.workers,
            page_size=args.page_size,
            checkpoint_file=args.checkpoint_file,
        )
    elif args.command == "translate":
        run_translate(
            out_dir=args.out_dir,
            model_url=args.model_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            limit=args.limit,
            skip=args.skip,
        )
    elif args.command == "evaluate":
        run_evaluate(
            out_dir=args.out_dir,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            reverse=args.reverse,
            limit=args.limit,
            mode=args.mode,
            skip=args.skip,
        )
    elif args.command == "restructure":
        restructure_directories(args.out_dir)
        if args.cleanup_old:
            from src.utils.restructure import cleanup_extra_files

            cleanup_extra_files(args.out_dir)


if __name__ == "__main__":
    main()

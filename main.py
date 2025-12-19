
import argparse
import argcomplete
import logging
from pathlib import Path

from src.flows.workflow import run_crawl, run_translate, run_batch_evaluate, run_batch_answer
from src.utils.restructure import restructure_directories
from src.conf.config import settings


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
        "crawl", help="Fetch questions from Stack Overflow."
    )
    crawl_parser.add_argument(
        "--tag", default="kubernetes", help="Stack Overflow tag to fetch (default: kubernetes)."
    )
    crawl_parser.add_argument(
        "--limit", type=int, default=5, help="Maximum number of questions to fetch (default: 5)."
    )
    crawl_parser.add_argument(
        "--out-dir",
        default="data",
        type=Path,
        help="Directory to save fetched data (default: data).",
    )
    crawl_parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Page size for Stack Exchange API calls (max 100).",
    )
    crawl_parser.add_argument(
        "--stack-key",
        default=settings.STACK_API_KEY,
        help="Stack Exchange API key for increased quota.",
    )
    crawl_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads (default: 4).",
    )
    crawl_parser.add_argument(
        "--checkpoint-file",
        type=Path,
        default=None,
        help="Path to the checkpoint file for resuming crawls.",
    )

    # Translate Command
    translate_parser = subparsers.add_parser(
        "translate", help="Translate content to Chinese (Q&A and Answers)."
    )
    translate_parser.add_argument(
        "--out-dir",
        default=None,
        type=Path,
        help="Input directory containing fetched content (Required).",
    )
    translate_parser.add_argument(
        "--base-url",
        dest="model_url", # Map to model_url for internal function if needed, or change internal
        default=settings.LOCAL_MODEL_URL,
        help="Base URL for the translation model API.",
    )
    translate_parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY or "test-key",
        help="API key for the translation model.",
    )
    translate_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of concurrent worker threads (default: 2).",
    )
    translate_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-translation of existing files.",
    )
    translate_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of items to process.",
    )
    translate_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N items.",
    )

    # Answer Command
    answer_parser = subparsers.add_parser(
        "answer", help="Generate answers for questions (Step 1)."
    )
    answer_parser.add_argument(
        "--out-dir",
        default=None,
        type=Path,
        help="Directory containing fetched content (Required unless --csv-path is used).",
    )
    answer_parser.add_argument(
        "--model",
        default=settings.DEFAULT_MODEL_ANSWER,
        help="Model name to use for answer generation.",
    )
    answer_parser.add_argument(
        "--base-url",
        default=settings.OPENAI_BASE_URL,
        help="Base URL for the model API.",
    )
    answer_parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY,
        help="API key for the model.",
    )
    answer_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of concurrent worker threads (default: 2).",
    )
    answer_parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration of existing answers.",
    )
    answer_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of items to process.",
    )
    answer_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N items.",
    )
    answer_parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Path to input CSV file containing questions (Alternative source).",
    )

    # Evaluate Command
    eval_parser = subparsers.add_parser(
        "evaluate", help="Evaluate generated answers (Step 2)."
    )
    eval_parser.add_argument(
        "--out-dir",
        default=None,
        type=Path,
        help="Directory containing data (Required unless --input-csv is used).",
    )
    eval_parser.add_argument(
        "--model",
        default=settings.DEFAULT_MODEL_ANSWER,
        help="Model name used for the answer to evaluate (also attempts to evaluate using this model).",
    )
    eval_parser.add_argument(
        "--base-url",
        default=settings.OPENAI_BASE_URL,
        help="Base URL for the evaluation model API.",
    )
    eval_parser.add_argument(
        "--api-key",
        default=settings.OPENAI_API_KEY,
        help="API key for the evaluation model.",
    )
    eval_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of concurrent worker threads (default: 2).",
    )
    eval_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-evaluation of existing items.",
    )
    eval_parser.add_argument(
        "--reverse",
        action="store_true",
        help="Process items in reverse order.",
    )
    eval_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of items to process.",
    )
    eval_parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N items.",
    )
    eval_parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Path to input CSV file (for question context).",
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
    # Silence noisy libraries unless verbose
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

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
        if not args.out_dir:
             print("Error: --out-dir is required for translate.")
             return
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
        if not args.out_dir and not args.input_csv:
             print("Error: must specify --out-dir or --input-csv.")
             return
        
        run_batch_evaluate(
            out_dir=args.out_dir or Path("data"), # Default to data ONLY if csv provided
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            reverse=args.reverse,
            limit=args.limit,
            skip=args.skip,
            input_csv=args.input_csv,
        )
    elif args.command == "answer":
        if not args.out_dir and not args.input_csv:
             print("Error: must specify --out-dir or --input-csv.")
             return

        run_batch_answer(
            out_dir=args.out_dir or Path("data"),
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            limit=args.limit,
            skip=args.skip,
            input_csv=args.input_csv,
        )
    elif args.command == "restructure":
        restructure_directories(args.out_dir)
        if args.cleanup_old:
            from src.utils.restructure import cleanup_extra_files

            cleanup_extra_files(args.out_dir)


if __name__ == "__main__":
    main()

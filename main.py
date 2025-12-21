import argparse
import argcomplete
import logging
from pathlib import Path

from src.cli import (
    run_crawl,
    run_translate,
    run_batch_evaluate,
    run_batch_answer,
)
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
        "--tag",
        default="kubernetes",
        help="Stack Overflow tag to fetch (default: kubernetes).",
    )
    crawl_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of questions to fetch (default: 5).",
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
    crawl_parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Path to output CSV file for crawled questions.",
    )
    crawl_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-crawl of existing content/ignore checkpoints.",
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
        dest="model_url",  # Map to model_url for internal function if needed, or change internal
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
    translate_parser.add_argument(
        "--input-csv",
        type=Path,
        default=None,
        help="Path to input CSV file containing questions (Alternative source).",
    )
    translate_parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Path to output CSV file for translation results.",
    )

    # Answer Command
    answer_parser = subparsers.add_parser(
        "answer", help="Generate answers for questions (Step 1)."
    )
    answer_parser.add_argument(
        "--input-dir",
        default=None,
        type=Path,
        help="Directory containing fetched content.",
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
    answer_parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Path to output CSV file for results (Default: out_dir/results.csv).",
    )

    # Evaluate Command
    eval_parser = subparsers.add_parser(
        "evaluate", help="Evaluate generated answers (Step 2)."
    )
    eval_parser.add_argument(
        "--input-dir",
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
    eval_parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Path to output CSV file for results (Default: out_dir/results.csv).",
    )
    eval_parser.add_argument(
        "--modules",
        nargs="+",
        choices=["lint", "coverage", "llm-eval", "compare", "all"],
        default=["all"],
        help="Evaluation modules to run. Options: lint, coverage, llm-eval, compare, all (default: all).",
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

    # Setup colored logging
    class ColoredFormatter(logging.Formatter):
        """Custom formatter with colors for different log levels."""

        COLORS = {
            "DEBUG": "\033[36m",  # Cyan
            "INFO": "\033[32m",  # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",  # Red
            "CRITICAL": "\033[35m",  # Magenta
        }
        RESET = "\033[0m"

        def format(self, record):
            color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            record.name = f"\033[34m{record.name}{self.RESET}"  # Blue for logger name
            return super().format(record)

    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter("%(levelname)s %(name)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    root_logger.addHandler(handler)

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
            output_csv=args.output_csv,
            force=args.force,
        )
    elif args.command == "translate":
        if not args.out_dir and not args.input_csv:
            print("Error: must specify --out-dir or --input-csv.")
            return
        run_translate(
            out_dir=args.out_dir or Path("data"),
            model_url=args.model_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            limit=args.limit,
            skip=args.skip,
            input_csv=args.input_csv,
            output_csv=args.output_csv,
        )
    elif args.command == "evaluate":
        if not args.input_dir and not args.input_csv:
            print("Error: must specify --input-dir or --input-csv.")
            return

        run_batch_evaluate(
            out_dir=args.input_dir
            or Path("data"),  # Default to data ONLY if csv provided
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            reverse=args.reverse,
            limit=args.limit,
            skip=args.skip,
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            modules=args.modules,
        )
    elif args.command == "answer":
        if not args.input_dir and not args.input_csv:
            print("Error: must specify --input-dir or --input-csv.")
            return

        run_batch_answer(
            input_dir=args.input_dir or Path("data"),
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            workers=args.workers,
            force=args.force,
            limit=args.limit,
            skip=args.skip,
            input_csv=args.input_csv,
            output_csv=args.output_csv,
        )
    elif args.command == "restructure":
        restructure_directories(args.input_csv)
        if args.cleanup_old:
            from src.utils.restructure import cleanup_extra_files

            cleanup_extra_files(args.input_csv)


if __name__ == "__main__":
    main()

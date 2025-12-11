import argparse
import logging
from pathlib import Path

from stackoverflowcollect.workflow import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and translate recent Stack Overflow Q&A for Kubernetes."
    )
    parser.add_argument("--tag", default="kubernetes", help="Stack Overflow tag to fetch.")
    parser.add_argument("--limit", type=int, default=5, help="Number of questions to fetch.")
    parser.add_argument(
        "--out-dir", default="data", type=Path, help="Directory to store fetched content."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="Page size per Stack Exchange API call (max 100).",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip sending content to the local GPT-4o endpoint.",
    )
    parser.add_argument(
        "--model-url",
        default="http://localhost:4141",
        help="Base URL for the GPT-4o-compatible endpoint.",
    )
    parser.add_argument("--api-key", default="test-key", help="API key used for the model endpoint.")
    parser.add_argument(
        "--stack-key",
        default=None,
        help="Stack Exchange API key to increase quota and allow higher request volume.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging for troubleshooting."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Thread workers for fetching answers and translations.",
    )
    parser.add_argument(
        "--checkpoint-file",
        type=Path,
        default=None,
        help="Path to checkpoint file for resume (defaults to <out-dir>/checkpoint.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    run_pipeline(
        tag=args.tag,
        limit=args.limit,
        out_dir=args.out_dir,
        translate=not args.no_translate,
        model_url=args.model_url,
        api_key=args.api_key,
        stack_key=args.stack_key,
        workers=args.workers,
        page_size=args.page_size,
        checkpoint_file=args.checkpoint_file,
    )


if __name__ == "__main__":
    main()

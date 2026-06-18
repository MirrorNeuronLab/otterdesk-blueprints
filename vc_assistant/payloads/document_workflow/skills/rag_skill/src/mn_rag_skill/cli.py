from __future__ import annotations

import argparse
import json
from pathlib import Path

from .rag import (
    DEFAULT_EMBEDDING_API_BASE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
    DEFAULT_EMBEDDING_START_COMMAND,
    DEFAULT_VECTOR_DIM,
    RagConfig,
    build_rag_context,
    delete_blueprint_index,
    ensure_embedding_backend,
    prepare_blueprint_knowledge_rag,
    public_rag_state,
)


def _config_from_args(args: argparse.Namespace) -> RagConfig:
    return RagConfig(
        redis_url=args.redis_url or None,
        namespace=args.namespace or None,
        blueprint_id=args.blueprint_id,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_api_base=args.embedding_api_base,
        embedding_start_command=args.embedding_start_command,
        embedding_healthcheck_enabled=not args.no_embedding_healthcheck,
        top_k=args.top_k,
        vector_dim=args.vector_dim,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Index and query blueprint knowledge with Redis vector search.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--blueprint-id", required=True)
    common.add_argument("--redis-url", default="")
    common.add_argument("--namespace", default="")
    common.add_argument("--embedding-provider", default=DEFAULT_EMBEDDING_PROVIDER)
    common.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    common.add_argument("--embedding-api-base", default=DEFAULT_EMBEDDING_API_BASE)
    common.add_argument("--embedding-start-command", default=DEFAULT_EMBEDDING_START_COMMAND)
    common.add_argument("--no-embedding-healthcheck", action="store_true")
    common.add_argument("--top-k", type=int, default=5)
    common.add_argument("--vector-dim", type=int, default=DEFAULT_VECTOR_DIM)

    index_parser = subparsers.add_parser("index", parents=[common])
    index_parser.add_argument("--knowledge-dir", required=True)

    query_parser = subparsers.add_parser("query", parents=[common])
    query_parser.add_argument("--query", required=True)
    query_parser.add_argument("--max-chars", type=int, default=6000)

    delete_parser = subparsers.add_parser("delete", parents=[common])

    args = parser.parse_args()
    config = _config_from_args(args)
    if args.command == "index":
        knowledge_dir = Path(args.knowledge_dir).expanduser().resolve()
        state = prepare_blueprint_knowledge_rag(
            blueprint_id=args.blueprint_id,
            blueprint_dir=knowledge_dir.parent,
            knowledge_dir=knowledge_dir,
            config={
                "knowledge_rag": {
                    "enabled": True,
                    "redis_url": args.redis_url,
                    "namespace": args.namespace,
                    "embedding_provider": args.embedding_provider,
                    "embedding_model": args.embedding_model,
                    "embedding_api_base": args.embedding_api_base,
                    "embedding_start_command": args.embedding_start_command,
                    "embedding_healthcheck_enabled": not args.no_embedding_healthcheck,
                    "top_k": args.top_k,
                    "vector_dim": args.vector_dim,
                    "index_on_startup": True,
                }
            },
        )
        print(json.dumps(public_rag_state(state), indent=2, sort_keys=True))
    elif args.command == "query":
        if config.embedding_healthcheck_enabled:
            ensure_embedding_backend(config)
        context = build_rag_context(args.query, config, max_chars=args.max_chars)
        print(json.dumps(context, indent=2, sort_keys=True))
    elif args.command == "delete":
        print(json.dumps(delete_blueprint_index(config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

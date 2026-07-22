import argparse
from biotarget.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="BioTarget - AI Drug Discovery Pipeline"
    )
    parser.add_argument("command", choices=["run"])
    parser.add_argument("subcommand", choices=["full"])
    parser.add_argument("--disease", type=str, required=True)
    parser.add_argument("--target-model", type=str, default="hetero-gnn")
    parser.add_argument("--structure-engine", type=str, default="openfold3")
    parser.add_argument("--binding-engine", type=str, default="gnina")
    parser.add_argument("--top-targets", type=int, default=10)
    parser.add_argument("--top-ligands", type=int, default=10)
    parser.add_argument("--out", type=str, default="./runs")

    args = parser.parse_args()

    if args.command == "run" and args.subcommand == "full":
        run_pipeline(
            args.disease,
            checkpoint_path=None,
            top_targets=args.top_targets,
            top_ligands=args.top_ligands,
        )


if __name__ == "__main__":
    main()

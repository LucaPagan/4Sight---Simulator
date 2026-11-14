import argparse
import json
from pathlib import Path

from .config import settings
from .datasets import audit_dataset


def main():
    parser = argparse.ArgumentParser(description="Audience Simulator · laboratorio locale")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--data", default="data")
    clean = commands.add_parser("cleanup")
    clean.add_argument(
        "--apply", action="store_true", help="Rimuovi log e cache non referenziata scaduti; default dry run"
    )
    for name in ["bootstrap", "train", "predict", "validate", "schemas", "ablation"]:
        commands.add_parser(name)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--model", default="qwen3.5:9b")
    benchmark.add_argument("--cases", type=int, default=96)
    simulate = commands.add_parser("simulate")
    simulate.add_argument("brief", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit_dataset(Path(args.data))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1 if result["errors"] else 0)
    from .service import SimulationService

    service = SimulationService(settings())
    if args.command == "bootstrap":
        result = service.import_dataset(service.cfg.data_dir)
    elif args.command == "train":
        model = service.get_models()
        result = {"version": model.version, "cutoff": model.cutoff}
    elif args.command == "predict":
        from .reporting import csv_export

        result = service.official_forecast()
        service.store.write_bytes("official/predictions.csv", csv_export(result["predictions"]))
        service.store.write_bytes("official/age_predictions.csv", csv_export(result["predictions"], age=True))
        result = {
            "rows": len(result["predictions"]),
            "aggregate": "artifacts/official/predictions.csv",
            "age": "artifacts/official/age_predictions.csv",
            "completion_status": "preliminary",
        }
    elif args.command == "validate":
        result = service.backtest()
    elif args.command == "benchmark":
        from .benchmark import benchmark_model

        result = benchmark_model(service, args.model, args.cases)
    elif args.command == "ablation":
        from .ablation import run_ablation

        result = run_ablation(service)
    elif args.command == "cleanup":
        from .cleanup import cleanup

        result = cleanup(service, apply=args.apply)
    elif args.command == "simulate":
        scenario = service.create_scenario(json.loads(args.brief.read_text()))
        run = service.repo.create_run(scenario["id"], "cli")
        service.execute_run(run["id"])
        result = service.repo.get("simulation_runs", run["id"])
    elif args.command == "schemas":
        from .api import create_app
        from .codegen import generate_contracts

        generate_contracts()

        Path("docs/openapi.json").write_text(
            json.dumps(create_app(service).openapi(), ensure_ascii=False, indent=2)
        )
        result = {"schema": "docs/openapi.json"}
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("audience_simulator.api:app", host="127.0.0.1", port=args.port)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

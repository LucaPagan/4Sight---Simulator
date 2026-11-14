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
    for name in ["bootstrap", "train", "predict", "validate", "validate-cold-start", "schemas"]:
        commands.add_parser(name)
    ablation = commands.add_parser("ablation")
    ablation.add_argument("--provider", choices=["ollama", "gemini", "cloudflare"], default="ollama")
    ablation.add_argument("--model", default=None)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--model", default="qwen3.5:9b")
    benchmark.add_argument("--provider", choices=["ollama", "gemini", "cloudflare"], default="ollama")
    benchmark.add_argument("--cases", type=int, default=96)
    simulate = commands.add_parser("simulate")
    simulate.add_argument("brief", type=Path)
    simulate.add_argument("--provider", choices=["ollama", "gemini", "cloudflare"], default="ollama")
    simulate.add_argument("--model", default=None)
    public = commands.add_parser("public-campaign", help="Test retrospettivo su campagna Meta pubblica reale")
    public.add_argument("action", choices=["prepare", "run", "score"])
    public.add_argument("identifier", nargs="?")
    public.add_argument("--provider", choices=["ollama", "gemini", "cloudflare"], default="gemini")
    public.add_argument("--model", default=None)
    public.add_argument("--max-new", type=int, default=240)
    corpus = commands.add_parser("corpus", help="Corpus di campagne reali confrontabili (fonti pubbliche)")
    corpus.add_argument("action", choices=["prepare"])
    corpus.add_argument("--upworthy-file", type=Path, help="CSV exploratory già scaricato")
    corpus.add_argument("--gwwc-file", type=Path, help="CSV GWWC già scaricato (opzionale)")
    corpus.add_argument(
        "--download", action="store_true", help="Scarica le fonti fissate per checksum (solo se esplicito)"
    )
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit_dataset(Path(args.data))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1 if result["errors"] else 0)
    from .service import SimulationService

    service = SimulationService(settings())
    if args.command == "corpus":
        import io

        import pandas as pd

        from .corpus import UPWORTHY_SHA256, fetch_source, prepare_corpus

        if args.download:
            upworthy_raw = fetch_source("upworthy")
            gwwc_raw = fetch_source("gwwc")
        elif args.upworthy_file:
            import hashlib

            upworthy_raw = args.upworthy_file.read_bytes()
            if hashlib.sha256(upworthy_raw).hexdigest() != UPWORTHY_SHA256:
                parser.error("Checksum del file Upworthy non corrispondente")
            gwwc_raw = args.gwwc_file.read_bytes() if args.gwwc_file else None
        else:
            parser.error("corpus prepare richiede --upworthy-file oppure --download")
        service.store.write_bytes("corpus/upworthy/source.csv", upworthy_raw)
        result = prepare_corpus(
            service.store,
            pd.read_csv(io.BytesIO(upworthy_raw)),
            pd.read_csv(io.BytesIO(gwwc_raw)) if gwwc_raw else None,
        )
    elif args.command == "public-campaign":
        from .retrospective import prepare_public_campaign, run_public_campaign, score_public_campaign

        if args.action == "prepare":
            result = prepare_public_campaign(service)
        elif not args.identifier:
            parser.error("run richiede case_id; score richiede evaluation_id")
        elif args.action == "run":
            result = run_public_campaign(
                service, args.identifier, service.client(args.provider, args.model), max_new=args.max_new
            )
        else:
            result = score_public_campaign(service, args.identifier)
    elif args.command == "bootstrap":
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
    elif args.command == "validate-cold-start":
        from .forecasting import validate_new_campaigns

        result = validate_new_campaigns(service.ensure_kit())
        service.store.write_json("validation/cold-start.json", result)
    elif args.command == "benchmark":
        from .benchmark import benchmark_model

        result = benchmark_model(service, args.model, args.cases, args.provider)
    elif args.command == "ablation":
        from .ablation import run_ablation

        result = run_ablation(service, service.client(args.provider, args.model))
    elif args.command == "cleanup":
        from .cleanup import cleanup

        result = cleanup(service, apply=args.apply)
    elif args.command == "simulate":
        scenario = service.create_scenario(json.loads(args.brief.read_text()))
        selected = service.client(args.provider, args.model)
        run = service.repo.create_run(
            scenario["id"], "cli", {"provider": args.provider, "model": selected.model}
        )
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

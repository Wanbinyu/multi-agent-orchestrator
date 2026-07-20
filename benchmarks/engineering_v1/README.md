# Engineering Benchmark v1

This public suite contains six small programmatic tasks: question, diagnosis, small change, build, review, and migration. It validates the benchmark contract, workspace isolation, deterministic acceptance, repeated-run stability, and reporting without calling a Provider.

Run from the repository root:

```bash
python scripts/benchmark_engineering.py
```

The built-in `fixture-fixed-single`, `fixture-auto-route`, and `fixture-multi-model` strategies produce synthetic contract data only. They validate three-strategy isolation and reporting, but their token values must not be presented as evidence that one real model or collaboration strategy is better. Live Provider comparison is a separately authorized Beta5 stage.

"""Reproducible latency and memory benchmark harness for prompt-contracts."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any

from prompt_contracts import Contract
from prompt_contracts.identity.lock import write_lock_atomic
from prompt_contracts.registry import PromptRegistry, generate_lock_for_directory


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    idx = min(
        len(sorted_samples) - 1,
        max(0, round((pct / 100.0) * (len(sorted_samples) - 1))),
    )
    return sorted_samples[idx]


def _summarize_ms(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    return {
        "min_ms": round(ordered[0], 4) if ordered else 0.0,
        "p50_ms": round(_percentile(ordered, 50.0), 4),
        "p95_ms": round(_percentile(ordered, 95.0), 4),
        "p99_ms": round(_percentile(ordered, 99.0), 4),
        "max_ms": round(ordered[-1], 4) if ordered else 0.0,
        "mean_ms": round(statistics.fmean(ordered), 4) if ordered else 0.0,
    }


def _create_benchmark_fixtures(
    root_dir: Path,
) -> tuple[Path, Path, dict[str, Any], str]:
    """Create a 100 KiB bundle for cold load and a 10 KiB 10-var/25-prop bundle for warm ops."""
    contracts_dir = root_dir / "contracts"
    lock_path = root_dir / "contracts.lock.json"

    # 1. Cold load bundle (~100 KiB total across templates and schemas)
    cold_dir = contracts_dir / "bench.cold-bundle" / "1.0.0"
    cold_dir.mkdir(parents=True, exist_ok=True)
    (cold_dir / "contract.toml").write_text(
        "format_version = 1\n"
        'name = "bench.cold-bundle"\n'
        'version = "1.0.0"\n'
        'description = "100 KiB cold-load benchmark bundle."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "json"\n'
        'schema = "output.schema.json"\n\n'
        "[[messages]]\n"
        'role = "system"\n'
        'file = "system.md"\n\n'
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n',
        encoding="utf-8",
    )
    padding_block = ("Benchmark reference context line with deterministic text.\n" * 800)[:45000]
    (cold_dir / "system.md").write_text(
        f"System instructions:\n{padding_block}\n", encoding="utf-8"
    )
    (cold_dir / "user.md").write_text(
        f"Task payload: {{{{query}}}}\nContext:\n{padding_block}\n", encoding="utf-8"
    )
    (cold_dir / "input.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {"query": {"type": "string", "minLength": 1}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (cold_dir / "output.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["result"],
                "properties": {"result": {"type": "string"}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Match the plan's cold bundle size exactly; padding participates in identity.
    cold_size = sum(asset.stat().st_size for asset in cold_dir.iterdir())
    with (cold_dir / "user.md").open("ab") as handle:
        handle.write(b" " * (100 * 1024 - cold_size))

    # 2. Warm render & output validation bundle (10 variables, 2 messages, 25 output properties)
    warm_dir = contracts_dir / "bench.warm-contract" / "1.0.0"
    warm_dir.mkdir(parents=True, exist_ok=True)
    (warm_dir / "contract.toml").write_text(
        "format_version = 1\n"
        'name = "bench.warm-contract"\n'
        'version = "1.0.0"\n'
        'description = "10 KiB warm render and 25-property output benchmark contract."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "json"\n'
        'schema = "output.schema.json"\n\n'
        "[[messages]]\n"
        'role = "system"\n'
        'file = "system.md"\n\n'
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n',
        encoding="utf-8",
    )
    var_names = [f"var_{i:02d}" for i in range(10)]
    (warm_dir / "system.md").write_text(
        "System guidance for {{var_00}} and {{var_01}}.\n"
        + ("Rule line for deterministic evaluation.\n" * 40),
        encoding="utf-8",
    )
    placeholders = "\n".join(f"- {name}: {{{{{name}}}}}" for name in var_names)
    (warm_dir / "user.md").write_text(
        f"Evaluate inputs:\n{placeholders}\n" + ("Context detail line.\n" * 60),
        encoding="utf-8",
    )
    (warm_dir / "input.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": var_names,
                "properties": {
                    name: {"type": "string", "minLength": 1, "maxLength": 2048}
                    for name in var_names
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_props = [f"field_{i:02d}" for i in range(25)]
    (warm_dir / "output.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": out_props,
                "properties": {
                    prop: {"type": "string", "minLength": 1, "maxLength": 1024}
                    for prop in out_props
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    lock, _ = generate_lock_for_directory(contracts_dir)
    write_lock_atomic(lock, lock_path, allow_update=True)

    warm_inputs = dict.fromkeys(var_names, "x" * 600)
    rendered_size = Contract.from_directory(warm_dir).render(warm_inputs).total_utf8_bytes
    warm_inputs["var_02"] = "x" * (600 + 10 * 1024 - rendered_size)
    warm_output = dict.fromkeys(out_props, "y" * 380)
    output_size = len(json.dumps(warm_output).encode("utf-8"))
    warm_output["field_02"] = "y" * (380 + 10 * 1024 - output_size)
    warm_output_raw = json.dumps(warm_output)
    return contracts_dir, lock_path, warm_inputs, warm_output_raw


def run_benchmarks(iterations: int) -> dict[str, Any]:
    """Execute cold load, warm render, warm output validation, and peak heap benchmarks."""
    with tempfile.TemporaryDirectory(prefix="pc_bench_") as tmp_str:
        root_dir = Path(tmp_str)
        contracts_dir, lock_path, warm_inputs, warm_output_raw = _create_benchmark_fixtures(
            root_dir
        )

        # Warm-up and peak heap measurement over a full load + render + validate cycle
        tracemalloc.start()
        reg = PromptRegistry.from_directory(contracts_dir, lock_file=lock_path)
        contract = reg.get("bench.warm-contract@1.0.0")
        _ = contract.render(warm_inputs)
        _ = contract.validate_output(warm_output_raw)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 1. Cold load timings (capped at min(iterations, 200) to keep total runtime fast)
        cold_runs = min(max(10, iterations // 5), 200)
        cold_samples_ms: list[float] = []
        for _ in range(cold_runs):
            t0 = time.perf_counter_ns()
            _ = PromptRegistry.from_directory(contracts_dir, lock_file=lock_path)
            t1 = time.perf_counter_ns()
            cold_samples_ms.append((t1 - t0) / 1_000_000.0)

        # 2. Warm render + input validation timings
        warm_render_samples_ms: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            _ = contract.render(warm_inputs)
            t1 = time.perf_counter_ns()
            warm_render_samples_ms.append((t1 - t0) / 1_000_000.0)

        # 3. Warm output validation timings
        warm_output_samples_ms: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter_ns()
            _ = contract.validate_output(warm_output_raw)
            t1 = time.perf_counter_ns()
            warm_output_samples_ms.append((t1 - t0) / 1_000_000.0)

        return {
            "environment": {
                "dependencies": {
                    name: importlib.metadata.version(name) for name in ("jsonschema", "referencing")
                },
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "cpu_count": os.cpu_count(),
                "iterations": iterations,
                "cold_load_iterations": cold_runs,
                "fixture_bytes": {
                    "cold_bundle": sum(
                        len(data)
                        for data in reg.get("bench.cold-bundle@1.0.0").asset_bytes.values()
                    ),
                    "loaded_catalog": sum(
                        sum(len(data) for data in c.asset_bytes.values()) for c in reg.contracts()
                    ),
                    "rendered_messages": contract.render(warm_inputs).total_utf8_bytes,
                    "output_json": len(warm_output_raw.encode("utf-8")),
                },
            },
            "metrics": {
                "cold_load_100kib": _summarize_ms(cold_samples_ms),
                "warm_render_10kib_10vars": _summarize_ms(warm_render_samples_ms),
                "warm_validate_output_10kib_25props": _summarize_ms(warm_output_samples_ms),
                "peak_heap_mib": round(peak_bytes / (1024.0 * 1024.0), 4),
            },
            "targets": {
                "cold_load_p95_ms_max": 100.0,
                "warm_render_p95_ms_max": 5.0,
                "warm_validate_output_p95_ms_max": 2.0,
                "peak_heap_mib_max": 8.0,
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run prompt-contracts latency and memory benchmarks."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Number of warm iterations to run (default: 1000).",
    )
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="Exit non-zero if p95 latency or peak heap exceeds plan targets.",
    )
    args = parser.parse_args(argv)

    report = run_benchmarks(max(10, args.iterations))
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")

    if args.enforce_thresholds:
        metrics = report["metrics"]
        targets = report["targets"]
        failures: list[str] = []
        if metrics["cold_load_100kib"]["p95_ms"] > targets["cold_load_p95_ms_max"]:
            failures.append(
                f"cold_load_100kib p95 {metrics['cold_load_100kib']['p95_ms']} ms > "
                f"{targets['cold_load_p95_ms_max']} ms"
            )
        if metrics["warm_render_10kib_10vars"]["p95_ms"] > targets["warm_render_p95_ms_max"]:
            failures.append(
                "warm_render_10kib_10vars p95 "
                f"{metrics['warm_render_10kib_10vars']['p95_ms']} ms > "
                f"{targets['warm_render_p95_ms_max']} ms"
            )
        if (
            metrics["warm_validate_output_10kib_25props"]["p95_ms"]
            > targets["warm_validate_output_p95_ms_max"]
        ):
            failures.append(
                "warm_validate_output_10kib_25props p95 "
                f"{metrics['warm_validate_output_10kib_25props']['p95_ms']} ms > "
                f"{targets['warm_validate_output_p95_ms_max']} ms"
            )
        if metrics["peak_heap_mib"] > targets["peak_heap_mib_max"]:
            failures.append(
                f"peak_heap_mib {metrics['peak_heap_mib']} MiB > {targets['peak_heap_mib_max']} MiB"
            )
        if failures:
            for failure in failures:
                sys.stderr.write(f"BENCHMARK THRESHOLD EXCEEDED: {failure}\n")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

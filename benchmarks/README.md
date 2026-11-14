# Runtime Benchmarks

Run `make benchmark` to emit JSON with Python/OS/machine/dependency versions, iteration counts, cold-load and warm-operation percentiles, and peak additional Python heap.

The generated fixtures include a cold-load bundle and a separate two-message, ten-variable contract with a 25-property output schema. Cold measurements reload and verify the catalog; warm operations reuse the loaded contract. Timings exclude dependency installation and model inference. Peak heap is measured separately with `tracemalloc` over loading, rendering and output validation.

The plan's investigation targets are cold verified load below 100 ms and warm rendering/input validation p95 below 5 ms. The harness also reports local output-validation and heap investigation thresholds; those additional thresholds are not plan acceptance requirements. Shared runners do not enforce absolute latency. `--enforce-thresholds` is an explicit local diagnostic option.

The audit's environment and measurements are retained in `results/2026-11-14-local.json`. They describe that machine and fixture, not a performance guarantee for every consumer.

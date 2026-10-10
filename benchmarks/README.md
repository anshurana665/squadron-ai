# Squadron.AI Benchmarks & Evaluation Suite

This directory contains evaluation pipelines and empirical benchmarking tools for measuring remediation effectiveness and Execution-Verified Patch Confidence (EVPC).

## Evaluation Scripts

- **`eval_security.py`**: Runs evaluation against the Hugging Face `s2e-lab/SecurityEval` dataset, checking pre-audit SAST detection, graph synthesis, and post-audit mitigation.
- **`eval_synthetic.py`**: Asynchronous multi-case benchmark evaluator with concurrency control and rate-limiting.
- **`generate_plots.py`**: Generates publication-ready figures (EVPC distribution, baseline comparison, CWE frequencies) saved to `plots/`.

## Running Evaluations

### 1. Synthetic Dry-Run
```bash
python benchmarks/eval_synthetic.py --test-dry-run
```

### 2. SecurityEval Evaluation
```bash
# Evaluate 5 cases
python benchmarks/eval_security.py 5
```

### 3. Generate Paper Plots
```bash
python benchmarks/generate_plots.py
```
Output charts are generated in `benchmarks/plots/`.

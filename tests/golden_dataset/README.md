# Golden Dataset for EntryAI Platform

This directory contains the curated test corpus for regression testing.

## Directory Structure

```
golden_dataset/
├── inputs/                    # Source documents (PDF, PNG, JPG)
│   ├── invoices/              # Invoice documents
│   ├── leases/                # Lease agreement documents
│   ├── cois/                  # Certificate of Insurance documents
│   ├── quotes/                # Vendor quote documents
│   └── adversarial/           # Edge cases and security tests
│
└── expected_outputs/          # Ground truth for comparison
    ├── invoices/
    ├── leases/
    ├── cois/
    ├── quotes/
    └── adversarial/
```

## Adding New Test Cases

1. Place the source document in the appropriate `inputs/` subfolder
2. Run extraction: `python run_benchmark.py --extract-only`
3. Review and correct the generated output
4. Save to the corresponding `expected_outputs/` subfolder
5. Commit with message: `test: Add golden dataset case <filename>`

## Running the Benchmark

```bash
# Run all tests
python run_benchmark.py

# Run specific document type
python run_benchmark.py --doc-type invoice

# Verbose output
python run_benchmark.py -v

# CI mode (fails on regression)
python run_benchmark.py --ci
```

## Quality Standards

- Each test case must cover a unique edge case
- Expected outputs must be manually verified
- Critical fields must have 100% accuracy requirement
- Document filenames should be descriptive

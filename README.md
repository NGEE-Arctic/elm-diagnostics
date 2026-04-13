# elm-diagnostics

Diagnostics and budget-closure tools for E3SM's ELM land model.

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from elm_diagnostics import Run

run = Run("/path/to/case/run")
print(run.streams)  # {'h0': <xr.Dataset>, ...}
```
# elm-diagnostics

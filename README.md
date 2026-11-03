# sysopt-rightsize

Recommend Kubernetes CPU and memory requests from observed usage, with an
honest cost estimate and explicit risk flags.

Most right-sizing advice is either "set requests equal to P95" or a dashboard
nobody acts on. This tool produces the concrete numbers, the YAML to apply, and
the monthly delta — plus warnings when the current limits are too close to real
usage.

```text
$ sysopt-rightsize examples/workload.json
workload: prod/checkout
pricing:  $0.0420/core-h + $0.0050/GiB-h x 730h

container           cpu p95 cpu request          mem p95 memory request       flags                                       $/mo
------------------------------------------------------------------------------------------------------------------------------
api                   0.310 500m -> 380m         431.7Mi 512Mi -> 512Mi       -                                          +3.68
worker                0.050 200m -> 60m           70.8Mi 128Mi -> 96Mi        cpu_over_requested                         +4.41

total: $23.74 -> $15.66 per month (save $8.09, 34.1%)
```

## Install

```bash
pip install -e .
sysopt-rightsize examples/workload.json

# or without installing
PYTHONPATH=src python -m sysopt_rightsize.cli examples/workload.json
```

## Input

```json
{
  "workload": "checkout",
  "namespace": "prod",
  "pricing": {
    "cpu_core_hour": 0.042,
    "memory_gib_hour": 0.005,
    "hours_per_month": 730
  },
  "containers": [
    {
      "name": "api",
      "current": {
        "cpu_request": "500m",
        "cpu_limit": "1",
        "memory_request": "512Mi",
        "memory_limit": "1Gi"
      },
      "metrics": {
        "cpu": [[1760000000, 0.18], [1760003600, 0.22]],
        "memory": [[1760000000, 398458880], [1760003600, 414187520]]
      }
    }
  ]
}
```

- CPU is in cores, memory is in bytes.
- Samples may be `[timestamp, value]` pairs or plain numbers.
- `pricing` is optional; pass `--cpu-price` / `--memory-price` to override it.

## How the recommendation is computed

| Resource | Request | Limit |
| --- | --- | --- |
| CPU | `max(P95 x 1.20, 10m)`, rounded up to 10m | `max(max x 1.50, request)`, rounded up to 10m |
| Memory | `max(P95 x 1.15, 32Mi)`, rounded up to 16Mi | `max(max x 1.25, request)`, rounded up to 16Mi |

Limits are only emitted when the container already declares one; the tool never
invents a limit where the workload intentionally has none.

The multipliers are deliberately conservative defaults, not universal truths.
Change them per workload:

```bash
sysopt-rightsize examples/workload.json \
  --cpu-headroom 1.4 \
  --memory-headroom 1.25 \
  --cpu-limit-headroom 2.0
```

## Flags

| Flag | Meaning |
| --- | --- |
| `cpu_throttle_risk` | P99 CPU is within 10% of the current CPU limit |
| `memory_oom_risk` | peak memory is within 10% of the current memory limit |
| `cpu_under_requested` | P95 CPU is above the current request |
| `memory_under_requested` | P95 memory is above the current request |
| `cpu_over_requested` | recommended CPU is less than half the current request |
| `memory_over_requested` | recommended memory is less than half the current request |
| `no_cpu_samples` / `no_memory_samples` | not enough data to recommend |

Use `--fail-on-risk` in CI to block a deploy when a container is running close
to its limits.

## Output formats

```bash
# human-readable table (default)
sysopt-rightsize examples/workload.json

# everything, including observations and per-container costs
sysopt-rightsize examples/workload.json --format json

# a Kubernetes patch you can review and apply
sysopt-rightsize examples/workload.json --format yaml
```

```yaml
# prod/checkout
containers:
  - name: api
    resources:
      requests:
        cpu: 380m
        memory: 512Mi
      limits:
        cpu: 500m
        memory: 560Mi
```

## Scope and limits

- The tool is a calculator, not a collector. Feed it samples from Prometheus,
  CloudWatch, or your own exporter.
- Quantiles are linear-interpolated over the samples you provide. Short or
  bursty windows will understate real peaks; use at least a few days of data.
- Recommendations assume the workload keeps its current traffic shape. A
  request change does not change the observed usage.
- Cost estimates use requests, because that is what cluster autoscalers and
  most chargeback models bill against.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## License

MIT
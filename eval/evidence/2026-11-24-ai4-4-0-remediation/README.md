# Evidence AI-4.0 remediation

Reviewed mirror `6667dead49d047c4971f73a95ff47229dc8dc4e9` matched 337 shared product blobs from P-019 local
`d2b5d4869bff35ad9e417bee504c6dbf652258b1` plus the reviewed [G1 patch](../2026-11-24-ai4-4-0/raw/candidate.patch).
The full [candidate patch](raw/candidate.patch) applies to the local base. The [remediation-only patch](raw/reviewed-to-remediation.patch)
applies on top of the reviewed code. The benchmark manifest reports the checked-out base HEAD. The patch SHA in
[gate provenance](raw/gate-patch-sha256.stdout.txt) identifies the actual source and tests.

- `remediation-before-final.*.txt` ran all 20 remediation cases on the reviewed tree with only the [new tests](raw/regression-before.patch) applied.
- `inherited-approval-before.*.txt` ran the original increase-approval regression on `d2b5d48` before Foundation changes.
- Golden used CRLF and the hash-checked P0 historical reference archive. Benchmark retained the report, resolved experiments and per-policy fingerprints. Gate outputs include command line, UTC times, exit codes and environment.
- The checkout contains no workspace `.env`. Tests use temporary SQLite. The PostgreSQL availability probe found no local server or Docker daemon.

Run from the P-019 root in an environment that permits Unix socketpair:

```bash
scratch=$(mktemp -d /tmp/chargepilot-g1-remediation-repro.XXXXXX)
G1_EVIDENCE_OUT="$scratch/evidence" \
  bash eval/evidence/2026-11-24-ai4-4-0-remediation/run_gate.sh "$scratch"
```

To reproduce fail-before, apply the reviewed G1 patch and then only `raw/regression-before.patch` to a checkout of the local base.
Run `python -m pytest tests/test_services/test_safety_event_delivery.py -q -k remediation`. Use the repo's `.simulator` venv.
[Exit codes](raw/exit-codes.tsv) · [Checksums](CHECKSUMS.sha256)

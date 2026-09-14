# Tiny mesh-pack v1 fixture

This deterministic synthetic test fixture was copied without modification from `int-brain-lab/ephys-atlas-web-v2` at commit `58a9418b7408ed3760016173df3a34903280cf24` on 2026-09-14 under the repository owner's direction for the cross-repository extraction spike. It is not Allen geometry and must never be published as scientific data or used as a runtime fallback.

The copied pack contains exactly `manifest.json`, `default.eam3.gz`, and `validation-report.json`. Their encoded byte sizes and SHA-256 identities are declared in the manifest and verified by the tests. The source repository regenerates the fixture deterministically with `just mesh-pack-fixture artifacts/mesh-pack-v1-fixture` and validates it with `just mesh-pack-validate artifacts/mesh-pack-v1-fixture`.

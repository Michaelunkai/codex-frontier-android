# Codex Frontier Web Runtime Provenance

- Upstream repository: `https://github.com/friuns2/codexui` (redirected by GitHub to `friuns2/codex-mobile`)
- Pinned commit: `fac2291b0e606c869d4760f56c0f49172214cb79`
- Commit date: `2026-05-26T23:34:55Z`
- Commit verification: GitHub API reported `verified: true` with reason `valid`
- Source archive SHA-256: `db4b56a89b84ed55ddd9eea7ad0b6623c38456ed848e3ae25245e6834fb0e4f6`
- npm comparison: the public `codexapp` latest tag was `0.1.90` on 2026-07-19; this pinned source is four days newer than that publication and adds project ZIP portability.

Frontier-specific source changes are maintained directly in this directory and compiled with `npm run build`. The build output is copied into the project-owned runtime at `vendor/codexapp-native-npm/node_modules/codexapp/dist` and `dist-cli`; no global CodexApp files are modified.

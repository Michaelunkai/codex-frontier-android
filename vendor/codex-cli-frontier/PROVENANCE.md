# Frontier Codex CLI provenance

- Wrapper package: `@openai/codex@0.144.6`
- Native package: `@openai/codex@0.144.6-linux-arm64`
- Registry tarball: `packages/openai-codex-0.144.6-linux-arm64.tgz`
- SHA-256: `19f0b01b33f273df94191670b2e0e5d0f624b0354e765bfdea5763920b713800`
- Registry SHA-1: `f5e32b1fcd40887e9b49a790be47306bf3d8e09c`

The native package is vendored explicitly because npm reports Termux as Android and therefore omits/refuses the package's Linux OS constraint, even though the published musl ARM64 binary is the correct executable for this environment. This install is project-local and does not alter the shared/global Codex CLI.

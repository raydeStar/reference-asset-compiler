# Security

## Reporting

Report a vulnerability in this repository's code through GitHub's private
vulnerability reporting on the repository's *Security* tab. Use a normal issue
for ordinary setup and usage problems. Private reporting is enabled on this
repository; include a minimal reproduction and the affected commit or release.

## Scope

In scope: the Python, PowerShell, Blender and Unreal scripts in this repository
(`src/`, `scripts/`, `workflows/`, `integrations/`) and the JSON contracts they
read. The launchers are meant to refuse to run when a pinned runner's hash
changes, to never auto-retry inference, and to never kill another process; a
way around any of those is a defect worth reporting.

Out of scope: the upstream projects, model weights, licensed Blender add-ons and
engine binaries that the AI and engine stages use. None of them are shipped
here. `docs/AI_STAGES_SETUP.md` names the pinned commits and revisions; you
clone and download them yourself and should vet those checkouts and weights
against their own projects' advisories before running them.

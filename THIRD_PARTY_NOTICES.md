# Third-party notices

## Cognee Codex integration source

- Project: [topoteretes/cognee-integrations](https://github.com/topoteretes/cognee-integrations).
- Included subtree: `integrations/codex/plugins/cognee`, with the local modifications identified in `NOTICE` and the community changelog.
- Copyright: 2026 Topoteretes UG.
- License: Apache-2.0; the complete upstream license is included at repository root.
- The root license was checked at commit `b132740960181e712f15c76ee80519cbd15fdb5d` on 2026-11-02. This records the license source, not a fabricated exact baseline commit for the pre-existing local code snapshot.
- The verified upstream root and Codex integration directory contained no `NOTICE` file. Existing source comments and attributions are retained.

## Separately installed components

Cognee server, its Python dependencies, embedding/extraction models and optional
Ollama/model installations are not vendored here. Their licensing and setup remain
separate. This source repository does not distribute model weights, API keys,
runtime virtualenvs or caches.

Python standard-library modules are used by the new adapter and portable tests.
No Harness² runtime, paper, experiment output, Codex binaries or private session
data is bundled. Harness² was used as a local development process only.

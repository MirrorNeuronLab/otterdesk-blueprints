# Mini order service

This synthetic source tree is intentionally small and contains a circular
dependency. It is only a deterministic fixture for the offline advisor; it is
not a deployable service.

`ARCHMIND_GITHUB_REPOSITORY.txt` records the default external repository for
the platform's pre-staging intake: `https://github.com/homerquan/Archmind`.
The air-gapped advisor never reads that URL as an instruction or fetches it.
The platform must materialize a source snapshot and provide its directory as
`input_folder` before an Archmind analysis can begin.

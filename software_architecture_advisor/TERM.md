# Terms and operating boundary

Software Architecture Advisor is read-only decision support. It inspects a
staged source snapshot, does not execute project code, does not install project
dependencies, and does not write into the inspected source tree.

The report is an evidence-backed architectural assessment, not a security
audit, production-readiness certification, or guarantee that an improvement
will preserve behavior. A qualified maintainer must validate every generated
implementation prompt, code change, migration, test, and deployment plan.

The isolated analysis run has no network access. A GitHub URL is a request for
OtterDesk's connected intake service to create a shallow, immutable snapshot
before the job starts. If that service is unavailable, provide the source
folder directly. The air-gapped job never fetches, pushes, uploads, or contacts
GitHub or another external service.

The required local model must be installed and licensed by the operator. This
blueprint does not bundle model weights or fetch models at run time.

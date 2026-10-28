# Publication gate

The human owner requires explicit confirmation in the chat before EACH version is pushed, tagged, uploaded as release assets, or published as a GitHub Release. Preparing local files does not authorize publication. Approval of one version never authorizes another.

- Show exact tag, title, release notes, file list and SHA-256 manifest before requesting confirmation.
- Record only actual human approval; never fabricate it or automatically grant it.
- Do not create a chain of unapproved historical commits and push them as ancestors of an approved version.
- Keep pending snapshots, release assets and review material OUTSIDE this repository.
- Do not publish `.env`, data/, token-sync/, cert-backups/, private keys, captures, user logs or mini-program bundles.
- Preserve source provenance. Never label recreated/compatible code as an original historical snapshot.
- Use existing external app modules and keep Windows query/SMTP/proxy behavior separate from release preparation.

# Upload order

The human owner requires main-application versions in ascending semantic-version order, starting with v0.1.0. Approval of the order is not approval to publish any individual version. Ask for that exact version's approval before its push, tag, assets or Release. Never push the saved v1.7.1 tree before earlier versions are approved and published.

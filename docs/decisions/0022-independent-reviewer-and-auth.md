# 0022 — Independent reviewer and production authentication (PROPOSED)

Date: 2026-11-07
Status: PROPOSED — not implemented, not a contract
Scope: design for customer-facing semantic review and publication

This ADR designs the step after the development-only M5.1 milestone. It does not
authorize any customer-facing publication. The current local token remains a
development gate and must not be exposed publicly.

## 1. Goal

A customer-facing report may include a management explanation only when:

1. the reviewer is a **named, qualified, independent person** (not the drafter,
   not an AI, not `local-reviewer`);
2. the reviewer authenticated through **production identity** (OIDC), not a local
   token;
3. the review is bound to the exact claim, evidence and context hashes;
4. the decision is **ADMIT** with every checklist item true;
5. the publication is recorded, auditable, and labelled as reviewed;
6. the whole path is unavailable in `FRP_ENV=production` unless 1–5 hold.

## 2. Roles

| Role | May | Cannot |
|---|---|---|
| Analyst / drafter | create drafts, request review | approve own claim |
| Reviewer | ADMIT / REJECT / UNCERTAIN | review own draft; publish |
| Publisher | release an approved report | change the review |
| Admin | manage registry and IdP | review on behalf of someone else |

Separation of duties: the reviewer's subject must differ from the drafter's
subject. A reviewer with a conflict of interest must recuse; the record stores the
recusal.

## 3. Identity (OIDC)

- Authorization Code + PKCE against the organization's IdP.
- MFA required for the reviewer role.
- Short-lived access tokens (≤ 15 min); refresh rotation; server-side session.
- The API validates `iss`, `aud`, `exp`, `nbf`, signature (JWKS), and the
  `reviewer` role claim; it never trusts a client-supplied reviewer id.
- Reviewer identity is the IdP `sub`; display name comes from the directory.
- Local token routes are disabled when `FRP_ENV=production`.

Open choice: which IdP (existing corporate IdP, Keycloak, Entra, Auth0). This
must be the organization's decision; the design does not assume one.

## 4. Reviewer qualification registry

A tracked, versioned registry (no secrets) with one entry per reviewer:

```json
{
  "schema_version": "frp-reviewer-registry-v1",
  "reviewers": [
    {
      "subject": "<oidc-sub>",
      "display_name": "<name>",
      "role": "REVIEWER",
      "status": "ACTIVE",
      "independent": true,
      "qualified_at": "2026-11-01",
      "qualification_ref": "<training/attestation id>",
      "expires_at": "2027-11-01"
    }
  ]
}
```

Rules:

- Only `ACTIVE`, unexpired, `independent = true` entries may review customer
  claims.
- `local-reviewer` is development-only and never qualifies.
- Qualification requires documented training on the six checks and the
  publication policy.
- Changes to the registry are reviewed changes (Git history), not runtime edits.

## 5. Review record (production)

Fields, in addition to the current record:

- `reviewer_subject` (IdP `sub`), `reviewer_display_name`, `reviewer_role`;
- `qualification_ref`, `independent: true`;
- `publication_channel`: `CUSTOMER`;
- `packet_sha256` over claim, excerpt, context and document identity;
- `idp_issuer`, `idp_audience`, `auth_time`;
- `record_signature` (server key; later asymmetric) and a hash-chain link;
- `environment`: `production`.

Storage: append-only (database with no update/delete grant, or WORM object
storage). No overwrite, no silent correction; a superseding review is a new
record that references the old one. Retention follows the organization's policy.

## 6. Publication channels

| Channel | Reviewer | Auth | Report label |
|---|---|---|---|
| `DEVELOPMENT` | `local-reviewer` | local token | development-only, not independently validated |
| `CUSTOMER` | independent qualified reviewer | OIDC | reviewed by <name> on <date>; semantic review performed |

The channel is determined server-side from the environment, never from the
request body. A `CUSTOMER` decision while `FRP_ENV != production` is refused; a
`DEVELOPMENT` decision in production is refused.

## 7. Gate changes

`decide_publication` / the semantic gate must check:

- channel = CUSTOMER;
- IdP-validated subject in the registry with `independent`, `ACTIVE`, unexpired;
- subject ≠ drafter subject;
- all six checks true, verdict ADMIT;
- claim, excerpt and context hashes match the packet;
- no review already superseded;
- report labelled with the reviewer's name and date.

Missing any item → no management claim; the report stays withheld with a visible
reason.

## 8. Threat model (minimum)

| Threat | Control |
|---|---|
| Forged review record | server signature + append-only store; registry check |
| Reviewer impersonation | OIDC + MFA; no client-supplied identity |
| Replay of an old packet | short expiry, packet hash, single-use review |
| Packet tampering | HMAC (current) → server signature; hashes in record |
| Self-review | drafter subject recorded; subject comparison |
| Collusion | independence declaration, recusal, audit sampling |
| Token leakage | short-lived tokens, no tokens in URLs/logs, server-side sessions |
| Storage tampering | WORM/append-only, backups, integrity checks |
| CSRF/XSS on the form | same-site cookies, CSRF token, output encoding |
| Local token in production | routes disabled when `FRP_ENV=production` |

## 9. Phases

1. **Design + interlock (this ADR).** No code until the IdP and qualification
   decisions are made. Existing production refusal stays.
2. **OIDC + registry.** Add the IdP integration, registry loading, subject-aware
   records, channel gate, and tests (including a customer-channel refusal in
   development).
3. **Customer pilot.** One independent reviewer, one document, one claim;
   audit the record and the report labels.
4. **Scale.** Batch review, multiple documents, evaluation, retention.

## 10. Decisions required from the owner

1. Which IdP (corporate / Keycloak / Entra / Auth0)?
2. Who qualifies reviewers, and what training/attestation is required?
3. Retention period and storage system for review records.
4. Whether a reviewer may also be a publisher (recommended: no).

Until these are decided, the platform stays development-only and no
customer-facing publication path is enabled.

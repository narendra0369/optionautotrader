# OPTIONX V82 AWS host custody audit — operator-reported completion
Date: 2026-11-26 IST
Branch: optionx-v82-readonly-attestation-readiness-20261126
Source commit audited: 96efb7a1811695b8cb098e9ea69c5993dc7a2d18

## Scope and evidence provenance
The AWS operator supplied the console output of the read-only script
`scripts/optionx_v82_aws_workload_custody_audit.sh`.
This document records *operator-reported* local checks. No ChatGPT-side AWS
access, independent host attestation, reproducible third-party verification
or external reviewer approval is claimed.

## Operator-reported result: V82_HOST_READ_ONLY_AUDIT_PASS
PASS:
- EXECUTOR_NONLOGIN
- EXECUTOR_SINGLE_GROUP
- PRIVATE_KEY_ROOT_OWNED
- PRIVATE_KEY_SOURCE_MODE_600
- EXECUTOR_CANNOT_DIRECTLY_READ_SOURCE_KEY
- ORIGINAL_SERVICE_USER_CANNOT_READ_PRIVATE_KEY
- PUBLIC_KEY_FINGERPRINT_MATCH
- ACTIVE_optionx-market-api
- ACTIVE_optionx-owner-receiver
- ACTIVE_optionx-paper-health-watchdog
- ACTIVE_optionx-v54-paper-worker
- ACTIVE_optionx-v58-recovery-observer
- ACTIVE_optionx-v78-executor-staging
- STAGING_User
- STAGING_Group
- STAGING_PrivateNetwork
- STAGING_IPAddressDeny
- STAGING_NoNewPrivileges
- STAGING_ProtectSystem
- STAGING_ProtectHome

End of output:
- INFO: LOCAL_SELF_REPORTED_AUDIT_NOT_INDEPENDENT_ATTESTATION
- INFO: NO_RESTART_NO_SECRET_EXPORT_NO_DB_WRITES_NO_ORDERS
- V82_HOST_READ_ONLY_AUDIT_PASS
- V82_AWS_SECURITY_AUDIT_COMPLETE

## Security decision (unchanged)
LOCAL_HOST_CUSTODY_CHECK=PASS (operator reported)
INDEPENDENT_REMOTE_WORKLOAD_ATTESTATION=NOT_VERIFIED
REVIEWER_INDEPENDENCE=NOT_VERIFIED
WORKER_PROMOTION=FORBIDDEN
LIVE_BUY_SELL_CANCEL=OFF
OWNER_STOP=RETAIN
BROKER_POSITION=DO_NOT_TOUCH

The root-owned 0600 key and service isolation are helpful host controls but
do not prevent a privileged host administrator from impersonating a workload.
No attestation row, promotion, database role change or live order is authorized
by this document.

## Next gate: independently reviewed external provenance
1. Select a verifier who is independently accountable and distinct from owner and AWS root/operator; record conflicts of interest.
2. Use a verifiable trust anchor and deployment/image/host binding; identify exactly what the attestation can and cannot prove.
3. Bind evidence to worker UUID and Ed25519 public-key fingerprint; externally verify challenge freshness, expiry and revocation.
4. Have independent reviewer sign a report outside the operator-controlled trust boundary, then arrange separate review of evidence.
5. Prototype only read-only, deny-first scoped gateway using mock inputs in nonproduction. No production keys or service_role secret on AWS.
6. Re-check V82 diagnostic blockers and owner STOP after independent evidence exists; never self-approve or blindly flip status.

No need to rerun successful V80/V81 proofs or this V82 local audit without a change in custody or service configuration.

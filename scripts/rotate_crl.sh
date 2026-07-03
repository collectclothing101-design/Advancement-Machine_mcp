#!/usr/bin/env bash
# CRL rotation script for test-certs
#
# Regenerates the CRL with a new revoked serial, then re-runs the mTLS
# handshake test harness to verify the new revocation is enforced.
#
# Usage:
#   ./scripts/rotate_crl.sh [--certs-dir test-certs] [--new-serial 02]
#
# Requires: openssl, advancement server running with --crlfile

set -euo pipefail

CERTS_DIR="${CERTS_DIR:-test-certs}"
NEW_SERIAL="${NEW_SERIAL:-02}"
CA_KEY="${CERTS_DIR}/ca.key"
CA_PEM="${CERTS_DIR}/ca.pem"
CRL_PEM="${CERTS_DIR}/crl.pem"
INDEX_FILE="${CERTS_DIR}/index.txt"
SERIAL_FILE="${CERTS_DIR}/serial"

# Generate a fresh client cert to revoke (so we have a new serial to add)
FRESH_KEY="${CERTS_DIR}/rotate_revoke_test.key"
FRESH_CSR="${CERTS_DIR}/rotate_revoke_test.csr"
FRESH_PEM="${CERTS_DIR}/rotate_revoke_test.pem"

echo "=== CRL Rotation Script ==="
echo "Certs dir: ${CERTS_DIR}"
echo "New serial to revoke: ${NEW_SERIAL}"

# Ensure index.txt and serial exist
if [ ! -f "${INDEX_FILE}" ]; then
    touch "${INDEX_FILE}"
fi
if [ ! -f "${SERIAL_FILE}" ]; then
    echo "01" > "${SERIAL_FILE}"
fi

# Generate a throwaway client cert for revocation testing
openssl req -new -newkey rsa:2048 -nodes \
    -keyout "${FRESH_KEY}" \
    -out "${FRESH_CSR}" \
    -subj "/CN=rotate-revoke-test"
openssl x509 -req -in "${FRESH_CSR}" \
    -CA "${CA_PEM}" -CAkey "${CA_KEY}" -CAcreateserial \
    -out "${FRESH_PEM}" -days 1
rm -f "${FRESH_CSR}"

# Revoke the fresh cert
openssl ca -config "${CERTS_DIR}/crl.cnf" \
    -revoke "${FRESH_PEM}" \
    -keyfile "${CA_KEY}" \
    -cert "${CA_PEM}" 2>/dev/null

# Regenerate CRL with the new serial
openssl ca -config "${CERTS_DIR}/crl.cnf" \
    -gencrl -out "${CRL_PEM}" \
    -keyfile "${CA_KEY}" \
    -cert "${CA_PEM}" 2>/dev/null

echo "CRL regenerated at ${CRL_PEM}"
echo "Revoked serials in CRL:"
openssl crl -in "${CRL_PEM}" -text -noout | grep "Serial Number" || true

# Cleanup the throwaway cert (leave revoked in index.txt)
rm -f "${FRESH_KEY}" "${FRESH_PEM}"

# Re-run the mTLS test harness
echo ""
echo "=== Re-running mTLS handshake tests ==="
python tests/test_mtls_handshake.py --certs-dir "${CERTS_DIR}" --format table
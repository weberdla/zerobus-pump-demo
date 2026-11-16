#!/usr/bin/env bash
# Create or remove the Zerobus service principal used by the demo bundle.
#
#   solution/zerobus_sp.sh setup   -p <cli-profile> [-c <catalog>] [-s <secret-scope>]
#   solution/zerobus_sp.sh cleanup -p <cli-profile> [-c <catalog>] [-s <secret-scope>] [-a <app-name>]
#
# setup   Creates the service principal and an OAuth secret (30-day lifetime), stores both in
#         a secret scope, works out the workspace's Zerobus endpoint, and writes the bundle
#         variables to .databricks/bundle/dev/variable-overrides.json.
# cleanup Revokes the USE CATALOG grants of the Zerobus service principal and the HMI app, then
#         deletes the secret scope and the service principal. Run it before `databricks bundle destroy`.
#
# Requires the Databricks CLI (authenticated as a workspace admin) and python3.

set -euo pipefail

SP_NAME="zerobus-pump-demo-simulator"
TARGET="dev"
BUNDLE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OVERRIDES="$BUNDLE_ROOT/.databricks/bundle/$TARGET/variable-overrides.json"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

ACTION="${1:-}"; [ -n "$ACTION" ] || usage; shift
PROFILE="" CATALOG="" SCOPE="zerobus-pump-demo" APP_NAME="zerobus-pump-hmi"  # app name matches the app_name bundle variable
while getopts "p:c:s:a:" opt; do
  case "$opt" in
    p) PROFILE="$OPTARG" ;;
    c) CATALOG="$OPTARG" ;;
    s) SCOPE="$OPTARG" ;;
    a) APP_NAME="$OPTARG" ;;
    *) usage ;;
  esac
done
[ -n "$PROFILE" ] || usage

db() { databricks "$@" -p "$PROFILE"; }
field() { python3 -c "import json,sys; d=json.loads(sys.stdin.read() or 'null'); print($1)"; }

find_sp() {  # prints "<id> <application-id>" if the service principal exists
  db service-principals list --filter "displayName eq \"$SP_NAME\"" -o json |
    field "' '.join([d[0]['id'], d[0]['applicationId']]) if d else ''"
}

default_catalog() {
  db api get /api/2.1/unity-catalog/current-metastore-assignment | field "d['default_catalog_name']"
}

setup() {
  local workspace_id cloud region domain endpoint sp sp_id app_id
  workspace_id=$(db api get /api/2.1/unity-catalog/current-metastore-assignment | field "d['workspace_id']")
  read -r cloud region < <(db api get /api/2.1/unity-catalog/metastore_summary | field "d['cloud'] + ' ' + d['region']")
  case "$cloud" in
    aws)   domain="cloud.databricks.com" ;;
    azure) domain="azuredatabricks.net" ;;
    gcp)   domain="gcp.databricks.com" ;;
    *)     echo "Unknown cloud '$cloud'" >&2; exit 1 ;;
  esac
  endpoint="https://${workspace_id}.zerobus.${region}.${domain}"
  CATALOG="${CATALOG:-$(default_catalog)}"

  sp=$(find_sp)
  if [ -z "$sp" ]; then
    db service-principals create --display-name "$SP_NAME" -o json >/dev/null
    sp=$(find_sp)
    echo "Created service principal $SP_NAME"
  else
    echo "Reusing service principal $SP_NAME"
  fi
  sp_id=${sp% *}; app_id=${sp#* }

  if ! db secrets list-scopes -o json | field "'$SCOPE' in [s['name'] for s in d or []]" | grep -q True; then
    db secrets create-scope "$SCOPE"
    echo "Created secret scope $SCOPE"
  fi
  printf '%s' "$app_id" | db secrets put-secret "$SCOPE" client-id
  # The OAuth secret goes straight from the API response into the scope; it is never printed.
  db service-principal-secrets-proxy create "$sp_id" --lifetime 2592000s -o json |
    python3 -c 'import json,sys; sys.stdout.write(json.load(sys.stdin)["secret"])' |
    db secrets put-secret "$SCOPE" client-secret
  echo "Stored a new OAuth secret (valid 30 days) in scope $SCOPE"

  mkdir -p "$(dirname "$OVERRIDES")"
  python3 - "$OVERRIDES" "$CATALOG" "$endpoint" "$app_id" "$SCOPE" <<'EOF'
import json, sys
path, catalog, endpoint, app_id, scope = sys.argv[1:]
json.dump({"catalog": catalog, "zerobus_endpoint": endpoint,
           "sp_application_id": app_id, "secret_scope": scope}, open(path, "w"), indent=2)
EOF

  cat <<EOF

Bundle variables written to ${OVERRIDES#"$BUNDLE_ROOT"/}:
  catalog            $CATALOG
  zerobus_endpoint   $endpoint
  sp_application_id  $app_id
  secret_scope       $SCOPE

Next:
  databricks bundle deploy -p $PROFILE
  databricks bundle run zerobus_pump_hmi -p $PROFILE     # start the plant screen app
  databricks bundle run zerobus_pump_demo -p $PROFILE    # or click Start demo in the app
EOF
}

revoke_use_catalog() {  # <principal> <description>
  db grants update catalog "$CATALOG" --json "{\"changes\": [{\"principal\": \"$1\", \"remove\": [\"USE_CATALOG\"]}]}" >/dev/null
  echo "Revoked USE CATALOG on $CATALOG from $2"
}

cleanup() {
  local sp sp_id app_id app_sp
  CATALOG="${CATALOG:-$(default_catalog)}"
  sp=$(find_sp)
  if [ -n "$sp" ]; then
    sp_id=${sp% *}; app_id=${sp#* }
    revoke_use_catalog "$app_id" "$SP_NAME"
  fi
  app_sp=$(db apps get "$APP_NAME" -o json 2>/dev/null | field "d['service_principal_client_id']" || true)
  if [ -n "$app_sp" ]; then
    revoke_use_catalog "$app_sp" "app $APP_NAME"
  fi
  if db secrets list-scopes -o json | field "'$SCOPE' in [s['name'] for s in d or []]" | grep -q True; then
    db secrets delete-scope "$SCOPE"
    echo "Deleted secret scope $SCOPE"
  fi
  if [ -n "$sp" ]; then
    db service-principals delete "$sp_id"
    echo "Deleted service principal $SP_NAME"
  fi
  # The bundle variables stay in $OVERRIDES: `databricks bundle destroy` still needs them.
  echo "Next: databricks bundle destroy -p $PROFILE"
}

case "$ACTION" in
  setup) setup ;;
  cleanup) cleanup ;;
  *) usage ;;
esac

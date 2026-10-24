# Todos

- Check if DKIM generation works on new setups
- Implement auto reverse DNS
- Activate IP6
- `global_admin` and the domain managers are reconciled at deploy time only (`tasks/02_manager_ops/rbac_reconcile.yml`, planned by `filter_plugins/mailu_rbac.py`), because the Mailu OIDC fork maps no group claim to a role, so a Keycloak group change takes effect on the next deploy. Options: a group-to-role mapping in the OIDC fork's sign-in handler, or a redeploy after each group change.
- Fix the preceding `kcadm.sh config credentials` failure inside the keycloak container that surfaces during the `web-app-mailu` deploy (Keycloak admin auth path).

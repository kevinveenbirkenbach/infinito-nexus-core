app_name = "infinito_rbac"
app_title = "Infinito RBAC"
app_publisher = "Kevin Veen-Birkenbach"
app_description = "Applies the role groups of a Keycloak sign-in to its account"
app_license = "Infinito.Nexus Community License (Non-Commercial)"

override_whitelisted_methods = {
    "frappe.integrations.oauth2_logins.login_via_keycloak": "infinito_rbac.login.login_via_keycloak",
}

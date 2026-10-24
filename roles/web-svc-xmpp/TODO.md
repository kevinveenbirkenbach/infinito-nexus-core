# Todo

- `meta/services.yml` declares `sso.flavor: oidc`, but ejabberd 26.09 has no OIDC client (`auth_method` takes internal, external, ldap, sql, anonymous, pam, jwt), so `templates/configuration.yml.j2` renders no SSO configuration; options: an `extauth` program that checks passwords against Keycloak, `auth_method: jwt` with Keycloak-issued tokens, or dropping the `sso` service from the role.
- `acl.admin` is a deploy-time snapshot of the `administrator` role, so a group change in Keycloak takes effect only on the next deploy, because ejabberd ACLs cannot query LDAP groups; options: redeploy the role after a group change.
- The vCard map is checked through `mod_http_api` `get_vcard`; what an XMPP client renders over 5222 is not covered by Playwright.

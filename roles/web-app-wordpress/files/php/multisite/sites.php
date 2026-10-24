<?php
// nocheck: mirrored-unit-test - evaluated by `wp eval-file -` inside a booted Multisite network; every call it makes is a global that only the CLI runtime defines
/**
 * Required env:
 *   WORDPRESS_MULTISITE_SITES  base64 of a JSON object
 *     scheme   URL scheme the sites are served on
 *     owner    login of the existing account that owns a created site
 *     domains  canonical domains beyond the network's main site; each one becomes the site of exactly that domain
 *
 * `wp site create --slug=<domain>` placed a site at `<domain>.<network domain>` on a sub-domain network; such a site
 * moves to `<domain>` instead of getting a second site next to it.
 *
 * Stdout, last line: changed | unchanged
 */

$config = json_decode((string) base64_decode((string) getenv('WORDPRESS_MULTISITE_SITES'), true), true, 8, JSON_THROW_ON_ERROR);
$network = get_network();
$owner = get_user_by('login', (string) $config['owner']);
if (!($owner instanceof WP_User)) {
    WP_CLI::error("no WordPress account carries the site owner login {$config['owner']}");
}
$changed = false;

foreach ($config['domains'] as $domain) {
    $domain = strtolower(trim((string) $domain));
    $blog_id = (int) get_blog_id_from_url($domain, $network->path);
    if ($blog_id === 0) {
        $legacy = (int) get_blog_id_from_url($domain . '.' . preg_replace('|^www\.|', '', $network->domain), $network->path);
        if ($legacy !== 0) {
            update_blog_details($legacy, array('domain' => $domain));
            $blog_id = $legacy;
            $changed = true;
        }
    }
    if ($blog_id === 0) {
        $created = wpmu_create_blog($domain, $network->path, $domain, (int) $owner->ID, array('public' => 1), (int) $network->id);
        if (is_wp_error($created)) {
            WP_CLI::error("cannot create the site {$domain}: " . $created->get_error_message());
        }
        $blog_id = (int) $created;
        $changed = true;
    }
    $url = $config['scheme'] . '://' . $domain . untrailingslashit($network->path);
    foreach (array('home', 'siteurl') as $option) {
        if (untrailingslashit((string) get_blog_option($blog_id, $option)) !== $url) {
            update_blog_option($blog_id, $option, $url);
            $changed = true;
        }
    }
    if (get_site($blog_id)->domain !== $domain) {
        WP_CLI::error("the site {$blog_id} still answers on " . get_site($blog_id)->domain . " instead of {$domain}");
    }
}

echo $changed ? "changed\n" : "unchanged\n";

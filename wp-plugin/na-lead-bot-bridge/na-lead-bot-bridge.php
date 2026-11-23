<?php
/**
 * Plugin Name: NA Lead Bot Bridge
 * Description: Connects Wix Lead Bot to this site: private audit pages for leads (with view alerts), website inquiries, portfolio and testimonials, the announcement offer, and draft projects for won clients.
 * Version: 1.0.0
 * Author: NA Developers
 * Requires at least: 5.6
 * Requires PHP: 7.4
 */

if (!defined('ABSPATH')) {
	exit;
}

define('NALB_VERSION', '1.0.0');
define('NALB_DIR', plugin_dir_path(__FILE__));

/* --------------------------------------------------------------------------
 * Audit pages: nadevelopers.com/audit/<business>-<code>/
 * ------------------------------------------------------------------------ */
add_action('init', function () {
	register_post_type('na_audit', array(
		'labels' => array(
			'name' => 'Lead audits',
			'singular_name' => 'Lead audit',
			'menu_name' => 'Lead audits',
		),
		'public' => true,
		'publicly_queryable' => true,
		'exclude_from_search' => true,
		'show_in_nav_menus' => false,
		'show_in_rest' => false,
		'show_ui' => true,
		'menu_icon' => 'dashicons-search',
		'menu_position' => 26,
		'supports' => array('title'),
		'has_archive' => false,
		'rewrite' => array('slug' => 'audit', 'with_front' => false),
		'capability_type' => 'post',
	));
});

register_activation_hook(__FILE__, function () {
	do_action('init');
	flush_rewrite_rules();
	if (!wp_next_scheduled('nalb_daily')) {
		wp_schedule_event(time() + 3600, 'daily', 'nalb_daily');
	}
});
register_deactivation_hook(__FILE__, function () {
	wp_clear_scheduled_hook('nalb_daily');
	flush_rewrite_rules();
});

// Old audits are binned 30 days after they expire.
add_action('nalb_daily', function () {
	$old = get_posts(array(
		'post_type' => 'na_audit',
		'posts_per_page' => 200,
		'fields' => 'ids',
		'meta_query' => array(array(
			'key' => '_nalb_expires',
			'value' => time() - 30 * DAY_IN_SECONDS,
			'compare' => '<',
			'type' => 'NUMERIC',
		)),
	));
	foreach ($old as $id) {
		wp_trash_post($id);
	}
});

function nalb_is_audit() {
	return is_singular('na_audit');
}

// Keep audit pages out of Google and out of every cache, so each visit is seen.
add_filter('wp_robots', function ($robots) {
	if (nalb_is_audit()) {
		$robots['noindex'] = true;
		$robots['nofollow'] = true;
	}
	return $robots;
});
add_filter('wpseo_robots', function ($v) {
	return nalb_is_audit() ? 'noindex, nofollow' : $v;
});
add_filter('wpseo_sitemap_exclude_post_type', function ($exclude, $type) {
	return $type === 'na_audit' ? true : $exclude;
}, 10, 2);
add_filter('wp_sitemaps_post_types', function ($types) {
	unset($types['na_audit']);
	return $types;
});
add_action('template_redirect', function () {
	if (!nalb_is_audit()) {
		return;
	}
	if (!defined('DONOTCACHEPAGE')) {
		define('DONOTCACHEPAGE', true);
	}
	header('X-LiteSpeed-Cache-Control: no-cache');
	header('X-Robots-Tag: noindex, nofollow', true);
	nocache_headers();
}, 1);

add_filter('template_include', function ($template) {
	return nalb_is_audit() ? NALB_DIR . 'templates/audit.php' : $template;
});

// Admin list: who looked, and when.
add_filter('manage_na_audit_posts_columns', function ($cols) {
	$cols['nalb_views'] = 'Views';
	$cols['nalb_last'] = 'Last viewed';
	$cols['nalb_expires'] = 'Expires';
	return $cols;
});
add_action('manage_na_audit_posts_custom_column', function ($col, $id) {
	if ($col === 'nalb_views') {
		echo (int) get_post_meta($id, '_nalb_views', true);
	} elseif ($col === 'nalb_last') {
		$t = (int) get_post_meta($id, '_nalb_last', true);
		echo $t ? esc_html(human_time_diff($t) . ' ago') : '—';
	} elseif ($col === 'nalb_expires') {
		$t = (int) get_post_meta($id, '_nalb_expires', true);
		echo $t ? esc_html(wp_date(get_option('date_format'), $t)) : '—';
	}
}, 10, 2);

/* --------------------------------------------------------------------------
 * REST API for the app (signs in with a WordPress Application Password)
 * ------------------------------------------------------------------------ */
function nalb_can() {
	return current_user_can('edit_posts');
}

add_action('rest_api_init', function () {
	$ns = 'nalb/v1';
	register_rest_route($ns, '/ping', array('methods' => 'GET', 'callback' => 'nalb_ping', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/audit', array('methods' => 'POST', 'callback' => 'nalb_save_audit', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/seen', array('methods' => 'GET', 'callback' => 'nalb_seen', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/inquiries', array('methods' => 'GET', 'callback' => 'nalb_inquiries', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/portfolio', array('methods' => 'GET', 'callback' => 'nalb_portfolio', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/offer', array('methods' => 'GET', 'callback' => 'nalb_offer', 'permission_callback' => 'nalb_can'));
	register_rest_route($ns, '/project', array('methods' => 'POST', 'callback' => 'nalb_project', 'permission_callback' => 'nalb_can'));
	// Public: the audit page reports that it was opened.
	register_rest_route($ns, '/beacon', array('methods' => 'POST', 'callback' => 'nalb_beacon', 'permission_callback' => '__return_true'));
});

function nalb_ping() {
	return array(
		'ok' => true,
		'version' => NALB_VERSION,
		'site' => home_url('/'),
		'user' => wp_get_current_user()->user_login,
		'audits' => (int) wp_count_posts('na_audit')->publish,
	);
}

function nalb_find_audit($domain) {
	$ids = get_posts(array(
		'post_type' => 'na_audit',
		'post_status' => array('publish', 'draft', 'private'),
		'posts_per_page' => 1,
		'fields' => 'ids',
		'meta_key' => '_nalb_domain',
		'meta_value' => $domain,
	));
	return $ids ? (int) $ids[0] : 0;
}

function nalb_save_image($b64, $name) {
	if (!$b64) {
		return '';
	}
	if (strpos($b64, ',') !== false) {
		$b64 = substr($b64, strpos($b64, ',') + 1);
	}
	$bytes = base64_decode($b64, true);
	if ($bytes === false || strlen($bytes) > 6 * 1024 * 1024) {
		return '';
	}
	$info = @getimagesizefromstring($bytes);
	if (!$info || !in_array($info['mime'], array('image/jpeg', 'image/png', 'image/webp'), true)) {
		return '';
	}
	$ext = array('image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp')[$info['mime']];
	$up = wp_upload_bits('nalb-' . $name . '-' . wp_generate_password(8, false) . '.' . $ext, null, $bytes);
	return empty($up['error']) ? $up['url'] : '';
}

function nalb_save_audit(WP_REST_Request $req) {
	$p = $req->get_json_params();
	$domain = sanitize_text_field($p['domain'] ?? '');
	$data = is_array($p['data'] ?? null) ? $p['data'] : array();
	if (!$domain || !$data) {
		return new WP_Error('nalb_bad', 'domain and data are required', array('status' => 400));
	}
	$business = sanitize_text_field($data['business'] ?? $domain);
	$id = nalb_find_audit($domain);
	$post = array(
		'post_type' => 'na_audit',
		'post_status' => 'publish',
		'post_title' => 'Website review for ' . $business,
	);
	if ($id) {
		$post['ID'] = $id;
		$id = wp_update_post($post, true);
	} else {
		// A random tail so nobody can guess other businesses' pages.
		$post['post_name'] = sanitize_title($business) . '-' . strtolower(wp_generate_password(6, false));
		$id = wp_insert_post($post, true);
	}
	if (is_wp_error($id)) {
		return $id;
	}
	$slug = sanitize_title($domain);
	$shot = nalb_save_image($p['screenshot_b64'] ?? '', $slug . '-now');
	$mock = nalb_save_image($p['mockup_b64'] ?? '', $slug . '-mockup');
	if ($shot) {
		update_post_meta($id, '_nalb_shot', esc_url_raw($shot));
	}
	if ($mock) {
		update_post_meta($id, '_nalb_mock', esc_url_raw($mock));
	}
	$days = max(7, min(365, (int) ($p['expires_days'] ?? 60)));
	update_post_meta($id, '_nalb_domain', $domain);
	update_post_meta($id, '_nalb_data', wp_slash(wp_json_encode($data)));
	update_post_meta($id, '_nalb_expires', time() + $days * DAY_IN_SECONDS);
	if (!get_post_meta($id, '_nalb_token', true)) {
		update_post_meta($id, '_nalb_token', wp_generate_password(16, false));
	}
	return array('id' => $id, 'url' => get_permalink($id), 'views' => (int) get_post_meta($id, '_nalb_views', true));
}

function nalb_beacon(WP_REST_Request $req) {
	$id = (int) $req->get_param('id');
	$tok = (string) $req->get_param('t');
	if (!$id || get_post_type($id) !== 'na_audit' || !hash_equals((string) get_post_meta($id, '_nalb_token', true), $tok)) {
		return new WP_REST_Response(array('ok' => false), 200);
	}
	$ua = strtolower($_SERVER['HTTP_USER_AGENT'] ?? '');
	if ($ua === '' || preg_match('/bot|crawl|spider|preview|scan|proofpoint|mimecast|barracuda|headless/', $ua)) {
		return new WP_REST_Response(array('ok' => true), 200);
	}
	// One view per visitor per 30 minutes.
	$ip = $_SERVER['REMOTE_ADDR'] ?? '';
	$key = 'nalb_v_' . md5($id . '|' . $ip . '|' . $ua);
	$now = time();
	if (!get_transient($key)) {
		set_transient($key, 1, 30 * MINUTE_IN_SECONDS);
		update_post_meta($id, '_nalb_views', (int) get_post_meta($id, '_nalb_views', true) + 1);
		if (!get_post_meta($id, '_nalb_first', true)) {
			update_post_meta($id, '_nalb_first', $now);
		}
	}
	update_post_meta($id, '_nalb_last', $now);
	return new WP_REST_Response(array('ok' => true), 200);
}

function nalb_seen(WP_REST_Request $req) {
	$since = (int) $req->get_param('since');
	$ids = get_posts(array(
		'post_type' => 'na_audit',
		'posts_per_page' => 500,
		'fields' => 'ids',
		'meta_query' => array(array('key' => '_nalb_last', 'value' => $since, 'compare' => '>', 'type' => 'NUMERIC')),
	));
	$out = array();
	foreach ($ids as $id) {
		$out[] = array(
			'domain' => get_post_meta($id, '_nalb_domain', true),
			'url' => get_permalink($id),
			'views' => (int) get_post_meta($id, '_nalb_views', true),
			'first' => (int) get_post_meta($id, '_nalb_first', true),
			'last' => (int) get_post_meta($id, '_nalb_last', true),
		);
	}
	return array('now' => time(), 'items' => $out);
}

function nalb_meta_like($meta, $words) {
	foreach ($meta as $k => $v) {
		foreach ($words as $w) {
			if (stripos($k, $w) !== false) {
				return is_array($v) ? (string) reset($v) : (string) $v;
			}
		}
	}
	return '';
}

function nalb_inquiries(WP_REST_Request $req) {
	$after = (int) $req->get_param('after_id');
	$posts = get_posts(array(
		'post_type' => 'na_inquiry',
		'post_status' => 'any',
		'posts_per_page' => 100,
		'orderby' => 'ID',
		'order' => 'ASC',
	));
	$out = array();
	foreach ($posts as $p) {
		if ($p->ID <= $after) {
			continue;
		}
		$meta = get_post_meta($p->ID);
		$out[] = array(
			'id' => $p->ID,
			'date' => get_post_time('c', true, $p),
			'title' => $p->post_title,
			'name' => nalb_meta_like($meta, array('name')),
			'email' => nalb_meta_like($meta, array('email')),
			'type' => nalb_meta_like($meta, array('type', 'service')),
			'website' => nalb_meta_like($meta, array('website', 'url', 'site')),
			'message' => nalb_meta_like($meta, array('message')) ?: wp_strip_all_tags($p->post_content),
			'page' => nalb_meta_like($meta, array('page', 'source')),
		);
	}
	return $out;
}

function nalb_portfolio() {
	$projects = array();
	foreach (get_posts(array('post_type' => 'na_project', 'posts_per_page' => 200, 'post_status' => 'publish')) as $p) {
		$terms = wp_get_post_terms($p->ID, 'na_platform', array('fields' => 'names'));
		$projects[] = array(
			'title' => html_entity_decode(get_the_title($p), ENT_QUOTES),
			'link' => get_permalink($p),
			'image' => get_the_post_thumbnail_url($p, 'medium_large') ?: '',
			'about' => wp_strip_all_tags(get_the_excerpt($p)),
			'platforms' => is_wp_error($terms) ? array() : $terms,
		);
	}
	$reviews = array();
	foreach (get_posts(array('post_type' => 'na_testimonial', 'posts_per_page' => 200, 'post_status' => 'publish')) as $p) {
		$meta = get_post_meta($p->ID);
		$reviews[] = array(
			'by' => html_entity_decode(get_the_title($p), ENT_QUOTES),
			'text' => trim(wp_strip_all_tags($p->post_content)),
			'role' => nalb_meta_like($meta, array('role', 'company', 'source', 'platform')),
		);
	}
	return array('projects' => $projects, 'testimonials' => $reviews);
}

function nalb_offer() {
	$o = get_option('na_ab_options', array());
	return array(
		'enabled' => !empty($o['enabled']),
		'text' => (string) ($o['text'] ?? ''),
		'link_text' => (string) ($o['link_text'] ?? ''),
		'link_url' => (string) ($o['link_url'] ?? ''),
	);
}

function nalb_project(WP_REST_Request $req) {
	$p = $req->get_json_params();
	$title = sanitize_text_field($p['title'] ?? '');
	if (!$title) {
		return new WP_Error('nalb_bad', 'title is required', array('status' => 400));
	}
	$existing = get_posts(array('post_type' => 'na_project', 'post_status' => 'any', 'title' => $title, 'posts_per_page' => 1, 'fields' => 'ids'));
	if ($existing) {
		return array('id' => (int) $existing[0], 'edit' => get_edit_post_link($existing[0], 'raw'), 'existing' => true);
	}
	$id = wp_insert_post(array(
		'post_type' => 'na_project',
		'post_status' => 'draft',
		'post_title' => $title,
		'post_excerpt' => sanitize_text_field($p['about'] ?? ''),
		'post_content' => wp_kses_post($p['note'] ?? ''),
	), true);
	if (is_wp_error($id)) {
		return $id;
	}
	if (!empty($p['platform'])) {
		wp_set_object_terms($id, sanitize_text_field($p['platform']), 'na_platform', false);
	}
	if (!empty($p['url'])) {
		update_post_meta($id, '_nalb_client_url', esc_url_raw($p['url']));
	}
	return array('id' => $id, 'edit' => get_edit_post_link($id, 'raw'), 'existing' => false);
}

<?php
/**
 * Audit page for one lead. Data comes from Wix Lead Bot.
 */
if (!defined('ABSPATH')) {
	exit;
}
$id = get_queried_object_id();
$d = json_decode((string) get_post_meta($id, '_nalb_data', true), true);
$d = is_array($d) ? $d : array();
$shot = (string) get_post_meta($id, '_nalb_shot', true);
$mock = (string) get_post_meta($id, '_nalb_mock', true);
$expires = (int) get_post_meta($id, '_nalb_expires', true);
$expired = $expires && $expires < time();
$token = (string) get_post_meta($id, '_nalb_token', true);
$biz = (string) ($d['business'] ?? get_the_title());
$site = (string) ($d['domain'] ?? '');
$cal = (string) ($d['calendly'] ?? 'https://calendly.com/na-developers');
$wa = (string) ($d['whatsapp_link'] ?? '');
$scores = is_array($d['scores'] ?? null) ? $d['scores'] : array();
$checks = is_array($d['checks'] ?? null) ? $d['checks'] : array();
$fixes = is_array($d['fixes'] ?? null) ? $d['fixes'] : array();
$reviews = is_array($d['testimonials'] ?? null) ? $d['testimonials'] : array();
$overall = isset($d['overall']) ? (int) $d['overall'] : null;
$groups = array('design' => 'Design & experience', 'seo' => 'Google & SEO', 'business' => 'Business & marketing');
$labels = array('performance' => 'Phone speed', 'seo' => 'Google basics', 'accessibility' => 'Easy to use', 'best-practices' => 'Security & quality');

if (!function_exists('nalb_ring')) {
function nalb_ring($score, $label) {
	if ($score === null || $score === '') {
		return '';
	}
	$score = (int) $score;
	$col = $score >= 90 ? '#1F9D55' : ($score >= 50 ? '#F08C2E' : '#E8222B');
	return '<div class="nalb-ring"><svg viewBox="0 0 36 36" aria-hidden="true"><path d="M18 2a16 16 0 1 1 0 32a16 16 0 1 1 0-32" fill="none" stroke="#E9EEF3" stroke-width="3.5"/>'
		. '<path d="M18 2a16 16 0 1 1 0 32a16 16 0 1 1 0-32" fill="none" stroke="' . $col . '" stroke-width="3.5" stroke-dasharray="' . $score . ',100" stroke-linecap="round"/>'
		. '<text x="18" y="21.5" text-anchor="middle">' . $score . '</text></svg><span>' . esc_html($label) . '</span></div>';
}
}

get_header();
?>
<style>
.nalb{--navy:#16212D;--teal:#1E91A8;--red:#E8222B;--muted:#6B7785;--line:#E3E8EF;--soft:#F4F7FA;max-width:980px;margin:0 auto;padding:40px 20px 70px;color:var(--navy);font-size:16px;line-height:1.6}
.nalb *{box-sizing:border-box}
.nalb-hero{background:var(--navy);color:#fff;border-radius:16px;padding:34px 34px 30px;position:relative;overflow:hidden}
.nalb-hero:after{content:"";position:absolute;left:0;right:0;bottom:0;height:5px;background:var(--teal)}
.nalb-kicker{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#9fd8e4;font-weight:700}
.nalb-hero h1{color:#fff;font-size:clamp(26px,4vw,38px);line-height:1.2;margin:8px 0 10px}
.nalb-hero p{color:#c9d3dd;margin:0;max-width:640px}
.nalb-hero .nalb-btn{margin-top:20px}
.nalb-btn{display:inline-block;background:var(--red);color:#fff!important;font-weight:700;padding:14px 26px;border-radius:9px;text-decoration:none!important}
.nalb-btn:hover{filter:brightness(1.08)}
.nalb-btn.alt{background:#fff;color:var(--navy)!important;border:1px solid var(--line)}
.nalb-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px;margin-top:22px}
.nalb-card h2{font-size:22px;margin:0 0 14px;color:var(--navy)}
.nalb-rings{display:flex;flex-wrap:wrap;gap:22px;justify-content:space-around}
.nalb-ring{text-align:center;width:120px}
.nalb-ring svg{width:92px;height:92px}
.nalb-ring text{font-size:10px;font-weight:700;fill:var(--navy)}
.nalb-ring span{display:block;font-size:13px;color:var(--muted);margin-top:4px}
.nalb-two{display:grid;grid-template-columns:1fr 1fr;gap:22px}
.nalb-two figure{margin:0;text-align:center}
.nalb-two img{max-width:100%;border-radius:12px;border:1px solid var(--line);box-shadow:0 10px 30px rgba(22,33,45,.10)}
.nalb-two figcaption{font-size:13px;color:var(--muted);margin-top:8px;font-weight:600}
.nalb-list{list-style:none;margin:0;padding:0}
.nalb-list li{padding:10px 0 10px 34px;border-top:1px solid var(--line);position:relative}
.nalb-list li:first-child{border-top:0}
.nalb-list li:before{position:absolute;left:0;top:10px;width:22px;height:22px;border-radius:11px;text-align:center;line-height:22px;font-size:12px;font-weight:700}
.nalb-list li.bad:before{content:"\2715";background:#FDE8E9;color:var(--red)}
.nalb-list li.ok:before{content:"\2713";background:#E5F6EC;color:#1F9D55}
.nalb-list li.fix:before{content:"\2192";background:#E3F4F7;color:var(--teal)}
.nalb-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:22px}
.nalb-groups h3{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 6px}
.nalb-quote{background:var(--soft);border-radius:12px;padding:18px 20px;margin-top:12px}
.nalb-quote .stars{color:#F5A623;letter-spacing:2px}
.nalb-quote small{color:var(--muted)}
.nalb-cta{text-align:center;background:var(--soft);border:0}
.nalb-cta p{color:var(--muted);margin:6px 0 18px}
.nalb-cta .nalb-btn{margin:4px}
.nalb-foot{font-size:13px;color:var(--muted);text-align:center;margin-top:24px}
@media (max-width:700px){.nalb-two{grid-template-columns:1fr}.nalb-hero{padding:26px 22px}.nalb-card{padding:20px}}
</style>
<main class="nalb">
<?php if ($expired) : ?>
	<section class="nalb-hero">
		<div class="nalb-kicker">NA Developers · Free website review</div>
		<h1>This review for <?php echo esc_html($biz); ?> has expired</h1>
		<p>Websites change quickly, so we keep these reviews up for a limited time. Book a free 15-minute call and we'll go through a fresh one with you.</p>
		<a class="nalb-btn" href="<?php echo esc_url($cal); ?>">Book a free 15-minute call &rarr;</a>
	</section>
<?php else : ?>
	<section class="nalb-hero">
		<div class="nalb-kicker">Free website review · prepared by NA Developers</div>
		<h1><?php echo esc_html($biz); ?>: what's holding your website back</h1>
		<p>We checked <?php echo esc_html($site); ?> on a phone, the way most of your customers see it, and against what Google looks for. Here's what we found and what we'd fix.</p>
		<a class="nalb-btn" href="<?php echo esc_url($cal); ?>">Book a free 15-minute call &rarr;</a>
	</section>

	<?php if ($scores || $overall !== null) : ?>
	<section class="nalb-card">
		<h2>Your scores<?php echo $overall !== null ? ' · overall ' . (int) $overall . '/100' : ''; ?></h2>
		<div class="nalb-rings">
			<?php foreach ($labels as $k => $l) {
				echo nalb_ring($scores[$k] ?? null, $l); // phpcs:ignore WordPress.Security.EscapeOutput
			} ?>
		</div>
	</section>
	<?php endif; ?>

	<?php if ($shot || $mock) : ?>
	<section class="nalb-card">
		<h2><?php echo $mock ? 'Today vs. what it could look like' : 'Your homepage on a phone today'; ?></h2>
		<div class="nalb-two" <?php echo ($shot && $mock) ? '' : 'style="grid-template-columns:1fr;max-width:320px;margin:0 auto"'; ?>>
			<?php if ($shot) : ?><figure><img src="<?php echo esc_url($shot); ?>" alt="<?php echo esc_attr($biz); ?> website today on a phone" loading="lazy"><figcaption>Today</figcaption></figure><?php endif; ?>
			<?php if ($mock) : ?><figure><img src="<?php echo esc_url($mock); ?>" alt="New design idea for <?php echo esc_attr($biz); ?>" loading="lazy"><figcaption>Our idea for you</figcaption></figure><?php endif; ?>
		</div>
	</section>
	<?php endif; ?>

	<?php if ($checks) : ?>
	<section class="nalb-card">
		<h2>What we checked</h2>
		<div class="nalb-groups">
		<?php foreach ($groups as $g => $title) :
			$items = array_values(array_filter($checks, function ($c) use ($g) {
				return is_array($c) && ($c['group'] ?? '') === $g;
			}));
			if (!$items) {
				continue;
			}
			usort($items, function ($a, $b) {
				return (int) !empty($a['ok']) - (int) !empty($b['ok']);
			}); ?>
			<div><h3><?php echo esc_html($title); ?></h3><ul class="nalb-list">
			<?php foreach ($items as $c) : ?>
				<li class="<?php echo !empty($c['ok']) ? 'ok' : 'bad'; ?>"><?php echo esc_html((string) ($c['text'] ?? '')); ?></li>
			<?php endforeach; ?>
			</ul></div>
		<?php endforeach; ?>
		</div>
	</section>
	<?php endif; ?>

	<?php if ($fixes) : ?>
	<section class="nalb-card">
		<h2>What we'd fix first</h2>
		<ul class="nalb-list">
		<?php foreach (array_slice($fixes, 0, 8) as $f) : ?>
			<li class="fix"><?php echo esc_html((string) $f); ?></li>
		<?php endforeach; ?>
		</ul>
	</section>
	<?php endif; ?>

	<?php if ($reviews) : ?>
	<section class="nalb-card">
		<h2>What our clients say</h2>
		<?php foreach (array_slice($reviews, 0, 3) as $r) :
			if (!is_array($r) || empty($r['text'])) {
				continue;
			} ?>
			<div class="nalb-quote"><div class="stars">★★★★★</div>
				<div>&ldquo;<?php echo esc_html((string) $r['text']); ?>&rdquo;</div>
				<small><?php echo esc_html((string) ($r['by'] ?? '')); ?></small></div>
		<?php endforeach; ?>
	</section>
	<?php endif; ?>

	<section class="nalb-card nalb-cta">
		<h2>Want us to walk you through it?</h2>
		<p>Free 15-minute call on Zoom or phone. No obligation, and you get a fixed written quote afterwards.</p>
		<a class="nalb-btn" href="<?php echo esc_url($cal); ?>">Book a free call &rarr;</a>
		<?php if ($wa) : ?><a class="nalb-btn alt" href="<?php echo esc_url($wa); ?>">Chat on WhatsApp</a><?php endif; ?>
	</section>
	<p class="nalb-foot">Wix Legend Partner · about 2,000 websites built in 8 years.
		<?php if ($expires) : ?>This review is available until <?php echo esc_html(wp_date(get_option('date_format'), $expires)); ?>.<?php endif; ?></p>
<?php endif; ?>
</main>
<?php if (!is_user_logged_in() && !$expired) : ?>
<script>
(function(){try{var b=JSON.stringify({id:<?php echo (int) $id; ?>,t:<?php echo wp_json_encode($token); ?>});
var u=<?php echo wp_json_encode(rest_url('nalb/v1/beacon')); ?>;
setTimeout(function(){fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:b,keepalive:true,credentials:'omit'});},1500);}catch(e){}})();
</script>
<?php endif; ?>
<?php get_footer(); ?>

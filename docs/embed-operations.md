# Publisher embed operations

This runbook covers the paid publisher forecast embed, its entitlement gateway,
and the iframe fallback. The Origin-and-token flow is browser-grade hotlink
deterrence, tier gating, metering, and a commercial control; it does not
authenticate the requester. Any publisher that needs an enforceable issuance
boundary should use `browser_issue: false` and mint short-lived tokens on its
own server with its publisher secret.

## 1. Deploy

Set the three required environment variables before importing the WSGI module.
There are no defaults: a missing variable or invalid registry prevents the
service from starting.

```sh
export PUBLISHERS_FILE=/srv/wc-embed/private/publishers.yaml
export BUNDLE_ROOT=/srv/wc-embed/publisher-bundles/current
export METER_PATH=/var/log/wc-embed/publisher-usage.jsonl
PYTHONPATH=src gunicorn \
  --workers 4 \
  --bind 127.0.0.1:8080 \
  --pid /run/wc-embed-gateway.pid \
  wcmodel.embedsvc.wsgi:application
```

Run behind TLS and a reverse proxy. Serve the versioned files from
`dashboard-ui/dist-embed/` as immutable static assets. A CDN may cache only
those static files. It must never cache `/v1/*`, including apparently harmless
error or status responses: shared caching of an authorized body bypasses the
token check, can return the wrong per-origin CORS header, and can outlive
publisher revocation. The gateway's bundle responses are deliberately
`private`; the token and frame responses are `no-store`.

The iframe HTML route reads the built
`dashboard-ui/dist-embed/embed-frame.html`. Its `/wc-embed-frame.js` and
`/wc-embed-frame.css` references must be served by the same gateway origin (the
reverse proxy can serve those two immutable files directly).

## 2. Install, SRI, and CSP

Publish each release at a new immutable prefix. Never replace bytes under an
existing version. These hashes match the current `v1.0.0` example build; the
release operator must regenerate and substitute them whenever the asset bytes
change:

```sh
openssl dgst -sha384 -binary dashboard-ui/dist-embed/wc-embed.js \
  | openssl base64 -A
openssl dgst -sha384 -binary dashboard-ui/dist-embed/wc-embed.css \
  | openssl base64 -A
```

Direct-embed installation:

```html
<link
  rel="stylesheet"
  href="https://cdn.forecasts.example/v1.0.0/wc-embed.css"
  integrity="sha384-KmH9VX+FuPmcZSu4dtCgSGiOg3gYHLtCUpXvoygSakEzgsg3OFriXECfc5gyS+M9"
  crossorigin="anonymous"
>
<div
  data-wc-embed
  data-endpoint="https://gateway.forecasts.example"
  data-publisher-id="daily-news"
  data-tournament="wc2026"
  data-surface="schedule"
></div>
<script
  defer
  src="https://cdn.forecasts.example/v1.0.0/wc-embed.js"
  integrity="sha384-4VqbSJTzWkYwj8yJozsUi+Z7lfmmpbR4wRiUA++xN6C8jgv2wg/iukCRrFfyKbtl"
  crossorigin="anonymous"
></script>
<script
  defer
  src="https://cdn.forecasts.example/v1.0.0/wc-embed-init.js"
  crossorigin="anonymous"
></script>
```

`wc-embed-init.js` is external so strict-CSP publishers do not need
`unsafe-inline`. Publish this initializer under the same immutable release
prefix, generate its own SRI after writing the final bytes, and add that
`integrity` value to the second script tag:

```js
document.querySelectorAll('[data-wc-embed]').forEach((node) => {
  const { endpoint, publisherId, tournament, surface } = node.dataset;
  window.WCEmbed.mount(node, { endpoint, publisherId, tournament, surface });
});
```

Merge these exact source allowances into the publisher's existing policy,
substituting the real origins:

```text
script-src https://cdn.forecasts.example
style-src https://cdn.forecasts.example
connect-src https://gateway.forecasts.example
frame-src https://gateway.forecasts.example
```

The first three directives support the direct embed. `frame-src` is also
required for the iframe path. The gateway adds
`Content-Security-Policy: frame-ancestors <publisher origins>` to the entitled
frame response.

For hard style isolation, use the onboarding-issued frame key:

```html
<iframe
  title="Forecast schedule"
  src="https://gateway.forecasts.example/v1/frame/daily-news?k=ONBOARDING_FRAME_KEY&tournament=wc2026&surface=schedule"
  loading="lazy"
></iframe>
```

Treat the long-lived frame key like an entitlement credential. Do not put it in
analytics events, support screenshots, or public source repositories.

## 3. Tiers and entitlement boundaries

- **Basic:** ladder and schedule surfaces, one registered origin, and one
  supported embed.
- **Advanced:** everything in Basic, plus internal match-detail surfaces, the
  documented fixture feed, and up to three registered origins.

Any JSON delivered to a browser is extractable by the publisher. These tiers
gate the documented product surface, supported integrations, and contractual
use; they are not cryptographic controls over data the browser has received.
The direct Origin-and-token pair deters browser hotlinking but does not prove
entitlement. The framekey plus `frame-ancestors` has the same honest browser
boundary. Use server-side token issuance when the publisher must keep its
secret and issuance decision off the browser.

## 4. Daily update and atomic publication

Run every command from the repository root. The Asian Cup example is:

```sh
PYTHONPATH=src .venv/bin/python scripts/daily_update.py \
  --latest \
  --tournament config/tournament_ac2027.yaml

PYTHONPATH=src .venv/bin/python scripts/build_publisher_bundle.py \
  --src data/dashboard/2027-01-07T000000Z \
  --out /srv/wc-embed/publisher-bundles/releases/2027-01-07/ac2027 \
  --tournament ac2027
```

Use the cutoff directory actually printed by `daily_update.py`; the timestamp
above is illustrative. The publisher builder projects out restricted fields
and strings, writes a manifest, validates the entire temporary tree, and then
swaps atomically. A failed build leaves the prior live bundle intact.

Publish every successful tree under a new versioned release directory. Switch
the `current` symlink only after all tournaments for that release validate:

```sh
ln -s /srv/wc-embed/publisher-bundles/releases/2027-01-07 \
  /srv/wc-embed/publisher-bundles/current.next
mv -Tf /srv/wc-embed/publisher-bundles/current.next \
  /srv/wc-embed/publisher-bundles/current
curl --fail --silent https://gateway.forecasts.example/v1/status
```

Never `rsync` into the live tree in place; readers must see either the complete
old release or the complete new release.

## 5. Revocation, reload, and refresh behavior

The registry is loaded once when the WSGI module is imported. After removing a
publisher or changing its expiry/origins in `publishers.yaml`, reload every
Gunicorn worker:

```sh
sudo systemctl reload wc-embed-gateway
```

Configure that unit's `ExecReload` to send `HUP` to the Gunicorn master. Confirm
the replacement workers loaded successfully before closing the incident.
Previously issued tokens have a maximum lifetime of 15 minutes; a removed
publisher is rejected as soon as all workers have reloaded. A publisher whose
unchanged `valid_until` date passes is rejected by the per-request active-date
check.

Embeds do not poll or auto-refresh bundle data. A long-lived tab continues to
show the snapshot it already loaded until the host page reloads or remounts the
embed. Revocation cannot erase data already delivered to that browser.

## 6. Metering and invoicing

Metering deliberately fails open: a log write error increments the worker's
in-process error count but never turns an entitled response into an outage.
Availability wins over revenue integrity. Alert on filesystem errors and on
gaps where successful `/v1/status` pings show the service was up but a
publisher's per-day token/bundle line counts unexpectedly fall to zero.

The meter contains one append-only JSON line per successful token, top-level
bundle, or fixture response. Generate the monthly invoice attachment with:

```sh
PYTHONPATH=src .venv/bin/python scripts/publisher_usage_report.py \
  --meter /var/log/wc-embed/publisher-usage.jsonl \
  --month 2027-01 \
  --out /srv/wc-embed/reports/usage
```

Review the report's malformed-line count and reconcile active-day counts
against status monitoring before invoicing. Preserve the raw meter according
to the contracted retention period.

## 7. Support boundaries and privacy

Supported inputs are the documented `WCEmbed.mount` options, CSS custom
properties, registered exact origins, the two direct surfaces, advanced detail
navigation, and the entitled iframe URL. Publisher DOM rewrites, private API
dependencies, scraped fields, arbitrary CSS overrides, and unregistered
origins are outside support.

The direct embed is scoped, not isolated. Host `!important` rules and other
aggressive selectors can still affect descendants. Only the entitled iframe
path provides a hard style boundary.

The client uses no cookies, local storage, session storage, fingerprinting, or
cross-origin services beyond the configured gateway. The application meter
stores only UTC day, publisher ID, and path class; it does not store reader IP,
page URL, user agent, or a per-reader identifier. Reverse-proxy/CDN access logs
are a separate system and must follow the publisher contract and retention
policy. Do not claim Origin authenticates a human or organization.

## 8. Accessibility release checklist

- Give every iframe a concise, surface-specific `title`.
- Use the keyboard to reach stage, detail, and back buttons; verify Enter and
  Space activate them without submitting an ancestor form.
- Confirm visible focus remains clear under every supported theme.
- Check heading order, table headers, `aria-pressed` stage state, and the
  announced uncertainty/coverage-gap text with a screen reader.
- Verify text and non-text contrast for the publisher's custom properties.
- Test reflow at 200% zoom and narrow mobile widths without horizontal loss of
  controls or forecast meaning.
- Confirm meaning is not conveyed by color alone and probability distributions
  retain text labels.
- Run the no-naked-number and publisher embed guards before every release, then
  perform one real-browser keyboard and screen-reader smoke test for both the
  direct and iframe paths.

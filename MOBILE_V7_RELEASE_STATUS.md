# OptionX V7 Mobile Update — Prepared, 24 Nov 2026

## Shipped to isolated V7 staging
- Android/Chrome PWA install capability with a secure manifest
- Working 192 px + 512 px PNG icons (verified by Node zlib inflate)
- Standalone display, premium navy / muted champagne gold design
- Mobile-friendly broker navigation and Stoxkart read-only login controls
- Quick-start shortcuts to Paper Auto and Broker Setup
- Browser Add-to-Home-Screen install option
- Offline notice that explicitly says trading and background paper engine do not run
- Service worker caches **only** the inert offline screen and public icons.
  Broker/OAuth callback, Supabase authentication, chart data and saved
  trading research are never put in an offline cache.
- Mobile Stoxkart login guidance uses a regular Chrome tab to preserve
  same-tab third-party redirect state.
- Native Flutter companion source patch:
  mobile_flutter/lib/optionx_v7_broker_hub.dart
  Opens trusted V7 in the external browser without embedded WebView or
  credential persistence; preserves original dark navy/champagne-gold style.

## Verified
- Render V7 frontend staging: mobile manifest, icon format and decompression,
  static asset packaging, restricted service-worker routing and existing
  strategy/paper/broker UI tests passed.
- Render V7 backend staging: 97 offline Python tests passed on the earlier
  Stoxkart integration commit; mobile changes are frontend-only and did not
  enable any backend order route.
- Production V6 unchanged by mobile additions; all real orders OFF.

## Not asserted as complete
- No signed Android APK is produced: the existing Flutter app source and
  Android package/signing configuration need user-provided current source
  before merging and verifying the Flutter widget.
- Flutter SDK/analyzer/build/device testing has NOT been run on this patch.
- Phone-specific browser install prompt, backgrounding and broker redirect
  have not been tested on the user's actual device.
- Official Stoxkart real-account login and order permissions require the
  owner to connect and verify separately. Mocked tests are not broker-live
  evidence.
- Automated real-money Buy/Sell is intentionally unavailable, as are
  broker-native SL, Target, idempotent real order reconciliation.

## Android install
Open https://optionx-v7-frontend-test-staging.onrender.com in Chrome,
then tap the Chrome three-dot menu -> Install app / Add to Home screen.
Some Android/browser combinations show different wording or no prompt.

For the first Stoxkart login, use the regular Chrome tab rather than
the installed standalone icon because cross-site third-party redirects
may move into another browsing context.

## Flutter safe merge
See mobile_flutter/README.md and
mobile_flutter/lib/optionx_v7_broker_hub.dart.
Backup original Flutter app sources before using the patch; never
overwrite main.dart, signed APK, or local research database automatically.

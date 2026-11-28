# OptionX AI Trader — Android / Flutter V7 Broker Update

**Status:** Native Flutter integration patch prepared, **not compiled into an
APK**. The existing installed Flutter app and local FastAPI database were not
touched or replaced.

The OptionX cloud V7 **installable PWA** is built from the same GitHub V7
branch and is the usable Android browser version of the broker setup.
This folder includes a **drop-in native Flutter screen** to be merged into
the original Flutter project after checking its current files.

## Included

- mobile_flutter/lib/optionx_v7_broker_hub.dart — premium dark navy /
  champagne-gold screen for Stoxkart, Angel One, Delta Exchange, and Paper Auto
- Stoxkart first-time login launches the external Chrome/browser, not an
  embedded WebView. Password/TOTP are entered only on the official broker site.
- No broker credential storage, native secret handling or order posting.
- Real Buy/Sell execution remains hard-blocked on the backend.

## Integrate without replacing existing app

1. Back up the full current Flutter source folder. Do not assume an older
   archive exactly matches the edited Windows project.
2. Copy mobile_flutter/lib/optionx_v7_broker_hub.dart into your existing
   Flutter project's lib/ directory.
3. In the Flutter project terminal run:

       flutter pub add url_launcher

4. Import at the top of the relevant navigation screen:

       import 'optionx_v7_broker_hub.dart';

   Add a navigation tile/button opening:

       Navigator.of(context).push(
         MaterialPageRoute(builder: (_) => const OptionXV7BrokerHub()),
       );

5. Run flutter analyze, existing tests, flutter build apk --debug, and an
   actual Android-device browser OAuth callback test. **Native Flutter tests
   and APK build were NOT run here** because the latest complete Flutter
   project and Android signing keys were not present in connected GitHub.
6. Do not blindly change the legacy localhost apiBase. The old mobile app
   uses a different local API, not the current V7 Supabase-authenticated
   cloud. This broker hub opens secure V7 in Chrome and uses its login.
7. Verify user login, callback, read-only profile and NFO positions, app
   resume, token expiry, logout and phone sleep/restart. Test before signing
   an upgrade APK with the original app's package identity/versionCode.

Do not share keystore passwords, broker PINs, API keys or TOTP in chat.

## Mobile PWA installation now

Open https://optionx-v7-frontend-test-staging.onrender.com in Android Chrome,
select browser menu -> Add to Home Screen or Install app (if supported).

- HTTPS manifest; 192 and 512 PNG icons; compact mobile navigation.
- Service worker caches only a safe offline screen and decorative icons.
- Broker OAuth callbacks, personal broker data, Supabase session responses,
  chart candles, saved backtests and paper trading responses are NEVER cached.
- Offline shows an offline / real orders OFF screen. Paper Auto does not
  continue when the app tab is closed or network is unavailable.
- Initial Stoxkart broker redirect should be done in a regular Chrome browser
  tab; cross-site login in standalone PWA mode can lose tab-scoped flow state.

## Release gates

Native Flutter APK is not built or signed. Existing APK remains unchanged.
No actual broker login has been performed by these offline tests, and
unattended auto-trading exchange/broker approval is unverified. All real
buy/sell orders remain OFF.

GitHub V7 draft PR: https://github.com/narendra0369/optionautotrader/pull/1
Stoxkart setup: live_v7/STOXKART_READONLY_SETUP.md

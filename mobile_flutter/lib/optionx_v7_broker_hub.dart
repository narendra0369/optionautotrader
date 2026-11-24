// OptionX native Flutter V7 broker hub drop-in (NO order submission).
//
// This file is intentionally independent of the legacy localhost FastAPI
// client and its signed APK. It launches the separately authenticated V7
// HTTPS website in the device's default browser. No broker login ever occurs
// in a Flutter WebView and no tokens are copied between app/browser.
//
// Dependency: flutter pub add url_launcher
// Integration: Navigator.of(context).push(MaterialPageRoute(
//   builder: (_) => const OptionXV7BrokerHub(),
// ));
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class OptionXV7BrokerHub extends StatelessWidget {
  const OptionXV7BrokerHub({super.key});

  static const _gold = Color(0xFFD6B36A);
  static const _navy = Color(0xFF090D14);
  static const _panel = Color(0xFF171D29);
  static const _muted = Color(0xFFADB8C7);
  static const _host = 'optionx-v7-frontend-test-staging.onrender.com';

  Uri _url(String fragment) {
    if (!{'live', 'paper', 'lab', 'markets', 'dashboard'}.contains(fragment)) {
      throw ArgumentError.value(fragment, 'fragment', 'Not an approved OptionX destination');
    }
    return Uri.https(_host, '/').replace(fragment: fragment);
  }

  Future<void> _open(BuildContext context, String fragment) async {
    // Android's default browser handles Stoxkart's official password/TOTP
    // login and same-tab authorization redirect. No embedded WebView.
    final destination = _url(fragment);
    try {
      if (!await launchUrl(destination, mode: LaunchMode.externalApplication)) {
        if (context.mounted) _message(context, 'Chrome could not open the secure OptionX V7 site.');
      }
    } catch (_) {
      if (context.mounted) _message(context, 'Could not open secure browser. Please retry with Chrome.');
    }
  }

  void _message(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Widget _brokerCard(BuildContext context, {
    required String broker,
    required String markets,
    required String note,
  }) {
    return Card(
      color: _panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFF334359)),
      ),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(broker, style: const TextStyle(
            color: _gold, fontSize: 18, fontWeight: FontWeight.w700,
          )),
          const SizedBox(height: 6),
          Text(markets, style: const TextStyle(
            color: Colors.white, fontSize: 13,
          )),
          const SizedBox(height: 8),
          Text(note, style: const TextStyle(
            color: _muted, fontSize: 12, height: 1.5,
          )),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => _open(context, 'live'),
            icon: const Icon(Icons.open_in_browser, size: 19),
            label: Text('Open $broker secure broker setup'),
            style: OutlinedButton.styleFrom(
              foregroundColor: _gold,
              side: const BorderSide(color: Color(0xFF8E7959)),
              minimumSize: const Size.fromHeight(45),
            ),
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _navy,
      appBar: AppBar(
        backgroundColor: _navy,
        foregroundColor: _gold,
        title: const Text('OPTIONX · Brokers', style: TextStyle(
          fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: 0.3,
        )),
      ),
      body: SafeArea(child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
        children: [
          const Text('V7 broker connections', style: TextStyle(
            color: Colors.white, fontSize: 23, fontWeight: FontWeight.w700,
          )),
          const SizedBox(height: 6),
          const Text('Stoxkart, Angel One and Delta Exchange. '
            'Sign in to OptionX in Chrome for owner-bound read-only verification.',
            style: TextStyle(color: _muted, height: 1.5)),
          const SizedBox(height: 16),
          DecoratedBox(
            decoration: BoxDecoration(
              color: const Color(0xFF282025),
              border: Border.all(color: const Color(0xFF80505A)),
              borderRadius: BorderRadius.circular(13),
            ),
            child: const Padding(
              padding: EdgeInsets.all(14),
              child: Row(children: [
                Icon(Icons.lock_outline, color: Color(0xFFF1A8AD)),
                SizedBox(width: 10),
                Expanded(child: Text(
                  'REAL MONEY AUTO TRADING: OFF\n'
                  'Read-only account verification; no broker orders.',
                  style: TextStyle(color: Colors.white, fontSize: 12,
                                  fontWeight: FontWeight.w600, height: 1.4),
                )),
              ]),
            ),
          ),
          const SizedBox(height: 18),
          _brokerCard(context,
            broker: 'Stoxkart Superr API',
            markets: 'NIFTY / BANKNIFTY · CE / PE / Futures',
            note: 'The API developer key/secret is entered only on the '
              'secure V7 website. Your broker password and TOTP belong '
              'on the official Stoxkart login page. Account profile and '
              'NFO positions are read-only.',
          ),
          _brokerCard(context,
            broker: 'Angel One SmartAPI',
            markets: 'NIFTY / BANKNIFTY · CE / PE / Futures',
            note: 'Temporary profile login on secure V7 site. '
              'Registered static IP and separate approval are required for real orders.',
          ),
          _brokerCard(context,
            broker: 'Delta Exchange India',
            markets: 'BTC derivatives · contract research',
            note: 'Public contract explorer and route preferences. '
              'Private broker read and real orders are not enabled.',
          ),
          const SizedBox(height: 9),
          FilledButton.icon(
            onPressed: () => _open(context, 'paper'),
            style: FilledButton.styleFrom(
              backgroundColor: _gold, foregroundColor: _navy,
              minimumSize: const Size.fromHeight(49),
            ),
            icon: const Icon(Icons.science_outlined),
            label: const Text('Open Paper Auto in Chrome'),
          ),
          const SizedBox(height: 12),
          const Text(
            'The older installed Flutter APK is separate from V7 cloud login. '
            'This page does not modify that APK or its local FastAPI database. '
            'Paper Auto runs only while the web tab stays active.',
            style: TextStyle(color: _muted, fontSize: 11, height: 1.5),
          ),
        ],
      )),
    );
  }
}

# WingRock for iPhone

WingRock is the live, in-cockpit view: a thin native shell around the web app in `../web/`. Swift receives
the OnFlight Hub's 50 Hz UDP frames and pushes each raw 67-byte frame into a `WKWebView` running the same
three.js app the Python bridge serves. No computer in the loop.

```
ios/
  project.yml                 XcodeGen spec — regenerate the .xcodeproj with `xcodegen generate`
  WingRock.xcodeproj          generated (committed)
  WingRock/
    WingRockApp.swift         SwiftUI app: full screen, status bar hidden, screen never sleeps
    WebView.swift             WKWebView + acro:// scheme serving the bundled web/ folder; frames pushed via
                              evaluateJavaScript; web settings mirrored to UserDefaults (window.acroStore)
    HubListener.swift         BSD UDP socket bound to 0.0.0.0:2000
    WingRock.entitlements     multicast entitlement — NOT wired in by default (see below)
    Assets.xcassets           app icon: the Eagle rendered top-down by web/icon.html
```

## Install on your iPhone

1. Open `ios/WingRock.xcodeproj` in Xcode. Signing is Automatic under team `R6P52BJ2K9` (already on this Mac).
2. Plug the phone in with USB and unlock it. First time only: on the phone enable
   Settings → Privacy & Security → **Developer Mode** (restart), then trust the Mac when asked.
3. Pick the phone as the run destination (top bar) and press Run (⌘R).
4. First launch: Settings → General → VPN & Device Management → trust your developer certificate, then open
   WingRock. Allow the **Local Network** prompt.
5. Join the phone to the Hub's Wi-Fi ("OnFlight Hub …") before flying. INS init takes ~45 s outdoors.

A free Apple ID installs fine but the app expires after 7 days (re-run from Xcode); the paid Developer
Program ($99/yr) gives year-long installs and TestFlight — and is required for the entitlement below.

## Real-time data: the broadcast catch

The Hub *broadcasts* its frames. Since iOS 16, an app only receives broadcast UDP if its provisioning
profile carries `com.apple.developer.networking.multicast`. Without it WingRock runs but shows "no data"
next to the Hub. Two ways forward, which can run in parallel:

**A. Relay from a Mac (works today).** On a Mac joined to the Hub's Wi-Fi:

```bash
python run_relay.py <phone IP on the Hub network>     # Settings → Wi-Fi → ⓘ on the phone
```

Unicast needs no entitlement, so the phone shows the live flight with the Mac temporarily in the loop.
Good for validating the whole chain in the airplane before Apple answers.

**B. Request the multicast entitlement (no computer, the goal).**
1. Be enrolled in the Apple Developer Program as Account Holder (free accounts cannot get it).
2. Fill in <https://developer.apple.com/contact/request/networking-multicast> with the bundle ID
   `org.livefreeandfly.wingrock` and a plain description, e.g.: *"Receives UDP broadcast telemetry
   (port 2000) from an aerobatic flight-data logger — the Bolder Flight OnFlight Hub — on the logger's own
   Wi-Fi access point. The device only broadcasts; it has no unicast mode. Traffic is local, in-cockpit,
   non-commercial."* Apple typically answers within days to two weeks.
3. When approved: developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → the App ID →
   enable **Multicast Networking**. Then wire the entitlement into the build by adding to `project.yml`
   under the target:
   ```yaml
   entitlements:
     path: WingRock/WingRock.entitlements
     properties:
       com.apple.developer.networking.multicast: true
   ```
   and `xcodegen generate`. Automatic signing regenerates the profile; rebuild, install, done.

## Simulator

`python run_fake_hub.py` sends recorded frames to loopback, which the simulator shares with the Mac.

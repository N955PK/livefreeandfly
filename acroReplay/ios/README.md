# acroReplay for iPhone

A thin native shell around the web app in `../web/`: Swift receives the OnFlight Hub's
50 Hz UDP broadcast on port 2000 and pushes each raw 67-byte frame into a `WKWebView`
running the same three.js app the Python bridge serves. No computer in the loop.

```
ios/
  project.yml                 XcodeGen spec — regenerate the .xcodeproj with `xcodegen generate`
  AcroReplay.xcodeproj        generated (committed for convenience)
  AcroReplay/
    AcroReplayApp.swift       SwiftUI app: full screen, status bar hidden, screen never sleeps
    WebView.swift             WKWebView + acro:// scheme handler serving the bundled web/ folder;
                              pushes frames via evaluateJavaScript("acroReplay.frame(b64, wall)")
    HubListener.swift         BSD UDP socket bound to 0.0.0.0:2000
    AcroReplay.entitlements   com.apple.developer.networking.multicast (needed for broadcast on device)
```

The web app detects the shell (`window.webkit.messageHandlers.acro`), decodes frames with
`web/onflight.js`, does the frame math in `web/frames.js`, and posts `ready` to start the
listener. Nothing else in the web app differs from bridge mode.

## Build and run in the simulator

1. Install Xcode from the App Store (the Command Line Tools alone cannot build iOS apps), then
   `sudo xcode-select -s /Applications/Xcode.app` once.
2. `brew install xcodegen` (already installed on this Mac) and, after editing `project.yml`,
   `cd ios && xcodegen generate`.
3. Open `ios/AcroReplay.xcodeproj`, pick an iPhone simulator, Run.
4. Feed it data — the simulator shares the Mac's loopback:

   ```bash
   python run_fake_hub.py                              # recorded fixture frames → 127.0.0.1:2000
   python run_fake_hub.py --replay captures/<stamp>/moving.pcap
   ```

   The app should go LIVE within a second and follow the recorded hand rotations.

## Run on your iPhone

1. Apple Developer Program membership ($99/yr) under team `R6P52BJ2K9` (the identity already
   on this Mac). Signing is set to Automatic in `project.yml`.
2. Request the multicast entitlement once, at
   <https://developer.apple.com/contact/request/networking-multicast> — say the app receives an
   avionics data logger's UDP broadcast on the device's own Wi-Fi network. Until it is granted,
   device builds fail signing with the entitlement present; temporarily comment out the
   `entitlements:` block in `project.yml` to install, knowing broadcast reception will be
   blocked on iOS 16+ until the profile carries it.
3. Plug in the phone, select it as the run destination, Run. Trust the developer certificate
   under Settings → General → VPN & Device Management the first time.
4. On the phone: join the "OnFlight Hub …" Wi-Fi, open acroReplay, allow the Local Network
   prompt. INS init takes ~45 s outdoors; then LIVE.

Battery/heat notes for the cockpit are in `../PLAN.md` §7.1.

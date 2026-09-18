import AVFoundation
import SwiftUI
import UIKit
import WebKit

/// Hosts the three.js web app (bundled `web/` folder, served over the `acro://app/` scheme so ES modules work),
/// pushes the Hub's raw INS frames into it as base64, and feeds it the phone's GPS position.
final class WebController: NSObject, ObservableObject, WKScriptMessageHandler {
    let webView: WKWebView
    private let listener = HubListener()
    private let location = LocationProvider()
    private let recorder = FlightRecorder()
    private let speech = AVSpeechSynthesizer()
    private var queued: [(String, TimeInterval)] = []
    private let queueLock = NSLock()
    private var flushScheduled = false
    private var inFlight = false
    private static let maxQueued = 250   // 5 s of frames; beyond that the page is stuck and old frames are useless

    override init() {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: "acro")
        config.userContentController.addUserScript(WKUserScript(source: WebController.storeScript(), injectionTime: .atDocumentStart,
                                                                forMainFrameOnly: true))
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()
        Self.activateAudioSession()   // Web Audio (the live cue + its Test) needs an active .playback session to sound
        config.userContentController.add(self, name: "acro")
        webView.isOpaque = true
        webView.backgroundColor = .black
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.load(URLRequest(url: URL(string: "acro://app/index.html")!))
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? String else { return }
        if body == "ready" {
            listener.start { [weak self] data, wall in
                self?.enqueue(data, wall: wall)
                self?.recorder.record(data, wall: wall)
            }
            location.start(onFix: { [weak self] lat, lon, acc in self?.eval("acroReplay.location(\(lat),\(lon),\(acc))") },
                           onError: { [weak self] msg in self?.eval("acroReplay.locationError(\(Self.jsString(msg)))") })
        } else if body.hasPrefix("store:") {
            WebController.store(body)
            if body.hasPrefix("store:acroReplay.box:") { recorder.setBox(String(body.dropFirst("store:acroReplay.box:".count))) }
            if body.hasPrefix("store:acroReplay.model:") { recorder.setModel(String(body.dropFirst("store:acroReplay.model:".count))) }
        } else if body.hasPrefix("say:") {
            speak(String(body.dropFirst("say:".count)))
        } else if body.hasPrefix("seqstart:") {
            recorder.startSequence(title: String(body.dropFirst("seqstart:".count)))
        } else if body == "seqstart" {
            recorder.startSequence(title: "Sequence")
        } else if body == "seqend" {
            recorder.endSequence()
        } else if body == "flights" {
            let json = (try? JSONSerialization.data(withJSONObject: FlightRecorder.list())).flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
            eval("acroReplay.flights(\(json))")
        } else if body.hasPrefix("export:") {
            exportImage(String(body.dropFirst("export:".count)))
        } else {
            NSLog("[web] %@", body)
        }
    }

    /// Settings the web app wants to survive app restarts (box, ground mode) live in UserDefaults under "web.<key>"
    /// and are injected as `window.acroStore` before the page runs. Message format: `store:<key>:<value>`.
    private static let storePrefix = "web."

    private static func store(_ message: String) {
        let payload = message.dropFirst("store:".count)
        guard let sep = payload.firstIndex(of: ":") else { return }
        let key = String(payload[..<sep]), value = String(payload[payload.index(after: sep)...])
        if value.isEmpty { UserDefaults.standard.removeObject(forKey: storePrefix + key) }
        else { UserDefaults.standard.set(value, forKey: storePrefix + key) }
    }

    private static func storeScript() -> String {
        var saved: [String: String] = [:]
        for (key, value) in UserDefaults.standard.dictionaryRepresentation() where key.hasPrefix(storePrefix) {
            if let s = value as? String { saved[String(key.dropFirst(storePrefix.count))] = s }
        }
        let json = (try? JSONSerialization.data(withJSONObject: saved)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        return "window.acroStore = \(json);"
    }

    /// Frames arrive at 50 Hz on the socket thread. They're batched into one JavaScript call per main-thread
    /// turn and delivered strictly one call at a time, so a slow render frame in the web process delays frames
    /// rather than dropping them, and the page sees at most one interruption per display refresh.
    private func enqueue(_ data: Data, wall: TimeInterval) {
        queueLock.lock()
        queued.append((data.base64EncodedString(), wall))
        if queued.count > Self.maxQueued { queued.removeFirst(queued.count - Self.maxQueued) }
        let schedule = !flushScheduled
        flushScheduled = true
        queueLock.unlock()
        if schedule { DispatchQueue.main.async { self.flush() } }
    }

    private func flush() {
        guard !inFlight else { return }   // the completion handler calls flush() again
        queueLock.lock()
        let batch = queued
        queued.removeAll(keepingCapacity: true)
        flushScheduled = false
        queueLock.unlock()
        guard !batch.isEmpty else { return }
        let args = batch.map { "'\($0.0)',\($0.1)" }.joined(separator: ",")
        inFlight = true
        webView.evaluateJavaScript("acroReplay.frames([\(args)])") { [weak self] _, _ in
            guard let self else { return }
            self.inFlight = false
            self.flush()
        }
    }

    /// A `.playback` session so both Web Audio (live cue / Test) and speech sound, over the ring/silent switch and
    /// out whatever route is active. Activated at startup, not only on first speech, so the cue works standalone.
    private static func activateAudioSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default, options: [.duckOthers, .allowBluetoothA2DP])
        try? session.setActive(true)
    }

    /// Save/share a PNG the web app exported (payload is "<filename>:<base64>"): write it to a temp file and present
    /// the iOS share sheet (Photos, Files, AirDrop, Print).
    private func exportImage(_ payload: String) {
        guard let sep = payload.firstIndex(of: ":") else { return }
        let name = String(payload[payload.startIndex..<sep])
        guard let data = Data(base64Encoded: String(payload[payload.index(after: sep)...])) else { return }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name.isEmpty ? "sequence.png" : name)
        try? data.write(to: url)
        DispatchQueue.main.async {
            guard let root = self.webView.window?.rootViewController else { return }
            let av = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            av.popoverPresentationController?.sourceView = self.webView   // iPad needs a popover anchor
            av.popoverPresentationController?.sourceRect = CGRect(x: self.webView.bounds.midX, y: self.webView.bounds.midY, width: 1, height: 1)
            root.present(av, animated: true)
        }
    }

    /// Spoken critique through whatever the phone's audio is routed to (headset over Bluetooth, or the speaker).
    private func speak(_ text: String) {
        Self.activateAudioSession()
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        utterance.postUtteranceDelay = 0.2
        speech.speak(utterance)
    }

    private func eval(_ script: String) {
        DispatchQueue.main.async { self.webView.evaluateJavaScript(script) { _, _ in } }
    }

    private static func jsString(_ s: String) -> String {
        let data = try? JSONSerialization.data(withJSONObject: [s])
        let array = data.flatMap { String(data: $0, encoding: .utf8) } ?? "[\"\"]"
        return String(array.dropFirst().dropLast())
    }
}

struct WebView: UIViewRepresentable {
    let controller: WebController

    func makeUIView(context: Context) -> WKWebView { controller.webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

/// Serves files from the bundled `web/` folder. A real scheme (not file://) gives the page an origin,
/// which `<script type="module">` and the import map require.
final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    private static let mimeTypes = [
        "html": "text/html", "js": "text/javascript", "mjs": "text/javascript", "css": "text/css",
        "json": "application/json", "png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml", "ico": "image/x-icon",
        "obj": "text/plain", "mtl": "text/plain", "bin": "application/octet-stream",
    ]

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url, let webDir = Bundle.main.url(forResource: "web", withExtension: nil) else {
            task.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        let relative = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        // Recorded flights live in Documents/Flights, everything else in the bundled web/ folder.
        let file = relative.hasPrefix("flights/")
            ? FlightRecorder.directory.appendingPathComponent(String(relative.dropFirst("flights/".count)).replacingOccurrences(of: "/", with: ""))
            : webDir.appendingPathComponent(relative.isEmpty ? "index.html" : relative)
        guard let data = try? Data(contentsOf: file) else {
            task.didReceive(HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1", headerFields: nil)!)
            task.didFinish()
            return
        }
        let headers = ["Content-Type": Self.mimeTypes[file.pathExtension] ?? "application/octet-stream",
                       "Content-Length": String(data.count), "Cache-Control": "no-cache"]
        task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

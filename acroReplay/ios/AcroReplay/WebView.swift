import SwiftUI
import WebKit

/// Hosts the three.js web app (bundled `web/` folder, served over the `acro://app/` scheme so ES modules work)
/// and pushes each raw INS frame from the Hub into it as base64.
final class WebController: NSObject, ObservableObject, WKScriptMessageHandler {
    let webView: WKWebView
    private let listener = HubListener()
    private var pending = 0

    override init() {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: "acro")
        config.userContentController.addUserScript(WKUserScript(source: WebController.storeScript(), injectionTime: .atDocumentStart,
                                                                forMainFrameOnly: true))
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()
        config.userContentController.add(self, name: "acro")
        webView.isOpaque = false
        webView.backgroundColor = .black
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.load(URLRequest(url: URL(string: "acro://app/index.html")!))
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? String else { return }
        if body == "ready" {
            listener.start { [weak self] data, wall in self?.push(data, wall: wall) }
        } else if body.hasPrefix("store:") {
            WebController.store(body)
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

    private func push(_ data: Data, wall: TimeInterval) {
        let call = "acroReplay.frame('\(data.base64EncodedString())',\(wall))"
        DispatchQueue.main.async {
            guard self.pending < 5 else { return }
            self.pending += 1
            self.webView.evaluateJavaScript(call) { _, _ in self.pending -= 1 }
        }
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
        "obj": "text/plain", "mtl": "text/plain",
    ]

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url, let webDir = Bundle.main.url(forResource: "web", withExtension: nil) else {
            task.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        let relative = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let file = webDir.appendingPathComponent(relative.isEmpty ? "index.html" : relative)
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

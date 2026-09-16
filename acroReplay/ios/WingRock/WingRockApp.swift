import SwiftUI

@main
struct WingRockApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .ignoresSafeArea()
                .statusBarHidden(true)
                .persistentSystemOverlays(.hidden)
                .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        }
    }
}

struct ContentView: View {
    @StateObject private var controller = WebController()

    var body: some View {
        WebView(controller: controller)
            .background(Color.black)
    }
}

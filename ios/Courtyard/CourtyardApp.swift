import SwiftUI

@main
struct CourtyardApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .tint(CourtyardTheme.green)
                .preferredColorScheme(.light)
        }
    }
}

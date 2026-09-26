import SwiftUI

struct RootView: View {
    @EnvironmentObject private var model: AppModel
    @State private var notices = false
    @State private var serverSheet = false

    var body: some View {
        NavigationStack {
            Group {
                if model.loading && model.community == nil {
                    ProgressView("Opening Sunrise Court")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(CourtyardTheme.paper)
                } else if model.community == nil {
                    offline
                } else if model.isStaff {
                    StaffView()
                } else {
                    TabView(selection: $model.section) {
                        FeedView()
                            .tabItem { Label("Feed", systemImage: "text.bubble") }
                            .tag("feed")
                        EventsView()
                            .tabItem { Label("Your events", systemImage: "calendar") }
                            .tag("events")
                        MessagesView()
                            .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }
                            .tag("messages")
                            .badge(model.messageUnread)
                        FriendsView()
                            .tabItem { Label("Friends", systemImage: "person.2") }
                            .tag("friends")
                    }
                }
            }
            .navigationTitle("Courtyard")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(model.headerHidden ? .hidden : .visible, for: .navigationBar)
            .animation(.easeOut(duration: 0.2), value: model.headerHidden)
            .onChange(of: model.section) { _, _ in
                model.headerHidden = false
            }
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Image("Wordmark")
                        .resizable()
                        .scaledToFit()
                        .frame(height: 22)
                        .accessibilityLabel("Courtyard")
                }
                ToolbarItem(placement: .topBarLeading) {
                    if !model.isStaff {
                        Button {
                            notices = true
                        } label: {
                            Label("Notices", systemImage: model.unreadCount > 0 ? "bell.badge" : "bell")
                        }
                        .accessibilityLabel(model.unreadCount > 0 ? "Notices, \(model.unreadCount) unread" : "Notices")
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        if let residents = model.community?.residents {
                            ForEach(residents) { person in
                                Button {
                                    Task { await model.switchAccount(person.id) }
                                } label: {
                                    Label {
                                        Text(person.name)
                                    } icon: {
                                        AvatarView(name: person.firstName, hue: person.hue, residentId: person.id, size: 28)
                                    }
                                }
                            }
                        } else {
                            Button("Helen Alvarez") { Task { await model.switchAccount("helen") } }
                        }
                        Button("Front desk") { Task { await model.switchAccount("staff") } }
                        Divider()
                        Button("Server address") { serverSheet = true }
                    } label: {
                        Text(accountLabel)
                    }
                }
            }
        }
        .sheet(isPresented: $notices) { NoticesSheet().environmentObject(model) }
        .sheet(isPresented: $serverSheet) { ServerSheet().environmentObject(model) }
        .task(id: model.viewer) {
            await model.refresh()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(4))
                await model.refresh()
            }
        }
    }

    private var accountLabel: String {
        if model.isStaff { return "Front desk" }
        return model.resident(model.viewer)?.firstName ?? "Account"
    }

    private var offline: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Sunrise Court")
                .font(.largeTitle.weight(.semibold))
            Text(model.status.isEmpty ? "Start the Courtyard server, then open the feed." : model.status)
                .foregroundStyle(CourtyardTheme.muted)
            Button("Try again") { Task { await model.refresh() } }
                .buttonStyle(.borderedProminent)
            Button("Server address") { serverSheet = true }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(CourtyardTheme.paper)
    }
}

struct StatusToast: ViewModifier {
    @EnvironmentObject private var model: AppModel

    func body(content: Content) -> some View {
        content.overlay(alignment: .bottom) {
            if model.community != nil, !model.status.isEmpty {
                Text(model.status)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(CourtyardTheme.ink)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(CourtyardTheme.card, in: Capsule())
                    .overlay(Capsule().stroke(CourtyardTheme.line))
                    .shadow(color: Color.black.opacity(0.06), radius: 8, y: 2)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 8)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: model.status)
    }
}

extension View {
    func statusToast() -> some View {
        modifier(StatusToast())
    }
}

struct NoticesSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                let items = model.community?.notifications ?? []
                if items.isEmpty {
                    Text("No notices yet.")
                        .foregroundStyle(CourtyardTheme.muted)
                } else {
                    ForEach(items) { item in
                        Button {
                            Task { await model.markRead(item.id) }
                        } label: {
                            Text(item.text)
                                .foregroundStyle(CourtyardTheme.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .listRowBackground(item.read ? Color.clear : Color(red: 0.957, green: 0.969, blue: 0.949))
                    }
                }
            }
            .navigationTitle("Notices")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                if model.unreadCount > 0 {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Mark all read") { Task { await model.markRead(nil) } }
                    }
                }
            }
        }
    }
}

struct ServerSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var address = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("http://127.0.0.1:8787", text: $address)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                } footer: {
                    Text("The iOS Simulator can use 127.0.0.1. A real iPhone needs this Mac's address, and the server has to be running.")
                }
            }
            .navigationTitle("Server")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        model.baseURL = address
                        dismiss()
                        Task {
                            model.community = nil
                            await model.refresh()
                        }
                    }
                }
            }
            .onAppear { address = model.baseURL }
        }
    }
}

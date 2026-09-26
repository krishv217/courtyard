import SwiftUI

struct MessagesView: View {
    @EnvironmentObject private var model: AppModel
    @State private var path: [String] = []
    @State private var picking = false

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Button {
                        picking = true
                    } label: {
                        Label("New conversation", systemImage: "square.and.pencil")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    let threads = model.community?.threads ?? []
                    if threads.isEmpty {
                        Text("No conversations yet. Start one, or join a plan and it will show up here.")
                            .foregroundStyle(CourtyardTheme.muted)
                    } else {
                        ForEach(threads) { thread in
                            Button {
                                path = [thread.peerId]
                                Task { await model.markThreadRead(thread.peerId) }
                            } label: {
                                threadRow(thread)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(16)
            }
            .background(CourtyardTheme.paper)
            .modifier(CollapsesHeaderOnScroll(section: "messages"))
            .navigationTitle("Messages")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: String.self) { otherId in
                ThreadView(otherId: otherId)
            }
        }
        .sheet(isPresented: $picking) {
            NewConversationSheet { personId in
                picking = false
                Task {
                    await model.openChat(personId)
                    path = [personId]
                }
            }
            .environmentObject(model)
        }
        .statusToast()
        .onAppear {
            if let id = model.chatWith {
                path = [id]
            }
        }
        .onChange(of: model.chatWith) { _, id in
            if let id {
                path = [id]
            }
        }
        .onChange(of: path) { _, next in
            if next.isEmpty {
                model.chatWith = nil
            }
        }
    }

    private func threadRow(_ thread: MessageThread) -> some View {
        HStack(spacing: 12) {
            AvatarView(
                name: model.resident(thread.peerId)?.firstName ?? thread.peerName,
                hue: model.resident(thread.peerId)?.hue ?? "#1e4a38",
                residentId: thread.peerId
            )
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(thread.peerName)
                        .font(.headline)
                        .foregroundStyle(CourtyardTheme.ink)
                    Spacer()
                    if thread.unread > 0 {
                        Text("\(thread.unread)")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(CourtyardTheme.green, in: Capsule())
                    }
                }
                Text(thread.last?.isEmpty == false ? thread.last! : "Say hello")
                    .font(.subheadline)
                    .foregroundStyle(CourtyardTheme.muted)
                    .lineLimit(2)
            }
        }
        .padding(14)
        .background(CourtyardTheme.card, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(CourtyardTheme.line))
    }
}

struct NewConversationSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    var onPick: (String) -> Void

    private var already: Set<String> {
        Set(model.community?.threads.map(\.peerId) ?? [])
    }

    private var people: [Resident] {
        (model.community?.residents ?? [])
            .filter { $0.id != model.viewer }
            .sorted { left, right in
                let leftNew = !already.contains(left.id)
                let rightNew = !already.contains(right.id)
                if leftNew != rightNew { return leftNew }
                return left.name < right.name
            }
    }

    var body: some View {
        NavigationStack {
            List {
                let fresh = people.filter { !already.contains($0.id) }
                let existing = people.filter { already.contains($0.id) }
                if !fresh.isEmpty {
                    Section("New") {
                        ForEach(fresh) { person in
                            personRow(person)
                        }
                    }
                }
                if !existing.isEmpty {
                    Section("Already chatting") {
                        ForEach(existing) { person in
                            personRow(person)
                        }
                    }
                }
            }
            .navigationTitle("New conversation")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }

    private func personRow(_ person: Resident) -> some View {
        Button {
            onPick(person.id)
        } label: {
            HStack(spacing: 12) {
                AvatarView(name: person.firstName, hue: person.hue, residentId: person.id, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.name)
                        .foregroundStyle(CourtyardTheme.ink)
                    if let tastes = person.tastes, !tastes.isEmpty {
                        Text(tastes.prefix(3).joined(separator: " · "))
                            .font(.subheadline)
                            .foregroundStyle(CourtyardTheme.muted)
                            .lineLimit(1)
                    }
                }
            }
        }
    }
}

struct ThreadView: View {
    @EnvironmentObject private var model: AppModel
    var otherId: String
    @State private var draft = ""
    @State private var suggestion: String?
    @State private var asking = false

    private var thread: MessageThread? {
        model.community?.threads.first { $0.peerId == otherId }
    }

    private var firstName: String {
        model.resident(otherId)?.firstName ?? "them"
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 8) {
                        if let tastes = model.resident(otherId)?.tastes, !tastes.isEmpty {
                            Text(tastes.joined(separator: " · "))
                                .font(.subheadline)
                                .foregroundStyle(CourtyardTheme.muted)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.bottom, 6)
                        }
                        if (thread?.messages ?? []).isEmpty {
                            Text("A quiet start. Say hello, or ask Grok for an idea.")
                                .font(.subheadline)
                                .foregroundStyle(CourtyardTheme.muted)
                                .multilineTextAlignment(.center)
                                .padding(.top, 24)
                        }
                        ForEach(thread?.messages ?? []) { message in
                            bubble(message)
                                .id(message.id)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                }
                .onChange(of: thread?.messages.count) { _, _ in
                    if let last = thread?.messages.last?.id {
                        withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                    }
                }
            }
            composer
        }
        .background(CourtyardTheme.paper)
        .navigationTitle(firstName)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: otherId) {
            await model.markThreadRead(otherId)
        }
        .onChange(of: thread?.unread) { _, unread in
            if (unread ?? 0) > 0 {
                Task { await model.markThreadRead(otherId) }
            }
        }
    }

    private var composer: some View {
        VStack(spacing: 10) {
            if let suggestion {
                suggestionCard(suggestion)
            }
            HStack(alignment: .bottom, spacing: 8) {
                Button {
                    Task { await ask() }
                } label: {
                    if asking {
                        ProgressView()
                            .frame(width: 36, height: 36)
                    } else {
                        Image(systemName: "sparkles")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(CourtyardTheme.green)
                            .frame(width: 36, height: 36)
                            .background(Color(red: 0.898, green: 0.941, blue: 0.910), in: Circle())
                    }
                }
                .disabled(asking)
                .accessibilityLabel("Ask Grok for a suggestion")
                TextField("Message \(firstName)", text: $draft, axis: .vertical)
                    .lineLimit(1...4)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(CourtyardTheme.line))
                Button {
                    let text = draft
                    draft = ""
                    Task { await send(text) }
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.body.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(canSend ? CourtyardTheme.green : CourtyardTheme.line, in: Circle())
                }
                .disabled(!canSend)
                .accessibilityLabel("Send")
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(CourtyardTheme.card)
        .overlay(alignment: .top) { Rectangle().fill(CourtyardTheme.line).frame(height: 1) }
    }

    private var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func suggestionCard(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Grok suggests", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(CourtyardTheme.green)
            ScrollView {
                Text(text)
                    .font(.body)
                    .foregroundStyle(CourtyardTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxHeight: 180)
            HStack {
                Button("Not now") { suggestion = nil }
                    .buttonStyle(.bordered)
                Spacer()
                Button("Send") {
                    suggestion = nil
                    Task { await send(text, suggested: true) }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(14)
        .background(Color(red: 0.933, green: 0.961, blue: 0.941), in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color(red: 0.78, green: 0.88, blue: 0.82)))
    }

    private func ask() async {
        asking = true
        defer { asking = false }
        do {
            suggestion = try await model.suggestPlan(otherId: otherId, text: draft)
        } catch {
            model.status = error.localizedDescription
        }
    }

    private func send(_ text: String, suggested: Bool = false) async {
        do {
            try await model.sendMessage(to: otherId, text: text, suggested: suggested)
        } catch {
            model.status = error.localizedDescription
        }
    }

    @ViewBuilder
    private func bubble(_ message: ChatMessage) -> some View {
        if message.kind == "event" {
            Text(message.text)
                .font(.caption)
                .foregroundStyle(CourtyardTheme.muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(CourtyardTheme.line.opacity(0.45), in: Capsule())
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
        } else {
            let mine = message.senderId == model.viewer
            let fromGrok = message.kind == "suggestion" || message.kind == "agent"
            HStack {
                if mine { Spacer(minLength: 48) }
                VStack(alignment: .leading, spacing: 4) {
                    if fromGrok {
                        Label("Suggested by Grok", systemImage: "sparkles")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(mine ? Color.white.opacity(0.9) : CourtyardTheme.green)
                    }
                    Text(message.text)
                        .foregroundStyle(mine ? Color.white : CourtyardTheme.ink)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                    .background(
                        mine ? CourtyardTheme.green : Color.white,
                        in: UnevenRoundedRectangle(
                            topLeadingRadius: 18,
                            bottomLeadingRadius: mine ? 18 : 5,
                            bottomTrailingRadius: mine ? 5 : 18,
                            topTrailingRadius: 18
                        )
                    )
                    .overlay(
                        UnevenRoundedRectangle(
                            topLeadingRadius: 18,
                            bottomLeadingRadius: mine ? 18 : 5,
                            bottomTrailingRadius: mine ? 5 : 18,
                            topTrailingRadius: 18
                        )
                        .stroke(mine ? Color.clear : CourtyardTheme.line)
                    )
                if !mine { Spacer(minLength: 48) }
            }
        }
    }
}

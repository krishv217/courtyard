import SwiftUI

struct FeedView: View {
    @EnvironmentObject private var model: AppModel
    @State private var filter = "all"
    @State private var composer = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Button {
                    composer = true
                } label: {
                    HStack(spacing: 12) {
                        if let person = model.resident(model.viewer) {
                            AvatarView(name: person.firstName, hue: person.hue, residentId: person.id)
                        }
                        Text("What would you like to do today?")
                            .foregroundStyle(CourtyardTheme.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(.white, in: Capsule())
                            .overlay(Capsule().stroke(CourtyardTheme.line))
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 12)

                Picker("Feed", selection: $filter) {
                    Text("All").tag("all")
                    Text("Friends").tag("friends")
                    Text("Community").tag("community")
                }
                .pickerStyle(.segmented)
                .padding(.bottom, 8)

                let plans = model.visiblePlans(filter: filter)
                if plans.isEmpty {
                    Text(emptyCopy)
                        .foregroundStyle(CourtyardTheme.muted)
                        .padding(.vertical, 24)
                } else {
                    ForEach(plans) { plan in
                        PlanCard(plan: plan, showsMembershipActions: false)
                        Divider()
                    }
                }
            }
            .padding(.horizontal, 16)
        }
        .background(CourtyardTheme.paper)
        .modifier(CollapsesHeaderOnScroll(section: "feed"))
        .refreshable { await model.refresh() }
        .statusToast()
        .sheet(isPresented: $composer) {
            ComposerSheet()
                .environmentObject(model)
        }
    }

    private var emptyCopy: String {
        switch filter {
        case "friends": return "Nothing from friends yet. Open plans are under Community."
        case "community": return "No open plans yet."
        default: return "Nothing posted yet."
        }
    }
}

struct ComposerSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var time = "11:30"
    @State private var friendsOnly = true
    @State private var preview = ""
    @State private var posting = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Suggestions") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(CourtyardTheme.choices, id: \.0) { choice in
                                Button(choice.0) {
                                    text = choice.1
                                    Task { await loadPreview() }
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }
                Section {
                    Toggle("Friends only", isOn: $friendsOnly)
                    Picker("Meet at", selection: $time) {
                        ForEach(CourtyardTheme.times, id: \.self) { slot in
                            Text(slot).tag(slot)
                        }
                    }
                }
                Section("Your note") {
                    TextField("A walk, or your own plan like golf or a grocery trip.", text: $text, axis: .vertical)
                        .lineLimit(3...6)
                        .onChange(of: text) { _, _ in
                            Task { await loadPreview() }
                        }
                }
                if !preview.isEmpty {
                    Section("What others can see") {
                        Text(preview)
                    }
                }
            }
            .navigationTitle("New plan")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Post") { Task { await post() } }
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || posting)
                }
            }
        }
    }

    private func loadPreview() async {
        let note = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !note.isEmpty else {
            preview = ""
            return
        }
        do {
            let decision = try await model.preview(text: note, time: time)
            if decision.kind == "plan" {
                let cards = decision.cards ?? (decision.card.map { [$0] } ?? [])
                let reach = friendsOnly ? "Only friends can see this." : "Anyone at Sunrise Court can join."
                preview = cards.map { "\($0.activity) in the \($0.place) at \($0.time). \(reach)" }.joined(separator: "\n")
            } else if decision.kind == "emergency" {
                preview = decision.summary ?? "This stays with the front desk."
            } else {
                preview = "Nothing goes on the board."
            }
            if let withheld = decision.withheld, !withheld.isEmpty {
                preview += "\nKept private: \(withheld.joined(separator: ", "))."
            }
        } catch {
            preview = ""
        }
    }

    private func post() async {
        posting = true
        defer { posting = false }
        do {
            try await model.postNote(text: text, time: time, friendsOnly: friendsOnly)
            dismiss()
        } catch {
            preview = error.localizedDescription
        }
    }
}

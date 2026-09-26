import SwiftUI

struct FriendsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                requests
                friends
                suggestions
                directory
            }
            .padding(16)
        }
        .background(CourtyardTheme.paper)
        .modifier(CollapsesHeaderOnScroll(section: "friends"))
        .refreshable { await model.refresh() }
        .statusToast()
    }

    @ViewBuilder
    private var requests: some View {
        let incoming = model.community?.incoming ?? []
        if !incoming.isEmpty {
            Text("Requests").font(.title2.weight(.semibold))
            ForEach(incoming) { person in
                FriendRow(personId: person.id, detail: "Wants to be friends") {
                    Button("Accept") { Task { await model.changeFriend(person.id, action: "accept") } }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
    }

    @ViewBuilder
    private var friends: some View {
        let people = model.community?.friends ?? []
        Text("Friends").font(.title2.weight(.semibold))
        if people.isEmpty {
            Text("No friends yet. Accept a request, or add someone below.")
                .foregroundStyle(CourtyardTheme.muted)
        } else {
            ForEach(people) { person in
                FriendRow(personId: person.id, detail: "") {
                    Button("Remove") { Task { await model.changeFriend(person.id, action: "remove") } }
                        .buttonStyle(.bordered)
                }
            }
        }
    }

    @ViewBuilder
    private var suggestions: some View {
        let people = model.community?.suggestions ?? []
        Text("Suggested for you").font(.title2.weight(.semibold))
        if people.isEmpty {
            Text("Join a few plans. People you've been with will show up here.")
                .foregroundStyle(CourtyardTheme.muted)
        } else {
            ForEach(people) { suggestion in
                FriendRow(personId: suggestion.id, detail: sharedLine(suggestion.shared)) {
                    Button("Add") { Task { await model.changeFriend(suggestion.id, action: "request") } }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
    }

    private var directory: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("People at Sunrise Court").font(.title2.weight(.semibold))
            ForEach(otherResidents) { person in
                DirectoryRow(person: person)
            }
        }
    }

    private var otherResidents: [Resident] {
        let friends = model.community?.friends.map(\.id) ?? []
        let incoming = model.community?.incoming.map(\.id) ?? []
        let suggestions = model.community?.suggestions.map(\.id) ?? []
        var known = Set(friends)
        known.formUnion(incoming)
        known.formUnion(suggestions)
        known.insert(model.viewer)
        return (model.community?.residents ?? []).filter { !known.contains($0.id) }
    }

    private func sharedLine(_ count: Int) -> String {
        count == 1 ? "You've been to 1 event together" : "You've been to \(count) events together"
    }
}

struct FriendRow<Trailing: View>: View {
    @EnvironmentObject private var model: AppModel
    var personId: String
    var detail: String
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        let person = model.resident(personId)
        HStack(spacing: 12) {
            Button {
                Task { await model.openChat(personId) }
            } label: {
                HStack(spacing: 12) {
                    AvatarView(name: person?.firstName ?? "?", hue: person?.hue ?? "#1e4a38", residentId: personId)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(person?.name ?? personId).font(.headline).foregroundStyle(CourtyardTheme.ink)
                        if !detail.isEmpty {
                            Text(detail).font(.subheadline).foregroundStyle(CourtyardTheme.muted)
                        }
                        if let tastes = person?.tastes, !tastes.isEmpty {
                            Text(tastes.prefix(3).joined(separator: " · "))
                                .font(.subheadline)
                                .foregroundStyle(CourtyardTheme.muted)
                                .lineLimit(2)
                        }
                    }
                }
            }
            .buttonStyle(.plain)
            Spacer()
            trailing()
        }
    }
}

struct DirectoryRow: View {
    @EnvironmentObject private var model: AppModel
    var person: Resident

    var body: some View {
        let waiting = model.community?.outgoing.contains { $0.id == person.id } ?? false
        HStack(spacing: 12) {
            Button {
                Task { await model.openChat(person.id) }
            } label: {
                HStack(spacing: 12) {
                    AvatarView(name: person.firstName, hue: person.hue, residentId: person.id)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(person.name).font(.headline).foregroundStyle(CourtyardTheme.ink)
                        if waiting {
                            Text("Waiting for them to accept")
                                .font(.subheadline)
                                .foregroundStyle(CourtyardTheme.muted)
                        }
                        if let tastes = person.tastes, !tastes.isEmpty {
                            Text(tastes.prefix(3).joined(separator: " · "))
                                .font(.subheadline)
                                .foregroundStyle(CourtyardTheme.muted)
                                .lineLimit(2)
                        }
                    }
                }
            }
            .buttonStyle(.plain)
            Spacer()
            if waiting {
                Text("Request sent").foregroundStyle(CourtyardTheme.muted)
            } else {
                Button("Add") { Task { await model.changeFriend(person.id, action: "request") } }
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}

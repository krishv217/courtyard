import SwiftUI

struct PlanCard: View {
    @EnvironmentObject private var model: AppModel
    var plan: Plan
    var showsMembershipActions: Bool

    @State private var confirmLeave = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Button {
                if let host = plan.residentIds.first {
                    Task { await model.openChat(host) }
                }
            } label: {
                AvatarView(name: hostName, hue: hostHue, residentId: plan.residentIds.first)
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Button {
                        if let host = plan.residentIds.first {
                            Task { await model.openChat(host) }
                        }
                    } label: {
                        Text(hostName)
                            .font(.headline)
                            .foregroundStyle(CourtyardTheme.ink)
                    }
                    .buttonStyle(.plain)
                    Text(plan.audience == "friends" ? "Friends only" : "Open")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(CourtyardTheme.line, in: Capsule())
                        .foregroundStyle(CourtyardTheme.muted)
                }
                Text("\(plan.activity) · \(plan.place) · \(plan.time)")
                    .foregroundStyle(CourtyardTheme.muted)
                if plan.names.count > 1 {
                    Text("With \(nameList(Array(plan.names.dropFirst())))")
                        .foregroundStyle(CourtyardTheme.muted)
                }
                Text(plan.line ?? "\(plan.names.first ?? "Someone") wants company for \(plan.activity.lowercased()).")
                    .font(.body)
                    .foregroundStyle(CourtyardTheme.ink)
                room
                if showsMembershipActions {
                    inviteList
                }
                actionRow
            }
        }
        .padding(.vertical, 14)
        .confirmationDialog(leaveTitle, isPresented: $confirmLeave, titleVisibility: .visible) {
            Button(leaveTitle, role: .destructive) {
                Task { await model.leave(plan) }
            }
            Button("Keep it", role: .cancel) {}
        }
    }

    private var hostName: String {
        model.resident(plan.residentIds.first ?? "")?.name ?? plan.names.first ?? "Resident"
    }

    private var hostHue: String {
        model.resident(plan.residentIds.first ?? "")?.hue ?? "#1e4a38"
    }

    private var isHost: Bool { plan.residentIds.first == model.viewer }

    private var inPlan: Bool { plan.residentIds.contains(model.viewer) }

    private var leaveTitle: String { isHost ? "Cancel event" : "Leave" }

    @ViewBuilder
    private var room: some View {
        if let url = model.imageURL(for: plan) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        .frame(maxWidth: .infinity)
                        .frame(height: 170)
                        .clipped()
                default:
                    placeFallback
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 170)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        } else {
            placeFallback
        }
    }

    private var placeFallback: some View {
        ZStack(alignment: .bottomLeading) {
            LinearGradient(
                colors: [Color(red: 0.97, green: 0.91, blue: 0.78), Color(red: 0.84, green: 0.89, blue: 0.83)],
                startPoint: .top,
                endPoint: .bottom
            )
            Text(plan.place)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(CourtyardTheme.ink)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(.white.opacity(0.9), in: Capsule())
                .padding(12)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 120)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    @ViewBuilder
    private var inviteList: some View {
        let going = Set(plan.residentIds)
        let invited = Set(plan.invited ?? [])
        let friends = (model.community?.friends ?? []).filter { !going.contains($0.id) && !invited.contains($0.id) }
        if let names = plan.invitedNames, !names.isEmpty {
            Text("Invited \(nameList(names))")
                .font(.subheadline)
                .foregroundStyle(CourtyardTheme.muted)
        }
        if !friends.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(friends) { friend in
                        Button("Invite \(friend.name)") {
                            Task { await model.invite(plan, friendId: friend.id) }
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
        }
    }

    private var actionRow: some View {
        HStack {
            if !model.isStaff && !inPlan {
                Button("Join") { Task { await model.join(plan) } }
                    .buttonStyle(.borderedProminent)
            }
            if plan.residentIds.count >= 2 || plan.line != nil {
                Button {
                    model.hear(plan)
                } label: {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(CourtyardTheme.green)
                        .frame(width: 36, height: 36)
                        .background(Color.white, in: Circle())
                        .overlay(Circle().stroke(CourtyardTheme.line))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Hear")
            }
            if showsMembershipActions && inPlan {
                Button(leaveTitle, role: .destructive) { confirmLeave = true }
                    .buttonStyle(.bordered)
            }
        }
        .padding(.top, 4)
    }

    private func nameList(_ names: [String]) -> String {
        if names.count <= 1 { return names.first ?? "someone" }
        if names.count == 2 { return "\(names[0]) and \(names[1])" }
        return "\(names.dropLast().joined(separator: ", ")), and \(names.last ?? "")"
    }
}

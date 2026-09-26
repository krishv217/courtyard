import SwiftUI

struct StaffView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Front desk")
                    .font(.largeTitle.weight(.semibold))
                HStack {
                    keyPill("Meta", on: model.community?.keys.meta ?? false)
                    keyPill("Grok", on: model.community?.keys.grok ?? false)
                }
                HStack {
                    Button("Run judging story") { Task { await model.runStory() } }
                    Button("Clear the board") { Task { await model.clearBoard() } }
                }
                Text("Check in person")
                    .font(.title2.weight(.semibold))
                Text("These notes asked for help. They are not turned into a neighbor visit, and they do not include a unit number.")
                    .foregroundStyle(CourtyardTheme.muted)
                let alerts = model.community?.alerts ?? []
                if alerts.isEmpty {
                    Text("No one has asked for an in-person check.")
                        .foregroundStyle(CourtyardTheme.muted)
                } else {
                    ForEach(alerts) { alert in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(alert.name).font(.headline)
                            Text(alert.summary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(Color(red: 0.973, green: 0.922, blue: 0.902), in: RoundedRectangle(cornerRadius: 16))
                    }
                }
                Text("Today's plans")
                    .font(.title2.weight(.semibold))
                ForEach(model.visiblePlans(filter: "all")) { plan in
                    PlanCard(plan: plan, showsMembershipActions: false)
                    Divider()
                }
                Text("What was withheld")
                    .font(.title2.weight(.semibold))
                Text("The front desk sees the category, not the address, the code, or the recording.")
                    .foregroundStyle(CourtyardTheme.muted)
                ForEach(model.community?.notes ?? []) { note in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(note.name ?? "Resident").font(.headline)
                        Text(note.card.map { "\($0.activity) in the \($0.place)" } ?? note.summary ?? "Not posted")
                        Text("Withheld: \((note.withheld?.isEmpty == false ? note.withheld!.joined(separator: ", ") : "nothing sensitive"))")
                            .font(.subheadline)
                            .foregroundStyle(CourtyardTheme.muted)
                    }
                    .padding(.vertical, 6)
                }
            }
            .padding(16)
        }
        .background(CourtyardTheme.paper)
        .modifier(CollapsesHeaderOnScroll(section: "staff"))
        .refreshable { await model.refresh() }
        .statusToast()
    }

    private func keyPill(_ name: String, on: Bool) -> some View {
        Text(on ? "\(name) connected" : "\(name) key missing")
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(on ? Color(red: 0.898, green: 0.941, blue: 0.910) : CourtyardTheme.line, in: Capsule())
            .foregroundStyle(on ? CourtyardTheme.green : CourtyardTheme.muted)
    }
}

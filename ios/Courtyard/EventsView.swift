import SwiftUI

struct EventsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Plans you are signed up for. Cancel takes the event down if you posted it. Leave drops you from someone else's plan.")
                    .foregroundStyle(CourtyardTheme.muted)
                let plans = model.myPlans()
                if plans.isEmpty {
                    Text("You haven't signed up for anything yet.")
                        .foregroundStyle(CourtyardTheme.muted)
                        .padding(.vertical, 12)
                } else {
                    ForEach(plans) { plan in
                        PlanCard(plan: plan, showsMembershipActions: true)
                        Divider()
                    }
                }
            }
            .padding(16)
        }
        .background(CourtyardTheme.paper)
        .modifier(CollapsesHeaderOnScroll(section: "events"))
        .refreshable { await model.refresh() }
        .statusToast()
    }
}

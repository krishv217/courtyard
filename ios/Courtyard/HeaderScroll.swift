import SwiftUI

struct CollapsesHeaderOnScroll: ViewModifier {
    @EnvironmentObject private var model: AppModel
    var section: String

    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content.onScrollGeometryChange(for: CGFloat.self, of: { geo in
                geo.contentOffset.y + geo.contentInsets.top
            }, action: { _, scrolled in
                model.noteScroll(scrolled, section: section)
            })
        } else {
            content
        }
    }
}

import SwiftUI

enum CourtyardTheme {
    static let paper = Color(red: 0.953, green: 0.925, blue: 0.875)
    static let ink = Color(red: 0.110, green: 0.157, blue: 0.133)
    static let green = Color(red: 0.118, green: 0.290, blue: 0.220)
    static let muted = Color(red: 0.369, green: 0.416, blue: 0.384)
    static let line = Color(red: 0.890, green: 0.835, blue: 0.761)
    static let card = Color(red: 1.0, green: 0.980, blue: 0.953)

    static let times = ["10:30", "11:30", "12:00", "1:00", "1:30", "2:00", "3:00", "4:00"]

    static let choices: [(String, String)] = [
        ("Walk to lunch", "I'd like company walking to lunch."),
        ("Lunch", "I'd like company at lunch."),
        ("Cards", "I'd like to play cards."),
        ("Library", "I'd like company in the library."),
        ("Cool room", "I'd like a seat in a cool common room."),
        ("Garden", "I'd like company in the garden."),
    ]

    static func color(hex: String) -> Color {
        var cleaned = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        if cleaned.count == 6 { cleaned = "FF" + cleaned }
        var value: UInt64 = 0
        Scanner(string: cleaned).scanHexInt64(&value)
        let red = Double((value >> 16) & 0xFF) / 255
        let green = Double((value >> 8) & 0xFF) / 255
        let blue = Double(value & 0xFF) / 255
        return Color(red: red, green: green, blue: blue)
    }
}

struct AvatarView: View {
    @EnvironmentObject private var model: AppModel
    var name: String
    var hue: String
    var residentId: String?
    var size: CGFloat = 48

    var body: some View {
        Group {
            if let residentId, let url = model.portraitURL(residentId) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    default:
                        initials
                    }
                }
            } else {
                initials
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }

    private var initials: some View {
        Text(String(name.prefix(1)))
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(CourtyardTheme.color(hex: hue))
    }
}

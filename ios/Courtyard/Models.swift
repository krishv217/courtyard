import Foundation

struct CommunityState: Codable {
    var community: String
    var residents: [Resident]
    var viewer: String
    var notes: [Note]
    var alerts: [DeskAlert]
    var friends: [PersonRef]
    var incoming: [PersonRef]
    var outgoing: [PersonRef]
    var suggestions: [Suggestion]
    var notifications: [Notice]
    var threads: [MessageThread]
    var plans: [Plan]
    var keys: APIKeys
}

struct Resident: Codable, Identifiable, Hashable {
    var id: String
    var firstName: String
    var name: String
    var role: String
    var hue: String
    var portrait: String?
    var tastes: [String]?
}

struct PersonRef: Codable, Identifiable, Hashable {
    var id: String
    var name: String
}

struct Suggestion: Codable, Identifiable, Hashable {
    var id: String
    var shared: Int
}

struct MessageThread: Codable, Identifiable, Hashable {
    var id: String
    var peerId: String
    var peerName: String
    var messages: [ChatMessage]
    var unread: Int
    var last: String?
}

struct ChatMessage: Codable, Identifiable, Hashable {
    var id: String
    var senderId: String
    var text: String
    var kind: String
    var createdAt: String?
}

struct Notice: Codable, Identifiable, Hashable {
    var id: String
    var kind: String
    var text: String
    var planId: String?
    var read: Bool
    var createdAt: String?
}

struct Plan: Codable, Identifiable, Hashable {
    var id: String
    var residentIds: [String]
    var activity: String
    var place: String
    var time: String
    var audience: String
    var status: String?
    var names: [String]
    var line: String?
    var image: String?
    var audio: String?
    var invited: [String]?
    var invitedNames: [String]?
}

struct ActivityCard: Codable, Hashable {
    var activity: String
    var place: String
    var time: String
}

struct Note: Codable, Identifiable, Hashable {
    var id: String
    var name: String?
    var kind: String?
    var withheld: [String]?
    var summary: String?
    var card: ActivityCard?
    var text: String?
}

struct DeskAlert: Codable, Identifiable, Hashable {
    var id: String
    var name: String
    var summary: String
}

struct APIKeys: Codable, Hashable {
    var meta: Bool
    var grok: Bool
}

struct PreviewDecision: Codable {
    var kind: String?
    var summary: String?
    var withheld: [String]?
    var card: ActivityCard?
    var cards: [ActivityCard]?
}

struct StateEnvelope: Codable {
    var state: CommunityState
}

struct SuggestionBody: Codable {
    var suggestion: String
}

import AVFoundation
import Foundation

@MainActor
final class AppModel: ObservableObject {
    @Published var baseURL: String {
        didSet { UserDefaults.standard.set(baseURL, forKey: "courtyard-server") }
    }
    @Published var viewer: String {
        didSet { UserDefaults.standard.set(viewer, forKey: "courtyard-resident") }
    }
    @Published var community: CommunityState?
    @Published var status = ""
    @Published var loading = false
    @Published var section = "feed"
    @Published var headerHidden = false
    @Published var chatWith: String?
    private var headerLockUntil = Date.distantPast

    private let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
    private let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 8
        config.timeoutIntervalForResource = 12
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()
    private var clip: AVAudioPlayer?
    private let speech = AVSpeechSynthesizer()
    private var statusToken = 0
    private var generation = 0

    init() {
        baseURL = UserDefaults.standard.string(forKey: "courtyard-server") ?? "http://127.0.0.1:8787"
        let saved = UserDefaults.standard.string(forKey: "courtyard-resident") ?? "helen"
        viewer = saved
    }

    var trimmedBase: String {
        baseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    var isStaff: Bool { viewer == "staff" }

    func noteScroll(_ scrolled: CGFloat, section: String) {
        let active = isStaff ? section == "staff" : self.section == section
        guard active, Date() >= headerLockUntil else { return }
        let hidden = headerHidden ? scrolled > 8 : scrolled > 28
        guard hidden != headerHidden else { return }
        headerHidden = hidden
        headerLockUntil = Date().addingTimeInterval(0.35)
    }

    var messageUnread: Int {
        community?.threads.reduce(0) { $0 + $1.unread } ?? 0
    }

    var unreadCount: Int {
        community?.notifications.filter { !$0.read }.count ?? 0
    }

    func resident(_ id: String) -> Resident? {
        community?.residents.first { $0.id == id }
    }

    func refresh() async {
        let token = generation
        let first = community == nil
        if first { loading = true }
        defer { if first { loading = false } }
        do {
            let next = try await get("/api/state?as=\(viewer.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? viewer)")
            guard token == generation else { return }
            community = try decoder.decode(CommunityState.self, from: next)
            if status == connectionHint { status = "" }
        } catch {
            guard token == generation else { return }
            if community == nil {
                status = connectionHint
            }
        }
    }

    func switchAccount(_ id: String) async {
        generation += 1
        viewer = id
        community = nil
        await refresh()
    }

    func openChat(_ otherId: String) async {
        guard otherId != viewer else { return }
        section = "messages"
        chatWith = otherId
        if let data = try? await post("/api/messages/open", ["resident_id": viewer, "other_id": otherId]),
           let next = try? decoder.decode(CommunityState.self, from: data) {
            community = next
        }
    }

    func sendMessage(to otherId: String, text: String, suggested: Bool = false) async throws {
        var body: [String: Any] = [
            "resident_id": viewer,
            "other_id": otherId,
            "text": text,
        ]
        if suggested { body["kind"] = "suggestion" }
        let data = try await post("/api/messages", body)
        community = try decoder.decode(CommunityState.self, from: data)
    }

    func suggestPlan(otherId: String, text: String) async throws -> String {
        let data = try await postSlow("/api/messages/agent", [
            "resident_id": viewer,
            "other_id": otherId,
            "text": text,
        ])
        return try decoder.decode(SuggestionBody.self, from: data).suggestion
    }

    func markThreadRead(_ otherId: String) async {
        guard (community?.threads.first { $0.peerId == otherId }?.unread ?? 0) > 0 else { return }
        await openChat(otherId)
    }

    func postNote(text: String, time: String, friendsOnly: Bool) async throws {
        let data = try await post("/api/notes", [
            "resident_id": viewer,
            "text": text,
            "time": time,
            "audience": friendsOnly ? "friends" : "everyone",
        ])
        community = try decoder.decode(StateEnvelope.self, from: data).state
        showStatus("Posted. Private details stayed off the feed.")
    }

    func preview(text: String, time: String) async throws -> PreviewDecision {
        let data = try await post("/api/preview", [
            "resident_id": viewer,
            "text": text,
            "time": time,
        ])
        return try decoder.decode(PreviewDecision.self, from: data)
    }

    func join(_ plan: Plan) async {
        await perform {
            let data = try await self.post("/api/plans/\(plan.id)/join", ["resident_id": self.viewer])
            self.community = try self.decoder.decode(StateEnvelope.self, from: data).state
            self.showStatus("You're on the plan.")
        }
    }

    func leave(_ plan: Plan) async {
        await perform {
            let data = try await self.post("/api/plans/\(plan.id)/leave", ["resident_id": self.viewer])
            self.community = try self.decoder.decode(CommunityState.self, from: data)
            let hosted = plan.residentIds.first == self.viewer
            self.showStatus(hosted ? "Canceled. The others were notified." : "You left. The others were notified.")
        }
    }

    func invite(_ plan: Plan, friendId: String) async {
        await perform {
            let data = try await self.post("/api/plans/\(plan.id)/invite", [
                "resident_id": self.viewer,
                "friend_id": friendId,
            ])
            self.community = try self.decoder.decode(CommunityState.self, from: data)
            self.showStatus("Invited. They'll see it in Notices.")
        }
    }

    func changeFriend(_ otherId: String, action: String) async {
        await perform {
            let data = try await self.post("/api/friends", [
                "resident_id": self.viewer,
                "other_id": otherId,
                "action": action,
            ])
            self.community = try self.decoder.decode(CommunityState.self, from: data)
        }
    }

    func markRead(_ id: String?) async {
        await perform {
            var body: [String: Any] = ["resident_id": self.viewer]
            if let id { body["id"] = id }
            let data = try await self.post("/api/notifications/read", body)
            self.community = try self.decoder.decode(CommunityState.self, from: data)
        }
    }

    func runStory() async {
        await perform {
            _ = try await self.post("/api/demo/story", [:])
            await self.refresh()
            self.showStatus("Loaded the judging story.")
        }
    }

    func clearBoard() async {
        await perform {
            _ = try await self.post("/api/demo/reset", [:])
            await self.refresh()
            self.showStatus("The board is clear. Restart the server to load the sample community again.")
        }
    }

    func hear(_ plan: Plan) {
        Task { await play(plan) }
    }

    private func play(_ plan: Plan) async {
        let audio = AVAudioSession.sharedInstance()
        try? audio.setCategory(.playback, mode: .spokenAudio)
        try? audio.setActive(true)
        speech.stopSpeaking(at: .immediate)
        clip?.stop()
        if plan.residentIds.count >= 2 || plan.audio != nil,
           let url = URL(string: "\(trimmedBase)/api/plans/\(plan.id)/audio") {
            var request = URLRequest(url: url)
            request.timeoutInterval = 40
            if let (data, response) = try? await URLSession.shared.data(for: request),
               let http = response as? HTTPURLResponse,
               (200..<300).contains(http.statusCode),
               let recording = try? AVAudioPlayer(data: data) {
                recording.prepareToPlay()
                clip = recording
                if recording.play() { return }
            }
        }
        let spoken = plan.line ?? "\(plan.names.joined(separator: " and ")) will meet in the \(plan.place) at \(plan.time)."
        let utterance = AVSpeechUtterance(string: spoken)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        speech.speak(utterance)
    }

    private func showStatus(_ message: String) {
        statusToken += 1
        let token = statusToken
        status = message
        Task {
            try? await Task.sleep(for: .seconds(3.5))
            guard token == statusToken else { return }
            status = ""
        }
    }

    func portraitURL(_ residentId: String) -> URL? {
        guard resident(residentId)?.portrait != nil else { return nil }
        return URL(string: "\(trimmedBase)/api/residents/\(residentId)/portrait")
    }

    func imageURL(for plan: Plan) -> URL? {
        guard plan.image != nil else { return nil }
        return URL(string: "\(trimmedBase)/api/plans/\(plan.id)/image")
    }

    func visiblePlans(filter: String) -> [Plan] {
        let plans = Array((community?.plans ?? []).reversed())
        if isStaff || filter == "all" { return plans }
        return plans.filter { bucket($0) == filter }
    }

    func myPlans() -> [Plan] {
        (community?.plans ?? []).reversed().filter { $0.residentIds.contains(viewer) }
    }

    func bucket(_ plan: Plan) -> String {
        let friendIds = Set(community?.friends.map(\.id) ?? [])
        if plan.audience == "friends" || plan.residentIds.contains(where: { friendIds.contains($0) }) {
            return "friends"
        }
        return "community"
    }

    private var connectionHint: String {
        "Can't reach the Courtyard server. Open Account, choose Server address, and paste the https link from this Mac."
    }

    private func perform(_ work: () async throws -> Void) async {
        do {
            try await work()
        } catch {
            showStatus(error.localizedDescription)
        }
    }

    private func get(_ path: String) async throws -> Data {
        guard let url = URL(string: trimmedBase + path) else {
            throw CourtyardError("The server address is not a valid URL.")
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 8
        let (data, response) = try await session.data(for: request)
        try check(response, data)
        return data
    }

    private func post(_ path: String, _ body: [String: Any]) async throws -> Data {
        guard let url = URL(string: trimmedBase + path) else {
            throw CourtyardError("The server address is not a valid URL.")
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 8
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try check(response, data)
        return data
    }

    private func postSlow(_ path: String, _ body: [String: Any]) async throws -> Data {
        guard let url = URL(string: trimmedBase + path) else {
            throw CourtyardError("The server address is not a valid URL.")
        }
        var request = URLRequest(url: url)
        request.timeoutInterval = 45
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await URLSession.shared.data(for: request)
        try check(response, data)
        return data
    }

    private func check(_ response: URLResponse, _ data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            if let payload = try? decoder.decode(ErrorBody.self, from: data) {
                throw CourtyardError(payload.error)
            }
            throw CourtyardError("The server returned \(http.statusCode).")
        }
    }
}

private struct ErrorBody: Codable {
    var error: String
}

struct CourtyardError: LocalizedError {
    var message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

import Foundation

struct RefreshRequest: Encodable {
    let refreshToken: String
}

private struct APIErrorEnvelope: Decodable {
    let error: APIErrorBody
}

private struct APIErrorBody: Decodable {
    let message: String
}

struct SessionRequestContext: Equatable {
    let session: ApiSession
    let generation: UUID
}

/// Owned by the API actor. Only its own rotations keep a request's identity.
struct SessionRenewalState {
    private var known: ApiSession?
    private var generation = UUID()

    mutating func capture(_ stored: ApiSession?) -> SessionRequestContext? {
        if stored != known {
            known = stored
            generation = UUID()
        }
        return stored.map { SessionRequestContext(session: $0, generation: generation) }
    }

    mutating func current(for original: SessionRequestContext, stored: ApiSession?) -> SessionRequestContext? {
        guard let current = capture(stored), current.generation == original.generation else { return nil }
        return current
    }

    mutating func didRenew(_ session: ApiSession) {
        known = session
    }
}

func requestSessionRenewal(baseURL: URL, urlSession: URLSession, session: ApiSession) async throws -> ApiSession {
    let path = "/v1/auth/refresh"
    let resource = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    var request = URLRequest(url: baseURL.appendingPathComponent(resource))
    request.httpMethod = "POST"
    request.cachePolicy = .reloadIgnoringLocalCacheData
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
    request.setValue(UUID().uuidString, forHTTPHeaderField: "X-Request-ID")
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    request.httpBody = try encoder.encode(RefreshRequest(refreshToken: session.refreshToken))
    let (data, response) = try await urlSession.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw APIClientError.invalidResponse }
    guard (200..<300).contains(http.statusCode) else {
        throw APIClientError.httpStatus(http.statusCode, sanitizedAPIErrorMessage(from: data))
    }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let tokens = try decoder.decode(TokenResponse.self, from: data)
    return ApiSession(accessToken: tokens.accessToken, refreshToken: tokens.refreshToken)
}

func sanitizedAPIErrorMessage(from data: Data) -> String? {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    guard data.count <= 64 * 1024, let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data) else { return nil }
    let message = envelope.error.message.trimmingCharacters(in: .whitespacesAndNewlines)
    return message.isEmpty ? nil : String(message.prefix(512))
}

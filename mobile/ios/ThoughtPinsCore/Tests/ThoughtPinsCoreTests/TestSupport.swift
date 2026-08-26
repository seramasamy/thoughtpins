import Foundation
import XCTest
@testable import ThoughtPinsCore

/// Shared across the test files: a session store that lives in memory, a
/// URLProtocol that answers from a closure, and a response builder.
enum StubResponse {
    static func make(
        for request: URLRequest,
        status: Int,
        body: [String: Any]
    ) throws -> (HTTPURLResponse, Data) {
        let response = try XCTUnwrap(
            HTTPURLResponse(
                url: try XCTUnwrap(request.url),
                statusCode: status,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )
        )
        return (response, try JSONSerialization.data(withJSONObject: body))
    }
}

final class TestSessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: ApiSession?

    init(_ value: ApiSession? = nil) {
        self.value = value
    }

    func load() throws -> ApiSession? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    func save(_ session: ApiSession?) throws {
        lock.lock()
        defer { lock.unlock() }
        value = session
    }
}

final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

extension URLRequest {
    /// The request body as URLProtocol actually receives it.
    ///
    /// URLSession converts httpBody into httpBodyStream before handing the
    /// request to a protocol, so reading httpBody here always returns nil and
    /// the assertion about the posted payload could never have passed.
    var bodyData: Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let capacity = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: capacity)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: capacity)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}

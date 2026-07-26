import Foundation

public enum ClientVersionStatus: Equatable {
    case supported
    case updateRecommended
    case blocked
}

public struct ClientVersionDecision: Equatable {
    public let status: ClientVersionStatus
    public let minimum: String
    public let recommended: String
    public let storeURL: String?
}

public func evaluateClientVersion(config: ClientConfig, platform: String = "ios", currentVersion: String) -> ClientVersionDecision {
    let minimum = config.minimumSupportedClients[platform] ?? "0.0.0"
    let recommended = config.recommendedClients[platform] ?? minimum
    let storeURL = config.storeUrls[platform] ?? nil
    if compareVersions(currentVersion, minimum) < 0 {
        return ClientVersionDecision(status: .blocked, minimum: minimum, recommended: recommended, storeURL: storeURL)
    }
    if compareVersions(currentVersion, recommended) < 0 {
        return ClientVersionDecision(status: .updateRecommended, minimum: minimum, recommended: recommended, storeURL: storeURL)
    }
    return ClientVersionDecision(status: .supported, minimum: minimum, recommended: recommended, storeURL: storeURL)
}

public func compareVersions(_ left: String, _ right: String) -> Int {
    let lhs = parseVersion(left)
    let rhs = parseVersion(right)
    for index in 0..<max(lhs.count, rhs.count) {
        let diff = (index < lhs.count ? lhs[index] : 0) - (index < rhs.count ? rhs[index] : 0)
        if diff != 0 {
            return diff > 0 ? 1 : -1
        }
    }
    return 0
}

private func parseVersion(_ value: String) -> [Int] {
    value
        .split { ".+-".contains($0) }
        .compactMap { Int($0.filter(\.isNumber)) }
}

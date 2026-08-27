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
    for index in 0..<max(lhs.release.count, rhs.release.count) {
        let leftPart = index < lhs.release.count ? lhs.release[index] : 0
        let rightPart = index < rhs.release.count ? rhs.release[index] : 0
        if leftPart != rightPart {
            return leftPart > rightPart ? 1 : -1
        }
    }
    // Same release numbers: a pre-release is lower than the release itself.
    if lhs.isPreRelease != rhs.isPreRelease {
        return lhs.isPreRelease ? -1 : 1
    }
    return 0
}

/// The numeric release part of a version, and whether it carried a pre-release.
///
/// This used to split on ".", "+" and "-" all at once and keep every number it
/// found, so "1.0.0-rc.1" parsed as [1, 0, 0, 1] -- one component *longer* than
/// "1.0.0", and therefore greater. Production advertises
/// `recommended_clients.ios = "1.0.0-rc.1"` (RECOMMENDED_IOS_VERSION falls back
/// to API_VERSION), so the shipping 1.0.0 build compared as older than the
/// recommendation and every day-one user would have been shown an update nag
/// for a version that does not exist.
///
/// Semver is the other way round: a pre-release sorts *below* its release.
private func parseVersion(_ value: String) -> (release: [Int], isPreRelease: Bool) {
    // Build metadata after "+" is not part of precedence at all.
    let withoutBuild = value.split(separator: "+", maxSplits: 1).first.map(String.init) ?? value
    // Everything from the first "-" is the pre-release identifier.
    let parts = withoutBuild.split(separator: "-", maxSplits: 1)
    let release = (parts.first.map(String.init) ?? withoutBuild)
        .split(separator: ".")
        .compactMap { Int($0.filter(\.isNumber)) }
    return (release, parts.count > 1)
}

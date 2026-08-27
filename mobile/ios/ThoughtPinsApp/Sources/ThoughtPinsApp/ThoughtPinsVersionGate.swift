import Foundation

/// The shipping build's marketing version, read from its own bundle.
///
/// Separated from `ThoughtPinsAppModel` because that file is at its size
/// budget, and because this is one self-contained question: what version does
/// this binary claim to be?
///
/// Falls back to "0.0.0" if `CFBundleShortVersionString` is missing or empty.
/// That compares below every real minimum, which is the safe direction: a build
/// that cannot say what it is should be treated as too old, not as current.
let thoughtPinsRunningVersion: String = {
    let raw = (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? ""
    let trimmed = raw.trimmingCharacters(in: .whitespaces)
    return trimmed.isEmpty ? "0.0.0" : trimmed
}()

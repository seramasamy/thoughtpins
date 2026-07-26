package com.thoughtpins.core

enum class ClientVersionStatus {
    SUPPORTED,
    UPDATE_RECOMMENDED,
    BLOCKED,
}

data class ClientVersionDecision(
    val status: ClientVersionStatus,
    val minimum: String,
    val recommended: String,
    val storeUrl: String?,
)

fun evaluateClientVersion(
    config: ClientConfig,
    platform: String = "android",
    currentVersion: String,
): ClientVersionDecision {
    val minimum = config.minimumSupportedClients[platform] ?: "0.0.0"
    val recommended = config.recommendedClients[platform] ?: minimum
    val storeUrl = config.storeUrls[platform]
    return when {
        compareVersions(currentVersion, minimum) < 0 ->
            ClientVersionDecision(ClientVersionStatus.BLOCKED, minimum, recommended, storeUrl)
        compareVersions(currentVersion, recommended) < 0 ->
            ClientVersionDecision(ClientVersionStatus.UPDATE_RECOMMENDED, minimum, recommended, storeUrl)
        else ->
            ClientVersionDecision(ClientVersionStatus.SUPPORTED, minimum, recommended, storeUrl)
    }
}

fun compareVersions(left: String, right: String): Int {
    val lhs = parseVersion(left)
    val rhs = parseVersion(right)
    repeat(maxOf(lhs.size, rhs.size)) { index ->
        val diff = (lhs.getOrElse(index) { 0 }) - (rhs.getOrElse(index) { 0 })
        if (diff != 0) return if (diff > 0) 1 else -1
    }
    return 0
}

private fun parseVersion(value: String): List<Int> =
    value.split('.', '+', '-').mapNotNull { part ->
        part.filter { it.isDigit() }.toIntOrNull()
    }

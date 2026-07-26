package com.thoughtpins.core

interface SessionStore {
    suspend fun load(): ApiSession?
    suspend fun save(session: ApiSession?)
}

class MemorySessionStore : SessionStore {
    private var session: ApiSession? = null

    override suspend fun load(): ApiSession? = session

    override suspend fun save(session: ApiSession?) {
        this.session = session
    }
}

package com.fitron.sellagent.companion

import android.app.Application
import com.fitron.sellagent.core.CoreContainer
import com.fitron.sellagent.core.CoreHost

/** Companion app: human-assisted dialing of campaign calls requested by the Windows backend. */
class CompanionApp : Application(), CoreHost {
    override lateinit var core: CoreContainer
        private set
    lateinit var calls: CallController
        private set

    override fun onCreate() {
        super.onCreate()
        core = CoreContainer(this)
        calls = CallController(this, core)
        core.startAll()
    }
}

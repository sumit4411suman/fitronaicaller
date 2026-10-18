package com.fitron.sellagent.core.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.brand.SellAgentTheme
import kotlinx.coroutines.delay

/** Dark splash: gold mark, two-tone word mark, subtitle, footer chips. Calls [onDone] after ~1.4 s. */
@Composable
fun SplashScreen(onDone: () -> Unit) {
    LaunchedEffect(Unit) {
        delay(1400)
        onDone()
    }
    SellAgentTheme(dark = true) {
        Box(modifier = Modifier.fillMaxSize().background(BrandColors.Background), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(24.dp)) {
                LogoMark(size = 132.dp)
                Spacer(Modifier.height(24.dp))
                WordMark(style = MaterialTheme.typography.displaySmall)
                Spacer(Modifier.height(8.dp))
                Text(stringResource(R.string.splash_subtitle), style = MaterialTheme.typography.bodyMedium, color = BrandColors.TextSecondary, textAlign = TextAlign.Center)
            }
            Row(
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 48.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                StatusChip(stringResource(R.string.splash_chip_smart), Tone.Info)
                StatusChip(stringResource(R.string.splash_chip_secure), Tone.Good)
                StatusChip(stringResource(R.string.splash_chip_local), Tone.Warn)
            }
        }
    }
}

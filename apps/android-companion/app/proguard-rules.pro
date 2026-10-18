# Keep kotlinx.serialization generated serializers for the protocol package.
-keepclassmembers class com.fitron.sellagent.protocol.** { *** Companion; }
-keepclasseswithmembers class com.fitron.sellagent.protocol.** { kotlinx.serialization.KSerializer serializer(...); }
-dontwarn okhttp3.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
